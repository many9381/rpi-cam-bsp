import os
from pathlib import Path
import tempfile
import unittest

from support import REPO_ROOT, read, run


class FlashContractTest(unittest.TestCase):
    def test_flash_requires_all_safety_inputs(self) -> None:
        script = read("scripts/flash-ssd.sh")
        for required in (
            "--build-id",
            "--profile",
            "--device",
            "--confirm",
            "qemu-test/PASS",
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
        for option in ("--build-id", "--profile", "--device", "--confirm"):
            with self.subTest(option=option):
                result = run("bash", "scripts/flash-ssd.sh", option)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Usage:", result.stderr)
                self.assertNotIn("unbound variable", result.stderr)

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
