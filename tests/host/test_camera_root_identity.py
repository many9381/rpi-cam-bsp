"""Execute the target shell probe against real, disposable UUID symlinks."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from support import REPO_ROOT


UUID = "3911ba06-e492-4ccc-b54e-d3c1ff7cfb83"
OTHER_UUID = "6da705b7-b664-48a6-a119-27b652c55a75"


class CameraRootIdentityTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.device = self.base / "sda2"
        self.device.touch()
        self.other = self.base / "sda1"
        self.other.touch()
        self.by_uuid = self.base / "by-uuid"
        self.by_uuid.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        # Only kernel/mount inventory commands are replaced. The actual shell,
        # directory traversal, symlinks and readlink all execute normally.
        commands = {
            "findmnt": '#!/bin/sh\n[ "$*" = "-n -o SOURCE /" ] || exit 91\nprintf "%s\\n" "$PROBE_DEVICE"\n',
            "lsblk": '''#!/bin/sh
case "$*" in
  "-no PKNAME $PROBE_DEVICE") printf 'sda\\n' ;;
  '-dn -o TRAN /dev/sda') printf 'usb\\n' ;;
  "-no UUID $PROBE_DEVICE")
    printf '%s\\n' "$PROBE_UUID"
    exit "$PROBE_UUID_EXIT" ;;
  *) exit 92 ;;
esac
''',
        }
        for name, text in commands.items():
            path = self.bin / name
            path.write_text(text)
            path.chmod(0o755)

    def probe(self, uuid="", uuid_exit=0):
        env = os.environ.copy()
        env.update(PATH=f"{self.bin}:{env['PATH']}", PROBE_DEVICE=str(self.device),
                   PROBE_UUID=uuid, PROBE_UUID_EXIT=str(uuid_exit))
        return subprocess.run([
            "sh", "-c", '. "$1"; camera_root_identity "$2"', "probe",
            str(REPO_ROOT / "scripts/lib/camera_root_identity.sh"), str(self.by_uuid),
        ], env=env, capture_output=True, text=True)

    def assert_identity(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{self.device}|/dev/sda|usb|{UUID}\n")

    def test_nonempty_lsblk_uuid_does_not_require_udev_links(self):
        self.by_uuid.rmdir()
        self.assert_identity(self.probe(uuid=UUID))

    def test_empty_lsblk_uuid_resolves_only_the_root_partition_link(self):
        (self.by_uuid / "9C23-D358").symlink_to(self.other)
        (self.by_uuid / UUID).symlink_to("../sda2")
        self.assert_identity(self.probe())

    def test_unavailable_uuid_column_uses_the_same_verified_link(self):
        (self.by_uuid / UUID).symlink_to(self.device)
        self.assert_identity(self.probe(uuid_exit=1))

    def test_missing_or_unrelated_uuid_links_fail_without_identity_output(self):
        for kind in ("empty", "other-partition", "broken", "regular-file"):
            with self.subTest(kind=kind):
                link = self.by_uuid / UUID
                if kind == "other-partition":
                    link.symlink_to(self.other)
                elif kind == "broken":
                    link.symlink_to(self.base / "missing-device")
                elif kind == "regular-file":
                    link.touch()
                try:
                    result = self.probe()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                finally:
                    link.unlink(missing_ok=True)

    def test_two_uuid_links_for_the_root_fail_instead_of_picking_one(self):
        for uuid in (UUID, OTHER_UUID):
            (self.by_uuid / uuid).symlink_to(self.device)
        result = self.probe()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_malformed_or_multiple_lsblk_values_are_not_hidden_by_fallback(self):
        (self.by_uuid / UUID).symlink_to(self.device)
        for value in ("garbage", UUID + "\n" + OTHER_UUID, "|other-device", "$(id)",
                      UUID[:8] + "\n" + UUID[8:], UUID[:8] + " " + UUID[8:]):
            with self.subTest(value=value):
                result = self.probe(uuid=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_non_uuid_root_alias_is_rejected(self):
        for name in ("not-a-filesystem-uuid", UUID + "\njunk", "junk\n" + UUID,
                     UUID + "\n", UUID + "\r"):
            with self.subTest(name=name):
                link = self.by_uuid / name
                link.symlink_to(self.device)
                try:
                    result = self.probe()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                finally:
                    link.unlink()

    def test_different_root_media_returns_its_new_identity(self):
        link = self.by_uuid / UUID
        link.symlink_to(self.device)
        self.assert_identity(self.probe())
        link.unlink()
        (self.by_uuid / OTHER_UUID).symlink_to(self.device)
        result = self.probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{self.device}|/dev/sda|usb|{OTHER_UUID}\n")


if __name__ == "__main__":
    unittest.main()
