"""Integrity checks for the locally supplied Hailo Debian archives."""

import hashlib
from pathlib import Path


def verify_sha256(path, expected):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"missing local Debian package: {path}")
    with path.open("rb") as package:
        actual = hashlib.file_digest(package, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")
