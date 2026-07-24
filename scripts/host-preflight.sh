#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

usage() {
    printf 'Usage: %s [--initial|--incremental] [--key PATH]\n' "$0"
}

mode="--incremental"
key_path="$(rpi5_repo_root)/keys/rpi5_admin"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --initial|--incremental) mode="$1"; shift ;;
        --key) key_path="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

repo_root="$(rpi5_repo_root)"
cd "$repo_root"
minimum_disk_kib=20971520
[[ "$mode" == "--initial" ]] && minimum_disk_kib=146800640

[[ "$EUID" -ne 0 ]] || rpi5_die "BitBake must not run as root"
[[ "$(uname -m)" == "x86_64" ]] || rpi5_die "host architecture must be x86_64"

source /etc/os-release
[[ "$ID" == "ubuntu" && "$VERSION_ID" == "24.04" ]] || \
    rpi5_die "supported host is Ubuntu 24.04"
[[ "$(nproc)" -ge 4 ]] || rpi5_die "at least 4 logical CPUs are required"

memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
swap_kib="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
[[ "$memory_kib" -ge 33554432 ]] || rpi5_die "at least 32 GiB RAM is required"
[[ "$swap_kib" -ge 4194304 ]] || rpi5_die "at least 4 GiB swap is required"

free_kib="$(df -Pk "$repo_root" | awk 'NR == 2 {print $4}')"
[[ "$free_kib" -ge "$minimum_disk_kib" ]] || \
    rpi5_die "insufficient free space: ${free_kib} KiB"
[[ -w "$repo_root" ]] || rpi5_die "repository is not writable"

locale -a | grep -Eiq '^en_US\.(utf-?8|UTF-?8)$' || \
    rpi5_die "en_US.UTF-8 locale is required"

required_commands=(
    git tar make gcc python3 uv
    bmaptool qemu-system-aarch64
    ssh scp ssh-keygen ssh-keyscan ss
    avahi-resolve-host-name ping
    lsblk findmnt blockdev partprobe udevadm
    mount umount sha256sum file ffprobe
)
for required in "${required_commands[@]}"; do
    rpi5_require_cmd "$required"
done

version_ge() {
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

git_version="$(git --version | awk '{print $3}')"
tar_version="$(tar --version | awk 'NR == 1 {print $NF}')"
make_version="$(make --version | awk 'NR == 1 {print $3}')"
gcc_version="$(gcc -dumpfullversion -dumpversion)"
version_ge "$git_version" "1.8.3.1" || rpi5_die "Git is too old"
version_ge "$tar_version" "1.28" || rpi5_die "tar is too old"
version_ge "$make_version" "4.0" || rpi5_die "make is too old"
version_ge "$gcc_version" "8.0" || rpi5_die "GCC is too old"
uv_version="$(uv --version | awk '{print $2}')"
[[ "$uv_version" == "0.11.31" ]] || rpi5_die "uv must be version 0.11.31"
test -z "${UV_PROJECT_ENVIRONMENT:-}" || \
    rpi5_die "UV_PROJECT_ENVIRONMENT must be unset or empty"
uv lock --check || rpi5_die "uv.lock is stale"
test -d .venv || rpi5_die ".venv must be a directory"
test ! -L .venv || rpi5_die ".venv must not be a symlink"
test "$(realpath .venv)" = "$(pwd -P)/.venv" || \
    rpi5_die ".venv must be physically checkout-local"
uv run --locked python -c \
    'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; system = pathlib.Path("/usr/bin/python3.12").resolve(); assert pathlib.Path(sys.prefix).resolve() == expected; assert pathlib.Path(sys._base_executable).resolve() == system; assert sys.version_info[:2] == (3, 12)' ||
    rpi5_die "uv must run physical checkout-local system Python 3.12"
python_version="$(uv run --locked python -c 'import platform; print(platform.python_version())')"
version_ge "$python_version" "3.12" || rpi5_die "Python must be at least 3.12"
version_ge "3.12.999" "$python_version" || rpi5_die "Python must be below 3.13"
uv run --locked kas --version |
    grep -Eq '(^|[[:space:]])5\.4([[:space:]]|$)' ||
    rpi5_die "kas must be version 5.4"

rpi5_validate_key_pair "$key_path"

printf 'PASS host-preflight mode=%s cpus=%s memory_kib=%s swap_kib=%s free_kib=%s\n' \
    "$mode" "$(nproc)" "$memory_kib" "$swap_kib" "$free_kib"
