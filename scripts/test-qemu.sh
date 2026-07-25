#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

test -z "${UV_PROJECT_ENVIRONMENT:-}" || \
    rpi5_die "UV_PROJECT_ENVIRONMENT must be unset or empty"

[[ "${1:-}" == "--build-id" && $# -eq 2 ]] || \
    rpi5_die "Usage: $0 --build-id ID"
build_id="$2"
rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"

repo_root="$(rpi5_repo_root)"
current_revision="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
[[ "$build_id" == *"-$current_revision" ]] || \
    rpi5_die "build ID revision does not match HEAD $current_revision"

key="$repo_root/keys/rpi5_admin"
rpi5_validate_key_pair "$key"
rpi5_require_pass "$repo_root/artifacts/$build_id/qemu/COMPLETE" "QEMU build"

evidence="$repo_root/artifacts/$build_id/qemu-test"
[[ ! -e "$evidence/PASS" ]] || rpi5_die "QEMU PASS already exists for $build_id"
mkdir -p "$evidence"
rm -f "$evidence/guest-PASS"
if ss -H -ltn 'sport = :2222' | grep -q .; then
    rpi5_die "localhost port 2222 is already in use"
fi

export RPI5_ADMIN_SSH_PUBKEY
RPI5_ADMIN_SSH_PUBKEY="$(tr -d '\n' < "${key}.pub")"
export RPI5_BUILD_ID="$build_id"
export KAS_WORK_DIR="$repo_root/build/kas-work"
export KAS_BUILD_DIR="$KAS_WORK_DIR/build/qemu"

qemu_pid=""
rpi5_wait_qemu_group() {
    local timeout_seconds="$1"
    local deadline=$((SECONDS + timeout_seconds))
    while kill -0 -- "-$qemu_pid" 2>/dev/null; do
        (( SECONDS < deadline )) || return 1
        sleep 1
    done
    return 0
}

cleanup() {
    if [[ -n "$qemu_pid" ]]; then
        kill -- "-$qemu_pid" 2>/dev/null || true
        rpi5_wait_qemu_group 5 || true
        kill -KILL -- "-$qemu_pid" 2>/dev/null || true
        if ! kill -0 "$qemu_pid" 2>/dev/null; then
            wait "$qemu_pid" 2>/dev/null || true
        fi
        qemu_pid=""
    fi
}
trap cleanup EXIT INT TERM

printf '%s\n' "uv run --locked kas shell kas/qemuarm64-minimal.yml -c runqemu qemuarm64 rpi5-minimal-image nographic slirp" \
    > "$evidence/launch-command.txt"
cd "$repo_root"
setsid uv run --locked kas shell kas/qemuarm64-minimal.yml \
    -c 'runqemu qemuarm64 rpi5-minimal-image nographic slirp' \
    > "$evidence/console.log" 2>&1 &
qemu_pid="$!"

"$repo_root/scripts/test-qemu-guest.sh" \
    --build-id "$build_id" --host 127.0.0.1 --port 2222 \
    --timeout 180 --key "$key" --evidence-dir "$evidence"

rpi5_wait_qemu_group 30 || {
    rpi5_die "QEMU did not exit within 30 seconds after poweroff"
}
wait "$qemu_pid"
qemu_pid=""

[[ -f "$evidence/guest-PASS" ]] || rpi5_die "guest assertions did not pass"
mv "$evidence/guest-PASS" "$evidence/PASS"
printf 'PASS qemu build_id=%s\n' "$build_id"
