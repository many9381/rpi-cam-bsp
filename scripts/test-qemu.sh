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

rpi5_port_2222_listening() {
    local listeners=""
    listeners="$(ss -H -ltn 'sport = :2222')" || return 2
    [[ -n "$listeners" ]]
}

evidence="$repo_root/artifacts/$build_id/qemu-test"
[[ ! -e "$evidence/PASS" ]] || rpi5_die "QEMU PASS already exists for $build_id"
mkdir -p "$evidence"
rm -f "$evidence/guest-PASS"
port_state=0
rpi5_port_2222_listening || port_state=$?
case "$port_state" in
    0) rpi5_die "localhost port 2222 is already in use" ;;
    1) ;;
    *) rpi5_die "could not inspect localhost port 2222" ;;
esac

export RPI5_ADMIN_SSH_PUBKEY
RPI5_ADMIN_SSH_PUBKEY="$(tr -d '\n' < "${key}.pub")"
export RPI5_BUILD_ID="$build_id"
export KAS_WORK_DIR="$repo_root/build/kas-work"
export KAS_BUILD_DIR="$KAS_WORK_DIR/build/qemu"

qemu_pid=""
qemu_pgid=""
guest_check_pid=""
guest_check_pgid=""

rpi5_wait_process_group_gone() {
    local pgid="$1"
    local timeout_seconds="$2"
    local deadline=$((SECONDS + timeout_seconds))
    while kill -0 -- "-$pgid" 2>/dev/null; do
        (( SECONDS < deadline )) || return 1
        sleep 1
    done
    return 0
}

rpi5_wait_process_stopped() {
    local pid="$1"
    local timeout_seconds="$2"
    local deadline=$((SECONDS + timeout_seconds))
    local state=""
    while kill -0 "$pid" 2>/dev/null; do
        state="$(ps -o stat= -p "$pid" 2>/dev/null || true)"
        [[ "$state" == Z* ]] && return 0
        (( SECONDS < deadline )) || return 1
        sleep 1
    done
    return 0
}

rpi5_cleanup_process_group() {
    local leader_pid="$1"
    local pgid="$2"
    local leader_stopped=0

    kill -TERM -- "-$pgid" 2>/dev/null || true
    if rpi5_wait_process_stopped "$leader_pid" 5; then
        leader_stopped=1
    else
        kill -KILL -- "-$pgid" 2>/dev/null || true
        rpi5_wait_process_stopped "$leader_pid" 5 && leader_stopped=1
    fi
    (( leader_stopped )) || return 1

    wait "$leader_pid" 2>/dev/null || true

    if ! rpi5_wait_process_group_gone "$pgid" 5; then
        kill -KILL -- "-$pgid" 2>/dev/null || true
        rpi5_wait_process_group_gone "$pgid" 5 || return 1
    fi
    return 0
}

rpi5_wait_port_2222_gone() {
    local timeout_seconds="$1"
    local deadline=$((SECONDS + timeout_seconds))
    local port_state=0
    while :; do
        port_state=0
        rpi5_port_2222_listening || port_state=$?
        case "$port_state" in
            0)
                (( SECONDS < deadline )) || return 1
                sleep 1
                ;;
            1) return 0 ;;
            *) return 2 ;;
        esac
    done
}

cleanup() {
    local status=$?
    local cleanup_failed=0

    if [[ -n "$guest_check_pid" ]]; then
        if rpi5_cleanup_process_group "$guest_check_pid" "$guest_check_pgid"; then
            guest_check_pid=""
            guest_check_pgid=""
        else
            cleanup_failed=1
        fi
    fi
    if [[ -n "$qemu_pid" ]]; then
        if rpi5_cleanup_process_group "$qemu_pid" "$qemu_pgid" &&
                rpi5_wait_port_2222_gone 5; then
            qemu_pid=""
            qemu_pgid=""
        else
            cleanup_failed=1
        fi
    fi
    (( cleanup_failed == 0 )) || printf '%s\n' \
        "ERROR: QEMU cleanup could not confirm all processes and port 2222 were gone" >&2

    trap - EXIT
    if (( cleanup_failed && status == 0 )); then
        status=1
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf '%s\n' "uv run --locked kas shell kas/qemuarm64-minimal.yml -c runqemu qemuarm64 rpi5-minimal-image nographic slirp" \
    > "$evidence/launch-command.txt"
cd "$repo_root"
setsid uv run --locked kas shell kas/qemuarm64-minimal.yml \
    -c 'runqemu qemuarm64 rpi5-minimal-image nographic slirp' \
    > "$evidence/console.log" 2>&1 &
qemu_pid="$!"
qemu_pgid="$qemu_pid"

setsid timeout --foreground --kill-after=10s 240s \
    "$repo_root/scripts/test-qemu-guest.sh" \
    --build-id "$build_id" --host 127.0.0.1 --port 2222 \
    --timeout 180 --key "$key" --evidence-dir "$evidence" &
guest_check_pid="$!"
guest_check_pgid="$guest_check_pid"
wait "$guest_check_pid"
if ! rpi5_wait_process_group_gone "$guest_check_pgid" 1; then
    rpi5_die "QEMU guest checker left surviving descendants"
fi
guest_check_pid=""
guest_check_pgid=""

rpi5_wait_process_stopped "$qemu_pid" 30 || {
    rpi5_die "QEMU did not exit within 30 seconds after poweroff"
}
qemu_status=0
wait "$qemu_pid" || qemu_status=$?
(( qemu_status == 0 )) || exit "$qemu_status"
if ! rpi5_wait_process_group_gone "$qemu_pgid" 5; then
    rpi5_die "QEMU left surviving descendants after poweroff"
fi
if ! rpi5_wait_port_2222_gone 5; then
    rpi5_die "QEMU left localhost port 2222 in use after poweroff"
fi
qemu_pid=""
qemu_pgid=""

[[ -f "$evidence/guest-PASS" ]] || rpi5_die "guest assertions did not pass"
mv "$evidence/guest-PASS" "$evidence/PASS"
printf 'PASS qemu build_id=%s\n' "$build_id"
