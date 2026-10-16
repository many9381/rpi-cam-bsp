import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import tempfile
import unittest

from support import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts/lib"))
import codex_auth


class CodexAuthTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.payload = json.dumps({
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "fixture-access",
                "refresh_token": "fixture-refresh",
                "id_token": "fixture-id",
                "account_id": "fixture-account",
            },
        }).encode()
        self.source = self.root / "auth.json"
        self.source.write_bytes(self.payload)
        self.source.chmod(0o600)

    def test_private_cache_preserves_bytes_and_replaces_atomically(self):
        target = self.root / "keys/codex-auth.json"
        codex_auth.write_private_cache(target, codex_auth.read_auth(self.source))
        self.assertEqual(target.read_bytes(), self.payload)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_rejects_public_symlink_invalid_or_nonrefreshable_credentials(self):
        self.source.chmod(0o644)
        with self.assertRaises(ValueError):
            codex_auth.read_auth(self.source)
        self.source.chmod(0o600)
        link = self.root / "linked.json"
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            codex_auth.read_auth(link)
        for contents in (b"secret-marker: invalid", b"{}", b"x" * 65537,
                         b'{"auth_mode":"chatgpt","tokens":{"access_token":"secret-marker"}}'):
            self.source.write_bytes(contents)
            with self.assertRaises(ValueError) as caught:
                codex_auth.read_auth(self.source)
            self.assertNotIn("secret-marker", str(caught.exception))

    def remote(self, digest):
        device_home = self.root / "device-home"
        device_home.mkdir(exist_ok=True)
        binaries = self.root / "bin"
        binaries.mkdir(exist_ok=True)
        cli = binaries / "codex"
        cli.write_text('#!/bin/sh\n[ "$1 $2" = "login status" ]\n')
        cli.chmod(0o755)
        environment = dict(os.environ, HOME=str(device_home),
                           PATH=f"{binaries}:/usr/bin:/bin")
        result = subprocess.run(
            ["sh", "-c", codex_auth.REMOTE_INSTALL, "codex-auth", digest,
             pwd.getpwuid(os.getuid()).pw_name],
            input=self.payload, capture_output=True, env=environment,
        )
        return result, device_home

    def test_remote_install_is_private_and_leaves_other_configuration_untouched(self):
        home = self.root / "device-home"
        directory = home / ".codex"
        directory.mkdir(parents=True)
        config = directory / "config.toml"
        config.write_text('model = "existing-model"\n')
        result, _ = self.remote(hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((directory / "auth.json").read_bytes(), self.payload)
        self.assertEqual(stat.S_IMODE((directory / "auth.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(config.read_text(), 'model = "existing-model"\n')
        self.assertNotIn(b"fixture-access", result.stdout + result.stderr)
        self.assertEqual(sorted(p.name for p in directory.iterdir()), ["auth.json", "config.toml"])

    def test_incomplete_transfer_preserves_existing_login(self):
        directory = self.root / "device-home/.codex"
        directory.mkdir(parents=True)
        auth = directory / "auth.json"
        auth.write_bytes(b"previous-login")
        result, _ = self.remote("0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(auth.read_bytes(), b"previous-login")
        self.assertEqual(list(directory.iterdir()), [auth])

    def test_auth_payload_is_never_part_of_the_remote_command(self):
        command = codex_auth.remote_command(self.payload, "rpiadmin")
        self.assertNotIn("fixture-access", command)
        self.assertNotIn("fixture-refresh", command)
        self.assertIn(hashlib.sha256(self.payload).hexdigest(), command)


if __name__ == "__main__":
    unittest.main()
