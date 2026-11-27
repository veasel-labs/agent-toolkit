import base64
import json
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_drift  # noqa: E402


def completed(stdout, returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=""
    )


def failed(stderr, returncode=1):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout="", stderr=stderr
    )


class TagOrderingTests(unittest.TestCase):
    def test_tag_version_key_uses_semver_not_tag_listing_order(self):
        tags = ["v1.51.0", "v1.50.9", "v1.51.1", "not-a-release"]
        supported = [tag for tag in tags if check_drift.tag_version_key(tag)]
        self.assertEqual(max(supported, key=check_drift.tag_version_key), "v1.51.1")

    def test_stable_tag_sorts_after_next_prerelease(self):
        self.assertGreater(
            check_drift.tag_version_key("v1.51.1"),
            check_drift.tag_version_key("v1.51.1-next.8"),
        )
        self.assertEqual(check_drift.tag_version("v1.51.1-next.8"), "1.51.1-next.8")

    def test_generic_semver_prerelease_and_build_metadata_ordering(self):
        versions = [
            "v2.0.0-rc.10+build.7",
            "v2.0.0-beta.2",
            "v2.0.0-rc.2",
            "v2.0.0",
        ]
        self.assertEqual(
            sorted(versions, key=check_drift.tag_version_key),
            ["v2.0.0-beta.2", "v2.0.0-rc.2", "v2.0.0-rc.10+build.7", "v2.0.0"],
        )
        self.assertIsNone(check_drift.tag_version("v2.0.0-rc.01"))

    @patch("check_drift.run_gh")
    def test_latest_tag_paginates_and_resolves_highest_plugin_manifest(self, run_gh):
        manifest = {"version": "1.51.1", "license": "MIT"}
        content = base64.b64encode(json.dumps(manifest).encode()).decode()
        run_gh.side_effect = [
            completed("v1.50.0\nv1.51.1\nv1.49.9\n"),
            completed(json.dumps({"sha": "a" * 40})),
            failed("HTTP 404"),
            completed(json.dumps({"content": content})),
        ]

        self.assertEqual(
            check_drift.latest_tag("ulises-jeremias/agent-toolkit", "plugins/core"),
            ("v1.51.1", "a" * 40, "1.51.1"),
        )
        tag_request = run_gh.call_args_list[0].args[0]
        self.assertIn("--paginate", tag_request)
        self.assertIn("repos/ulises-jeremias/agent-toolkit/tags?per_page=100", tag_request)

    @patch("check_drift.run_gh")
    def test_skips_invalid_highest_tag_and_uses_next_valid_manifest(self, run_gh):
        good = base64.b64encode(json.dumps({"version": "1.1.0"}).encode()).decode()
        bad = base64.b64encode(b'{"version":"not-semver"}').decode()
        run_gh.side_effect = [
            completed("v1.2.0\nv1.1.0\n"),
            completed(json.dumps({"sha": "a" * 40})),
            completed(json.dumps({"content": bad})),
            failed("HTTP 404"),
            completed(json.dumps({"sha": "b" * 40})),
            completed(json.dumps({"content": good})),
            failed("HTTP 404"),
        ]
        self.assertEqual(
            check_drift.latest_tag("owner/repo"),
            ("v1.1.0", "b" * 40, "1.1.0"),
        )

    @patch("check_drift.run_gh")
    def test_non_404_github_failure_fails_closed(self, run_gh):
        run_gh.return_value = failed("HTTP 403: rate limit")
        with self.assertRaises(check_drift.UpstreamResolutionError):
            check_drift.latest_tag("owner/repo")

    @patch("check_drift.run_gh")
    def test_highest_tag_resolution_api_failure_does_not_fallback(self, run_gh):
        run_gh.side_effect = [
            completed("v1.2.0\nv1.1.0\n"),
            failed("HTTP 403: rate limit"),
        ]
        with self.assertRaises(check_drift.UpstreamResolutionError):
            check_drift.latest_tag("owner/repo")

    def test_registry_pin_update_is_scoped_to_exact_plugin_and_updates_version(self):
        old_sha = "a" * 40
        registry = (
            "version: 1\nplugins:\n"
            "  - id: demo\n"
            "    source:\n"
            "      type: github\n"
            "      ref: v1.0.0\n"
            f"      sha: {old_sha}\n"
            "    version: 1.0.0\n"
            "  - id: other\n"
            "    source:\n"
            "      type: github\n"
            "      ref: v1.0.0\n"
            f"      sha: {old_sha}\n"
            "    version: 1.0.0\n"
        )

        updated = check_drift.replace_entry_pin(
            registry, "demo", "v1.2.3", "b" * 40, "1.2.3"
        )

        self.assertIn("ref: v1.2.3", updated)
        self.assertIn("sha: " + "b" * 40, updated)
        self.assertIn("version: 1.2.3", updated)
        other = updated.split("  - id: other", maxsplit=1)[1]
        self.assertIn("ref: v1.0.0", other)
        self.assertIn("sha: " + old_sha, other)
        self.assertIn("version: 1.0.0", other)

    def test_immutable_tag_movement_and_downgrade_fail_closed(self):
        entry = {
            "id": "demo",
            "source": {"ref": "v1.0.0", "sha": "a" * 40},
            "version": "1.0.0",
        }
        with self.assertRaisesRegex(check_drift.UpstreamResolutionError, "moved"):
            check_drift.pin_needs_update(entry, "v1.0.0", "b" * 40, "1.0.0")
        with self.assertRaisesRegex(check_drift.UpstreamResolutionError, "downgrade"):
            check_drift.pin_needs_update(entry, "v0.9.0", "b" * 40, "0.9.0")


if __name__ == "__main__":
    unittest.main()
