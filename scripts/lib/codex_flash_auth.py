"""Provision Codex credentials onto an installed SSD, never a build image."""

import argparse
import os
from pathlib import Path
import pwd
import stat
import tempfile

from codex_auth import read_auth, write_private_cache


def snapshot_auth(source_uid, source_file, output):
    """Freeze the invoking user's current login before erasing the SSD."""
    if source_uid < 0:
        raise ValueError("Invalid source user")
    source = Path(source_file) if source_file else Path(pwd.getpwuid(source_uid).pw_dir) / ".codex/auth.json"
    if not source.is_absolute():
        raise ValueError("Codex auth source must be an absolute path")
    raw = read_auth(source, owner_uid=source_uid)
    output = Path(output)
    parent = output.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise ValueError("Credential staging requires a private operator-owned directory")
    write_private_cache(output, raw)


def safe_path(root, relative, missing=False):
    """Reject symlinks under the private mount used by the flash process."""
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or ".." in parts:
        raise ValueError("Invalid target path")
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing and index == len(parts) - 1:
                return current
            raise ValueError("Required target path is missing") from None
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Target credential paths must not contain symlinks")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ValueError("Target parent is not a directory")
    return current


def target_account(rootfs, build_id):
    root = Path(rootfs)
    if (not root.is_absolute() or root != root.resolve() or root == Path("/")
            or not os.path.ismount(root)):
        raise ValueError("Credentials can only be restored onto the mounted SSD")
    # The flash script creates this parent with umask 077. Other users cannot
    # replace paths while root validates and personalizes the mounted image.
    parent = root.parent.stat()
    if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError("SSD mount must have a private operator-owned parent")
    identity = safe_path(root, "etc/rpi5-build-id")
    if not identity.is_file() or identity.read_text().strip() != build_id:
        raise ValueError("SSD build identity does not match the selected image")
    codex = safe_path(root, "usr/bin") / "codex"
    if codex.is_symlink():
        # The image recipe exposes one absolute package link. Resolve that
        # known target inside the mounted image, never against the host root.
        # Credential paths and every directory in the package stay link-free.
        if os.readlink(codex) != "/usr/lib/codex/bin/codex":
            raise ValueError("Unexpected Codex executable link in selected image")
        codex = safe_path(root, "usr/lib/codex/bin/codex")
    else:
        codex = safe_path(root, "usr/bin/codex")
    if not codex.is_file():
        raise ValueError("Selected image does not contain Codex")
    passwd = safe_path(root, "etc/passwd")
    rows = [line.split(":") for line in passwd.read_text().splitlines()
            if line.split(":", 1)[0] == "rpiadmin"]
    if len(rows) != 1 or len(rows[0]) != 7 or rows[0][5] != "/home/rpiadmin":
        raise ValueError("Image must contain one rpiadmin account with its expected home")
    try:
        uid, gid = int(rows[0][2]), int(rows[0][3])
    except ValueError:
        raise ValueError("Invalid target account identity") from None
    if uid <= 0 or gid <= 0:
        raise ValueError("Codex credentials require an unprivileged target account")
    home = safe_path(root, "home/rpiadmin")
    info = home.stat()
    if not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid) != (uid, gid):
        raise ValueError("Target home ownership does not match rpiadmin")
    return home, uid, gid


def install_auth(rootfs, source, build_id):
    raw = read_auth(source, owner_uid=os.geteuid())
    home, uid, gid = target_account(rootfs, build_id)
    directory = safe_path(home, ".codex", missing=True)
    directory.mkdir(mode=0o700, exist_ok=True)
    destination = safe_path(directory, "auth.json", missing=True)
    if destination.exists() and not destination.is_file():
        raise ValueError("Existing target credential path is not a regular file")
    directory.chmod(0o700)
    os.chown(directory, uid, gid)
    fd, temporary = tempfile.mkstemp(prefix=".auth-flash-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchown(stream.fileno(), uid, gid)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify_auth(rootfs, source, build_id):
    expected = read_auth(source, owner_uid=os.geteuid())
    home, uid, gid = target_account(rootfs, build_id)
    directory = safe_path(home, ".codex")
    destination = safe_path(directory, "auth.json")
    for path, mode in ((directory, 0o700), (destination, 0o600)):
        info = path.stat()
        if stat.S_IMODE(info.st_mode) != mode or (info.st_uid, info.st_gid) != (uid, gid):
            raise ValueError("Restored Codex credential ownership or permissions are incorrect")
    if read_auth(destination, owner_uid=uid) != expected:
        raise ValueError("Restored Codex credentials do not match the staged login")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--source-user", type=int, required=True)
    snapshot.add_argument("--source-file", type=Path)
    snapshot.add_argument("--output", type=Path, required=True)
    for name in ("install", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--rootfs", type=Path, required=True)
        command.add_argument("--auth-file", type=Path, required=True)
        command.add_argument("--build-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            snapshot_auth(args.source_user, args.source_file, args.output)
        else:
            action = install_auth if args.command == "install" else verify_auth
            action(args.rootfs, args.auth_file, args.build_id)
    except (ValueError, OSError, KeyError):
        # Never echo credential contents, parsed account fields or tracebacks.
        parser.exit(1, "ERROR: Codex auth validation failed; check the current host login, private file ownership and selected SSD image\n")
    print(f"Codex auth {args.command}: PASS")


if __name__ == "__main__":
    main()
