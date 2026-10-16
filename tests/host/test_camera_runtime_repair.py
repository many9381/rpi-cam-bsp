from pathlib import Path
import hashlib
import json
import os
import signal
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from support import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts/lib"))
import camera_runtime_repair as repair


def elf_library(soname, marker, machine=183):
    """Minimal ELF64 fixture with PT_LOAD/PT_DYNAMIC and a real DT_SONAME."""
    strings = b"\0" + soname.encode() + b"\0"
    strings_offset = 240
    size = strings_offset + len(strings) + len(marker)
    header = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01" + b"\0" * 9,
                         3, machine, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    load = struct.pack("<IIQQQQQQ", 1, 4, 0, 0, 0, size, size, 4096)
    dynamic = struct.pack("<IIQQQQQQ", 2, 4, 176, 176, 176, 64, 64, 8)
    tags = struct.pack("<qQqQqQqQ", 5, strings_offset, 10, len(strings), 14, 1, 0, 0)
    return header + load + dynamic + tags + strings + marker


class CameraRuntimeRepairTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.source = self.work / "source"
        self.root = self.work / "root"
        self.payload = self.work / "payload"
        self.files = (
            "usr/lib/libcamera.so.0.6.0", "usr/lib/libcamera-base.so.0.6.0",
            "usr/lib/libcamera/ipa/ipa_rpi_pisp.so",
            "usr/lib/libcamera/ipa/ipa_rpi_pisp.so.sign",
            "usr/libexec/libcamera/raspberrypi_ipa_proxy",
            "usr/share/libcamera/ipa/rpi/pisp/imx708_wide.json",
        )
        self.before = {}
        self.after = {}
        for relative in self.files:
            for parent, data in ((self.source, b"new library data"), (self.root, b"original data")):
                if relative in repair.LIBRARIES:
                    data = elf_library(Path(relative).name.removesuffix(".0"), data)
                (self.after if parent == self.source else self.before)[relative] = data
                path = parent / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o644)
        (self.root / "etc").mkdir()
        (self.root / "etc/rpi5-camera-profile").write_text("rpi5-camera-hailo\n")
        for name in ("libcamera", "libcamera-base"):
            (self.root / f"usr/lib/{name}.so.0.6").symlink_to(f"{name}.so.0.6.0")
        repair.prepare(self.source, self.payload)

    def test_update_preserves_accounts_and_creates_restorable_backup(self):
        account = self.root / "etc/account-test"
        account.write_bytes(b"account and TLS state must remain unchanged")
        backup = repair.install(self.root, self.payload)
        for relative in self.files:
            self.assertEqual((self.root / relative).read_bytes(), self.after[relative])
            self.assertEqual((backup / relative).read_bytes(), self.before[relative])
        self.assertEqual(account.read_bytes(), b"account and TLS state must remain unchanged")
        repair.verify(self.root, self.payload)
        self.assertIsNone(repair.install(self.root, self.payload))

    def test_tampered_payload_is_rejected_before_target_changes(self):
        (self.payload / self.files[0]).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            repair.install(self.root, self.payload)
        self.assertEqual((self.root / self.files[0]).read_bytes(), self.before[self.files[0]])
        self.assertFalse((self.root / "var").exists())

    def test_invalid_profile_and_symlink_parent_are_rejected(self):
        (self.root / "etc/rpi5-camera-profile").write_text("other-image\n")
        with self.assertRaises(ValueError):
            repair.install(self.root, self.payload)
        (self.root / "etc/rpi5-camera-profile").write_text("rpi5-camera-hailo\n")
        target = self.root / "usr/lib/libcamera/ipa"
        target.rename(target.with_name("outside"))
        target.symlink_to("outside")
        with self.assertRaises(ValueError):
            repair.install(self.root, self.payload)
        self.assertEqual((self.root / self.files[0]).read_bytes(), self.before[self.files[0]])

    def test_failed_write_rolls_back_every_modified_file(self):
        real = repair.replace_file
        calls = 0

        def failing(path, data, mode):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated disk error")
            return real(path, data, mode)

        with patch.object(repair, "replace_file", side_effect=failing):
            with self.assertRaises(OSError):
                repair.install(self.root, self.payload)
        for relative in self.files:
            self.assertEqual((self.root / relative).read_bytes(), self.before[relative])

    def test_manifest_cannot_write_outside_libcamera_paths(self):
        manifest = self.payload / "manifest.json"
        content = json.loads(manifest.read_text())
        content["files"]["etc/shadow"] = content["files"][self.files[0]]
        manifest.write_text(json.dumps(content))
        with self.assertRaises(ValueError):
            repair.install(self.root, self.payload)
        self.assertFalse((self.root / "etc/shadow").exists())

    def test_persistent_write_failure_restores_prior_files_without_allocating_new_data(self):
        real = repair.replace_file
        calls = 0

        def disk_full(path, data, mode):
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise OSError("no space left on device")
            return real(path, data, mode)

        with patch.object(repair, "replace_file", side_effect=disk_full):
            with self.assertRaises(OSError):
                repair.install(self.root, self.payload)
        for relative in self.files:
            self.assertEqual((self.root / relative).read_bytes(), self.before[relative])

    def test_interrupt_and_termination_restore_original_files(self):
        real = repair.replace_file
        for reason in (KeyboardInterrupt, signal.SIGINT, signal.SIGTERM):
            calls = 0

            def interrupted(path, data, mode):
                nonlocal calls
                calls += 1
                if calls == 2:
                    if reason is KeyboardInterrupt:
                        raise KeyboardInterrupt()
                    # Signal at the atomic rename/record boundary must be deferred.
                    real(path, data, mode)
                    os.kill(os.getpid(), reason)
                    return
                real(path, data, mode)

            with self.subTest(reason=reason), patch.object(repair, "replace_file", side_effect=interrupted):
                with self.assertRaises((KeyboardInterrupt, InterruptedError)):
                    repair.install(self.root, self.payload)
                for relative in self.files:
                    self.assertEqual((self.root / relative).read_bytes(), self.before[relative])

    def test_invalid_elf_machine_soname_and_truncated_payload_are_rejected(self):
        relative = self.files[0]
        invalid = (b"not an ELF library", self.after[relative][:32],
                   elf_library("libcamera.so.0.6", b"", machine=62),
                   elf_library("libcamera.so.0.7", b""))
        for data in invalid:
            with self.subTest(data=data[:20]):
                (self.payload / relative).write_bytes(data)
                manifest = self.payload / "manifest.json"
                content = json.loads(manifest.read_text())
                content["files"][relative]["sha256"] = hashlib.sha256(data).hexdigest()
                manifest.write_text(json.dumps(content))
                with self.assertRaises(ValueError):
                    repair.install(self.root, self.payload)
                self.assertEqual((self.root / relative).read_bytes(), self.before[relative])
                self.assertFalse((self.root / "var").exists())

    def test_incompatible_installed_library_is_rejected_before_writes(self):
        (self.root / self.files[0]).write_bytes(elf_library("libcamera.so.0.7", b""))
        with self.assertRaises(ValueError):
            repair.install(self.root, self.payload)
        self.assertFalse((self.root / "var").exists())

    def test_rollback_attempts_every_file_and_reports_any_unrestored_backup(self):
        real_replace = repair.os.replace
        real_write = repair.replace_file
        calls = 0
        restore_attempts = []

        def failing_write(path, data, mode):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("simulated write failure")
            real_write(path, data, mode)

        def failing_restore(source, target):
            if "/var/backups/" in str(source):
                restore_attempts.append(str(target))
                if len(restore_attempts) == 1:
                    raise OSError("one original cannot be restored")
            real_replace(source, target)

        with patch.object(repair, "replace_file", side_effect=failing_write), \
                patch.object(repair.os, "replace", side_effect=failing_restore):
            with self.assertRaisesRegex(OSError, "rollback incomplete.*originals retained"):
                repair.install(self.root, self.payload)
        self.assertEqual(len(restore_attempts), 2)
        self.assertEqual(Path(restore_attempts[1]).read_bytes(),
                         self.before[str(Path(restore_attempts[1]).relative_to(self.root))])
        backups = list((self.root / "var/backups/rpi5-camera-runtime").glob("libcamera-*"))
        failed = str(Path(restore_attempts[0]).relative_to(self.root))
        self.assertEqual((backups[0] / failed).read_bytes(), self.before[failed])


if __name__ == "__main__":
    unittest.main()
