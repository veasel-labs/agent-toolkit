#!/usr/bin/env python3
"""Drift detection for pinned community plugins.

Compares each github/git-subdir registry entry's pinned sha against the
upstream repo's latest release tag (via `gh api`). With --update, bumps
ref+sha in registry.yaml to the latest tag; the workflow then opens a
review PR (never auto-merged — docs/REVIEW_POLICY.md).

Requires: gh authenticated (CI provides GH_TOKEN). Stdlib only.
Exit 0 = no drift (or updated), 2 = drift found without --update.
"""
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate_registry import parse_registry, ROOT  # noqa: E402


def latest_tag(repo):
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/tags", "--jq", ".[0].name"],
        capture_output=True, text=True, check=False)
    if out.returncode != 0:
        return None, None
    tag = out.stdout.strip()
    if not tag:
        return None, None
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/commits/{tag}", "--jq", ".sha"],
        capture_output=True, text=True, check=False)
    if out.returncode != 0:
        return tag, None
    return tag, out.stdout.strip()


def main():
    update = "--update" in sys.argv
    text = (ROOT / "registry" / "registry.yaml").read_text()
    entries = parse_registry(text)
    drift = []
    for e in entries:
        src = e.get("source", {})
        if src.get("type") not in ("github", "git-subdir") or not src.get("repo"):
            continue
        tag, sha = latest_tag(src["repo"])
        if not tag or not sha:
            print(f"warn: {e['id']}: could not resolve upstream tag for {src['repo']}")
            continue
        if sha != src.get("sha"):
            drift.append((e["id"], src.get("ref"), src.get("sha"), tag, sha))
    for eid, old_ref, old_sha, tag, sha in drift:
        print(f"drift: {eid}: {old_ref}@{old_sha[:12]} -> {tag}@{sha[:12]}")
    if drift and update:
        for eid, old_ref, old_sha, tag, sha in drift:
            text = text.replace(old_sha, sha)
            if old_ref:
                text = text.replace(f"ref: {old_ref}", f"ref: {tag}", 1)
        (ROOT / "registry" / "registry.yaml").write_text(text)
        print("registry updated; regenerate manifests before opening the PR")
        return 0
    return 2 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
