"""Exercise offline provisioning with real OpenSSL and disposable filesystems."""
import hashlib
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import yaml
from support import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts/lib"))
BUILD = "20261011T120000Z-0123456789ab"


class CameraProvisionTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue((REPO_ROOT / "scripts/lib/camera_identity.py").is_file(),
                        "host camera signing identity preparation is missing")
        self.identity = importlib.import_module("camera_identity")
        self.provision = importlib.import_module("camera_provision")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.identity.prepare(self.repo)
        self.keys = self.repo / "keys/camera-firmware"
        # The explicit-address path remains supported for existing deployments.
        (self.keys / "device.json").write_text('{"public_host": "198.51.100.61"}\n')
        self.root = self.base / "root"
        self.boot = self.base / "boot"
        self.boot.mkdir()
        for name in ("etc/camera-firmware", "usr/bin", "usr/share/camera-firmware",
                     "var/lib/systemd/timesync", "usr/lib/systemd/system"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / "etc/rpi5-build-id").write_text(BUILD + "\n")
        (self.root / "etc/passwd").write_text(
            f"camera-firmware:x:{os.getuid()}:{os.getgid()}::/var/lib/camera-firmware:/sbin/nologin\n"
            f"systemd-timesync:x:{os.getuid()}:{os.getgid()}::/:/sbin/nologin\n")
        self.public = self.root / "usr/share/camera-firmware/integrity-public-key.pem"
        shutil.copyfile(self.keys / "integrity-public.pem", self.public)
        self.public.chmod(0o644)
        (self.root / "usr/bin/camera-firmware").write_bytes(b"fixture ELF\0" + self.public.read_bytes())
        (self.boot / "kernel_2712.img").write_bytes(b"fixture Pi kernel")
        template = REPO_ROOT / "meta-rpi-cam-hailo/recipes-camera/camera-firmware/files/app-hailo.yaml.example"
        (self.root / "etc/camera-firmware/app.yaml.example").write_text(
            template.read_text().replace("@SYSCONFDIR@", "/etc").replace("@DATADIR@", "/usr/share"))
        self.stage = self.base / "staged"
        self.identity.stage(self.repo, self.public, self.stage, os.getuid())
        self.config = self.root / "etc/camera-firmware/app.yaml"
        self.clock = self.root / "var/lib/systemd/timesync/clock"

    def test_offline_boot_restored_clock_makes_real_certificate_valid(self):
        # A stale RTC/build epoch must be repaired before NTP is available.
        self.clock.touch(mode=0o644)
        os.utime(self.clock, (1773360000, 1773360000))  # 2026-03-13 UTC
        self.install()
        certificate = self.config.parent / "tls/device.crt"
        start = subprocess.check_output([
            "openssl", "x509", "-in", str(certificate), "-noout", "-startdate",
            "-dateopt", "iso_8601"], text=True).strip().split("=", 1)[1]
        not_before = int(datetime.fromisoformat(start).timestamp())
        restored = self.clock.stat().st_mtime_ns // 1_000_000_000
        # Provisioning keeps a conservative full-second margin after notBefore.
        self.assertGreater(restored, not_before)
        for label, boot_time, expected in (("past RTC", not_before - 86400, 2),
                                          ("NTP unavailable", restored, 0),
                                          ("NTP delayed", restored + 120, 0)):
            with self.subTest(label=label):
                result = subprocess.run(["openssl", "verify", "-attime", str(boot_time),
                                         "-CAfile", str(certificate), str(certificate)],
                                        capture_output=True)
                self.assertEqual(result.returncode, expected, result.stderr)
        info = self.clock.stat()
        self.assertEqual((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)),
                         (os.getuid(), os.getgid(), 0o644))
        self.assertEqual(self.clock.read_bytes(), b"")
        self.assertFalse((self.root / "run/systemd/timesync/synchronized").exists())

    def test_newer_saved_clock_is_not_rolled_back_on_install_or_retry(self):
        self.clock.touch(mode=0o644)
        newer = time.time_ns() + 86400 * 1_000_000_000
        os.utime(self.clock, ns=(newer, newer))
        self.install()
        self.assertEqual(self.clock.stat().st_mtime_ns, newer)
        self.install()
        self.assertEqual(self.clock.stat().st_mtime_ns, newer)

    def test_fresh_image_without_timesync_state_directory_gets_a_verified_clock(self):
        self.clock.parent.rmdir()
        self.install()
        self.verify()
        self.assertTrue(self.clock.is_file())
        self.assertEqual(stat.S_IMODE(self.clock.parent.stat().st_mode), 0o755)

    def test_retry_seeds_missing_clock_without_changing_existing_materials(self):
        self.install()
        before = {p: p.read_bytes() for p in self.config.parent.rglob("*") if p.is_file()}
        self.clock.unlink(missing_ok=True)
        self.install()
        self.assertTrue(self.clock.is_file())
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.verify()

    def test_readonly_verification_rejects_missing_stale_or_writable_clock(self):
        self.clock.touch(mode=0o644)
        self.install()
        original = self.clock.stat().st_mtime_ns
        os.utime(self.clock, (1, 1))
        with self.assertRaises(ValueError):
            self.verify()
        self.assertEqual(self.clock.stat().st_mtime_ns, 1_000_000_000)
        os.utime(self.clock, ns=(original, original))
        self.clock.chmod(0o666)
        with self.assertRaises(ValueError):
            self.verify()
        self.assertEqual(stat.S_IMODE(self.clock.stat().st_mode), 0o666)
        self.clock.unlink()
        with self.assertRaises(ValueError):
            self.verify()
        self.assertFalse(self.clock.exists())

    def test_missing_timesync_account_prevents_activation(self):
        passwd = self.root / "etc/passwd"
        passwd.write_text(passwd.read_text().splitlines()[0] + "\n")
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse(self.config.exists())

    def test_clock_links_cannot_modify_an_outside_file_or_activate_app(self):
        outside = self.base / "outside-clock"
        outside.touch(mode=0o644)
        os.utime(outside, (1, 1))
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    self.clock.symlink_to(outside)
                else:
                    os.link(outside, self.clock)
                try:
                    with self.assertRaises(ValueError):
                        self.install()
                    self.assertFalse(self.config.exists())
                    self.assertEqual(outside.stat().st_mtime_ns, 1_000_000_000)
                finally:
                    self.clock.unlink()

    def test_saved_time_after_certificate_expiry_prevents_activation_without_rollback(self):
        self.clock.touch(mode=0o644)
        too_late = time.time_ns() + 400 * 86400 * 1_000_000_000
        os.utime(self.clock, ns=(too_late, too_late))
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(self.clock.stat().st_mtime_ns, too_late)
        self.assertFalse(self.config.exists())

    def test_timestamp_write_failure_never_activates_app(self):
        with patch.object(os, "utime", side_effect=OSError("timestamp write failed")):
            with self.assertRaises(OSError):
                self.install()
        self.assertFalse(self.config.exists())

    def install(self):
        # Mounting is the only privileged external boundary replaced here.
        with patch.object(os.path, "ismount", return_value=True):
            self.provision.install(self.root, self.boot, self.stage, BUILD)

    def verify(self):
        with patch.object(os.path, "ismount", return_value=True):
            self.provision.verify(self.root, self.boot, self.stage, BUILD)

    def test_prepare_reuses_keys_and_rejects_partial_identity(self):
        before = (self.keys / "integrity-private.pem").read_bytes()
        self.identity.prepare(self.repo)
        self.assertEqual(before, (self.keys / "integrity-private.pem").read_bytes())
        self.assertEqual(stat.S_IMODE((self.keys / "integrity-private.pem").stat().st_mode), 0o600)
        (self.keys / "integrity-public.pem").unlink()
        with self.assertRaises(ValueError):
            self.identity.prepare(self.repo)
        self.assertEqual(before, (self.keys / "integrity-private.pem").read_bytes())

    def test_new_identity_and_provisioning_need_no_network_address(self):
        other = self.base / "dhcp-repo"
        other.mkdir()
        self.identity.prepare(other)
        _, _, config = self.identity.load_identity(other, os.getuid())
        self.assertIsNone(config["public_host"])
        (self.stage / "device.json").write_text('{"public_host": null}\n')
        self.install()
        self.verify()
        installed = yaml.safe_load(self.config.read_text())
        self.assertEqual(installed["http"]["public_base_url"], "")
        self.assertTrue(installed["security"]["enabled"])
        self.assertTrue(installed["http"]["tls"]["enabled"])
        certificate = self.config.parent / "tls/device.crt"
        result = subprocess.run(["openssl", "verify", "-CAfile", str(certificate), str(certificate)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_config_tls_and_manifest_are_usable_and_private_key_stays_off_device(self):
        self.install()
        self.verify()
        config = yaml.safe_load(self.config.read_text())
        self.assertEqual(config["http"]["public_base_url"], "https://198.51.100.61:8443")
        self.assertTrue(config["security"]["enabled"])
        self.assertFalse(config["http"]["tls"]["allow_development_self_signed_tls"])
        self.assertTrue(config["secure_rtsp"]["client_auth"]["enabled"])
        self.assertEqual(config["ai"]["backend"], "hailo")
        directory = self.config.parent
        manifest = directory / "integrity/manifest.yaml"
        document = yaml.safe_load(manifest.read_text())
        entries = {item["path"]: item for item in document["files"]}
        self.assertEqual(set(entries), {"/usr/bin/camera-firmware", "/etc/camera-firmware/app.yaml",
                                        "/boot/kernel_2712.img"})
        self.assertEqual(entries["/etc/camera-firmware/app.yaml"]["sha256"],
                         hashlib.sha256(self.config.read_bytes()).hexdigest())
        result = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(self.public),
                                 "-rawin", "-in", str(manifest), "-sigfile",
                                 str(directory / "integrity/manifest.sig")], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        cert = directory / "tls/device.crt"
        result = subprocess.run(["openssl", "verify", "-CAfile", str(cert), "-verify_ip", "198.51.100.61", str(cert)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        secret = (self.keys / "integrity-private.pem").read_bytes()
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(secret, path.read_bytes(), str(path))
        self.assertEqual(stat.S_IMODE((directory / "tls/device.key").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o640)
        # The application's setup wizard creates these; never seed a shared account.
        self.assertFalse((self.root / "var/lib/camera-firmware/security/rtsp-digest.credentials").exists())

    def test_repeated_install_preserves_tls_srtp_and_runtime_state(self):
        self.install()
        state = self.root / "var/lib/camera-firmware/security/operator-state"
        state.write_bytes(b"keep administrator settings")
        before = {p: p.read_bytes() for p in self.config.parent.rglob("*") if p.is_file()}
        self.install()
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(state.read_bytes(), b"keep administrator settings")

    def test_long_valid_dns_name_works_after_preerase_address_validation(self):
        host = "camera." + "a" * 58 + ".example.com"
        self.assertEqual(self.identity.validate_host(host), host)
        (self.stage / "device.json").write_text(json.dumps({"public_host": host}))
        self.install()
        certificate = self.config.parent / "tls/device.crt"
        result = subprocess.run(["openssl", "verify", "-CAfile", str(certificate),
                                 "-verify_hostname", host, str(certificate)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrong_signing_key_is_rejected_before_device_or_stage_changes(self):
        other = self.base / "other"
        other.mkdir()
        self.identity.prepare(other)
        with self.assertRaises(ValueError):
            self.identity.stage(other, self.public, self.base / "bad-stage", os.getuid())
        self.assertFalse((self.base / "bad-stage").exists())
        shutil.copyfile(other / "keys/camera-firmware/integrity-private.pem", self.stage / "integrity-private.pem")
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse(self.config.exists())

    def test_tampered_kernel_and_config_fail_readback(self):
        self.install()
        for path in (self.boot / "kernel_2712.img", self.config):
            original = path.read_bytes()
            path.write_bytes(original + b"tamper")
            with self.assertRaises(ValueError):
                self.verify()
            path.write_bytes(original)

    def test_wrong_build_unmounted_target_and_symlink_escape_do_not_activate(self):
        with self.assertRaises(ValueError):
            self.provision.install(self.root, self.boot, self.stage, BUILD)
        with patch.object(os.path, "ismount", return_value=True), self.assertRaises(ValueError):
            self.provision.install(self.root, self.boot, self.stage, "wrong-build")
        (self.config.parent / "tls").symlink_to(self.base / "outside")
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse(self.config.exists())
        self.assertFalse((self.base / "outside").exists())

    def test_signing_failure_never_publishes_active_config(self):
        def fail(*args):
            raise ValueError("test signing failure")
        with patch.object(self.provision, "sign_manifest", side_effect=fail):
            with self.assertRaises(ValueError):
                self.install()
        self.assertFalse(self.config.exists())

    def test_public_private_key_modes_and_unsafe_host_are_rejected(self):
        private = self.keys / "integrity-private.pem"
        private.chmod(0o644)
        with self.assertRaises(ValueError):
            self.identity.stage(self.repo, self.public, self.base / "bad-stage", os.getuid())
        private.chmod(0o600)
        for host in ("https://camera/", "camera\nsubjectAltName=DNS:bad", "*.example.com", "-bad", ""):
            (self.keys / "device.json").write_text(json.dumps({"public_host": host}))
            with self.subTest(host=host), self.assertRaises(ValueError):
                self.identity.stage(self.repo, self.public, self.base / "bad-stage", os.getuid())

    def test_flash_preparation_validates_and_snapshots_current_operator_identity(self):
        command = r'''
source "$1"
uv_run_locked() { shift 2; /usr/bin/python3 "$@"; }
prepare_camera_identity rpi5-camera-hailo fixture-uv "$4" "$2" "$3" "$5" 0
printf 'prepared=%s\n' "$camera_identity_prepared"
'''
        result = subprocess.run(["bash", "-c", command, "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"),
                                 str(self.repo), str(self.public), str(self.base / "shell-stage"),
                                 str(os.getuid())], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("prepared=true", result.stdout)
        self.assertEqual((self.base / "shell-stage/integrity-public.pem").read_bytes(), self.public.read_bytes())
        self.assertNotIn("PRIVATE KEY", result.stdout + result.stderr)

    def test_flash_readback_remounts_readonly_and_propagates_verification_failure(self):
        command = r'''
source "$1"
mount() { printf 'mount %s\n' "$*"; }
umount() { printf 'umount %s\n' "$*"; }
sync() { :; }
uv_run_locked() {
    printf 'helper %s\n' "$*"
    [[ " $* " != *" verify "* ]] || return 73
}
provision_camera fixture-uv fixture-identity /dev/boot /dev/root boot-mount root-mount fixture-build
printf 'incorrect-success\n'
'''
        result = subprocess.run(["bash", "-c", command, "bash", str(REPO_ROOT / "scripts/flash-ssd.sh")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertNotIn("incorrect-success", result.stdout)
        self.assertIn("mount -o ro,noload,nodev,nosuid,noexec /dev/root root-mount", result.stdout)
        self.assertLess(result.stdout.index(" install "), result.stdout.index("ro,noload"))
        self.assertLess(result.stdout.index("ro,noload"), result.stdout.index(" verify "))


if __name__ == "__main__":
    unittest.main()
