"""Read-only image and registered-SSD selection for install-ssd.sh."""

import argparse
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import subprocess

from block_device import bmap_image_size, parse_topology, validate_target
from codex_auth import read_auth
from camera_identity import check_image


BUILD_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}")
PROFILES = ("rpi5-minimal", "rpi5-camera", "rpi5-camera-hailo")


def select_image(repo, profile, build_id=None):
    if profile not in PROFILES:
        raise ValueError("Unsupported SSD image profile")
    artifacts = Path(repo) / "artifacts"
    if build_id is None:
        candidates = sorted(path.name for path in artifacts.iterdir()
                            if BUILD_ID.fullmatch(path.name)
                            and (path / profile / "COMPLETE").is_file())
        if not candidates:
            raise ValueError(f"No completed {profile} image; run scripts/build.sh first")
        build_id = candidates[-1]
    if not BUILD_ID.fullmatch(build_id):
        raise ValueError("Invalid build ID")
    directory = artifacts / build_id / profile
    if directory.resolve() != directory.absolute():
        raise ValueError("Image directory must not use symlinks")
    name = "rpi5-minimal-image" if profile == "rpi5-minimal" else "rpi5-camera-image"
    image = directory / "images" / f"{name}-raspberrypi5.rootfs.wic.bz2"
    bmap = image.with_suffix(".bmap")
    metadata_path = directory / "manifests/build-metadata.json"
    for path in (directory / "COMPLETE", image, bmap, metadata_path,
                 directory / "checksums/SHA256SUMS"):
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Selected image is incomplete: {path}")
    metadata = json.loads(metadata_path.read_text())
    expected = {"build_id": build_id, "profile": profile,
                "machine": "raspberrypi5", "image": name}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("Selected image metadata does not match its build/profile")
    return dict(expected, image=str(image), bmap=str(bmap), directory=str(directory))


def validate_identity(identity):
    if not isinstance(identity, dict):
        raise ValueError("SSD registration must be a JSON object")
    for key in ("serial", "model", "vendor"):
        value = identity.get(key)
        if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError(f"Registered SSD needs a nonempty {key}")
    size = identity.get("size_bytes")
    if type(size) is not int or size <= 0:
        raise ValueError("Registered SSD needs a positive size_bytes")


def select_target(payload, identity, image_bytes, protected):
    validate_identity(identity)
    nodes = parse_topology(payload)
    candidates = [node for node in nodes.values()
                  if node.type == "disk" and node.tran == "usb"
                  and node.serial == identity["serial"] and node.model == identity["model"]
                  and node.size == identity["size_bytes"]]
    if len(candidates) != 1:
        raise ValueError("Connect exactly one USB SSD matching keys/ssd-target.json")
    # Existing flash-ssd.sh unmounts the target after rechecking its identity.
    return validate_target(nodes, candidates[0].path, image_bytes, protected, allow_mounted=True)


def validate_fingerprint(fingerprint, device, identity):
    validate_identity(identity)
    if "\n" in fingerprint or "\r" in fingerprint:
        raise ValueError("Invalid SSD fingerprint")
    values = dict(field.split("=", 1) for field in shlex.split(fingerprint))
    expected = {"PATH": device, "TYPE": "disk", "TRAN": "usb",
                "SIZE": str(identity["size_bytes"]), "VENDOR": identity["vendor"],
                "MODEL": identity["model"], "SERIAL": identity["serial"]}
    if values != expected:
        raise ValueError("SSD identity changed during discovery")


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          env=dict(os.environ, LC_ALL="C")).stdout.strip()


def live_target_plan(repo, image_bytes=1):
    """Select the registered USB disk without needing an image or credentials."""
    repo = Path(repo).resolve()
    identity_path = repo / "keys/ssd-target.json"
    if not identity_path.is_file() or identity_path.is_symlink():
        raise ValueError("Register the intended SSD in keys/ssd-target.json first")
    identity = json.loads(identity_path.read_text())
    payload = json.loads(command("lsblk", "--json", "--bytes", "--paths", "-o",
                                 "NAME,KNAME,PATH,PKNAME,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL,MOUNTPOINTS"))
    protected = []
    for path in ("/", "/boot", "/home", str(repo)):
        source = command("findmnt", "-n", "-o", "SOURCE", "--target", path)
        if source.startswith("/dev/"):
            protected.append(os.path.realpath(source))
    target = select_target(payload, identity, image_bytes, protected)
    fingerprint = command("lsblk", "-dn", "-b", "-P", "-o",
                          "PATH,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL", target["path"])
    validate_fingerprint(fingerprint, target["path"], identity)
    if command("lsblk", "-dnro", "RO", target["path"]) != "0":
        raise ValueError("Selected SSD is read-only")
    return dict(device=target["path"], fingerprint=fingerprint, target=target)


def live_plan(repo, profile, build_id=None):
    repo = Path(repo).resolve()
    selected = select_image(repo, profile, build_id)
    target = live_target_plan(repo, bmap_image_size(Path(selected["bmap"])))
    if profile != "rpi5-minimal":
        check_image(repo, Path(selected["directory"]) / "manifests/camera-integrity-public.pem", os.getuid())
        # Validate only; credentials are staged by flash-ssd.sh just before writing.
        source = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".codex/auth.json"
        read_auth(source, owner_uid=os.getuid())
    return dict(selected, **target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--profile", choices=PROFILES, default="rpi5-camera-hailo")
    parser.add_argument("--build-id")
    args = parser.parse_args()
    try:
        plan = live_plan(args.repo, args.profile, args.build_id)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        # read_auth never includes credential values in its error messages.
        parser.exit(1, f"ERROR: {error}\n")
    print(json.dumps(plan))


if __name__ == "__main__":
    main()
