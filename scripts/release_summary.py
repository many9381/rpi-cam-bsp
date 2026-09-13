#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml


BUILD_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
CHECKSUM_PATH_RE = re.compile(r"^images/[A-Za-z0-9][A-Za-z0-9._+-]*$")
UTC_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
H264_MODE = "libx264-1920x1080-30fps"
EXPECTED_IMAGES = {
    "rpi5-minimal": "rpi5-minimal-image-raspberrypi5.rootfs.wic.bz2",
    "rpi5-camera": "rpi5-camera-image-raspberrypi5.rootfs.wic.bz2",
}
CAMERA_EVIDENCE = {
    "rpi5-camera": "camera-test",
    "rpi5-camera-hailo": "camera-hailo-test",
}
COMMON_REQUIRED_MARKERS = (
    "qemu/COMPLETE",
    "qemu-test/PASS",
    "rpi5-minimal/COMPLETE",
    "flash/rpi5-minimal-PASS",
    "rpi5-test/PASS",
)
REQUIRED_MARKERS = COMMON_REQUIRED_MARKERS + (
    "rpi5-camera/COMPLETE",
    "flash/rpi5-camera-PASS",
    "camera-test/PASS",
)


def require_regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file: {path}")


def load_json(path: Path, label: str) -> dict[str, Any]:
    require_regular_file(path, label)
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def load_pins(root: Path) -> dict[str, str]:
    path = root / "kas/lock.yml"
    require_regular_file(path, "kas lock")
    try:
        with path.open(encoding="utf-8") as stream:
            lock = yaml.safe_load(stream)
        repositories = lock["overrides"]["repos"]
    except (OSError, UnicodeError, yaml.YAMLError, KeyError, TypeError) as error:
        raise ValueError(f"invalid kas lock: {path}") from error
    if not isinstance(repositories, dict) or not repositories:
        raise ValueError(f"invalid kas repository pins: {path}")

    pins: dict[str, str] = {}
    for name, data in repositories.items():
        if (
            not isinstance(name, str)
            or not REPOSITORY_RE.fullmatch(name)
            or not isinstance(data, dict)
        ):
            raise ValueError(f"invalid kas repository pin: {path}")
        commit = data.get("commit")
        if not isinstance(commit, str) or not GIT_SHA_RE.fullmatch(commit):
            raise ValueError(f"invalid kas repository commit for {name}")
        pins[name] = commit
    return pins


def load_revisions(path: Path) -> dict[str, str]:
    require_regular_file(path, "source revision manifest")
    revisions: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"invalid source revision manifest: {path}") from error
    for line in lines:
        fields = line.split()
        if len(fields) != 2:
            raise ValueError(f"invalid source revision line: {path}")
        name, commit = fields
        if (
            not REPOSITORY_RE.fullmatch(name)
            or not GIT_SHA_RE.fullmatch(commit)
        ):
            raise ValueError(f"invalid source revision line: {path}")
        if name in revisions:
            raise ValueError(f"duplicate source revision for {name}")
        revisions[name] = commit
    if not revisions:
        raise ValueError(f"source revision manifest is empty: {path}")
    return revisions


def image_checksum(path: Path, expected_filename: str) -> dict[str, str]:
    require_regular_file(path, "checksum file")
    entries: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"invalid checksum file: {path}") from error
    for line in lines:
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise ValueError(f"invalid checksum line: {path}")
        digest, filename = fields
        filename = filename.removeprefix("*")
        if (
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not CHECKSUM_PATH_RE.fullmatch(filename)
            or filename in entries
        ):
            raise ValueError(f"invalid checksum line: {path}")
        entries[filename] = digest

    wic_entries = {
        filename: digest
        for filename, digest in entries.items()
        if filename.endswith(".wic.bz2")
    }
    expected_path = f"images/{expected_filename}"
    if set(wic_entries) != {expected_path}:
        raise ValueError(
            f"checksum file must contain exactly {expected_path}: {path}"
        )
    return {
        "filename": expected_filename,
        "sha256": wic_entries[expected_path],
    }


