import importlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from support import REPO_ROOT, read, run


BUILD_ID = "20261010T070850Z-e664cb9647e7"
HELPER = REPO_ROOT / "scripts/lib/codex_flash_auth.py"
sys.path.insert(0, str(HELPER.parent))


class CodexFlashAuthTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), "SSD auth restore helper is missing")
        self.helper = importlib.import_module("codex_flash_auth")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.raw = json.dumps({"auth_mode": "chatgpt", "tokens": {
            "access_token": "fixture-access", "refresh_token": "fixture-refresh",
            "id_token": "fixture-id", "account_id": "fixture-account",
        }}).encode()
        self.source = self.base / "auth.json"
        self.source.write_bytes(self.raw)
        self.source.chmod(0o600)
        private = self.base / "private"
        private.mkdir(mode=0o700)
        self.snapshot = private / "codex-auth.json"
        self.rootfs = self.base / "rootfs"
        for name in ("etc", "usr/bin", "home/rpiadmin"):
            (self.rootfs / name).mkdir(parents=True, exist_ok=True)
        (self.rootfs / "etc/rpi5-build-id").write_text(BUILD_ID + "\n")
        (self.rootfs / "etc/passwd").write_text(
            f"rpiadmin:x:{os.getuid()}:{os.getgid()}::/home/rpiadmin:/bin/sh\n")
        (self.rootfs / "usr/bin/codex").write_bytes(b"fixture executable")
        self.target = self.rootfs / "home/rpiadmin/.codex/auth.json"

    def install(self):
        # Only a real mount needs root. All credential/path operations are real.
        with patch.object(self.helper.os.path, "ismount", return_value=True):
            self.helper.install_auth(self.rootfs, self.source, BUILD_ID)

    def verify(self):
        with patch.object(self.helper.os.path, "ismount", return_value=True):
            self.helper.verify_auth(self.rootfs, self.source, BUILD_ID)

    def test_snapshot_reads_current_invoking_users_cache_each_time(self):
        host_home = self.base / "host-home"
        directory = host_home / ".codex"
        directory.mkdir(parents=True)
        current = directory / "auth.json"
        current.write_bytes(self.raw)
        current.chmod(0o600)
        with patch.object(self.helper.pwd, "getpwuid", return_value=SimpleNamespace(pw_dir=str(host_home))):
            self.helper.snapshot_auth(os.getuid(), None, self.snapshot)
            self.assertEqual(self.snapshot.read_bytes(), self.raw)
            updated = self.raw.replace(b"fixture-refresh", b"fixture-new-refresh")
            current.write_bytes(updated)
            self.helper.snapshot_auth(os.getuid(), None, self.snapshot)
        self.assertEqual(self.snapshot.read_bytes(), updated)
        self.assertEqual(stat.S_IMODE(self.snapshot.stat().st_mode), 0o600)

    def test_snapshot_rejects_wrong_owner_public_or_invalid_input(self):
        for uid, mode, contents in (
            (os.getuid() + 1, 0o600, self.raw),
            (os.getuid(), 0o644, self.raw),
            (os.getuid(), 0o600, b"fixture-secret-invalid"),
        ):
            with self.subTest(uid=uid, mode=mode):
                self.source.write_bytes(contents)
                self.source.chmod(mode)
                with self.assertRaises(ValueError) as caught:
                    self.helper.snapshot_auth(uid, self.source, self.snapshot)
                self.assertNotIn("fixture-secret", str(caught.exception))
                self.assertFalse(self.snapshot.exists())

    def test_camera_prepare_function_stages_the_selected_current_login(self):
        command = r'''
source "$1"
uv_run_locked() { shift 2; /usr/bin/python3 "$@"; }
prepare_codex_auth rpi5-camera-hailo fixture-uv "$3" "$4" "$2" 0
printf 'prepared=%s\n' "$codex_auth_prepared"
'''
        result = run("bash", "-c", command, "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"),
                     str(self.source), str(self.snapshot), str(os.getuid()))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("prepared=true", result.stdout)
        self.assertNotIn("fixture-access", result.stdout + result.stderr)
        self.assertEqual(self.snapshot.read_bytes(), self.raw)

    def test_install_uses_target_account_and_preserves_configuration(self):
        self.target.parent.mkdir()
        config = self.target.parent / "config.toml"
        config.write_text('model = "existing-model"\n')
        self.install()
        self.install()
        self.verify()
        self.assertEqual(self.target.read_bytes(), self.raw)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.target.parent.stat().st_mode), 0o700)
        self.assertEqual((self.target.stat().st_uid, self.target.stat().st_gid),
                         (os.getuid(), os.getgid()))
        self.assertEqual(config.read_text(), 'model = "existing-model"\n')
        self.assertEqual(sorted(p.name for p in self.target.parent.iterdir()),
                         ["auth.json", "config.toml"])

    def test_rejects_unmounted_or_wrong_build_before_writing(self):
        with self.assertRaises(ValueError):
            self.helper.install_auth(self.rootfs, self.source, BUILD_ID)
        (self.rootfs / "etc/rpi5-build-id").write_text("other-build\n")
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse(self.target.parent.exists())

    def test_packaged_codex_link_restores_and_verifies_auth(self):
        """Catch rejecting the public symlink created by the Codex image recipe."""
        package_binary = self.rootfs / "usr/lib/codex/bin/codex"
        package_binary.parent.mkdir(parents=True)
        package_binary.write_bytes(b"packaged executable")
        public = self.rootfs / "usr/bin/codex"
        public.unlink()
        public.symlink_to("/usr/lib/codex/bin/codex")
        self.install()
        self.verify()
        self.assertEqual(self.target.read_bytes(), self.raw)

    def test_codex_link_cannot_select_an_arbitrary_host_or_image_file(self):
        """Only the known image-package link is allowed, never host resolution."""
        public = self.rootfs / "usr/bin/codex"
        public.unlink()
        for target in (str(self.source), "/etc/passwd", "../../../auth.json"):
            with self.subTest(target=target):
                public.symlink_to(target)
                with self.assertRaises(ValueError):
                    self.install()
                public.unlink()
                self.assertFalse(self.target.parent.exists())

    def test_packaged_codex_link_cannot_escape_through_target_parents(self):
        """Catch following an allowed public link through a malicious package path."""
        public = self.rootfs / "usr/bin/codex"
        public.unlink()
        public.symlink_to("/usr/lib/codex/bin/codex")
        (self.rootfs / "usr/lib").symlink_to(self.base)
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse(self.target.parent.exists())

    def test_rejects_missing_codex_and_unsafe_target_account(self):
        binary = self.rootfs / "usr/bin/codex"
        binary.unlink()
        with self.assertRaises(ValueError):
            self.install()
        binary.write_bytes(b"fixture")
        for row in ("rpiadmin:x:0:0::/home/rpiadmin:/bin/sh\n",
                    "rpiadmin:x:1000:1000::/root:/bin/sh\n", ""):
            (self.rootfs / "etc/passwd").write_text(row)
            with self.assertRaises(ValueError):
                self.install()
        self.assertFalse(self.target.parent.exists())

    def test_symlinked_directories_or_auth_file_cannot_escape_target(self):
        outside = self.base / "outside"
        outside.mkdir()
        for relative in ("home", "home/rpiadmin", "home/rpiadmin/.codex", "etc"):
            with self.subTest(relative=relative):
                link = self.rootfs / relative
                saved = link.with_name(link.name + ".saved")
                existed = link.exists()
                if existed:
                    link.rename(saved)
                link.symlink_to(outside, target_is_directory=True)
                with self.assertRaises((ValueError, OSError)):
                    self.install()
                link.unlink()
                if existed:
                    saved.rename(link)
                self.assertEqual(list(outside.iterdir()), [])
        self.target.parent.mkdir()
        victim = outside / "keep"
        victim.write_bytes(b"do not change")
        self.target.symlink_to(victim)
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(victim.read_bytes(), b"do not change")

    def test_readback_rejects_content_and_permission_changes(self):
        self.install()
        self.target.chmod(0o644)
        with self.assertRaises(ValueError):
            self.verify()
        self.target.chmod(0o600)
        self.target.write_bytes(self.raw.replace(b"fixture-access", b"changed-access"))
        with self.assertRaises(ValueError):
            self.verify()

    def test_cli_failure_does_not_log_credentials_or_create_snapshot(self):
        self.source.write_bytes(b"fixture-secret-invalid")
        result = run(sys.executable, str(HELPER), "snapshot", "--source-user", str(os.getuid()),
                     "--source-file", str(self.source), "--output", str(self.snapshot))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("fixture-secret", result.stdout + result.stderr)
        self.assertFalse(self.snapshot.exists())


