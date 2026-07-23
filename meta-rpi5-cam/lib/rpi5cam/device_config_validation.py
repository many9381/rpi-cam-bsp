"""Validation for untrusted device configuration build variables."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
import re


_BUILD_ID_PATTERN = re.compile(
    r"^(?P<timestamp>[0-9]{8}T[0-9]{6}Z)-(?P<sha>[0-9a-f]{7,40})$"
)
_ECDSA_KEYS = {
    "ecdsa-sha2-nistp256": ("nistp256", 65),
    "ecdsa-sha2-nistp384": ("nistp384", 97),
    "ecdsa-sha2-nistp521": ("nistp521", 133),
}
_SUPPORTED_ALGORITHMS = {"ssh-ed25519", "ssh-rsa", *_ECDSA_KEYS}


def _read_ssh_string(
    blob: bytes,
    offset: int,
    field_name: str,
) -> tuple[bytes, int]:
    if len(blob) - offset < 4:
        raise ValueError(f"OpenSSH key has a truncated {field_name}")
    length = int.from_bytes(blob[offset : offset + 4], "big")
    start = offset + 4
    end = start + length
    if end > len(blob):
        raise ValueError(f"OpenSSH key has a truncated {field_name}")
    return blob[start:end], end


def _require_blob_end(blob: bytes, offset: int) -> None:
    if offset != len(blob):
        raise ValueError("OpenSSH key blob has trailing data")


def _positive_mpint(value: bytes, field_name: str) -> int:
    if not value or value[0] & 0x80:
        raise ValueError(f"OpenSSH RSA {field_name} must be positive")
    if len(value) > 1 and value[0] == 0 and not value[1] & 0x80:
        raise ValueError(f"OpenSSH RSA {field_name} is not canonical")
    integer = int.from_bytes(value, "big")
    if integer == 0:
        raise ValueError(f"OpenSSH RSA {field_name} must be positive")
    return integer


def _validate_ed25519(blob: bytes, offset: int) -> None:
    public_key, offset = _read_ssh_string(blob, offset, "public key")
    if len(public_key) != 32:
        raise ValueError("OpenSSH Ed25519 public key must be 32 bytes")
    _require_blob_end(blob, offset)


def _validate_rsa(blob: bytes, offset: int) -> None:
    exponent_bytes, offset = _read_ssh_string(blob, offset, "exponent")
    modulus_bytes, offset = _read_ssh_string(blob, offset, "modulus")
    exponent = _positive_mpint(exponent_bytes, "exponent")
    modulus = _positive_mpint(modulus_bytes, "modulus")
    if exponent < 3 or exponent % 2 == 0:
        raise ValueError("OpenSSH RSA exponent must be an odd integer")
    if modulus.bit_length() < 1024:
        raise ValueError("OpenSSH RSA modulus must be at least 1024 bits")
    _require_blob_end(blob, offset)


def _validate_ecdsa(algorithm: str, blob: bytes, offset: int) -> None:
    expected_curve, expected_point_length = _ECDSA_KEYS[algorithm]
    curve_bytes, offset = _read_ssh_string(blob, offset, "curve")
    point, offset = _read_ssh_string(blob, offset, "public point")
    try:
        curve = curve_bytes.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("OpenSSH ECDSA curve must be ASCII") from error
    if curve != expected_curve:
        raise ValueError("OpenSSH ECDSA curve does not match algorithm")
    if len(point) != expected_point_length or point[:1] != b"\x04":
        raise ValueError("OpenSSH ECDSA public point is malformed")
    _require_blob_end(blob, offset)


def validate_ssh_public_key(public_key: str) -> None:
    """Reject anything other than one supported OpenSSH public key."""

    if (
        not isinstance(public_key, str)
        or not public_key
        or public_key != public_key.strip()
        or any(character in public_key for character in "\r\n\x00")
    ):
        raise ValueError(
            "RPI5_ADMIN_SSH_PUBKEY must contain one OpenSSH public key"
        )

    fields = public_key.split(None, maxsplit=2)
    if len(fields) < 2 or fields[0] not in _SUPPORTED_ALGORITHMS:
        raise ValueError(
            "RPI5_ADMIN_SSH_PUBKEY uses an unsupported key algorithm"
        )
    algorithm, encoded_blob = fields[:2]
    try:
        blob = base64.b64decode(encoded_blob, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("OpenSSH public key blob is not valid base64") from error

    blob_algorithm, offset = _read_ssh_string(blob, 0, "algorithm")
    if blob_algorithm != algorithm.encode("ascii"):
        raise ValueError("OpenSSH key algorithm does not match key blob")

    if algorithm == "ssh-ed25519":
        _validate_ed25519(blob, offset)
    elif algorithm == "ssh-rsa":
        _validate_rsa(blob, offset)
    else:
        _validate_ecdsa(algorithm, blob, offset)


def validate_build_id(build_id: str) -> None:
    """Require a real UTC calendar timestamp and 7-40 lowercase hex SHA."""

    if not isinstance(build_id, str):
        raise ValueError("RPI5_BUILD_ID must be a string")
    match = _BUILD_ID_PATTERN.fullmatch(build_id)
    if match is None:
        raise ValueError(
            "RPI5_BUILD_ID must be UTC timestamp plus 7-40 lowercase hex SHA"
        )
    try:
        datetime.strptime(match.group("timestamp"), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError(
            "RPI5_BUILD_ID contains an invalid UTC timestamp"
        ) from error
