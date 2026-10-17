#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

usage() {
    printf 'Usage: %s [--build-id ID] {qemu|rpi5-minimal|rpi5-camera|rpi5-camera-hailo} {checkout|layers|parse|build}\n' "$0"
    cat <<'EOF'

ID identifies a build run: YYYYMMDDTHHMMSSZ-<12-character Git revision>.
Without --build-id, use the repository's .state/active-build-id.
The profile selects the image; for example, rpi5-camera-hailo.

Examples:
  ./scripts/build.sh rpi5-camera-hailo build
  ./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo build

Start a new build with BUILD_ID="$(./scripts/new-build-id.sh)" and
pass --build-id "$BUILD_ID". Continue using that ID for later profiles.
Image builds do not require QEMU or hardware PASS records.
Target GCC/C++ headers and build tools are excluded by default. For Pi-side
development, set RPI5_LOCAL_BUILDTOOLS=1 and use a fresh build ID.
EOF
}

argument_error() {
    printf 'ERROR: %s\n\n' "$*" >&2
    usage >&2
    exit 2
}

if [[ $# -eq 1 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
    usage
    exit 0
fi

test -z "${UV_PROJECT_ENVIRONMENT:-}" || \
    rpi5_die "UV_PROJECT_ENVIRONMENT must be unset or empty"

build_id=""
explicit_build_id="0"
if [[ "${1:-}" == "--build-id" ]]; then
    case "${2:-}" in
        qemu|rpi5-minimal|rpi5-camera|rpi5-camera-hailo)
            argument_error "$2 is a profile, not a build ID. Use: $0 $2 build (active ID), or: $0 --build-id ID $2 build."
            ;;
    esac
    [[ $# -eq 4 ]] || argument_error "--build-id requires ID, PROFILE and ACTION as separate arguments"
    build_id="$2"
    explicit_build_id="1"
    shift 2
fi
[[ $# -eq 2 ]] || argument_error "expected PROFILE and ACTION, optionally preceded by --build-id ID"
profile="$1"
action="$2"

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
    *) argument_error "unknown profile: $profile" ;;
esac

case "$action" in checkout|layers|parse|build) ;; *) argument_error "unknown action: $action" ;; esac

case "${RPI5_LOCAL_BUILDTOOLS:-0}" in
    0|1) ;;
    *) argument_error "RPI5_LOCAL_BUILDTOOLS must be 0 or 1" ;;
esac

repo_root="$(rpi5_repo_root)"
if [[ "$explicit_build_id" == "0" ]]; then
    active_build_file="$repo_root/.state/active-build-id"
    [[ -f "$active_build_file" && -r "$active_build_file" ]] || \
        argument_error "active build ID is missing or unreadable: $active_build_file; supply --build-id ID"
    build_id="$(< "$active_build_file")"
fi
rpi5_validate_build_id "$build_id" || \
    argument_error "invalid build ID: $build_id; expected YYYYMMDDTHHMMSSZ-<12-character Git revision>"
if [[ "$explicit_build_id" == "0" ]]; then
    printf 'Using active build ID: %s\n' "$build_id" >&2
fi
current_revision="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
[[ "$build_id" == *"-$current_revision" ]] || \
    rpi5_die "build ID revision does not match HEAD $current_revision"

out="$repo_root/artifacts/$build_id/$profile"
[[ ! -e "$out/COMPLETE" ]] || rpi5_die "evidence already complete: $out"

key_path="$repo_root/keys/rpi5_admin"
preflight_args=(--incremental --key "$key_path")
if [[ "${RPI5_CI_CONTAINER:-0}" == "1" ]]; then
    preflight_args+=(--container)
fi
"$repo_root/scripts/host-preflight.sh" "${preflight_args[@]}"

if [[ "$profile" == rpi5-camera* && ( "$action" == "parse" || "$action" == "build" ) ]]; then
    python3 "$repo_root/scripts/lib/camera_identity.py" prepare --repo "$repo_root"
fi

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
        python3 "$repo_root/scripts/lib/build_provenance.py" snapshot \
            --repo "$repo_root" --out "$out/provenance" --profile "$profile"
        run_logged uv run --locked kas build "$config"
        "$repo_root/scripts/collect-artifacts.sh" \
            --build-id "$build_id" --profile "$profile" \
            --config "$config" --machine "$machine" --image "$image"
        ;;
esac
