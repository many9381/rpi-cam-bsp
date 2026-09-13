from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support import REPO_ROOT


class FirmwareNpmLockTest(unittest.TestCase):
    """Exercise fetch metadata generation, never npm or network access."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="firmware-npm-lock-")
        self.root = Path(self.temporary.name)
        self.lock = self.root / "package-lock.json"
        self.integrity = "sha512-" + base64.b64encode(bytes(range(64))).decode()
        self.package = {
            "version": "1.2.3",
            "resolved": "https://registry.npmjs.org/@scope/tool/-/tool-1.2.3.tgz",
            "integrity": self.integrity,
            "dev": True,
        }
        self.document = {
            "name": "camera-firmware-web",
            "lockfileVersion": 3,
            "packages": {"": {"name": "camera-firmware-web"},
                         "node_modules/@scope/tool": self.package},
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def generate(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        self.lock.write_text(json.dumps(self.document), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/firmware_npm_lock.py"),
             str(self.lock), *arguments],
            text=True, capture_output=True, check=False,
        )

    def test_scoped_dev_archive_gets_strong_checksum_and_no_unpack(self) -> None:
        """Catch omitting build dependencies or losing SRI during conversion."""
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.package["resolved"], result.stdout)
        self.assertIn(";unpack=0", result.stdout)
        self.assertIn(
            'SRC_URI[cf_npm_0000.sha512sum] = "'
            '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f'
            '202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f"',
            result.stdout,
        )
        self.assertIn("${DL_DIR}/camera-firmware-npm-", result.stdout)

    def test_duplicate_nested_archive_is_fetched_once(self) -> None:
        """Catch duplicate downloads for the same locked nested dependency."""
        self.document["packages"]["node_modules/other/node_modules/@scope/tool"] = copy.deepcopy(self.package)
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count(self.package["resolved"]), 1)

    def test_generation_is_independent_of_package_order(self) -> None:
        """Catch unstable metadata churn when npm changes package key order."""
        other = dict(self.package, resolved="https://registry.npmjs.org/another/-/another-1.2.3.tgz")
        self.document["packages"]["node_modules/another"] = other
        first = self.generate()
        self.document["packages"] = dict(reversed(list(self.document["packages"].items())))
        second = self.generate()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        # Raw lock hash deliberately changes; fetch entries must remain stable.
        first_lines = [line for line in first.stdout.splitlines() if not line.startswith("CF_NPM_LOCK_SHA256")]
        second_lines = [line for line in second.stdout.splitlines() if not line.startswith("CF_NPM_LOCK_SHA256")]
        self.assertEqual(first_lines, second_lines)

    def test_rejects_non_registry_or_metadata_injection_urls(self) -> None:
        """Catch a lock entry escaping the supported fetch origin or recipe syntax."""
        for url in (
            "http://registry.npmjs.org/tool/-/tool.tgz",
            "https://example.com/tool.tgz",
            "https://registry.npmjs.org/tool.tgz;unpack=1",
            'https://registry.npmjs.org/tool.tgz"${MALICIOUS}',
            "https://user@registry.npmjs.org/tool.tgz",
            "https://registry.npmjs.org:443/tool.tgz",
            "https://registry.npmjs.org/../tool.tgz",
        ):
            with self.subTest(url=url):
                self.package["resolved"] = url
                result = self.generate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsupported archive URL", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_rejects_missing_weak_or_malformed_integrity(self) -> None:
        """Catch accepting an archive whose lock cannot authenticate its bytes."""
        for integrity in (None, "sha1-AAAA", "sha512-AAAA", "sha512-%%%%"):
            with self.subTest(integrity=integrity):
                self.package["integrity"] = integrity
                result = self.generate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("SHA-512 integrity", result.stderr)

    def test_rejects_conflicting_hashes_for_same_archive(self) -> None:
        """Catch trusting two inconsistent definitions of one remote archive."""
        other = dict(self.package, integrity="sha512-" + base64.b64encode(b"x" * 64).decode())
        self.document["packages"]["node_modules/other"] = other
        result = self.generate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting integrity", result.stderr)

    def test_check_mode_detects_source_lock_changes_without_writing(self) -> None:
        """Catch a firmware revision update reusing obsolete web fetch metadata."""
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        include = self.root / "npm.inc"
        include.write_text(result.stdout, encoding="utf-8")
        self.assertEqual(self.generate("--check", str(include)).returncode, 0)
        self.document["packages"][""]["version"] = "0.1.0"
        changed = self.generate("--check", str(include))
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("stale", changed.stderr)
        self.assertEqual(include.read_text(encoding="utf-8"), result.stdout)

    def test_rejects_local_links_and_unsupported_lock_format(self) -> None:
        """Catch silently depending on files absent from the fetched source."""
        self.package["link"] = True
        self.assertIn("local or bundled", self.generate().stderr)
        self.package.pop("link")
        self.document["lockfileVersion"] = 1
        self.assertIn("lockfileVersion 3", self.generate().stderr)


if __name__ == "__main__":
    unittest.main()
