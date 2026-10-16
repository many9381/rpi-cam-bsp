from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from support import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts/lib"))
import camera_boot


class CameraBootTest(unittest.TestCase):
    def setUp(self):
        self.module = camera_boot
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.boot = Path(temporary.name)
        for relative in ("kernel_2712.img", "bcm2712-rpi-5-b.dtb", "overlays/imx708.dtbo"):
            path = self.boot / relative
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"unchanged boot artifact")
        (self.boot / "cmdline.txt").write_text("root=/dev/sda2 rootwait console=tty1\n")
        self.original = ("# keep comments\ndtoverlay=vc4-kms-v3d\n"
                         "dtparam=fan_temp0=50000\ndtoverlay=imx708\n")
        (self.boot / "config.txt").write_text(self.original)

    def test_repairs_camera_selection_preserving_other_boot_settings(self):
        changed = self.module.repair_config(self.boot)
        self.assertTrue(changed)
        self.assertEqual((self.boot / "config.txt").read_text(),
                         "# keep comments\ndtoverlay=vc4-kms-v3d\n"
                         "dtparam=fan_temp0=50000\ncamera_auto_detect=1\n")
        self.assertEqual((self.boot / "config.txt.before-camera-autodetect").read_text(),
                         self.original)
        self.assertEqual((self.boot / "kernel_2712.img").read_bytes(), b"unchanged boot artifact")
        self.assertFalse(self.module.repair_config(self.boot))
        self.assertEqual((self.boot / "config.txt.before-camera-autodetect").read_text(),
                         self.original)

    def test_disabled_auto_detection_and_explicit_cam0_are_normalized(self):
        self.assertEqual(self.module.auto_config(
            "camera_auto_detect=0\ndtoverlay=imx708,cam0\narm_64bit=1\n"),
            "arm_64bit=1\ncamera_auto_detect=1\n")

    def test_unrecognized_conditional_or_custom_camera_configs_fail_without_writing(self):
        for config in ("[pi5]\ndtoverlay=imx708\n", "include custom.txt\n",
                       "dtoverlay=imx708,vcm=off\n", "camera_auto_detect=maybe\n",
                       "dtoverlay=imx708\ndtparam=cam0\n",
                       "cmdline=other.txt\ndtoverlay=imx708\n",
                       "overlay_prefix=custom/\ndtoverlay=imx708\n",
                       "os_prefix=other-os/\ndtoverlay=imx708\n",
                       "kernel=other.img\ndtoverlay=imx708\n",
                       "device_tree_overlay=imx708\n",
                       "dtoverlay=imx708\ndevice_tree_param=cam0\n"):
            with self.subTest(config=config):
                (self.boot / "config.txt").write_text(config)
                with self.assertRaises(ValueError):
                    self.module.repair_config(self.boot)
                self.assertEqual((self.boot / "config.txt").read_text(), config)
                self.assertFalse((self.boot / "config.txt.before-camera-autodetect").exists())

    def test_missing_overlay_or_wrong_root_disk_is_rejected_before_write(self):
        for relative in ("overlays/imx708.dtbo", "cmdline.txt"):
            path = self.boot / relative
            saved = path.read_bytes()
            path.unlink()
            with self.assertRaises(ValueError):
                self.module.repair_config(self.boot)
            path.write_bytes(saved)
        (self.boot / "cmdline.txt").write_text("root=/dev/mmcblk0p2\n")
        with self.assertRaises(ValueError):
            self.module.repair_config(self.boot)
        self.assertEqual((self.boot / "config.txt").read_text(), self.original)

    def test_existing_different_backup_is_never_overwritten(self):
        backup = self.boot / "config.txt.before-camera-autodetect"
        backup.write_text("earlier original\n")
        with self.assertRaises(ValueError):
            self.module.repair_config(self.boot)
        self.assertEqual(backup.read_text(), "earlier original\n")
        self.assertEqual((self.boot / "config.txt").read_text(), self.original)

    def test_symlink_config_or_backup_is_rejected(self):
        for relative in ("config.txt", "config.txt.before-camera-autodetect"):
            with self.subTest(relative=relative):
                path = self.boot / relative
                path.unlink(missing_ok=True)
                path.symlink_to(self.boot / "kernel_2712.img")
                with self.assertRaises(ValueError):
                    self.module.repair_config(self.boot)
                self.assertEqual((self.boot / "kernel_2712.img").read_bytes(), b"unchanged boot artifact")
                path.unlink()
                (self.boot / "config.txt").write_text(self.original)

    def test_failed_atomic_replace_preserves_original_and_backup(self):
        with patch.object(self.module.os, "replace", side_effect=OSError("simulated IO failure")):
            with self.assertRaises(OSError):
                self.module.repair_config(self.boot)
        self.assertEqual((self.boot / "config.txt").read_text(), self.original)
        self.assertEqual((self.boot / "config.txt.before-camera-autodetect").read_text(), self.original)
        self.assertFalse((self.boot / ".config.txt.camera-autodetect.tmp").exists())

    def test_failed_unmount_never_recursively_deletes_the_mounted_boot_files(self):
        private = self.boot / "mount-private"
        private.mkdir()
        mounted = private / "boot"
        plan = {"device": "/dev/test-ssd", "fingerprint": "same",
                "target": {"mounted": []}}

        def run(*args):
            if args[0] == "lsblk":
                return "vfat"
            if args[:3] == ("mount", "-o", "ro,nodev,nosuid,noexec"):
                for relative in ("kernel_2712.img", "bcm2712-rpi-5-b.dtb",
                                 "overlays/imx708.dtbo", "cmdline.txt", "config.txt"):
                    target = mounted / relative
                    target.parent.mkdir(exist_ok=True)
                    shutil.copy2(self.boot / relative, target)
            if args[0] == "umount":
                raise subprocess.CalledProcessError(1, args)
            return ""

        with patch.object(self.module.os, "geteuid", return_value=0), \
             patch.object(self.module, "live_target_plan", return_value=plan), \
             patch.object(self.module.tempfile, "mkdtemp", return_value=str(private)), \
             patch.object(self.module.os.path, "ismount", return_value=True), \
             patch.object(self.module, "command", side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):
                self.module.repair_ssd(self.boot, "same")
        self.assertEqual((mounted / "kernel_2712.img").read_bytes(), b"unchanged boot artifact")
        self.assertEqual((mounted / "config.txt.before-camera-autodetect").read_text(), self.original)
        self.assertIn("camera_auto_detect=1", (mounted / "config.txt").read_text())

    def test_identity_change_stops_before_mount_or_write(self):
        with patch.object(self.module.os, "geteuid", return_value=0), \
             patch.object(self.module, "live_target_plan", return_value={"fingerprint": "changed"}), \
             patch.object(self.module, "command", side_effect=AssertionError("must not mount")):
            with self.assertRaisesRegex(ValueError, "identity changed"):
                self.module.repair_ssd(self.boot, "original")

    def test_runtime_failures_unmount_safely_and_preserve_failed_unmount_tree(self):
        import camera_runtime_repair as runtime
        plan = {"device": "/dev/test-ssd", "fingerprint": "same", "target": {"mounted": []}}
        for failure in ("inspect", "install", "verify", "umount"):
            with self.subTest(failure=failure):
                private = self.boot / ("runtime-" + failure)
                private.mkdir()
                mounted = set()
                unmounted = []

                def run(*args):
                    if args[0] == "lsblk":
                        return "ext4" if args[-1].endswith("2") else "vfat"
                    path = Path(args[-1])
                    if args[0] == "mount" and args[2].startswith(("ro,", "rw,")):
                        mounted.add(path)
                        if path.name == "boot":
                            for relative in ("kernel_2712.img", "bcm2712-rpi-5-b.dtb",
                                             "overlays/imx708.dtbo", "cmdline.txt", "config.txt"):
                                target = path / relative
                                target.parent.mkdir(exist_ok=True)
                                shutil.copy2(self.boot / relative, target)
                        else:
                            (path / "accounts-must-survive").write_bytes(b"account state")
                    elif args[0] == "umount":
                        if failure == "umount" and path.name == "root":
                            raise OSError("simulated root unmount failure")
                        unmounted.append(path.name)
                        mounted.remove(path)
                        # Simulate a successful unmount exposing the empty mountpoint.
                        for child in path.iterdir():
                            if child.is_dir():
                                shutil.rmtree(child)
                            else:
                                child.unlink()
                    return ""

                with patch.object(self.module.os, "geteuid", return_value=0), \
                        patch.object(self.module, "live_target_plan", return_value=plan), \
                        patch.object(self.module.tempfile, "mkdtemp", return_value=str(private)), \
                        patch.object(self.module.os.path, "ismount", side_effect=lambda p: p in mounted), \
                        patch.object(self.module, "command", side_effect=run), \
                        patch.object(runtime, "load", return_value={}), \
                        patch.object(runtime, "inspect_target", side_effect=OSError("inspection failed")
                                     if failure == "inspect" else None), \
                        patch.object(runtime, "install", return_value=None,
                                     side_effect=OSError("installation failed") if failure == "install" else None), \
                        patch.object(runtime, "verify", side_effect=OSError("verification failed")
                                     if failure == "verify" else None):
                    with self.assertRaises(OSError):
                        self.module.repair_ssd(self.boot, "same", self.boot / "payload")
                self.assertIn("boot", unmounted)
                if failure == "umount":
                    self.assertEqual((private / "root/accounts-must-survive").read_bytes(), b"account state")
                else:
                    self.assertIn("root", unmounted)
                    self.assertFalse(private.exists())

    def test_shell_repair_does_not_select_an_image_or_invoke_the_flasher(self):
        import json
        import os
        for relative in ("scripts/install-ssd.sh", "scripts/lib/common.sh"):
            target = self.boot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / relative, target)
        (self.boot / "scripts/lib/camera_boot.py").write_text(
            'import json,sys\nassert sys.argv[1] == "plan"\n'
            'print(json.dumps({"fingerprint": "registered-ssd"}))\n')
        fake_bin = self.boot / "bin"
        fake_bin.mkdir()
        sudo = fake_bin / "sudo"
        sudo.write_text('#!/usr/bin/env python3\nimport pathlib,json,sys\n'
                        'pathlib.Path("repair-args.json").write_text(json.dumps(sys.argv[1:]))\n')
        sudo.chmod(0o755)
        environment = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"])
        environment.pop("UV_PROJECT_ENVIRONMENT", None)
        for mode in ("--repair-camera-boot", "--repair-camera-runtime"):
            result = subprocess.run(["bash", "scripts/install-ssd.sh", mode],
                                    cwd=self.boot, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = json.loads((self.boot / "repair-args.json").read_text())
            self.assertIn(str(self.boot / "scripts/lib/camera_boot.py"), arguments)
            self.assertIn("apply", arguments)
            self.assertEqual(arguments[arguments.index("--expected-fingerprint") + 1], "registered-ssd")
            self.assertEqual("--runtime" in arguments, mode == "--repair-camera-runtime")
            self.assertFalse((self.boot / "artifacts").exists())


if __name__ == "__main__":
    unittest.main()
