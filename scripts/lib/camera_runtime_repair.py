"""Offline libcamera 0.6 repair payloads; accounts and signed app files are excluded."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
from contextlib import contextmanager

from codex_flash_auth import safe_path

VERSION = "0.6.0+rpt20251202"
LIBRARIES = ("usr/lib/libcamera.so.0.6.0", "usr/lib/libcamera-base.so.0.6.0")
REQUIRED = (*LIBRARIES, "usr/lib/libcamera/ipa/ipa_rpi_pisp.so",
            "usr/lib/libcamera/ipa/ipa_rpi_pisp.so.sign",
            "usr/libexec/libcamera/raspberrypi_ipa_proxy",
            "usr/share/libcamera/ipa/rpi/pisp/imx708_wide.json")


def validate_library(path, soname):
    result = subprocess.run(
        ["readelf", "--file-header", "--dynamic", "--", str(path)],
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    output = result.stdout
    if (result.returncode or result.stderr
            or not re.search(r"Class:\s+ELF64\b", output)
            or not re.search(r"Data:\s+2's complement, little endian", output)
            or not re.search(r"Machine:\s+AArch64\b", output)
            or re.findall(r"\(SONAME\).*?\[([^]]+)\]", output) != [soname]):
        raise ValueError(f"Invalid AArch64 libcamera ABI: {path.name}")


@contextmanager
def deferred_interrupts():
    """Observe cancellation between atomic replacements, and finish any rollback."""
    pending = []
    previous = {}

    def requested(number, frame):
        pending.append(number)

    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, requested)
        yield pending
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def allowed(relative):
    path = Path(relative)
    return (not path.is_absolute() and ".." not in path.parts and str(path) == relative
            and (relative in LIBRARIES or relative.startswith(
                ("usr/lib/libcamera/", "usr/libexec/libcamera/", "usr/share/libcamera/"))))


def prepare(source, destination):
    for relative in LIBRARIES:
        validate_library(safe_path(source, relative), Path(relative).name.removesuffix(".0"))
    destination.mkdir(mode=0o700)
    files = {}
    for path in sorted(source.rglob("*")):
        relative = str(path.relative_to(source))
        if path.is_symlink() or not path.is_file() or not allowed(relative):
            continue
        data = safe_path(source, relative).read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode not in (0o644, 0o755):
            raise ValueError("Unexpected package file permissions")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files[relative] = {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode}
    if not set(REQUIRED).issubset(files):
        raise ValueError("Incomplete Raspberry Pi libcamera package")
    (destination / "manifest.json").write_text(json.dumps({"version": VERSION, "files": files}, indent=2) + "\n")


def load(payload):
    manifest = json.loads(safe_path(payload, "manifest.json").read_text())
    files = manifest.get("files")
    if manifest.get("version") != VERSION or not isinstance(files, dict) or not set(REQUIRED).issubset(files):
        raise ValueError("Invalid or incomplete camera runtime repair manifest")
    result = {}
    for relative, record in files.items():
        if not allowed(relative) or record.get("mode") not in (0o644, 0o755):
            raise ValueError("Runtime repair contains an unauthorized path or mode")
        source = safe_path(payload, relative)
        if not source.is_file():
            raise ValueError("Runtime repair requires regular package files")
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != record.get("sha256"):
            raise ValueError("Runtime repair payload checksum mismatch")
        if relative in LIBRARIES:
            validate_library(source, Path(relative).name.removesuffix(".0"))
        result[relative] = (data, record["mode"])
    return result


def target_path(root, relative):
    path = root
    for part in Path(relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Runtime target paths must not contain symlinks")
    return path


def inspect_target(root, files):
    profile = safe_path(root, "etc/rpi5-camera-profile").read_text().strip()
    if profile not in ("rpi5-camera", "rpi5-camera-hailo"):
        raise ValueError("SSD is not a camera image")
    for relative in LIBRARIES:
        library = safe_path(root, relative)
        if not library.is_file():
            raise ValueError("Installed libcamera ABI differs from repair payload")
        validate_library(library, library.name.removesuffix(".0"))
        soname = root / relative.removesuffix(".0")
        if not soname.is_symlink() or os.readlink(soname) != library.name:
            raise ValueError("Installed libcamera SONAME link is unexpected")
    original = {}
    for relative in files:
        path = target_path(root, relative)
        if path.exists():
            if not path.is_file():
                raise ValueError("Runtime target is not a regular file")
            original[relative] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        else:
            original[relative] = None
    return original


def replace_file(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".camera-runtime-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def verify(root, payload):
    files = load(payload)
    original = inspect_target(root, files)
    if original != files:
        raise ValueError("Installed camera runtime does not match repair payload")


def install(root, payload):
    files = load(payload)
    original = inspect_target(root, files)
    if original == files:
        return None
    backups = target_path(root, "var/backups/rpi5-camera-runtime")
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="libcamera-", dir=backups))
    for relative, content in original.items():
        if content is not None:
            path = backup / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content[0])
            path.chmod(content[1])
    (backup / "record.json").write_text(json.dumps({
        "new_version": VERSION, "original_files": {
            name: None if value is None else {"sha256": hashlib.sha256(value[0]).hexdigest(), "mode": value[1]}
            for name, value in original.items()}}, indent=2) + "\n")
    os.sync()
    with deferred_interrupts() as pending:
        changed = []
        try:
            for relative, (data, mode) in files.items():
                replace_file(target_path(root, relative), data, mode)
                changed.append(relative)
                if pending:
                    raise InterruptedError("Camera runtime repair cancelled; restoring original files")
            verify(root, payload)
            os.sync()
            if pending:
                raise InterruptedError("Camera runtime repair cancelled; restoring original files")
        except BaseException as error:
            failed = []
            for relative in reversed(changed):
                try:
                    path = target_path(root, relative)
                    if original[relative] is None:
                        path.unlink(missing_ok=True)
                    else:
                        # Same-filesystem rename needs no second copy of file data,
                        # so rollback still works when replacement ran out of space.
                        os.replace(backup / relative, path)
                except OSError:
                    failed.append(relative)
            os.sync()
            if failed:
                raise OSError(f"Runtime rollback incomplete: {', '.join(failed)}; "
                              f"originals retained in /{backup.relative_to(root)}") from error
            raise
    return backup
