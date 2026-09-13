#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

usage() {
    printf 'Usage: %s --build-id ID {qemu|rpi5-minimal|rpi5-camera|rpi5-camera-hailo} {checkout|layers|parse|build}\n' "$0"
}

test -z "${UV_PROJECT_ENVIRONMENT:-}" || \
    rpi5_die "UV_PROJECT_ENVIRONMENT must be unset or empty"

[[ "${1:-}" == "--build-id" && $# -eq 4 ]] || { usage >&2; exit 2; }
build_id="$2"
profile="$3"
action="$4"
rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID: $build_id"

case "$profile" in
    qemu)
        config="kas/qemuarm64-minimal.yml"
        machine="qemuarm64"
        image="rpi5-minimal-image"
        ;;
    rpi5-minimal)
        config="kas/rpi5-minimal.yml"
        machine="raspberrypi5"
        image="rpi5-minimal-image"
        ;;
    rpi5-camera)
        config="kas/rpi5-camera.yml"
        machine="raspberrypi5"
        image="rpi5-camera-image"
        ;;
    rpi5-camera-hailo)
        config="kas/rpi5-camera-hailo.yml"
        machine="raspberrypi5"
        image="rpi5-camera-image"
        ;;
    *) usage >&2; exit 2 ;;
esac

case "$action" in checkout|layers|parse|build) ;; *) usage >&2; exit 2 ;; esac

repo_root="$(rpi5_repo_root)"
current_revision="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
[[ "$build_id" == *"-$current_revision" ]] || \
    rpi5_die "build ID revision does not match HEAD $current_revision"

out="$repo_root/artifacts/$build_id/$profile"
[[ ! -e "$out/COMPLETE" ]] || rpi5_die "evidence already complete: $out"

if [[ "$action" == "build" && "$profile" != "qemu" ]]; then
    rpi5_require_pass "$repo_root/artifacts/$build_id/qemu-test/PASS" "QEMU"
fi
if [[ "$action" == "build" && ( "$profile" == "rpi5-camera" || "$profile" == "rpi5-camera-hailo" ) ]]; then
    rpi5_require_pass "$repo_root/artifacts/$build_id/rpi5-test/PASS" "phase-1 hardware"
fi

key_path="$repo_root/keys/rpi5_admin"
preflight_args=(--incremental --key "$key_path")
if [[ "${RPI5_CI_CONTAINER:-0}" == "1" ]]; then
    preflight_args+=(--container)
fi
"$repo_root/scripts/host-preflight.sh" "${preflight_args[@]}"

export RPI5_ADMIN_SSH_PUBKEY
RPI5_ADMIN_SSH_PUBKEY="$(tr -d '\n' < "${key_path}.pub")"
export RPI5_BUILD_ID="$build_id"
export KAS_WORK_DIR="$repo_root/build/kas-work"
export KAS_BUILD_DIR="$KAS_WORK_DIR/build/$profile"
mkdir -p "$KAS_WORK_DIR" "$KAS_BUILD_DIR" "$out"

log="$out/${action}.log"
run_logged() {
    set +e
    "$@" 2>&1 | tee "$log"
    local statuses=("${PIPESTATUS[@]}")
    set -e
    (( statuses[0] == 0 && statuses[1] == 0 )) || return 1
}

cd "$repo_root"
case "$action" in
    checkout) run_logged uv run --locked kas checkout "$config" ;;
    layers) run_logged uv run --locked kas shell "$config" -c 'bitbake-layers show-layers' ;;
    parse) run_logged uv run --locked kas shell "$config" -c 'bitbake -p' ;;
    build)
        run_logged uv run --locked kas build "$config"
        "$repo_root/scripts/collect-artifacts.sh" \
            --build-id "$build_id" --profile "$profile" \
            --config "$config" --machine "$machine" --image "$image"
        ;;
esac
