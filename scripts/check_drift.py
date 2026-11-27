#!/usr/bin/env python3
"""Drift detection for pinned community plugins.

Compares each github/git-subdir registry entry's pinned sha against the
upstream repo's latest release tag (via `gh api`). With --update, bumps
ref+sha in registry.yaml to the latest tag; the workflow then opens a
review PR (never auto-merged — docs/REVIEW_POLICY.md).

Requires: gh authenticated (CI provides GH_TOKEN). Stdlib only.
Exit 0 = no drift (or updated), 1 = upstream resolution failed closed,
2 = drift found without --update.
"""
import base64
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate_registry import parse_registry, ROOT  # noqa: E402

SEMVER_RE = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class UpstreamResolutionError(ValueError):
    """An upstream could not be checked completely; drift must fail closed."""


class MissingUpstreamManifest(UpstreamResolutionError):
    """A semver tag does not contain a supported plugin manifest."""


class InvalidUpstreamManifest(UpstreamResolutionError):
    """A plugin manifest is present but malformed or has no valid version."""


def tag_version(tag):
    """Return the normalized SemVer version represented by an upstream tag."""
    if not isinstance(tag, str):
        return None
    match = SEMVER_RE.fullmatch(tag)
    if match is None:
        return None
    version = tag[1:] if tag.startswith("v") else tag
    if not valid_semver(version):
        return None
    return version


def valid_semver(version):
    if not isinstance(version, str):
        return False
    match = SEMVER_RE.fullmatch(version)
    if match is None:
        return False
    prerelease = match["prerelease"]
    if prerelease:
        for identifier in prerelease.split("."):
            if (
                identifier.isdigit()
                and len(identifier) > 1
                and identifier.startswith("0")
            ):
                return False
    return True


def tag_version_key(tag):
    version = tag_version(tag)
    if version is None:
        return None
    match = SEMVER_RE.fullmatch(version)
    prerelease = match["prerelease"]
    prerelease_key = ()
    if prerelease:
        prerelease_key = tuple(
            (0, int(identifier)) if identifier.isdigit() else (1, identifier)
            for identifier in prerelease.split(".")
        )
    return (
        int(match["major"]),
        int(match["minor"]),
        int(match["patch"]),
        1 if prerelease is None else 0,
        prerelease_key,
    )


def run_gh(args):
    return subprocess.run(
        ["gh", "api", *args], capture_output=True, text=True, check=False
    )


def _manifest_at(repo, manifest_path, commit):
    out = run_gh([f"repos/{repo}/contents/{manifest_path}?ref={commit}"])
    if out.returncode != 0:
        if "HTTP 404" in out.stderr:
            return None
        raise UpstreamResolutionError(
            f"GitHub API failed reading {repo}/{manifest_path} at {commit}: "
            f"{out.stderr.strip() or 'unknown error'}"
        )
    try:
        response = json.loads(out.stdout)
        encoded = response["content"]
        if not isinstance(encoded, str) or len(encoded) > 1_400_000:
            raise ValueError("manifest content is missing or exceeds the size limit")
        manifest = json.loads(base64.b64decode(encoded, validate=False))
    except (KeyError, ValueError, json.JSONDecodeError) as error:
        raise InvalidUpstreamManifest(
            f"{repo}/{manifest_path} at {commit} is not a valid plugin manifest: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise InvalidUpstreamManifest(
            f"{repo}/{manifest_path} at {commit} must be a JSON object"
        )
    return manifest


def plugin_version(repo, path, commit):
    base = f"{path}/" if path else ""
    manifests = []
    for client in (".claude-plugin", ".cursor-plugin"):
        manifest_path = f"{base}{client}/plugin.json"
        manifest = _manifest_at(repo, manifest_path, commit)
        if manifest is not None:
            manifests.append((manifest_path, manifest))
    if not manifests:
        raise MissingUpstreamManifest(
            f"{repo} at {commit} has no supported plugin.json under {base or './'}"
        )
    versions = []
    for manifest_path, manifest in manifests:
        version = manifest.get("version")
        normalized = tag_version(version) if isinstance(version, str) else None
        if normalized is None:
            raise InvalidUpstreamManifest(
                f"{repo}/{manifest_path} at {commit} has an invalid SemVer version"
            )
        versions.append((manifest_path, normalized))
    unique_versions = {version for _, version in versions}
    if len(unique_versions) != 1:
        paths = ", ".join(f"{path}={version}" for path, version in versions)
        raise InvalidUpstreamManifest(
            f"{repo} at {commit} has conflicting client plugin versions: {paths}"
        )
    return versions[0][1]