def validate_identity(
    build_id: str,
    project_revision: str,
    completed_at: str,
) -> None:
    if not BUILD_ID_RE.fullmatch(build_id):
        raise ValueError("invalid build ID")
    try:
        datetime.strptime(build_id[:16], "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("invalid build ID timestamp") from error
    if not GIT_SHA_RE.fullmatch(project_revision):
        raise ValueError("project revision must be a full lowercase Git SHA")
    if not build_id.endswith(f"-{project_revision[:12]}"):
        raise ValueError("build ID does not match project revision")
    if not UTC_TIMESTAMP_RE.fullmatch(completed_at):
        raise ValueError("completion time must be a UTC RFC 3339 timestamp")
    try:
        datetime.strptime(completed_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError(
            "completion time must be a valid UTC RFC 3339 timestamp"
        ) from error


def validate_metadata(
    base: Path,
    profile: str,
    build_id: str,
    project_revision: str,
) -> None:
    metadata = load_json(
        base / profile / "manifests/build-metadata.json",
        f"{profile} build metadata",
    )
    if metadata.get("build_id") != build_id:
        raise ValueError(f"{profile} build ID mismatch")
    if metadata.get("project_revision") != project_revision:
        raise ValueError(f"{profile} project revision mismatch")
    if (
        profile in CAMERA_EVIDENCE
        and metadata.get("profile", "rpi5-camera") != profile
    ):
        raise ValueError(f"{profile} build metadata profile mismatch")


def validate_results(base: Path, build_id: str, profile: str) -> None:
    rpi_result = load_json(
        base / "rpi5-test/result.json",
        "Raspberry Pi acceptance result",
    )
    if (
        rpi_result.get("build_id") != build_id
        or rpi_result.get("result") != "PASS"
    ):
        raise ValueError("Raspberry Pi result mismatch")
    if rpi_result.get("reboots") != 3:
        raise ValueError("exactly three Raspberry Pi reboots are required")

    camera_result = load_json(
        base / CAMERA_EVIDENCE[profile] / "result.json",
        "camera acceptance result",
    )
    if (
        camera_result.get("build_id") != build_id
        or camera_result.get("result") != "PASS"
    ):
        raise ValueError("camera result mismatch")
    # Older standard capture evidence predates explicit profile recording.
    if camera_result.get("profile", "rpi5-camera") != profile:
        raise ValueError("camera profile mismatch")
    if camera_result.get("sensor") != "imx708":
        raise ValueError("camera sensor is not IMX708")
    if camera_result.get("lens_variant") != "wide-operator-verified":
        raise ValueError("Camera Module 3 Wide was not operator-confirmed")
    if camera_result.get("h264") != H264_MODE:
        raise ValueError("camera H.264 result does not use the approved mode")


def build_record(
    root: Path,
    build_id: str,
    project_revision: str,
    completed_at: str,
    profile: str = "rpi5-camera",
) -> dict[str, Any]:
    if profile not in CAMERA_EVIDENCE:
        raise ValueError("invalid camera profile")
    validate_identity(build_id, project_revision, completed_at)
    base = root / "artifacts" / build_id

    markers = (
        *COMMON_REQUIRED_MARKERS,
        f"{profile}/COMPLETE",
        f"flash/{profile}-PASS",
        f"{CAMERA_EVIDENCE[profile]}/PASS",
    )
    for marker in markers:
        require_regular_file(base / marker, f"required marker {marker}")

    for image_profile in ("rpi5-minimal", profile):
        validate_metadata(base, image_profile, build_id, project_revision)

    pins = load_pins(root)
    revisions = load_revisions(
        base / profile / "manifests/layer-revisions.txt"
    )
    if revisions != pins:
        raise ValueError("source revisions do not exactly match the kas lock")

    validate_results(base, build_id, profile)
    minimal_checksum = image_checksum(
        base / "rpi5-minimal/checksums/SHA256SUMS",
        EXPECTED_IMAGES["rpi5-minimal"],
    )
    camera_checksum = image_checksum(
        base / profile / "checksums/SHA256SUMS",
        EXPECTED_IMAGES["rpi5-camera"],
    )

    record = {
        "schema_version": 1,
        "build_id": build_id,
        "project_revision": project_revision,
        "source_revisions": {
            name: pins[name]
            for name in sorted(pins)
        },
        "images": {
            "rpi5_minimal": minimal_checksum,
            "rpi5_camera": camera_checksum,
        },
        "validation": {
            "qemu": "PASS",
            "rpi5": "PASS",
            "reboots": 3,
            "camera": "PASS",
            "sensor": "imx708",
            "lens_variant": "wide-operator-verified",
            "h264": H264_MODE,
        },
        "validation_completed_at": completed_at,
    }
    if profile == "rpi5-camera-hailo":
        record["schema_version"] = 2
        record["camera_profile"] = profile
        record["validation"]["hailo_inference"] = "NOT_TESTED"
    return record


def write_record(output: Path, record: dict[str, Any]) -> None:
    serialized = json.dumps(record, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.is_dir():
        raise ValueError(
            f"release record directory must be a regular directory: "
            f"{output.parent}"
        )
    with output.open("x", encoding="utf-8") as stream:
        stream.write(serialized)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a sanitized Raspberry Pi 5 release evidence record."
    )
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--profile", choices=tuple(CAMERA_EVIDENCE), default="rpi5-camera")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    if status:
        raise SystemExit(
            "tracked worktree must be clean before release summary generation"
        )
    project_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    completed_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    try:
        record = build_record(
            root,
            args.build_id,
            project_revision,
            completed_at,
            profile=args.profile,
        )
        suffix = "" if args.profile == "rpi5-camera" else f"-{args.profile}"
        output = (
            root / "artifacts/releases" / f"{args.build_id}{suffix}.json"
        )
        write_record(output, record)
    except FileExistsError as error:
        raise SystemExit(
            f"release record already exists: {error.filename}"
        ) from error
    except ValueError as error:
        raise SystemExit(f"release record rejected: {error}") from error

    print(output.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
