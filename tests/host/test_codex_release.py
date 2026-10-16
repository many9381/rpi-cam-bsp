import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

from support import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "meta-rpi5-cam/lib"))


class CodexReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = importlib.import_module("rpi5cam.codex_release")
        self.commit = "a" * 40
        self.release = {
            "tag_name": "rust-v1.2.3",
            "draft": False,
            "prerelease": False,
            # This can be a moving branch and must not be used as a commit.
            "target_commitish": "main",
            "assets": [{
                "name": "codex-package-aarch64-unknown-linux-musl.tar.gz",
                "browser_download_url": "https://github.com/openai/codex/releases/download/rust-v1.2.3/codex-package-aarch64-unknown-linux-musl.tar.gz",
                "digest": "sha256:" + "b" * 64,
            }],
        }
        self.notices = {
            "LICENSE": b"license fixture\n",
            "NOTICE": b"notice fixture\n",
            "third_party/wezterm/LICENSE": b"wezterm fixture\n",
            "codex-rs/vendor/bubblewrap/COPYING": b"bubblewrap fixture\n",
        }
        self.requested = []

    def read_url(self, url):
        self.requested.append(url)
        if url == "https://api.github.com/repos/openai/codex/releases/latest":
            return json.dumps(self.release).encode()
        if url == f"https://api.github.com/repos/openai/codex/commits/{self.release['tag_name']}":
            return json.dumps({"sha": self.commit}).encode()
        prefix = f"https://raw.githubusercontent.com/openai/codex/{self.commit}/"
        if url.startswith(prefix):
            return self.notices[url.removeprefix(prefix)]
        self.fail(f"unexpected URL: {url}")

    def test_resolves_actual_version_asset_digest_and_matching_source_notices(self):
        result = self.module.resolve_latest(self.read_url)
        self.assertEqual(result["version"], "1.2.3")
        self.assertEqual(result["source_rev"], self.commit)
        self.assertEqual(result["binary_sha256"], "b" * 64)
        self.assertEqual(result["binary_url"], self.release["assets"][0]["browser_download_url"])
        for name, path in (("license", "LICENSE"), ("notice", "NOTICE"), ("wezterm", "third_party/wezterm/LICENSE")):
            self.assertEqual(result[f"{name}_sha256"], hashlib.sha256(self.notices[path]).hexdigest())
        self.assertFalse(any("/main/" in url for url in self.requested))

    def test_bundled_sandbox_license_matches_the_release_commit(self):
        """Catch omitting the license for the newly shipped sandbox resource."""
        result = self.module.resolve_latest(self.read_url)
        self.assertEqual(result.get("bubblewrap_sha256"), hashlib.sha256(b"bubblewrap fixture\n").hexdigest())

    def test_next_resolution_observes_new_release_and_checksums(self):
        previous = self.module.resolve_latest(self.read_url)
        self.release["tag_name"] = "rust-v1.3.0"
        asset = self.release["assets"][0]
        asset["browser_download_url"] = asset["browser_download_url"].replace("1.2.3", "1.3.0")
        asset["digest"] = "sha256:" + "c" * 64
        current = self.module.resolve_latest(self.read_url)
        self.assertEqual(current["version"], "1.3.0")
        self.assertNotEqual(previous["binary_url"], current["binary_url"])
        self.assertNotEqual(previous["binary_sha256"], current["binary_sha256"])

    def test_rejects_drafts_prereleases_and_non_release_tags(self):
        for changes in ({"draft": True}, {"prerelease": True}, {"tag_name": "rust-v1.2.3-alpha.1"}, {"tag_name": "main"}):
            with self.subTest(changes=changes):
                original = copy.deepcopy(self.release)
                self.release.update(changes)
                with self.assertRaises(ValueError):
                    self.module.resolve_latest(self.read_url)
                self.release = original

    def test_rejects_missing_ambiguous_or_unverified_arm64_asset(self):
        original = copy.deepcopy(self.release["assets"])
        for assets in ([], original * 2, [{**original[0], "digest": None}], [{**original[0], "digest": "sha256:bad"}], [{**original[0], "browser_download_url": "https://example.org/codex.tar.gz"}]):
            with self.subTest(assets=assets):
                self.release["assets"] = assets
                with self.assertRaises(ValueError):
                    self.module.resolve_latest(self.read_url)

    def test_rejects_non_commit_source_revision(self):
        self.commit = "main"
        with self.assertRaises(ValueError):
            self.module.resolve_latest(self.read_url)

    def test_network_failure_does_not_fall_back_to_previous_version(self):
        reader = Mock(side_effect=OSError("offline"))
        with self.assertRaises(OSError):
            self.module.resolve_latest(reader)
        reader.assert_called_once()


if __name__ == "__main__":
    unittest.main()
