#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/../scripts/lib/common.sh"
source "$(dirname "$0")/container.env"

usage() {
    printf 'Usage: %s {unit|qemu|rpi5-image}\n' "$0"
}

[[ $# -eq 1 ]] || { usage >&2; exit 2; }
case "$1" in
    unit|qemu|rpi5-image) stage="$1" ;;
    *) usage >&2; exit 2 ;;
esac

repo_root="$(rpi5_repo_root)"

ensure_uv() {
    if ! command -v uv >/dev/null 2>&1 ||
       [[ "$(uv --version | awk '{print $2}')" != "0.11.31" ]]; then
        mkdir -p "$repo_root/.state/uv-bin"
        curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
            env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR="$repo_root/.state/uv-bin" sh
        export PATH="$repo_root/.state/uv-bin:$PATH"
    fi
    [[ "$(uv --version | awk '{print $2}')" == "0.11.31" ]] ||
        rpi5_die "uv must be version 0.11.31"
    cd "$repo_root"
    test -z "${UV_PROJECT_ENVIRONMENT:-}"
    uv lock --check
    uv sync --locked
    test -d .venv
    test ! -L .venv
    test "$(realpath .venv)" = "$(pwd -P)/.venv"
    uv run --locked python -c \
        'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
}

ensure_uv
export RPI5_CI_CONTAINER=1
created_key="0"

cleanup() {
    if [[ "$created_key" == "1" ]]; then
        rm -f "$repo_root/keys/rpi5_admin" "$repo_root/keys/rpi5_admin.pub"
    fi
}
trap cleanup EXIT INT TERM

ensure_test_key() {
    mkdir -p "$repo_root/keys"
    if [[ -e "$repo_root/keys/rpi5_admin" ||
          -e "$repo_root/keys/rpi5_admin.pub" ]]; then
        rpi5_die "CI key paths must be absent before a build stage"
        return 1
    fi
    created_key="1"
    ssh-keygen -q -t ed25519 -N '' \
        -f "$repo_root/keys/rpi5_admin" -C ci-rpi5
    chmod 600 "$repo_root/keys/rpi5_admin"
    chmod 644 "$repo_root/keys/rpi5_admin.pub"
}

run_unit() {
    uv run --locked python -m unittest discover \
        -s tests/host -p 'test_*.py' -v
    while IFS= read -r script; do
        bash -n "$script"
    done < <(find scripts ci -type f -name '*.sh' -print | LC_ALL=C sort)
}

run_qemu_for_build_id() {
    local build_id="$1"
    "$repo_root/scripts/build.sh" --build-id "$build_id" qemu checkout
    "$repo_root/scripts/build.sh" --build-id "$build_id" qemu parse
    "$repo_root/scripts/build.sh" --build-id "$build_id" qemu build
    "$repo_root/scripts/test-qemu.sh" --build-id "$build_id"
}

case "$stage" in
    unit)
        run_unit
        ;;
    qemu)
        ensure_test_key
        build_id="$("$repo_root/scripts/new-build-id.sh")"
        run_qemu_for_build_id "$build_id"
        printf 'BUILD_ID=%s\n' "$build_id"
        ;;
    rpi5-image)
        ensure_test_key
        build_id="$("$repo_root/scripts/new-build-id.sh")"
        run_qemu_for_build_id "$build_id"
        "$repo_root/scripts/build.sh" \
            --build-id "$build_id" rpi5-minimal build
        printf 'BUILD_ID=%s\n' "$build_id"
        ;;
esac
