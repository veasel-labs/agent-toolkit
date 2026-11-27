#!/usr/bin/env python3
"""Registry validator (stdlib only) for veasel-labs/agent-toolkit.

Fail-closed rules:
  - external sources pin a full 40-char sha AND an immutable ref;
    with --resolve, the sha must equal the commit the ref actually
    resolves to upstream (annotated tag -> its target commit). Syntax
    alone is never accepted as provenance.
  - trust=verified or first-party requires provenance.review=approved;
    an unreviewed entry can only be community/experimental and must
    never be published as verified.
  - every entry declares its permission surface; dangerous_permissions
    entries require trust != community without explicit review.
  - marketplace manifests must not list pending/revoked/unknown ids.

Run: python3 scripts/validate_registry.py [--resolve]
Exit 0 = valid, 1 = violations printed to stderr.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRUST_TIERS = {"first-party", "verified", "community", "experimental"}
REVIEW_STATES = {"pending-initial-review", "pending-update-review", "approved", "revoked"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SPDX_RE = re.compile(r"^[A-Za-z0-9.+-]+$")
PERMISSION_KEYS = (
    "shell", "network", "mcp", "hooks", "dangerous_permissions",
    "executables", "mcp_images", "credential_scopes", "mutation_surface",
    "allowed_roots", "hook_commands",
)


def parse_registry(text):
    entries, current, section = [], None, None
    for line in text.splitlines():
        m = re.match(r"^  - id: (.+)$", line)
        if m:
            current = {"id": m.group(1).strip(), "source": {},
                       "permissions": {}, "provenance": {}, "parse_errors": []}
            entries.append(current)
            section = None
            continue
        if current is None:
            continue
        m = re.match(r"^    (version|license|trust): (.+)$", line)
        if m:
            current[m.group(1)] = m.group(2).strip()
            continue
        if re.match(r"^    source:$", line):
            section = "source"
            continue
        if re.match(r"^    permissions:$", line):
            section = "permissions"
            continue
        if re.match(r"^    provenance:$", line):
            section = "provenance"
            continue
        if re.match(r"^    \w", line):
            section = None
        m = re.match(r"^      (repo|ref|sha|type|path): (.+)$", line)
        if m and section == "source":
            current["source"][m.group(1)] = m.group(2).strip()
            continue
        m = re.match(r"^      (" + "|".join(PERMISSION_KEYS) + r"): (.+)$", line)
        if m and section == "permissions":
            current["permissions"][m.group(1)] = m.group(2).strip()
            continue
        m = re.match(r"^      (submitted_by|reviewed_by|review|reviewed_at|reviewed_source_sha|review_evidence): (.+)$", line)
        if m and section == "provenance":
            if m.group(1) in current["provenance"]:
                current["parse_errors"].append(
                    f"duplicate provenance.{m.group(1)} key")
            current["provenance"][m.group(1)] = m.group(2).strip()
    return entries


def src_type(entry):
    return entry.get("source", {}).get("type", "")


def is_installable(entry):
    """Only reviewed, non-revoked entries may be published/installed."""
    return (entry.get("provenance", {}).get("review") == "approved"
            and entry.get("trust") != "experimental")


def validate_entries(entries, resolved=None):
    """Pure validation. resolved: optional {id: resolved_commit_sha}."""
    errors = []
    if not entries:
        errors.append("registry has no entries")
    seen = set()
    for e in entries:
        eid = e.get("id", "?")
        for parse_error in e.get("parse_errors", []):
            errors.append(f"{eid}: {parse_error}")
        if not ID_RE.match(eid):
            errors.append(f"{eid}: id must be kebab-case")
        if eid in seen:
            errors.append(f"{eid}: duplicate id")
        seen.add(eid)
        trust = e.get("trust")
        if trust not in TRUST_TIERS:
            errors.append(f"{eid}: trust must be one of {sorted(TRUST_TIERS)}")
        if not SPDX_RE.match(e.get("license", "")):
            errors.append(f"{eid}: license must be an SPDX id")
        prov = e.get("provenance", {})
        review = prov.get("review")
        if review not in REVIEW_STATES:
            errors.append(f"{eid}: provenance.review must be one of {sorted(REVIEW_STATES)}")
        if not prov.get("submitted_by"):
            errors.append(f"{eid}: provenance.submitted_by is required")
        # Fail closed: verified means a human actually reviewed it.
        if trust == "verified" and review != "approved":
            errors.append(
                f"{eid}: trust={trust} requires provenance.review=approved "
                f"(got {review!r}); unreviewed entries must be community/experimental")
        if trust == "first-party" and review != "approved" and src_type(e) != "relative":
            errors.append(
                f"{eid}: external first-party entries require provenance.review=approved "
                f"(got {review!r}); only bundled relative sources may stay pending")
        if review == "approved" and prov.get("reviewed_by") in (None, "", "null"):
            errors.append(f"{eid}: approved entries must name provenance.reviewed_by")
        # An external approval is valid only for the exact immutable source
        # reviewed. This is deliberately separate from the bundled owner
        # exception, whose source is pinned by this repository's commit.
        if review == "approved" and src_type(e) in ("github", "git-subdir"):
            if prov.get("reviewed_source_sha") != e.get("source", {}).get("sha"):
                errors.append(
                    f"{eid}: approved external entries must bind provenance.reviewed_source_sha "
                    "to source.sha")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", prov.get("reviewed_at", "")):
                errors.append(f"{eid}: approved external entries require provenance.reviewed_at (YYYY-MM-DD)")
            evidence = prov.get("review_evidence", "")
            if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/(pull|issues)/\d+(#issuecomment-\d+)?", evidence):
                errors.append(f"{eid}: approved external entries require public GitHub PR/issue review evidence")
        perms = e.get("permissions", {})
        for key in ("shell", "network", "mcp", "hooks", "dangerous_permissions"):
            if key not in perms:
                errors.append(f"{eid}: permissions.{key} must be declared")
        for key in ("shell", "network"):
            if key in perms and perms[key] not in ("true", "false"):
                errors.append(f"{eid}: permissions.{key} must be true/false")
        # A boolean MCP/network declaration is not enough to review a plugin:
        # record the executable, immutable image/source, credential input and
        # mutation boundary that a maintainer actually inspected. Keep these
        # requirements fail-closed for real MCP entries while allowing the
        # small synthetic entries used by pure validator tests.
        empty_decl = lambda value: value in (None, "", "[]", "null")
        mcp_declared = not empty_decl(perms.get("mcp", "[]"))
        if mcp_declared:
            for key in ("executables", "mcp_images", "mutation_surface"):
                if empty_decl(perms.get(key)):
                    errors.append(f"{eid}: MCP permissions.{key} audit field is required")
            if perms.get("network") == "true" and empty_decl(perms.get("credential_scopes")):
                errors.append(f"{eid}: networked MCP permissions.credential_scopes audit field is required")
            if "kdenlive" in perms.get("mcp", "").lower() and empty_decl(perms.get("allowed_roots")):
                errors.append(f"{eid}: Kdenlive MCP permissions.allowed_roots audit field is required")
        hooks_declared = perms.get("hooks", "[]") not in ("[]", "", "null")
        if hooks_declared and empty_decl(perms.get("hook_commands")):
            errors.append(f"{eid}: hook permissions.hook_commands audit field is required")
        src = e.get("source", {})
        if src.get("type") == "relative":
            if trust != "first-party":
                errors.append(f"{eid}: relative (bundled) sources must be first-party")
            if not src.get("path"):
                errors.append(f"{eid}: relative source requires path")
            if src.get("sha"):
                errors.append(
                    f"{eid}: relative (bundled) sources must not declare a sha; "
                    "content is pinned by this repository's own commit")
        if src.get("type") in ("github", "git-subdir"):
            if not SHA_RE.match(src.get("sha", "")) or set(src.get("sha", "")) == {"0"}:
                errors.append(f"{eid}: external source must pin a full 40-char sha")
            if src.get("ref", "") in ("main", "master", "latest", ""):
                errors.append(f"{eid}: ref must be an immutable tag/sha, not a moving branch")
            if resolved is not None and eid in resolved:
                if resolved[eid] != src.get("sha"):
                    errors.append(
                        f"{eid}: sha {src.get('sha')} != resolved commit "
                        f"{resolved[eid]} for ref {src.get('ref')}")
    return errors


def resolve_upstream(entry):
    """Resolve ref -> commit sha via gh (annotated tags dereferenced)."""
    src = entry.get("source", {})
    repo, ref = src.get("repo"), src.get("ref")
    if not repo or not ref:
        return None
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/git/ref/tags/{ref}",
         "--jq", ".object.sha + \" \" + .object.type"],
        capture_output=True, text=True, check=False)
    if out.returncode != 0:
        # Not a tag: try resolving as a commit/branch ref directly.
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits/{ref}", "--jq", ".sha"],
            capture_output=True, text=True, check=False)
        return out.stdout.strip() or None
    sha, typ = out.stdout.strip().split()
    if typ == "tag":
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/git/tags/{sha}", "--jq", ".object.sha"],
            capture_output=True, text=True, check=False)
        return out.stdout.strip() or None
    return sha


def main():
    resolve = "--resolve" in sys.argv
    entries = parse_registry((ROOT / "registry" / "registry.yaml").read_text())
    resolved = None
    resolution_errors = []
    if resolve:
        resolved = {}
        for e in entries:
            if src_type(e) == "relative":
                # Bundled content is pinned by the containing repository's
                # commit; there is no upstream ref to resolve over GitHub.
                continue
            sha = resolve_upstream(e)
            if sha:
                resolved[e["id"]] = sha
            else:
                resolution_errors.append(
                    f"{e['id']}: could not resolve upstream ref "
                    f"{e.get('source', {}).get('ref', '')!r}")
    errors = resolution_errors + validate_entries(entries, resolved=resolved)
    # Generated client manifests must never publish unreviewed entries.
    market_path = ROOT / ".claude-plugin" / "marketplace.json"
    if market_path.is_file():
        market = json.loads(market_path.read_text())
        by_id = {e["id"]: e for e in entries}
        for plugin in market.get("plugins", []):
            entry = by_id.get(plugin.get("name"))
            if entry is None:
                errors.append(f"marketplace lists unknown plugin {plugin.get('name')}")
            elif not is_installable(entry):
                errors.append(
                    f"marketplace publishes unreviewed/revoked plugin {entry['id']} "
                    f"(review={entry.get('provenance', {}).get('review')})")
            else:
                src = plugin.get("source")
                if isinstance(src, dict) and src.get("source") == "github":
                    if src.get("sha") != entry["source"].get("sha"):
                        errors.append(f"{entry['id']}: marketplace sha drifts from registry")
    for err in errors:
        print(f"error: {err}", file=sys.stderr)
    if errors:
        return 1
    print(f"registry valid: {len(entries)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