def latest_tag(repo, path=""):
    """Resolve the highest SemVer tag whose pinned plugin manifest is valid."""
    out = run_gh([
        "--paginate", f"repos/{repo}/tags?per_page=100", "--jq", ".[].name"
    ])
    if out.returncode != 0:
        raise UpstreamResolutionError(
            f"GitHub API failed listing tags for {repo}: "
            f"{out.stderr.strip() or 'unknown error'}"
        )
    tags = [
        line.strip()
        for line in out.stdout.splitlines()
        if tag_version_key(line.strip())
    ]
    if not tags:
        raise UpstreamResolutionError(f"{repo} has no supported SemVer tags")
    tags = list(dict.fromkeys(tags))
    tags.sort(
        key=lambda candidate: (tag_version_key(candidate), candidate), reverse=True
    )
    failures = []
    for tag in tags:
        out = run_gh([f"repos/{repo}/commits/{tag}"])
        if out.returncode != 0:
            if "HTTP 404" in out.stderr:
                failures.append(f"{tag}: tag does not resolve to a commit")
                continue
            raise UpstreamResolutionError(
                f"GitHub API failed resolving {repo}@{tag}: "
                f"{out.stderr.strip() or 'unknown error'}"
            )
        try:
            commit = json.loads(out.stdout).get("sha", "")
        except json.JSONDecodeError as error:
            failures.append(f"{tag}: invalid commit response ({error})")
            continue
        if not SHA_RE.fullmatch(commit):
            failures.append(f"{tag}: invalid commit SHA")
            continue
        try:
            version = plugin_version(repo, path, commit)
        except (MissingUpstreamManifest, InvalidUpstreamManifest) as error:
            failures.append(f"{tag}: {error}")
            continue
        return tag, commit, version
    raise UpstreamResolutionError(
        f"{repo} has no valid plugin manifest at any SemVer tag: "
        + "; ".join(failures)
    )


def replace_entry_pin(text, plugin_id, tag, sha, version):
    """Update ref, resolved SHA, and plugin version in only one registry entry."""
    entry = re.search(rf"(?m)^  - id: {re.escape(plugin_id)}\s*$", text)
    if entry is None:
        raise ValueError(f"registry entry not found: {plugin_id}")
    next_entry = re.search(r"(?m)^  - id: ", text[entry.end():])
    end = entry.end() + next_entry.start() if next_entry else len(text)
    block = text[entry.start():end]
    replacements = (
        (r"(?m)^(      ref: ).*$", rf"\g<1>{tag}"),
        (r"(?m)^(      sha: ).*$", rf"\g<1>{sha}"),
        (r"(?m)^(    version: ).*$", rf"\g<1>{version}"),
    )
    for pattern, replacement in replacements:
        block, count = re.subn(pattern, replacement, block, count=1)
        if count != 1:
            raise ValueError(f"registry entry {plugin_id} has incomplete pin metadata")
    return text[:entry.start()] + block + text[end:]


def pin_needs_update(entry, tag, sha, version):
    plugin_id = entry["id"]
    source = entry.get("source", {})
    current_sha = source.get("sha")
    current_ref = source.get("ref")
    if current_ref == tag and current_sha != sha:
        raise UpstreamResolutionError(
            f"{plugin_id}: immutable tag {tag} moved from {current_sha} to {sha}"
        )
    current_version = tag_version_key(entry.get("version", ""))
    candidate_version = tag_version_key(version)
    if current_version is None or candidate_version is None:
        raise UpstreamResolutionError(
            f"{plugin_id}: current or upstream plugin version is not SemVer"
        )
    if candidate_version < current_version:
        raise UpstreamResolutionError(
            f"{plugin_id}: refusing version downgrade from {entry['version']} to {version}"
        )
    return (
        sha != current_sha
        or tag != current_ref
        or version != entry.get("version")
    )


def main():
    update = "--update" in sys.argv
    text = (ROOT / "registry" / "registry.yaml").read_text()
    entries = parse_registry(text)
    drift = []
    errors = []
    for e in entries:
        src = e.get("source", {})
        if src.get("type") not in ("github", "git-subdir") or not src.get("repo"):
            continue
        try:
            tag, sha, version = latest_tag(src["repo"], src.get("path", ""))
        except UpstreamResolutionError as error:
            errors.append(f"{e['id']}: {error}")
            continue
        try:
            needs_update = pin_needs_update(e, tag, sha, version)
        except UpstreamResolutionError as error:
            errors.append(str(error))
            continue
        if needs_update:
            drift.append(
                (e["id"], src.get("ref"), src.get("sha"), tag, sha, version)
            )
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    for eid, old_ref, old_sha, tag, sha, version in drift:
        print(
            f"drift: {eid}: {old_ref}@{old_sha[:12]} -> {tag}@{sha[:12]} "
            f"(version {version})"
        )
    if drift and update:
        for eid, old_ref, old_sha, tag, sha, version in drift:
            text = replace_entry_pin(text, eid, tag, sha, version)
        (ROOT / "registry" / "registry.yaml").write_text(text)
        print("registry updated; regenerate manifests before opening the PR")
        return 0
    return 2 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
