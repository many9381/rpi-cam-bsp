"""Host-only camera signing identity. No private input belongs in BitBake."""
import argparse
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

from codex_flash_auth import safe_path


def openssl(*args, data=None):
    result = subprocess.run(["/usr/bin/openssl", *map(str, args)], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValueError("OpenSSL camera identity operation failed")
    return result.stdout


def regular_bytes(path, owner=None, private=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536
                or (owner is not None and info.st_uid != owner)
                or stat.S_IMODE(info.st_mode) & 0o022
                or (private and stat.S_IMODE(info.st_mode) != 0o600)):
            raise ValueError("Invalid camera identity file ownership, type or permissions")
        return stream.read(65537)


def public_from_private(path):
    public = openssl("pkey", "-in", path, "-pubout")
    der = openssl("pkey", "-pubin", "-outform", "DER", data=public)
    if len(der) != 44 or not der.startswith(bytes.fromhex("302a300506032b6570032100")):
        raise ValueError("Camera integrity signing requires an Ed25519 key")
    return public


def validate_host(value):
    # No stable address is needed for direct HTTPS access over DHCP.
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ValueError("device.json needs a public_host IP address or DNS name")
    try:
        address = ipaddress.ip_address(value)
        if address.is_unspecified or address.is_multicast or "%" in value:
            raise ValueError("Invalid camera address")
        return str(address)
    except ValueError:
        labels = value.split(".")
        if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                   for label in labels) or re.fullmatch(r"[0-9.]+", value):
            raise ValueError("public_host must be an IP address or DNS name, without a URL or wildcard")
        return value.lower()


def private_directory(path, owner):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != owner
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("Camera identity directory must be owner-only (0700)")


def write_new(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def load_identity(repo, owner):
    directory = safe_path(Path(repo), "keys/camera-firmware")
    private_directory(directory, owner)
    private = safe_path(directory, "integrity-private.pem")
    regular_bytes(private, owner, private=True)
    public = regular_bytes(safe_path(directory, "integrity-public.pem"), owner)
    if public != public_from_private(private):
        raise ValueError("Camera signing public/private keys do not match")
    config = json.loads(regular_bytes(safe_path(directory, "device.json"), owner, private=True))
    if not isinstance(config, dict) or set(config) != {"public_host"}:
        raise ValueError("device.json must contain only public_host")
    return private, public, {"public_host": validate_host(config["public_host"])}


def prepare(repo):
    repo = Path(repo).resolve()
    keys = safe_path(repo, "keys", missing=True)
    keys.mkdir(mode=0o700, exist_ok=True)
    directory = safe_path(keys, "camera-firmware", missing=True)
    directory.mkdir(mode=0o700, exist_ok=True)
    private_directory(directory, os.getuid())
    lock = os.open(directory / ".identity.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        names = ("integrity-private.pem", "integrity-public.pem", "device.json")
        present = [os.path.lexists(directory / name) for name in names]
        if any(present):
            if not all(present):
                raise ValueError("Incomplete camera identity; restore its files instead of rotating the signing key")
            load_identity(repo, os.getuid())
            return
        with tempfile.TemporaryDirectory(prefix=".create-", dir=directory) as temporary:
            temporary = Path(temporary)
            private = temporary / names[0]
            openssl("genpkey", "-algorithm", "ED25519", "-out", private)
            private.chmod(0o600)
            write_new(temporary / names[1], public_from_private(private), 0o644)
            write_new(temporary / names[2], b'{"public_host": null}\n')
            for name in names:
                os.replace(temporary / name, directory / name)
    finally:
        os.close(lock)


def check_image(repo, image_public, owner):
    private, public, config = load_identity(repo, owner)
    if regular_bytes(image_public) != public:
        raise ValueError("Image signing key differs from the local key; rebuild the camera image before installing")
    return private, public, config


def stage(repo, image_public, output, owner):
    private, public, config = check_image(repo, image_public, owner)
    output = Path(output)
    private_directory(output.parent, os.geteuid())
    # Read only the invoking operator's identity, then recheck the frozen copy.
    raw = regular_bytes(private, owner, private=True)
    output.mkdir(mode=0o700)
    try:
        write_new(output / "integrity-private.pem", raw)
        write_new(output / "integrity-public.pem", public, 0o644)
        write_new(output / "device.json", (json.dumps(config) + "\n").encode())
        if public_from_private(output / "integrity-private.pem") != public:
            raise ValueError("Signing identity changed while preparing the SSD installation")
    except Exception:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check", "stage"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--image-public-key", type=Path)
    parser.add_argument("--source-user", type=int, default=os.getuid())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.repo)
        elif args.command == "check":
            check_image(args.repo, args.image_public_key, args.source_user)
        else:
            stage(args.repo, args.image_public_key, args.output, args.source_user)
    except (ValueError, OSError, TypeError):
        parser.exit(1, "ERROR: camera signing identity validation failed; check keys/camera-firmware and the selected image public key\n")
    print(f"Camera identity {args.command}: PASS")


if __name__ == "__main__":
    main()