class FlashAuthWorkflowTest(unittest.TestCase):
    def test_camera_snapshot_failure_stops_before_disk_write(self):
        command = r'''
source "$1"
uv_run_locked() { return 1; }
prepare_codex_auth rpi5-camera fixture-uv "$2/auth.json" 1000 "" 0
touch "$2/WRITE"
'''
        with tempfile.TemporaryDirectory() as temporary:
            result = run("bash", "-c", command, "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"), temporary)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(temporary) / "WRITE").exists())
            self.assertNotIn("command not found", result.stderr)

    def test_minimal_and_explicit_skip_do_not_read_login(self):
        command = r'''
source "$1"
uv_run_locked() { touch "$4/READ"; return 1; }
prepare_codex_auth "$2" fixture-uv "$4/auth.json" 1000 "" "$3"
printf '%s\n' "$codex_auth_prepared"
'''
        for profile, skip in (("rpi5-minimal", "0"), ("rpi5-camera", "1"), ("rpi5-camera-hailo", "1")):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temporary:
                result = run("bash", "-c", command, "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"), profile, skip, temporary)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "false")
                self.assertFalse((Path(temporary) / "READ").exists())

    def test_flash_stages_before_erasing_and_verifies_before_pass(self):
        script = read("scripts/flash-ssd.sh")
        self.assertIn('\nprepare_codex_auth "$profile"', script)
        self.assertIn('\n    restore_codex_auth ', script)
        stage = script.index('\nprepare_codex_auth "$profile"')
        write = script.index('\nbmaptool copy ')
        restore = script.index('\n    restore_codex_auth ')
        complete = script.index('\ntouch "$flash_marker"')
        self.assertLess(stage, write)
        self.assertLess(write, restore)
        self.assertLess(restore, complete)

    def test_restore_remounts_read_only_and_failure_prevents_success(self):
        command = r'''
source "$1"
calls="$2/calls"
failure="$3"
mount() { printf 'mount %s\n' "$*" >> "$calls"; }
umount() { printf 'umount\n' >> "$calls"; }
sync() { printf 'sync\n' >> "$calls"; }
uv_run_locked() {
    printf '%s\n' "$4" >> "$calls"
    [[ "$4" != "$failure" ]]
}
restore_codex_auth fixture-uv fixture-auth /dev/fixture fixture-mount fixture-build
touch "$2/PASS"
'''
        for failure in ("none", "install", "verify"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                result = run("bash", "-c", command, "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"), temporary, failure)
                root = Path(temporary)
                self.assertEqual(result.returncode == 0, failure == "none", result.stderr)
                self.assertEqual((root / "PASS").exists(), failure == "none")
                calls = (root / "calls").read_text().splitlines()
                expected = ["mount -o rw,nodev,nosuid,noexec /dev/fixture fixture-mount", "install",
                            "sync", "umount", "mount -o ro,noload,nodev,nosuid,noexec /dev/fixture fixture-mount",
                            "verify", "umount"]
                if failure != "none":
                    expected = expected[:expected.index(failure) + 1]
                self.assertEqual(calls, expected)

    def test_auth_options_are_available_and_reject_missing_or_relative_paths(self):
        for arguments in (("--codex-auth-file",), ("--codex-auth-file", "relative.json")):
            result = run("bash", "scripts/flash-ssd.sh", *arguments)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("Usage:", result.stderr)
        for arguments in (("--skip-codex-auth", "--help"),
                          ("--codex-auth-file", "/private/auth.json", "--help")):
            result = run("bash", "scripts/flash-ssd.sh", *arguments)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--skip-codex-auth", result.stdout)


if __name__ == "__main__":
    unittest.main()
