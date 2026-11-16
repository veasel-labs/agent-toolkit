#!/usr/bin/env python3
"""Generate client marketplace manifests from registry/registry.yaml.

Stdlib only. Usage:
    python3 scripts/generate_manifests.py           # write manifests
    python3 scripts/generate_manifests.py --check   # fail on drift

Generated:
    .claude-plugin/marketplace.json   (Claude Code marketplace)
    .cursor-plugin/marketplace.json   (Cursor marketplace, same catalog shape)
    generated/veasel-catalog.json     (Veasel Library catalog: registry +
                                       trust tier + declared permissions)
Entries whose review is revoked, or whose trust tier is experimental,
are excluded from client manifests. The Veasel catalog keeps community
entries but marks them opt-in; experimental entries are excluded there
too. Deterministic output: sorted keys, stable ordering by id.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate_registry import parse_registry, is_installable, ROOT  # noqa: E402


def listed(entries):
    # Client manifests publish ONLY reviewed, installable entries.
    # Pending/revoked entries fail closed: they exist in the registry
    # for review, never in a generated marketplace.
    return sorted((e for e in entries if is_installable(e)),
                  key=lambda e: e["id"])


def marketplace(entries, name):
    plugins = []
    for e in listed(entries):
        src = e.get("source", {})
        if src.get("type") in ("github", "git-subdir"):
            source = {
                "source": src["type"],
                "repo": src.get("repo", ""),
                "ref": src.get("ref", ""),
                "sha": src.get("sha", ""),
            }
            if src.get("path"):
                source["path"] = src["path"]
        else:
            source = f"./plugins/{e['id']}"
        plugins.append({
            "name": e["id"],
            "source": source,
            "description": e.get("description", ""),
            "version": e.get("version", ""),
            "category": "productivity",
            "tags": [],
        })
    return {
        "name": name,
        "owner": {"name": "veasel-labs", "url": "https://github.com/veasel-labs"},
        "metadata": {
            "description": "Generated from registry/registry.yaml by scripts/generate_manifests.py — do not hand-edit.",
            "version": "0.1.0",
            "pluginRoot": "./plugins",
        },
        "plugins": plugins,
    }


def veasel_catalog(entries):
    # The Veasel catalog shows review state honestly: pending entries
    # are visible for review but installable=false; revoked and
    # experimental entries are excluded entirely.
    plugins = []
    for e in sorted(entries, key=lambda x: x["id"]):
        review = e.get("provenance", {}).get("review")
        if review == "revoked" or e.get("trust") == "experimental":
            continue
        plugins.append({
            "id": e["id"],
            "version": e.get("version", ""),
            "license": e.get("license", ""),
            "trust": e.get("trust", ""),
            "review": review,
            "installable": is_installable(e),
            "opt_in_required": e.get("trust") == "community",
            "source": e.get("source", {}),
            "permissions": e.get("permissions", {}),
        })
    return {"name": "veasel", "version": 1, "plugins": plugins}


def targets(entries):
    return {
        ".claude-plugin/marketplace.json": marketplace(entries, "veasel"),
        ".cursor-plugin/marketplace.json": marketplace(entries, "veasel"),
        "generated/veasel-catalog.json": veasel_catalog(entries),
    }


def render(data):
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def main():
    check = "--check" in sys.argv
    entries = parse_registry((ROOT / "registry" / "registry.yaml").read_text())
    # parse_registry only keeps a subset of fields; descriptions are
    # optional in generated output, so tolerate their absence.
    drift = []
    for rel, data in targets(entries).items():
        path = ROOT / rel
        content = render(data)
        if check:
            if not path.is_file() or path.read_text() != content:
                drift.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    if drift:
        print(f"error: generated manifests drift: {', '.join(drift)}", file=sys.stderr)
        return 1
    print("manifests " + ("up to date" if check else "generated"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
