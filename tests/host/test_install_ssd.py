import copy
import hashlib
import os
import shutil
import subprocess
import json
from pathlib import Path
import sys
import tempfile
import unittest

from support import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts/lib"))
from install_ssd import select_image, select_target, validate_fingerprint


OLD = "20261010T070850Z-0123456789ab"
NEW = "20261010T094100Z-0123456789ab"
PROFILE = "rpi5-camera-hailo"
IDENTITY = {"serial": "003987654321", "model": "GP-GSTFS31120GN",
            "vendor": "GIGABYTE", "size_bytes": 120034123776}


def topology():
    return {"blockdevices": [
        {"path": "/dev/sda", "kname": "sda", "type": "disk", "tran": None,
         "size": 412316860416, "model": "HOST", "serial": "host",
         "mountpoints": [], "children": [
             {"path": "/dev/sda2", "kname": "sda2", "type": "part",
              "size": 412314746368, "mountpoints": ["/"]}]},
        {"path": "/dev/sdc", "kname": "sdc", "type": "disk", "tran": "usb",
         "size": 120034123776, "model": "GP-GSTFS31120GN", "serial": "003987654321",
         "mountpoints": [], "children": [
             {"path": "/dev/sdc1", "kname": "sdc1", "type": "part",
              "size": 136314880, "mountpoints": ["/media/operator/boot"]}]},
    ]}


class InstallSsdTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def image(self, build_id, complete=True, profile=PROFILE):
        directory = self.root / "artifacts" / build_id / profile
        (directory / "images").mkdir(parents=True)
        (directory / "manifests").mkdir()
        (directory / "checksums").mkdir()
        name = "rpi5-minimal-image" if profile == "rpi5-minimal" else "rpi5-camera-image"
        for suffix in ("wic.bz2", "wic.bmap"):
            (directory / "images" / f"{name}-raspberrypi5.rootfs.{suffix}").touch()
        (directory / "checksums/SHA256SUMS").touch()
        (directory / "manifests/build-metadata.json").write_text(json.dumps({
            "build_id": build_id, "profile": profile, "machine": "raspberrypi5", "image": name,
        }))
        if complete:
            (directory / "COMPLETE").touch()
        return directory

    def test_install_without_qemu_reaches_writer_without_any_build(self):
        """Catch automatic QEMU builds before writing an already completed Pi image."""
        directory = self.image(NEW)
        image = directory / "images/rpi5-camera-image-raspberrypi5.rootfs.wic.bz2"
        (directory / "checksums/SHA256SUMS").write_text(
            hashlib.sha256(image.read_bytes()).hexdigest() + "  images/" + image.name + "\n"
        )
        for relative in ("scripts/install-ssd.sh", "scripts/lib/common.sh"):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / relative, destination)
        plan = {"build_id": NEW, "device": "/dev/sdc", "fingerprint": "registered-ssd",
                "directory": str(directory)}
        (self.root / "scripts/lib/install_ssd.py").write_text(
            "import json\nprint(json.dumps(" + repr(plan) + "))\n"
        )
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        def executable(path, contents):
            path.write_text(contents)
            path.chmod(0o755)
        for name in ("build.sh", "test-qemu.sh"):
            executable(self.root / "scripts" / name,
                       "#!/bin/sh\ntouch forbidden-build\nexit 95\n")
        for name in ("curl", "uv"):
            executable(fake_bin / name, "#!/bin/sh\nexit 96\n")
        # Disk discovery and privileged writing are external boundaries. Neither
        # real disks nor credentials are used by this orchestration test.
        executable(fake_bin / "sudo", "#!/usr/bin/env python3\n"
                   "import json, pathlib, sys\n"
                   "pathlib.Path('writer-args.json').write_text(json.dumps(sys.argv[1:]))\n")
        # Supply a fake downloaded uv archive; image checksum verification stays real.
        executable(fake_bin / "sha256sum", "#!/usr/bin/env python3\n"
                   "import os, sys\n"
                   "if '--status' in sys.argv: sys.stdin.read(); sys.exit(0)\n"
                   "os.execv('/usr/bin/sha256sum', ['/usr/bin/sha256sum', *sys.argv[1:]])\n")
        archive = self.root / ".state/uv-release/uv-x86_64-unknown-linux-gnu.tar.gz"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"test archive")
        environment = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"])
        environment.pop("UV_PROJECT_ENVIRONMENT", None)
        result = subprocess.run(["bash", "scripts/install-ssd.sh"], cwd=self.root,
                                env=environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "forbidden-build").exists())
        self.assertFalse((self.root / "artifacts" / NEW / "qemu").exists())
        arguments = json.loads((self.root / "writer-args.json").read_text())
        self.assertIn(str(self.root / "scripts/flash-ssd.sh"), arguments)
        self.assertEqual(arguments[arguments.index("--build-id") + 1], NEW)
        self.assertEqual(arguments[arguments.index("--device") + 1], "/dev/sdc")
        self.assertEqual(arguments[arguments.index("--expected-fingerprint") + 1], "registered-ssd")

    def test_latest_completed_image_ignores_stale_active_id_and_incomplete_build(self):
        self.image(OLD)
        self.image(NEW)
        self.image("20261011T010000Z-0123456789ab", complete=False)
        (self.root / ".state").mkdir()
        (self.root / ".state/active-build-id").write_text(OLD)
        self.assertEqual(select_image(self.root, PROFILE)["build_id"], NEW)
        self.assertEqual(select_image(self.root, PROFILE, OLD)["build_id"], OLD)

    def test_broken_newest_image_does_not_silently_flash_older_image(self):
        self.image(OLD)
        latest = self.image(NEW)
        (latest / "images/rpi5-camera-image-raspberrypi5.rootfs.wic.bz2").unlink()
        with self.assertRaises(ValueError):
            select_image(self.root, PROFILE)

    def test_metadata_mismatch_and_incomplete_explicit_image_are_rejected(self):
        latest = self.image(NEW)
        (latest / "manifests/build-metadata.json").write_text(json.dumps({"build_id": OLD}))
        with self.assertRaises(ValueError):
            select_image(self.root, PROFILE)
        self.image(OLD, complete=False)
        with self.assertRaises(ValueError):
            select_image(self.root, PROFILE, OLD)

    def test_profile_selection_does_not_cross_into_other_images(self):
        self.image(OLD, profile="rpi5-minimal")
        self.image(NEW)
        self.assertEqual(select_image(self.root, "rpi5-minimal")["build_id"], OLD)
        with self.assertRaises(ValueError):
            select_image(self.root, "qemu")
        with self.assertRaises(ValueError):
            select_image(self.root, PROFILE, "../../outside")

    def test_registered_ssd_is_found_after_device_name_changes_and_with_mounts(self):
        result = select_target(topology(), IDENTITY, 6423995392, ["/dev/sda2"])
        self.assertEqual(result["path"], "/dev/sdc")
        self.assertEqual(result["mounted"], ["/dev/sdc1"])

    def test_absent_or_duplicate_registered_ssd_is_rejected(self):
        data = topology()
        data["blockdevices"][1]["serial"] = "different"
        with self.assertRaises(ValueError):
            select_target(data, IDENTITY, 6423995392, ["/dev/sda2"])
        data = topology()
        clone = copy.deepcopy(data["blockdevices"][1])
        clone.update(path="/dev/sdd", kname="sdd", children=[])
        data["blockdevices"].append(clone)
        with self.assertRaises(ValueError):
            select_target(data, IDENTITY, 6423995392, ["/dev/sda2"])

    def test_registered_target_still_cannot_back_a_protected_filesystem(self):
        with self.assertRaises(ValueError):
            select_target(topology(), IDENTITY, 6423995392, ["/dev/sdc1"])

    def test_invalid_identity_and_oversize_image_are_rejected(self):
        for identity in ({}, dict(IDENTITY, serial=""), dict(IDENTITY, size_bytes=-1)):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                select_target(topology(), identity, 6423995392, ["/dev/sda2"])
        with self.assertRaises(ValueError):
            select_target(topology(), IDENTITY, 130034123776, ["/dev/sda2"])

    def test_fingerprint_rechecks_identity_between_discovery_and_privileged_write(self):
        fingerprint = ('PATH="/dev/sdc" TYPE="disk" TRAN="usb" SIZE="120034123776" '
                       'VENDOR="GIGABYTE" MODEL="GP-GSTFS31120GN" SERIAL="003987654321"')
        validate_fingerprint(fingerprint, "/dev/sdc", IDENTITY)
        for changed in (fingerprint.replace("003987654321", "different"),
                        fingerprint.replace("/dev/sdc", "/dev/sdd"),
                        fingerprint.replace('TRAN="usb"', 'TRAN="sata"')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_fingerprint(changed, "/dev/sdc", IDENTITY)


if __name__ == "__main__":
    unittest.main()
