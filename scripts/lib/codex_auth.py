"""Copy the current ChatGPT login to a trusted Pi, outside image builds."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_AUTH_BYTES = 65536

# Credentials arrive only on stdin. Verify the complete transfer before
# replacing auth.json, and do not change user configuration or project trust.
REMOTE_INSTALL = r'''
set -eu
umask 077
[ "$(id -un)" = "$2" ]
command -v codex >/dev/null
codex_dir="$HOME/.codex"
[ ! -L "$codex_dir" ]
mkdir -p "$codex_dir"
chmod 700 "$codex_dir"
auth_temporary="$(mktemp "$codex_dir/.auth-import.XXXXXXXX")"
trap 'rm -f "$auth_temporary"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
cat > "$auth_temporary"
actual="$(sha256sum "$auth_temporary")"
[ "${actual%% *}" = "$1" ] || {
    printf 'Authentication transfer checksum mismatch; previous login preserved.\n' >&2
    exit 1
}
chmod 600 "$auth_temporary"
mv -f "$auth_temporary" "$codex_dir/auth.json"
if ! codex login status >/dev/null 2>&1; then
    printf 'Auth file installed, but Codex did not recognize it. Check CODEX_HOME and credential-store settings.\n' >&2
    exit 1
fi
printf 'Codex login cache installed and recognized.\n'
'''


def read_auth(path, owner_uid=None):
    """Read only a private, bounded, refreshable ChatGPT credential file."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise ValueError("Cannot read a regular local Codex auth file; log in on this host first") from None
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Codex auth input must be a regular file with mode 0600")
        if owner_uid is not None and info.st_uid != owner_uid:
            raise ValueError("Codex auth input must belong to the selected user")
        raw = source.read(MAX_AUTH_BYTES + 1)
    if len(raw) > MAX_AUTH_BYTES:
        raise ValueError("Codex auth input exceeds 64 KiB")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError("Codex auth input is not valid JSON") from None
    if not isinstance(data, dict) or data.get("auth_mode") not in (None, "chatgpt"):
        raise ValueError("A cached ChatGPT login is required")
    tokens = data.get("tokens")
    if not isinstance(tokens, dict) or not all(
        isinstance(tokens.get(name), str) and tokens[name]
        for name in ("access_token", "refresh_token", "id_token", "account_id")
    ):
        raise ValueError("A complete, refreshable ChatGPT login is required")
    return raw


def write_private_cache(path, raw):
    path = Path(path)
    if path.parent.is_symlink():
        raise ValueError("Auth cache directory must not be a symlink")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix=".codex-auth-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as destination:
            destination.write(raw)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def remote_command(raw, user):
    return shlex.join(["sh", "-c", REMOTE_INSTALL, "codex-auth",
                       hashlib.sha256(raw).hexdigest(), user])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Pi IP address or hostname")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--key", type=Path, default=REPO_ROOT / "keys/rpi5_admin")
    parser.add_argument("--known-hosts", type=Path,
                        default=REPO_ROOT / ".state/codex-known-hosts")
    codex_directory = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--auth-file", type=Path, default=codex_directory / "auth.json")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]*", args.host) or not 1 <= args.port <= 65535:
        parser.error("Invalid SSH host or port")
    if not args.key.expanduser().is_file() or not args.known_hosts.expanduser().is_file():
        parser.error("SSH key and trusted known-hosts file must already exist")
    cache = REPO_ROOT / "keys/codex-auth.json"
    relative = str(cache.relative_to(REPO_ROOT))
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative],
                             cwd=REPO_ROOT, capture_output=True).returncode == 0
    ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", relative],
                             cwd=REPO_ROOT).returncode == 0
    if tracked or not ignored:
        parser.error("Local auth cache must be Git-ignored and untracked")
    try:
        raw = read_auth(args.auth_file.expanduser())
        write_private_cache(cache, raw)
    except (ValueError, OSError) as error:
        # All validation errors are deliberately independent of input values.
        parser.exit(1, f"ERROR: {error}\n")
    command = [
        "ssh", "-p", str(args.port), "-i", str(args.key.expanduser()),
        "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
        "-o", "PasswordAuthentication=no", "-o", "KbdInteractiveAuthentication=no",
        "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=10",
        "-o", "ServerAliveCountMax=2", "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={args.known_hosts.expanduser()}",
        f"rpiadmin@{args.host}", remote_command(raw, "rpiadmin"),
    ]
    result = subprocess.run(command, input=raw, capture_output=True)
    if result.returncode:
        # Do not relay arbitrary remote output into logs containing credentials.
        parser.exit(1, "ERROR: SSH provisioning or Codex login-status check failed; check the trusted host, key and target credential-store settings\n")
    print("Codex login installed for rpiadmin; private auth cache is Git-ignored.")


if __name__ == "__main__":
    main()
