"""Stdlib-only registry/marketplace consistency tests.

Run: python3 -m unittest discover -s tests -v
No third-party packages: YAML subset parsing is intentionally minimal
(the registry file only uses the documented flat shape).
"""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def registry_entries():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "validate_registry", ROOT / "scripts" / "validate_registry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    parsed = mod.parse_registry((ROOT / "registry" / "registry.yaml").read_text())
    if parsed:
        return parsed
    text = (ROOT / "registry" / "registry.yaml").read_text()
    entries, current = [], None
    for line in text.splitlines():
        m = re.match(r"^  - id: (.+)$", line)
        if m:
            current = {"id": m.group(1).strip()}
            entries.append(current)
        elif current is not None:
            m = re.match(r"^    (version|license): (.+)$", line)
            if m:
                current[m.group(1)] = m.group(2).strip()
            m = re.match(r"^      (repo|ref|sha|type): (.+)$", line)
            if m:
                current.setdefault("source", {})[m.group(1)] = m.group(2).strip()
    return entries


class RegistryTest(unittest.TestCase):
    def test_registry_entries_have_provenance_shape(self):
        entries = registry_entries()
        self.assertTrue(entries, "registry must not be empty")
        ids = [e["id"] for e in entries]
        self.assertEqual(len(ids), len(set(ids)), "ids must be unique")
        for e in entries:
            self.assertRegex(e["id"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
            self.assertIn("version", e)
            self.assertIn("license", e)
            src = e.get("source", {})
            if src.get("type") in ("github", "git-subdir"):
                self.assertRegex(src.get("sha", ""), r"^[0-9a-f]{40}$",
                                   "external sources must pin a full sha")
                self.assertIn("ref", src)

    def test_marketplace_matches_registry(self):
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        by_id = {e["id"]: e for e in registry_entries()}
        self.assertEqual(market["name"], "veasel")
        for plugin in market["plugins"]:
            self.assertIn(plugin["name"], by_id)
            self.assertEqual(
                by_id[plugin["name"]]["provenance"]["review"], "approved",
                "marketplace must never publish unreviewed entries")
            entry = by_id[plugin["name"]]
            self.assertEqual(plugin["version"], entry["version"])
            self.assertEqual(plugin["description"], entry["description"])
            src = plugin["source"]
            if isinstance(src, dict) and src.get("source") == "github":
                self.assertEqual(src["sha"], entry["source"]["sha"])

    def test_veasel_catalog_preserves_registry_provenance(self):
        catalog = json.loads(
            (ROOT / "generated" / "veasel-catalog.json").read_text())
        by_id = {e["id"]: e for e in registry_entries()}
        for plugin in catalog["plugins"]:
            self.assertEqual(plugin["provenance"],
                             by_id[plugin["id"]]["provenance"])

        pending = next(p for p in catalog["plugins"]
                       if p["review"] != "approved")
        self.assertIsNone(pending["provenance"]["reviewed_by"])

    def test_copied_schemas_present(self):
        for rel in [
            "schemas/agent-plugins/1.0.0/plugin.schema.json",
            "schemas/agent-plugins/1.0.0/mcp.schema.json",
            "schemas/products.schema.yaml",
            "schemas/upstream-lock.schema.json",
        ]:
            path = ROOT / rel
            self.assertTrue(path.is_file(), rel)
            if rel.endswith(".json"):
                json.loads(path.read_text())


if __name__ == "__main__":
    unittest.main()
