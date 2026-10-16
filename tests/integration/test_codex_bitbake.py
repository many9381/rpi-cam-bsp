"""Exercise latest-release selection with the checked-out BitBake cache.

Run after kas checkout: python3 tests/integration/test_codex_bitbake.py
No image tasks, network requests or device operations are performed.
"""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "bitbake/lib"), str(ROOT / "meta-rpi5-cam/lib")]

import bb.data
import bb.fetch2
from rpi5cam.codex_release import configure_latest


class CodexBitBakeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = bb.data.init()
        self.data.setVar("BB_CACHEDIR", self.temporary.name)
        self.data.setVar("BB_SRCREV_POLICY", "clear")

    def test_workers_share_selection_and_next_invocation_refreshes(self):
        with patch("rpi5cam.codex_release.resolve_latest", side_effect=[
            {"version": "1.2.3", "binary_sha256": "a" * 64},
            {"version": "1.3.0", "binary_sha256": "b" * 64},
        ]) as resolve:
            bb.fetch2.fetcher_init(self.data)
            configure_latest(self.data)
            self.assertEqual(self.data.getVar("CODEX_RELEASE_VERSION"), "1.2.3")
            bb.fetch2.fetcher_parse_done()

            worker = self.data.createCopy()
            worker.delVar("CODEX_RELEASE_VERSION")
            bb.fetch2.fetcher_init(worker, servercontext=False)
            configure_latest(worker)
            self.assertEqual(worker.getVar("CODEX_RELEASE_VERSION"), "1.2.3")
            self.assertEqual(resolve.call_count, 1)

            bb.fetch2.fetcher_init(self.data)
            configure_latest(self.data)
            self.assertEqual(self.data.getVar("CODEX_RELEASE_VERSION"), "1.3.0")
            self.assertEqual(self.data.getVar("CODEX_RELEASE_BINARY_SHA256"), "b" * 64)
            self.assertEqual(resolve.call_count, 2)

    def test_offline_policy_prevents_http_request(self):
        self.data.setVar("BB_NO_NETWORK", "1")
        bb.fetch2.fetcher_init(self.data)
        with patch("urllib.request.urlopen") as request:
            with patch("bb.fatal", side_effect=RuntimeError) as fatal:
                with self.assertRaises(RuntimeError):
                    configure_latest(self.data)
            request.assert_not_called()
            self.assertIn("Cannot resolve latest Codex", fatal.call_args.args[0])

    def test_cached_revision_policy_is_rejected(self):
        self.data.setVar("BB_SRCREV_POLICY", "cache")
        with patch("urllib.request.urlopen") as request:
            with patch("bb.fatal", side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    configure_latest(self.data)
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
