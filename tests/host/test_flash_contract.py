import os
from pathlib import Path
import tempfile
import unittest

from support import REPO_ROOT, read, run


class FlashContractTest(unittest.TestCase):
    def test_boot_mount_must_select_the_usb_ssd(self) -> None:
        cases = (
            ("/dev/sda1\t/boot\tvfat\tdefaults\t0\t0\n", True),
            ("# /dev/mmcblk0p1 /boot vfat defaults 0 0\n"
             "/dev/sda1 /boot vfat defaults 0 0\n", True),
            ("/dev/mmcblk0p1 /boot vfat defaults 0 0\n", False),
            ("/dev/root / auto defaults 1 1\n", False),
            ("/dev/sda1 /boot ext4 defaults 0 0\n", False),
            ("/dev/sda1 /boot vfat defaults 0 0\n"
             "/dev/mmcblk0p1 /boot vfat defaults 0 0\n", False),
        )
        with tempfile.TemporaryDirectory() as directory:
            fstab = Path(directory) / "fstab"
            for content, valid in cases:
                with self.subTest(content=content):
                    fstab.write_text(content)
                    result = run(
                        "bash", "-c", 'source "$1"; validate_usb_boot_fstab "$2"',
                        "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"), str(fstab),
                    )
                    self.assertEqual(result.returncode == 0, valid, result.stderr)

    def test_flash_profile_selects_correct_image_and_rejects_unknown_profile(self) -> None:
        """Catches a camera variant resolving to the minimal image."""
        for profile, expected_image in (
            ("rpi5-minimal", "rpi5-minimal-image-raspberrypi5.rootfs.wic.bz2"),
            ("rpi5-camera", "rpi5-camera-image-raspberrypi5.rootfs.wic.bz2"),
            ("rpi5-camera-hailo", "rpi5-camera-image-raspberrypi5.rootfs.wic.bz2"),
        ):
            with self.subTest(profile=profile):
                result = run(
                    "bash", "-c", 'source "$1"; flash_profile_image "$2"',
                    "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"), profile,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected_image)
        result = run(
            "bash", "-c", 'source "$1"; flash_profile_image "$2"',
            "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"), "rpi5-camera-other",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid profile", result.stderr)

    def test_camera_flash_profiles_require_selected_build_and_phase_one_without_qemu(self) -> None:
        """Catches Hailo flashing bypassing phase-one or using normal COMPLETE."""
        for profile in ("rpi5-camera", "rpi5-camera-hailo"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base = root / "artifacts/test-build"
                unrelated = base / "rpi5-minimal/COMPLETE"
                unrelated.parent.mkdir(parents=True)
                unrelated.touch()
                for marker, error in (
                    (f"{profile}/COMPLETE", f"{profile} build PASS marker missing"),
                    ("rpi5-test/PASS", "phase-1 hardware PASS marker missing"),
                ):
                    result = run(
                        "bash", "-c",
                        'source "$1"; require_flash_prerequisites "$2" test-build "$3"',
                        "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"),
                        str(root), profile,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(error, result.stderr)
                    path = base / marker
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
                result = run(
                    "bash", "-c",
                    'source "$1"; require_flash_prerequisites "$2" test-build "$3"',
                    "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"), str(root), profile,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_development_flash_accepts_image_without_qemu_or_hardware_evidence(self) -> None:
        for profile in ("rpi5-camera", "rpi5-camera-hailo"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base = root / "artifacts/test-build"
                command = (
                    'source "$1"; '
                    'require_flash_prerequisites "$2" test-build "$3" 1; '
                    'printf "bypassed=%s\\n" "$hardware_gate_bypassed"'
                )
                for marker, error in (
                    (f"{profile}/COMPLETE", f"{profile} build PASS marker missing"),
                ):
                    result = run(
                        "bash", "-c", command, "bash",
                        str(REPO_ROOT / "scripts/flash-ssd.sh"), str(root), profile,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(error, result.stderr)
                    path = base / marker
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
                result = run(
                    "bash", "-c", command, "bash",
                    str(REPO_ROOT / "scripts/flash-ssd.sh"), str(root), profile,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("bypassed=true", result.stdout)
                self.assertFalse((base / "rpi5-test/PASS").exists())

    def test_development_option_preserves_existing_hardware_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "artifacts/test-build"
            for marker in ("rpi5-camera-hailo/COMPLETE", "rpi5-test/PASS"):
                path = base / marker
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("existing evidence\n")
            result = run(
                "bash", "-c",
                'source "$1"; require_flash_prerequisites "$2" test-build '
                'rpi5-camera-hailo 1; printf "bypassed=%s\\n" "$hardware_gate_bypassed"',
                "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"), str(root),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("bypassed=false", result.stdout)
            self.assertEqual((base / "rpi5-test/PASS").read_text(), "existing evidence\n")

    def test_development_flag_is_an_explicit_cli_option(self) -> None:
        result = run("bash", "scripts/flash-ssd.sh", "--allow-unvalidated-hardware", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--allow-unvalidated-hardware", result.stdout)

    def test_flash_requires_all_safety_inputs(self) -> None:
        script = read("scripts/flash-ssd.sh")
        for required in (
            "--build-id",
            "--profile",
            "--device",
            "--confirm",
            "bmaptool copy",
            "lsblk --json --bytes --paths",
            "VENDOR",
            "fingerprint_before",
            "mount -o ro",
            "root=/dev/sda2",
            "blockdev --flushbufs",
            "transport",
            "size_bytes",
            "written_at",
        ):
            self.assertIn(required, script)

    def test_flash_has_no_dd_fallback(self) -> None:
        script = read("scripts/flash-ssd.sh")
        self.assertNotIn("dd if=", script)
        self.assertNotIn(" of=", script)

    def test_flash_script_is_valid_bash(self) -> None:
        result = run("bash", "-n", "scripts/flash-ssd.sh")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_spoofed_uv_executable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_root = root / "archive-root"
            payload = archive_root / "uv-x86_64-unknown-linux-gnu"
            payload.mkdir(parents=True)
            spoof = payload / "uv"
            archive = root / "spoof.tar.gz"
            marker = root / "SPOOF_EXECUTED"
            private = root / "private"
            private.mkdir(mode=0o700)
            spoof.write_text(
                "#!/usr/bin/env bash\n"
                ': > "${SPOOF_MARKER:?}"\n'
                "printf 'uv 0.11.31\\n'\n",
                encoding="utf-8",
            )
            spoof.chmod(0o755)
            tar_result = run(
                "tar",
                "--create",
                "--gzip",
                "--file",
                os.fspath(archive),
                "--directory",
                os.fspath(archive_root),
                "uv-x86_64-unknown-linux-gnu",
            )
            self.assertEqual(tar_result.returncode, 0, tar_result.stderr)
            command = (
                'source "$1"\n'
                'authenticate_uv_archive "$2" "$3" || exit 1\n'
                'uv_bin="$authenticated_uv_bin"\n'
                '"$uv_bin" --version\n'
            )
            result = run(
                "bash",
                "-c",
                command,
                "bash",
                str(REPO_ROOT / "scripts/flash-ssd.sh"),
                str(archive),
                str(private),
                env={"SPOOF_MARKER": os.fspath(marker)},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "authenticated uv archive checksum mismatch",
                result.stderr,
            )
            self.assertFalse(marker.exists(), "spoofed executable was run")

    def test_device_identity_change_is_rejected(self) -> None:
        command = (
            'source "$1"\n'
            'require_unchanged_device "SERIAL=USB1" "SERIAL=USB2" '
            '"after write"\n'
        )
        result = run(
            "bash",
            "-c",
            command,
            "bash",
            str(REPO_ROOT / "scripts/flash-ssd.sh"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target identity changed after write", result.stderr)

    def test_archive_authentication_ignores_untrusted_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_root = root / "archive-root"
            payload = archive_root / "uv-x86_64-unknown-linux-gnu"
            payload.mkdir(parents=True)
            spoof = payload / "uv"
            spoof.write_text(
                "#!/usr/bin/env bash\nprintf 'uv 0.11.31\\n'\n",
                encoding="utf-8",
            )
            spoof.chmod(0o755)
            archive = root / "spoof.tar.gz"
            tar_result = run(
                "tar",
                "--create",
                "--gzip",
                "--file",
                os.fspath(archive),
                "--directory",
                os.fspath(archive_root),
                "uv-x86_64-unknown-linux-gnu",
            )
            self.assertEqual(tar_result.returncode, 0, tar_result.stderr)

            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            marker = root / "FAKE_SHA256SUM_EXECUTED"
            fake_sha256sum = fake_bin / "sha256sum"
            fake_sha256sum.write_text(
                "#!/usr/bin/env bash\n"
                ': > "${PATH_MARKER:?}"\n'
                "exit 0\n",
                encoding="utf-8",
            )
            fake_sha256sum.chmod(0o755)
            private = root / "private"
            private.mkdir(mode=0o700)
            command = (
                'source "$1"\n'
                'authenticate_uv_archive "$2" "$3"\n'
            )
            result = run(
                "bash",
                "-c",
                command,
                "bash",
                str(REPO_ROOT / "scripts/flash-ssd.sh"),
                str(archive),
                str(private),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "PATH_MARKER": os.fspath(marker),
                },
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "authenticated uv archive checksum mismatch",
                result.stderr,
            )
            self.assertFalse(marker.exists(), "untrusted PATH command was run")

    def test_truncated_value_option_prints_usage(self) -> None:
        for option in ("--build-id", "--profile", "--device", "--confirm", "--expected-fingerprint"):
            with self.subTest(option=option):
                result = run("bash", "scripts/flash-ssd.sh", option)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Usage:", result.stderr)
                self.assertNotIn("unbound variable", result.stderr)

    def test_confirmed_identity_survives_setup_until_write(self) -> None:
        """A replacement during setup must not become an accepted baseline.

        Execute the real pre-write section with harmless shell functions in
        place of every device/privileged operation. Never run the full flasher.
        """
        script = read("scripts/flash-ssd.sh")
        start = script.index("lsblk --json --bytes --paths")
        finish = script.index("\nsync\n", start)
        phase = script[start:finish]
        setup = r'''
source "$1"
device=/dev/test-fixture
profile=test
flash_root="$3"
topology="$3/topology.json"
image=fixture-image
bmap=fixture-bmap
image_bytes=1
uv_bin=fixture-uv
helper=fixture-helper
protected=()
expected_fingerprint="$4"
uv_run_locked() { printf '{}\n'; }
lsblk() {
    case "$*" in
        *--json*) printf '{}\n' ;;
        *' -P '*)
            if [[ -f "$flash_root/fingerprint-seen" ]]; then
                printf '%s\n' "$TEST_FINGERPRINT_AFTER"
            else
                touch "$flash_root/fingerprint-seen"
                printf '%s\n' "$TEST_FINGERPRINT_BEFORE"
            fi ;;
        *) printf 'fixture-device\n' ;;
    esac
}
umount() { :; }
bmaptool() { printf 'simulated write\n' > "$flash_root/WRITE"; }
source "$2"
'''
        confirmed = 'SERIAL="USB1"'
        replacement = 'SERIAL="USB2"'
        for pin, before, after, writes in (
            (confirmed, confirmed, confirmed, True),
            (confirmed, replacement, replacement, False),
            (confirmed, confirmed, replacement, False),
            ("", replacement, replacement, True),
        ):
            with self.subTest(pin=pin, before=before, after=after):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    fragment = root / "pre-write.sh"
                    fragment.write_text(phase, encoding="utf-8")
                    result = run(
                        "bash", "-c", setup, "bash",
                        str(REPO_ROOT / "scripts/flash-ssd.sh"),
                        str(fragment), str(root), pin,
                        env={"TEST_FINGERPRINT_BEFORE": before,
                             "TEST_FINGERPRINT_AFTER": after},
                    )
                    self.assertEqual((root / "WRITE").exists(), writes, result.stderr)
                    self.assertEqual(result.returncode == 0, writes, result.stderr)
                    if not writes:
                        self.assertIn("target identity changed", result.stderr)

    def test_expected_fingerprint_option_is_literal_and_nonempty(self) -> None:
        # --help exits during parsing, before any privileged operation.
        result = run(
            "bash", "scripts/flash-ssd.sh", "--expected-fingerprint",
            'MODEL="USB SSD" SERIAL="USB1"', "--help",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--expected-fingerprint", result.stdout)
        result = run(
            "bash", "scripts/flash-ssd.sh", "--expected-fingerprint", "",
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Usage:", result.stderr)

    def test_privileged_uv_runs_locked_and_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_uv = root / "uv"
            fake_uv.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'args=%s\\n' \"$*\"\n"
                "printf 'UV_PYTHON=%s\\n' \"${UV_PYTHON-unset}\"\n",
                encoding="utf-8",
            )
            fake_uv.chmod(0o755)
            command = (
                'source "$1"\n'
                'uv_run_locked "$2" python -c pass\n'
            )
            result = run(
                "bash",
                "-c",
                command,
                "bash",
                str(REPO_ROOT / "scripts/flash-ssd.sh"),
                str(fake_uv),
                env={"UV_PYTHON": "/tmp/untrusted-python"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout.splitlines(),
                [
                    "args=run --locked --offline python -c pass",
                    "UV_PYTHON=unset",
                ],
            )


if __name__ == "__main__":
    unittest.main()
