#!/usr/bin/env bash
# Reusable development installer. Run as the normal build user, without sudo.
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

usage() {
    cat <<'EOF'
Usage: ./scripts/install-ssd.sh [--check] [--profile PROFILE] [--build-id ID]
       ./scripts/install-ssd.sh --repair-camera-boot [--check]
       ./scripts/install-ssd.sh --repair-camera-runtime [--check]

Defaults: latest completed rpi5-camera-hailo image and the USB SSD registered
in keys/ssd-target.json. The selected SSD's existing contents are replaced.
Run without sudo; only the disk-writing stage requests administrator access.

The installer checks the completed image and SSD, unmounts the SSD, writes the
image, mounts it for verification, Codex login restoration and camera app
provisioning, then unmounts it. Camera identity and public address come from
keys/camera-firmware; the image must contain the matching public key.
QEMU builds and tests are separate, optional commands. Development
installation may precede hardware acceptance. No image path, device name or checksum needs updating per build.

--check       Read-only preflight; no builds, downloads, mounts or disk writes.
--profile     rpi5-minimal, rpi5-camera, or rpi5-camera-hailo (default).
--build-id    Select an explicit completed build instead of the latest one.
--repair-camera-boot  Back up and repair only config.txt for camera auto-detection.
                      Preserves the installed root filesystem and accounts.
--repair-camera-runtime  Also install the validated Raspberry Pi libcamera payload
                         from .state/camera-runtime-repair; preserve accounts/config.
EOF
}

check_only=0
repair_camera_boot=0
repair_camera_runtime=0
profile=rpi5-camera-hailo
selected_id=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) check_only=1; shift ;;
        --repair-camera-boot) repair_camera_boot=1; shift ;;
        --repair-camera-runtime) repair_camera_boot=1; repair_camera_runtime=1; shift ;;
        --profile|--build-id)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            if [[ "$1" == --profile ]]; then profile="$2"; else selected_id="$2"; fi
            shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
[[ "$EUID" -ne 0 ]] || rpi5_die "Run without sudo; the installer requests it only for disk writing"
[[ -z "${UV_PROJECT_ENVIRONMENT:-}" ]] || rpi5_die "UV_PROJECT_ENVIRONMENT must be unset"

repo_root="$(rpi5_repo_root)"
cd "$repo_root"
umask 077
mkdir -p .state
exec 9>.state/install-ssd.lock
flock -n 9 || rpi5_die "Another SSD installation is already running"
plan_file="$(mktemp .state/install-plan.XXXXXXXX)"
download=""
cleanup() {
    rm -f -- "$plan_file"
    [[ -z "$download" ]] || rm -f -- "$download"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if (( repair_camera_boot )); then
    [[ -z "$selected_id" && "$profile" == rpi5-camera-hailo ]] || \
        rpi5_die "Camera boot repair cannot be combined with image/profile selection"
    repair_args=()
    (( ! repair_camera_runtime )) || repair_args+=(--runtime)
    python3 scripts/lib/camera_boot.py plan --repo "$repo_root" "${repair_args[@]}" > "$plan_file"
    fingerprint="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fingerprint"])' "$plan_file")"
    if (( repair_camera_runtime )); then
        printf 'Camera boot/runtime repair; accounts/config preserved; registered SSD: %s\n' "$fingerprint"
    else
        printf 'Camera boot repair only; registered SSD: %s\n' "$fingerprint"
    fi
    if (( check_only )); then
        printf 'PASS repair target preflight; boot config will be inspected when mounted for repair\n'
        exit 0
    fi
    sudo /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin /usr/bin/python3 \
        "$repo_root/scripts/lib/camera_boot.py" apply --repo "$repo_root" \
        --expected-fingerprint "$fingerprint" "${repair_args[@]}"
    exit 0
fi

plan_args=(--repo "$repo_root" --profile "$profile")
[[ -z "$selected_id" ]] || plan_args+=(--build-id "$selected_id")
python3 scripts/lib/install_ssd.py "${plan_args[@]}" > "$plan_file"
mapfile -t selected < <(python3 - "$plan_file" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1]))
for key in ("build_id", "device", "fingerprint", "directory"):
    print(plan[key])
PY
)
[[ "${#selected[@]}" == 4 ]] || rpi5_die "Invalid installation plan"
build_id="${selected[0]}"
device="${selected[1]}"
fingerprint="${selected[2]}"
image_directory="${selected[3]}"
printf 'Image: %s / %s\nSSD: %s\n' "$build_id" "$profile" "$fingerprint"
[[ ! -e "$repo_root/artifacts/$build_id/flash/$profile-PASS" ]] || \
    rpi5_die "This build/profile already has a completed installation record"
(cd "$image_directory" && sha256sum --check --strict checksums/SHA256SUMS)
if (( check_only )); then
    printf 'PASS install preflight; SSD has not been modified\n'
    exit 0
fi

uv_archive="$repo_root/.state/uv-release/uv-x86_64-unknown-linux-gnu.tar.gz"
uv_sha=8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa78821cf85091b4b
if [[ ! -e "$uv_archive" ]]; then
    mkdir -p "$(dirname "$uv_archive")"
    download="$(mktemp "$(dirname "$uv_archive")/uv-download.XXXXXXXX")"
    curl --fail --location --proto '=https' --tlsv1.2 \
        https://releases.astral.sh/github/uv/releases/download/0.11.31/uv-x86_64-unknown-linux-gnu.tar.gz \
        --output "$download"
    printf '%s  %s\n' "$uv_sha" "$download" | sha256sum --check --strict --status
    mv -- "$download" "$uv_archive"
    download=""
fi
[[ -f "$uv_archive" && ! -L "$uv_archive" ]] || rpi5_die "Invalid uv archive"
printf '%s  %s\n' "$uv_sha" "$uv_archive" | sha256sum --check --strict --status

# flash-ssd.sh rechecks this exact fingerprint after sudo/setup and before write.
printf 'Installing onto the registered SSD; keep it connected until PASS flash.\n'
sudo UV_ARCHIVE="$uv_archive" /usr/bin/bash "$repo_root/scripts/flash-ssd.sh" \
    --build-id "$build_id" --profile "$profile" --device "$device" \
    --confirm "ERASE:$device:$build_id" --expected-fingerprint "$fingerprint" \
    --allow-unvalidated-hardware
