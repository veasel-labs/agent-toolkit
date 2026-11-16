#!/usr/bin/env python3
"""Registry validator (stdlib only) for veasel-labs/agent-toolkit.

Fails closed on: mutable/unpinned external sources, missing trust tier,
missing permission declaration, non-SPDX-looking license, duplicate ids,
and marketplace/registry drift. Run locally or in CI:
    python3 scripts/validate_registry.py
Exit 0 = valid, 1 = violations printed to stderr.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRUST_TIERS = {"first-party", "verified", "community", "experimental"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SPDX_RE = re.compile(r"^[A-Za-z0-9.+-]+$")


def parse_registry(text):
    entries, current, section = [], None, None
    for line in text.splitlines():
        m = re.match(r"^  - id: (.+)$", line)
        if m:
            current = {"id": m.group(1).strip(), "source": {}, "permissions": {}}
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
        if re.match(r"^    \w", line):
            section = None
        m = re.match(r"^      (repo|ref|sha|type|path): (.+)$", line)
        if m and section == "source":
            current["source"][m.group(1)] = m.group(2).strip()
            continue
        m = re.match(r"^      (shell|network): (.+)$", line)
        if m and section == "permissions":
            current["permissions"][m.group(1)] = m.group(2).strip()
            continue
        m = re.match(r"^      (mcp|hooks|dangerous_permissions): (.+)$", line)
        if m and section == "permissions":
            current["permissions"][m.group(1)] = m.group(2).strip()
    return entries


def main():
    errors = []
    entries = parse_registry((ROOT / "registry" / "registry.yaml").read_text())
    if not entries:
        errors.append("registry has no entries")
    seen = set()
    for e in entries:
        eid = e.get("id", "?")
        if not ID_RE.match(eid):
            errors.append(f"{eid}: id must be kebab-case")
        if eid in seen:
            errors.append(f"{eid}: duplicate id")
        seen.add(eid)
        if e.get("trust") not in TRUST_TIERS:
            errors.append(f"{eid}: trust must be one of {sorted(TRUST_TIERS)}")
        if not SPDX_RE.match(e.get("license", "")):
            errors.append(f"{eid}: license must be an SPDX id")
        perms = e.get("permissions", {})
        for key in ("shell", "network", "mcp", "hooks", "dangerous_permissions"):
            if key not in perms:
                errors.append(f"{eid}: permissions.{key} must be declared")
        src = e.get("source", {})
        if src.get("type") in ("github", "git-subdir"):
            if not SHA_RE.match(src.get("sha", "")):
                errors.append(f"{eid}: external source must pin a full 40-char sha")
            if src.get("ref", "") in ("main", "master", "latest", ""):
                errors.append(f"{eid}: ref must be an immutable tag/sha, not a moving branch")
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    by_id = {e["id"]: e for e in entries}
    for plugin in market.get("plugins", []):
        entry = by_id.get(plugin.get("name"))
        if entry is None:
            errors.append(f"marketplace lists unknown plugin {plugin.get('name')}")
            continue
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
