"""Personalize a mounted camera SSD without executing any target binary."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
import time

import yaml

from camera_identity import (openssl, private_directory, public_from_private,
                             regular_bytes, validate_host)
from codex_flash_auth import safe_path

CONFIG = "etc/camera-firmware/app.yaml"
PUBLIC = "usr/share/camera-firmware/integrity-public-key.pem"
MANIFEST = "etc/camera-firmware/integrity/manifest.yaml"
SIGNATURE = "etc/camera-firmware/integrity/manifest.sig"
RECEIPT = "etc/camera-firmware/provisioning.json"
CLOCK = "var/lib/systemd/timesync/clock"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def target(root, boot, stage, build):
    for path in (root, boot):
        if (not path.is_absolute() or path != path.resolve() or path == Path("/")
                or not os.path.ismount(path)):
            raise ValueError("Camera provisioning requires privately mounted SSD partitions")
        private_directory(path.parent, os.geteuid())
    private_directory(stage, os.geteuid())
    private = safe_path(stage, "integrity-private.pem")
    regular_bytes(private, os.geteuid(), private=True)
    public = regular_bytes(safe_path(root, PUBLIC))
    if public != public_from_private(private):
        raise ValueError("Installed camera image and signing key do not match")
    if safe_path(root, "etc/rpi5-build-id").read_text().strip() != build:
        raise ValueError("Camera image build ID mismatch")
    rows = [row.split(":") for row in safe_path(root, "etc/passwd").read_text().splitlines()
            if row.startswith("camera-firmware:")]
    if len(rows) != 1 or len(rows[0]) != 7 or rows[0][5] != "/var/lib/camera-firmware":
        raise ValueError("Camera service account missing or invalid")
    uid, gid = int(rows[0][2]), int(rows[0][3])
    if uid <= 0 or gid <= 0:
        raise ValueError("Camera service must use an unprivileged account")
    config = json.loads(regular_bytes(safe_path(stage, "device.json"), os.geteuid(), private=True))
    host = validate_host(config["public_host"])
    for path in (safe_path(root, "usr/bin/camera-firmware"), safe_path(boot, "kernel_2712.img")):
        if not path.is_file():
            raise ValueError("Camera binary or boot kernel is missing")
    return uid, gid, host, private


def directory(root, relative, uid, gid, mode):
    path = safe_path(root, relative, missing=True)
    path.mkdir(mode=mode, exist_ok=True)
    if not path.is_dir():
        raise ValueError("Camera provisioning directory is not a directory")
    os.chown(path, uid, gid)
    path.chmod(mode)
    return path


def publish(path, data, uid, gid, mode, *, mtime_ns=None):
    # No symlink/hardlink replacement, even when retrying an interrupted install.
    if os.path.lexists(path):
        regular_bytes(path)
    fd, temporary = tempfile.mkstemp(prefix=".provision-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchown(stream.fileno(), uid, gid)
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            if mtime_ns is not None:
                os.utime(stream.fileno(), ns=(mtime_ns, mtime_ns))
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def clock_target(root):
    # IDs belong to the target image, not the build PC's passwd database.
    rows = [row.split(":") for row in safe_path(root, "etc/passwd").read_text().splitlines()
            if row.startswith("systemd-timesync:")]
    if len(rows) != 1 or len(rows[0]) != 7:
        raise ValueError("Target time synchronization account missing or invalid")
    uid, gid = int(rows[0][2]), int(rows[0][3])
    if uid <= 0 or gid <= 0:
        raise ValueError("Time synchronization must use an unprivileged account")
    parent = safe_path(root, str(Path(CLOCK).parent), missing=True)
    if parent.exists() and not parent.is_dir():
        raise ValueError("Time synchronization state path is not a directory")
    path = safe_path(parent, "clock", missing=True)
    if path.exists() and regular_bytes(path) != b"":
        raise ValueError("Time synchronization clock must be an empty regular file")
    return path, uid, gid


def certificate_interval(certificate):
    dates = openssl("x509", "-in", certificate, "-noout", "-startdate", "-enddate",
                    "-dateopt", "iso_8601").decode().splitlines()
    values = dict(line.split("=", 1) for line in dates)
    return tuple(int(datetime.fromisoformat(values[name]).timestamp())
                 for name in ("notBefore", "notAfter"))


def check_clock_time(stamp_ns, certificate):
    not_before, not_after = certificate_interval(certificate)
    # Keep a full-second margin after notBefore and remain before expiry.
    # The conservative margin avoids depending on sub-second clock precision.
    if not not_before < stamp_ns // 1_000_000_000 < not_after:
        raise ValueError("Saved initial time falls outside the camera TLS certificate validity")


def seed_clock(root, certificate):
    path, uid, gid = clock_target(root)
    not_before, _ = certificate_interval(certificate)
    stamp_ns = max(time.time_ns(), (not_before + 1) * 1_000_000_000,
                   path.stat().st_mtime_ns if path.exists() else 0)
    check_clock_time(stamp_ns, certificate)
    directory(root, str(Path(CLOCK).parent), uid, gid, 0o755)
    # timesyncd restores CLOCK_REALTIME from this mtime before time-set.target.
    # Persist it before activating the app; do not claim that NTP synchronized.
    publish(path, b"", uid, gid, 0o644, mtime_ns=stamp_ns)
    verify_clock(root, certificate)


def verify_clock(root, certificate):
    path, uid, gid = clock_target(root)
    safe_path(root, CLOCK)
    info = path.stat()
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (uid, gid, 0o644):
        raise ValueError("Saved initial time ownership or permissions differ")
    check_clock_time(info.st_mtime_ns, certificate)


def sign_manifest(manifest, private, signature):
    openssl("pkeyutl", "-sign", "-rawin", "-inkey", private, "-in", manifest, "-out", signature)


def render_config(example, host):
    config = yaml.safe_load(example.read_text())
    authority = f"[{host}]" if host and ":" in host else host
    config["http"]["public_base_url"] = f"https://{authority}:8443" if host else ""
    if (not config["security"]["enabled"] or not config["http"]["tls"]["enabled"]
            or config["http"]["tls"]["allow_development_self_signed_tls"]
            or not config["secure_rtsp"]["client_auth"]["enabled"]):
        raise ValueError("Camera configuration example must retain security controls")
    return yaml.safe_dump(config, sort_keys=False).encode()


def install(root, boot, stage, build):
    root, boot, stage = Path(root), Path(boot), Path(stage)
    uid, gid, host, private = target(root, boot, stage, build)
    clock_target(root)
    config_path = safe_path(root, CONFIG, missing=True)
    if config_path.exists():
        # Upgrade an already provisioned SSD without regenerating any identity.
        _verify_materials(root, boot, stage, build)
        seed_clock(root, config_path.parent / "tls/device.crt")
        return
    config_bytes = render_config(safe_path(root, CONFIG + ".example"), host)
    # Validate every destination before generating or publishing secrets.
    paths = ("etc/camera-firmware/tls", "etc/camera-firmware/integrity", "var/lib/camera-firmware")
    for relative in paths:
        safe_path(root, relative, missing=True)
    owner = os.geteuid()  # root in the privileged SSD writer
    directory(root, "etc/camera-firmware", owner, gid, 0o750)
    tls = directory(root, paths[0], owner, gid, 0o750)
    integrity = directory(root, paths[1], owner, gid, 0o750)
    directory(root, paths[2], uid, gid, 0o700)
    directory(root, "var/lib/camera-firmware/security", uid, gid, 0o700)
    with tempfile.TemporaryDirectory(prefix="camera-material-", dir=stage) as temporary:
        temporary = Path(temporary)
        certificate, tls_key = temporary / "device.crt", temporary / "device.key"
        if host is None:
            # Bootstrap certificate identifies the device, without guessing a
            # DHCP address. It is self-signed, as in explicit-address installs.
            san = "DNS:camera.local"
        else:
            try:
                ipaddress.ip_address(host)
                san = f"IP:{host}"
            except ValueError:
                san = f"DNS:{host}"
        openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                "-nodes", "-days", "365", "-subj", "/CN=Raspberry Pi Camera",
                "-addext", f"subjectAltName={san}", "-addext", "basicConstraints=critical,CA:FALSE",
                "-addext", "keyUsage=critical,digitalSignature", "-addext", "extendedKeyUsage=serverAuth",
                "-keyout", tls_key, "-out", certificate)
        tls_key.chmod(0o600)
        seed_clock(root, certificate)
        session_key = (secrets.token_hex(30) + "\n").encode()
        manifest = {"schema_version": 1, "product": "camera-firmware",
                    "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "files": [
                        {"id": "configuration", "category": "configuration", "path": "/" + CONFIG,
                         "sha256": hashlib.sha256(config_bytes).hexdigest()},
                        {"id": "firmware", "category": "firmware", "path": "/usr/bin/camera-firmware",
                         "sha256": digest(safe_path(root, "usr/bin/camera-firmware"))},
                        {"id": "kernel", "category": "kernel", "path": "/boot/kernel_2712.img",
                         "sha256": digest(safe_path(boot, "kernel_2712.img"))}]}
        manifest_bytes = yaml.safe_dump(manifest, sort_keys=False).encode()
        manifest_file, signature = temporary / "manifest.yaml", temporary / "manifest.sig"
        manifest_file.write_bytes(manifest_bytes)
        sign_manifest(manifest_file, private, signature)
        openssl("pkeyutl", "-verify", "-pubin", "-inkey", root / PUBLIC,
                "-rawin", "-in", manifest_file, "-sigfile", signature)
        materials = {
            "tls/device.crt": (certificate.read_bytes(), uid, 0o644),
            "tls/device.key": (tls_key.read_bytes(), uid, 0o600),
            "srtp-session.hex": (session_key, uid, 0o600),
            "integrity/manifest.yaml": (manifest_bytes, owner, 0o640),
            "integrity/manifest.sig": (signature.read_bytes(), owner, 0o640),
        }
        receipt = {"schema_version": 1, "build_id": build, "public_host": host,
                   "sha256": {name: hashlib.sha256(value[0]).hexdigest() for name, value in materials.items()}}
        for name, (data, file_uid, mode) in materials.items():
            path = safe_path(config_path.parent, name, missing=True)
            publish(path, data, file_uid, gid, mode)
        publish(safe_path(root, RECEIPT, missing=True), (json.dumps(receipt, indent=2) + "\n").encode(),
                owner, gid, 0o640)
        # ConditionPathExists becomes true only after all prerequisites are durable.
        publish(config_path, config_bytes, owner, gid, 0o640)
    verify(root, boot, stage, build)


def _verify_materials(root, boot, stage, build):
    root, boot, stage = Path(root), Path(boot), Path(stage)
    uid, gid, host, _ = target(root, boot, stage, build)
    config_path = safe_path(root, CONFIG)
    receipt = json.loads(regular_bytes(safe_path(root, RECEIPT)))
    if receipt.get("build_id") != build or receipt.get("public_host") != host:
        raise ValueError("Camera provisioning receipt does not match this install")
    if config_path.read_bytes() != render_config(safe_path(root, CONFIG + ".example"), host):
        raise ValueError("Installed camera configuration differs from its provisioned configuration")
    permissions = {"app.yaml": (os.geteuid(), 0o640), "tls/device.crt": (uid, 0o644),
                   "tls/device.key": (uid, 0o600), "srtp-session.hex": (uid, 0o600),
                   "integrity/manifest.yaml": (os.geteuid(), 0o640),
                   "integrity/manifest.sig": (os.geteuid(), 0o640),
                   "provisioning.json": (os.geteuid(), 0o640)}
    for name, (expected_uid, mode) in permissions.items():
        path = safe_path(config_path.parent, name)
        raw = regular_bytes(path)
        info = path.stat()
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (expected_uid, gid, mode):
            raise ValueError("Camera provisioning file ownership or permissions differ")
        if name not in ("app.yaml", "provisioning.json") and receipt["sha256"].get(name) != hashlib.sha256(raw).hexdigest():
            raise ValueError("Camera TLS, SRTP or integrity material changed")
    manifest_path, signature = safe_path(root, MANIFEST), safe_path(root, SIGNATURE)
    openssl("pkeyutl", "-verify", "-pubin", "-inkey", root / PUBLIC,
            "-rawin", "-in", manifest_path, "-sigfile", signature)
    manifest = yaml.safe_load(manifest_path.read_text())
    for entry in manifest["files"]:
        path = (safe_path(boot, "kernel_2712.img") if entry["path"] == "/boot/kernel_2712.img"
                else safe_path(root, entry["path"].removeprefix("/")))
        if digest(path) != entry["sha256"]:
            raise ValueError("Provisioned firmware, configuration or kernel digest differs")
    key = config_path.parent / "tls/device.key"
    cert = config_path.parent / "tls/device.crt"
    if openssl("pkey", "-in", key, "-pubout") != openssl("x509", "-in", cert, "-pubkey", "-noout"):
        raise ValueError("Camera TLS key and certificate do not match")


def verify(root, boot, stage, build):
    _verify_materials(root, boot, stage, build)
    root = Path(root)
    verify_clock(root, root / "etc/camera-firmware/tls/device.crt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "verify"))
    parser.add_argument("--rootfs", type=Path, required=True)
    parser.add_argument("--boot", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--build-id", required=True)
    args = parser.parse_args()
    try:
        (install if args.command == "install" else verify)(args.rootfs, args.boot, args.identity, args.build_id)
    except (ValueError, OSError, KeyError, TypeError, yaml.YAMLError):
        parser.exit(1, "ERROR: camera provisioning failed; check the image, signing identity and private SSD mounts\n")
    print(f"Camera provisioning {args.command}: PASS")


if __name__ == "__main__":
    main()
