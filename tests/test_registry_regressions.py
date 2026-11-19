"""Regression tests for catalog correctness failures found in review:

1. sha/ref mismatch (pin must equal the resolved upstream commit)
2. unreviewed entries must never validate or publish as verified
3. revoked entries excluded from every generated manifest
4. permission surface flows from registry to the Veasel catalog verbatim
5. invalid registry structures fail validation

Run: python3 -m unittest discover -s tests -v
"""
import copy
import json
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


validate = load("validate_registry")
generate = load("generate_manifests")

SHA_A = "a" * 40
SHA_B = "b" * 40


def entry(**overrides):
    base = {
        "id": "demo-plugin",
        "version": "1.0.0",
        "license": "MIT",
        "trust": "verified",
        "source": {"type": "github", "repo": "example/demo",
                   "ref": "v1.0.0", "sha": SHA_A},
        "permissions": {"shell": "false", "network": "false",
                        "mcp": "[]", "hooks": "[]",
                        "dangerous_permissions": "[]"},
        "provenance": {"submitted_by": "alice", "reviewed_by": "bob",
                       "review": "approved"},
    }
    base.update(overrides)
    return base


class PinResolutionTest(unittest.TestCase):
    def test_sha_ref_mismatch_fails(self):
        errors = validate.validate_entries(
            [entry()], resolved={"demo-plugin": SHA_B})
        self.assertTrue(any("resolved commit" in e for e in errors), errors)

    def test_sha_ref_match_passes(self):
        errors = validate.validate_entries(
            [entry()], resolved={"demo-plugin": SHA_A})
        self.assertEqual(errors, [])

    def test_mutable_ref_and_short_sha_fail(self):
        bad = entry(source={"type": "github", "repo": "example/demo",
                            "ref": "main", "sha": "abc123"})
        errors = validate.validate_entries([bad])
        self.assertTrue(any("40-char" in e for e in errors))
        self.assertTrue(any("immutable" in e for e in errors))


class ReviewGateTest(unittest.TestCase):
    def test_unreviewed_verified_fails_closed(self):
        pending = entry(provenance={"submitted_by": "alice",
                                    "reviewed_by": "null",
                                    "review": "pending-initial-review"})
        errors = validate.validate_entries([pending])
        self.assertTrue(any("requires provenance.review=approved" in e
                            for e in errors), errors)

    def test_unreviewed_entry_is_not_installable_or_listed(self):
        pending = entry(trust="community",
                        provenance={"submitted_by": "alice",
                                    "reviewed_by": "null",
                                    "review": "pending-initial-review"})
        self.assertEqual(validate.validate_entries([pending]), [])
        self.assertFalse(validate.is_installable(pending))
        self.assertEqual(generate.listed([pending]), [])
        catalog = generate.veasel_catalog([pending])
        self.assertEqual(len(catalog["plugins"]), 1)
        self.assertFalse(catalog["plugins"][0]["installable"])
        self.assertEqual(catalog["plugins"][0]["review"],
                         "pending-initial-review")

    def test_revoked_excluded_everywhere(self):
        revoked = entry(provenance={"submitted_by": "alice",
                                    "reviewed_by": "bob",
                                    "review": "revoked"})
        self.assertEqual(generate.listed([revoked]), [])
        self.assertEqual(generate.veasel_catalog([revoked])["plugins"], [])
        self.assertEqual(
            generate.marketplace([revoked], "veasel")["plugins"], [])

    def test_approved_without_reviewer_fails(self):
        bad = entry(provenance={"submitted_by": "alice",
                                "reviewed_by": "null",
                                "review": "approved"})
        errors = validate.validate_entries([bad])
        self.assertTrue(any("reviewed_by" in e for e in errors))


class PermissionFlowTest(unittest.TestCase):
    def test_permissions_flow_verbatim_to_veasel_catalog(self):
        e = entry()
        e["permissions"]["shell"] = "true"
        catalog = generate.veasel_catalog([e])
        self.assertEqual(catalog["plugins"][0]["permissions"]["shell"], "true")
        changed = copy.deepcopy(e)
        changed["permissions"]["network"] = "true"
        catalog2 = generate.veasel_catalog([changed])
        self.assertNotEqual(catalog["plugins"][0]["permissions"],
                            catalog2["plugins"][0]["permissions"])

    def test_missing_permission_declaration_fails(self):
        bad = entry()
        del bad["permissions"]["network"]
        errors = validate.validate_entries([bad])
        self.assertTrue(any("permissions.network" in e for e in errors))


class InvalidStructureTest(unittest.TestCase):
    def test_duplicate_ids_fail(self):
        errors = validate.validate_entries([entry(), entry()])
        self.assertTrue(any("duplicate" in e for e in errors))

    def test_bad_id_and_license_fail(self):
        bad = entry(id="Bad ID", license="not a license!!")
        errors = validate.validate_entries([bad])
        self.assertTrue(any("kebab-case" in e for e in errors))
        self.assertTrue(any("SPDX" in e for e in errors))

    def test_unknown_trust_and_review_fail(self):
        bad = entry(trust="trusted",
                    provenance={"submitted_by": "a", "reviewed_by": "b",
                                "review": "looks-fine"})
        errors = validate.validate_entries([bad])
        self.assertTrue(any("trust must be" in e for e in errors))
        self.assertTrue(any("provenance.review must be" in e for e in errors))


class LiveRegistryTest(unittest.TestCase):
    def test_live_registry_parses_with_review_state(self):
        entries = validate.parse_registry(
            (ROOT / "registry" / "registry.yaml").read_text())
        self.assertTrue(entries)
        for e in entries:
            self.assertIn(e["provenance"].get("review"),
                          validate.REVIEW_STATES)
        self.assertEqual(validate.validate_entries(entries), [])


if __name__ == "__main__":
    unittest.main()


class BundledPluginTest(unittest.TestCase):
    def test_essentials_manifest_shape(self):
        manifest = json.loads(
            (ROOT / "plugins" / "veasel-essentials" / ".claude-plugin" / "plugin.json").read_text())
        for key in ("name", "version", "description", "license"):
            self.assertIn(key, manifest)
        self.assertEqual(manifest["name"], "veasel-essentials")
        skill = ROOT / "plugins" / "veasel-essentials" / "skills" / "output-handshake" / "SKILL.md"
        self.assertTrue(skill.is_file())

    def test_relative_source_must_not_declare_sha(self):
        relative = entry(
            id="bundled-demo", trust="first-party",
            source={"type": "relative", "path": "plugins/demo", "ref": "main",
                    "sha": "0" * 40},
            provenance={"submitted_by": "alice", "reviewed_by": "null",
                        "review": "pending-initial-review"})
        errors = validate.validate_entries([relative])
        self.assertTrue(any("must not declare a sha" in e for e in errors), errors)

    def test_all_zero_external_sha_fails(self):
        zero = entry(source={"type": "github", "repo": "example/demo",
                             "ref": "v1.0.0", "sha": "0" * 40})
        errors = validate.validate_entries([zero])
        self.assertTrue(any("40-char sha" in e for e in errors), errors)

    def test_bundled_pending_is_not_installable(self):
        entries = validate.parse_registry(
            (ROOT / "registry" / "registry.yaml").read_text())
        essentials = [e for e in entries if e["id"] == "veasel-essentials"]
        self.assertEqual(len(essentials), 1)
        self.assertFalse(validate.is_installable(essentials[0]))
        self.assertNotIn(essentials[0],
                         generate.listed(entries))
