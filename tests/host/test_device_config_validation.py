from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from support import REPO_ROOT


VALIDATION_PATH = (
    REPO_ROOT / "meta-rpi5-cam/lib/rpi5cam/device_config_validation.py"
)


def load_validation_module():
    spec = importlib.util.spec_from_file_location(
        "device_config_validation",
        VALIDATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load validation helper: {VALIDATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeviceConfigValidationTest(unittest.TestCase):
    def generate_ed25519_public_key(self) -> str:
        ssh_keygen = shutil.which("ssh-keygen")
        self.assertIsNotNone(ssh_keygen, "host ssh-keygen is required")
        with tempfile.TemporaryDirectory() as temporary_directory:
            key_path = Path(temporary_directory) / "id_ed25519"
            result = subprocess.run(
                [
                    ssh_keygen,
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    "validation-test",
                    "-f",
                    str(key_path),
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return key_path.with_suffix(".pub").read_text(
                encoding="utf-8"
            ).rstrip("\n")

    def generate_ecdsa_public_key(self, bits: int) -> str:
        ssh_keygen = shutil.which("ssh-keygen")
        self.assertIsNotNone(ssh_keygen, "host ssh-keygen is required")
        with tempfile.TemporaryDirectory() as temporary_directory:
            key_path = Path(temporary_directory) / f"id_ecdsa_{bits}"
            result = subprocess.run(
                [
                    ssh_keygen,
                    "-q",
                    "-t",
                    "ecdsa",
                    "-b",
                    str(bits),
                    "-N",
                    "",
                    "-C",
                    "validation-test",
                    "-f",
                    str(key_path),
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return key_path.with_suffix(".pub").read_text(
                encoding="utf-8"
            ).rstrip("\n")

    def replace_ecdsa_point_with_zeroes(self, public_key: str) -> str:
        algorithm, encoded_blob, comment = public_key.split(" ", maxsplit=2)
        blob = bytearray(base64.b64decode(encoded_blob, validate=True))
        offset = 0
        for _field in ("algorithm", "curve"):
            field_length = int.from_bytes(blob[offset : offset + 4], "big")
            offset += 4 + field_length
        point_length = int.from_bytes(blob[offset : offset + 4], "big")
        point_start = offset + 4
        blob[point_start : point_start + point_length] = (
            b"\x04" + bytes(point_length - 1)
        )
        return (
            f"{algorithm} {base64.b64encode(blob).decode('ascii')} {comment}"
        )

    def test_accepts_real_openssh_public_key(self) -> None:
        validation = load_validation_module()

        validation.validate_ssh_public_key(
            self.generate_ed25519_public_key()
        )

    def test_accepts_injection_shaped_key_comment_as_inert_data(self) -> None:
        validation = load_validation_module()
        algorithm, blob, _comment = self.generate_ed25519_public_key().split(
            " ", maxsplit=2
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            marker = Path(temporary_directory) / "comment-was-executed"
            key = (
                f'{algorithm} {blob} comment"with quote '
                f"`touch {marker}` $(touch {marker})"
            )

            validation.validate_ssh_public_key(key)

            self.assertFalse(marker.exists())

    def test_rejects_truncated_base64_key_blob(self) -> None:
        validation = load_validation_module()

        with self.assertRaises(ValueError):
            validation.validate_ssh_public_key("ssh-ed25519 A")

    def test_rejects_algorithm_and_blob_mismatch(self) -> None:
        validation = load_validation_module()
        _algorithm, blob, comment = self.generate_ed25519_public_key().split(
            " ", maxsplit=2
        )

        with self.assertRaisesRegex(ValueError, "algorithm"):
            validation.validate_ssh_public_key(
                f"ssh-rsa {blob} {comment}"
            )

    def test_accepts_real_supported_ecdsa_points(self) -> None:
        validation = load_validation_module()

        for bits in (256, 384, 521):
            with self.subTest(bits=bits):
                validation.validate_ssh_public_key(
                    self.generate_ecdsa_public_key(bits)
                )

    def test_rejects_correctly_sized_off_curve_ecdsa_points(self) -> None:
        validation = load_validation_module()

        for bits in (256, 384, 521):
            with self.subTest(bits=bits):
                public_key = self.generate_ecdsa_public_key(bits)
                off_curve_key = self.replace_ecdsa_point_with_zeroes(
                    public_key
                )
                with self.assertRaisesRegex(ValueError, "curve"):
                    validation.validate_ssh_public_key(off_curve_key)

    def test_accepts_real_utc_timestamp_and_lowercase_sha(self) -> None:
        validation = load_validation_module()

        for build_id in (
            "20260228T235959Z-deadbee",
            f"20240229T000000Z-{'a' * 40}",
        ):
            with self.subTest(build_id=build_id):
                validation.validate_build_id(build_id)

    def test_rejects_invalid_build_identifiers(self) -> None:
        validation = load_validation_module()

        for build_id in (
            "20261340T996199Z-deadbee",
            "20260228T235959Z-ABCDEF0",
            "20260228T235959Z-deadbe",
            f"20260228T235959Z-{'a' * 41}",
        ):
            with self.subTest(build_id=build_id):
                with self.assertRaises(ValueError):
                    validation.validate_build_id(build_id)


if __name__ == "__main__":
    unittest.main()
