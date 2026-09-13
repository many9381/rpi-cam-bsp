#!/usr/bin/env bash
set -euo pipefail

PATH="/usr/sbin:/usr/bin:/sbin:/bin"
export PATH

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$script_dir/lib/common.sh"

readonly UV_RELEASE_SHA256="8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa78821cf85091b4b"
authenticated_uv_bin=""

authenticate_uv_archive() {
    local uv_archive="$1"
    local uv_private_dir="$2"
    local uv_archive_copy="$uv_private_dir/uv-release.tar.gz"
    local uv_extract_dir="$uv_private_dir/extract"
    local candidate_uv_bin="$uv_extract_dir/uv-x86_64-unknown-linux-gnu/uv"

    authenticated_uv_bin=""
    if [[ "$uv_archive" != /* || ! -f "$uv_archive" || -L "$uv_archive" ]]; then
        rpi5_die "UV_ARCHIVE must be an absolute regular non-symlink archive path" || true
        return 1
    fi
    if ! install -m 0600 -- "$uv_archive" "$uv_archive_copy"; then
        rpi5_die "failed to copy uv archive into private storage" || true
        return 1
    fi
    if [[ ! -f "$uv_archive_copy" || -L "$uv_archive_copy" ]]; then
        rpi5_die "private uv archive copy is not a regular file" || true
        return 1
    fi
    if [[ "$(stat -c %u "$uv_archive_copy")" != "$EUID" ]]; then
        rpi5_die "private uv archive copy ownership is invalid" || true
        return 1
    fi
    if ! printf '%s  %s\n' "$UV_RELEASE_SHA256" "$uv_archive_copy" |
        sha256sum --check --strict --status; then
        rpi5_die "authenticated uv archive checksum mismatch" || true
        return 1
    fi

    if ! install -d -m 0700 "$uv_extract_dir"; then
        rpi5_die "failed to create private uv extraction directory" || true
        return 1
    fi
    if ! tar --extract --file "$uv_archive_copy" \
        --directory "$uv_extract_dir" --gzip --no-same-owner \
        --no-same-permissions; then
        rpi5_die "failed to extract authenticated uv archive" || true
        return 1
    fi
    if [[ ! -f "$candidate_uv_bin" || -L "$candidate_uv_bin" ]]; then
        rpi5_die "authenticated archive is missing the expected uv executable" || true
        return 1
    fi
    if ! chmod 0700 "$candidate_uv_bin"; then
        rpi5_die "failed to restrict authenticated uv executable mode" || true
        return 1
    fi
    if [[ "$(stat -c %u "$candidate_uv_bin")" != "$EUID" ||
          "$(stat -c %a "$candidate_uv_bin")" != "700" ]]; then
        rpi5_die "authenticated uv executable ownership or mode is invalid" || true
        return 1
    fi
    authenticated_uv_bin="$candidate_uv_bin"
}

require_unchanged_device() {
    local expected="$1"
    local actual="$2"
    local phase="$3"

    if [[ -z "$expected" || "$actual" != "$expected" ]]; then
        rpi5_die "target identity changed $phase" || true
        return 1
    fi
}

uv_run_locked() {
    local uv_executable="$1"
    shift
    /usr/bin/env -i \
        HOME=/root \
        PATH="$PATH" \
        UV_NO_CONFIG=1 \
        "$uv_executable" run --locked --offline "$@"
}

flash_profile_image() {
    case "$1" in
        rpi5-minimal)
            printf '%s\n' 'rpi5-minimal-image-raspberrypi5.rootfs.wic.bz2'
            ;;
        rpi5-camera|rpi5-camera-hailo)
            printf '%s\n' 'rpi5-camera-image-raspberrypi5.rootfs.wic.bz2'
            ;;
        *) rpi5_die "invalid profile"; return 1 ;;
    esac
}

require_flash_prerequisites() {
    local artifact_root="$1/artifacts/$2"
    local selected_profile="$3"

    rpi5_require_pass "$artifact_root/qemu-test/PASS" "QEMU"
    rpi5_require_pass \
        "$artifact_root/$selected_profile/COMPLETE" "$selected_profile build"
    if [[ "$selected_profile" == "rpi5-camera" ||
          "$selected_profile" == "rpi5-camera-hailo" ]]; then
        rpi5_require_pass "$artifact_root/rpi5-test/PASS" "phase-1 hardware"
    fi
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    return 0
fi

usage() {
    printf 'Usage: sudo UV_ARCHIVE=/absolute/path/to/uv-release.tar.gz %s --build-id ID --profile {rpi5-minimal|rpi5-camera|rpi5-camera-hailo} --device /dev/DEVICE --confirm ERASE:/dev/DEVICE:ID\n' "$0"
}

build_id=""
profile=""
device=""
confirmation=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-id)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            build_id="$2"
            shift 2
            ;;
        --profile)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            profile="$2"
            shift 2
            ;;
        --device)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            device="$2"
            shift 2
            ;;
        --confirm)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            confirmation="$2"
            shift 2
            ;;
        --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

[[ "$EUID" -eq 0 ]] || \
    rpi5_die "flash requires root for the selected device only"
[[ -z "${UV_PROJECT_ENVIRONMENT:-}" ]] || \
    rpi5_die "UV_PROJECT_ENVIRONMENT must be unset for privileged flashing"
rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"
image_name="$(flash_profile_image "$profile")"
[[ "$device" == /dev/* ]] || \
    rpi5_die "device must be an explicit /dev path"
[[ "$confirmation" == "ERASE:$device:$build_id" ]] || \
    rpi5_die "confirmation must exactly match ERASE:$device:$build_id"

repo_root="$(rpi5_repo_root)"
cd "$repo_root"
[[ -d .venv && ! -L .venv ]] || \
    rpi5_die "privileged uv requires a physical checkout-local .venv"
[[ "$(realpath .venv)" == "$repo_root/.venv" ]] || \
    rpi5_die "privileged uv environment resolves outside the checkout"
uv_archive="${UV_ARCHIVE:-}"
[[ "$uv_archive" = /* && -f "$uv_archive" && ! -L "$uv_archive" ]] || \
    rpi5_die "UV_ARCHIVE must be an absolute regular non-symlink archive path"
umask 077
uv_private_dir=""
cleanup_uv() {
    if [[ "${uv_private_dir:-}" =~ ^/var/tmp/rpi5-flash-uv\.[A-Za-z0-9]{8}$ ]] &&
       [[ -d "$uv_private_dir" && ! -L "$uv_private_dir" ]] &&
       [[ "$(stat -c %u "$uv_private_dir")" == "0" ]]; then
        find "$uv_private_dir" -xdev -depth -delete
    fi
    uv_private_dir=""
}
uv_private_dir="$(mktemp -d /var/tmp/rpi5-flash-uv.XXXXXXXX)"
trap cleanup_uv EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
chown root:root "$uv_private_dir"
chmod 0700 "$uv_private_dir"
[[ -d "$uv_private_dir" && ! -L "$uv_private_dir" ]] || \
    rpi5_die "private uv directory is invalid"
[[ "$(stat -c %u "$uv_private_dir")" == "0" ]] || \
    rpi5_die "private uv directory is not root-owned"

authenticate_uv_archive "$uv_archive" "$uv_private_dir" || exit 1
uv_bin="$authenticated_uv_bin"
[[ "$("$uv_bin" --version | awk '{print $2}')" == "0.11.31" ]] || \
    rpi5_die "authenticated uv executable must be version 0.11.31"
uv_run_locked "$uv_bin" python -c \
    'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
profile_root="$repo_root/artifacts/$build_id/$profile"
flash_root="$repo_root/artifacts/$build_id/flash"
flash_marker="$flash_root/${profile}-PASS"
[[ ! -e "$flash_marker" ]] || \
    rpi5_die "flash PASS already exists for $profile"
mkdir -p "$flash_root"
require_flash_prerequisites "$repo_root" "$build_id" "$profile"
image="$profile_root/images/$image_name"
bmap="${image%.bz2}.bmap"
[[ -f "$image" && -f "$bmap" ]] || \
    rpi5_die "Wic image or bmap is missing"
(
    cd "$profile_root"
    sha256sum -c checksums/SHA256SUMS
)

helper="$repo_root/scripts/lib/block_device.py"
image_bytes="$(
    uv_run_locked "$uv_bin" python "$helper" \
        bmap-size --bmap "$bmap"
)"
temporary="$(mktemp -d /tmp/rpi5-flash.XXXXXX)"
topology="$temporary/lsblk.json"
boot_mount="$temporary/boot"
root_mount="$temporary/root"
mkdir "$boot_mount" "$root_mount"

cleanup() {
    mountpoint -q "$root_mount" && umount "$root_mount" || true
    mountpoint -q "$boot_mount" && umount "$boot_mount" || true
    rm -f "$topology"
    rmdir "$root_mount" "$boot_mount" "$temporary" 2>/dev/null || true
    cleanup_uv
}
trap cleanup EXIT

protected=()
for protected_path in / /boot /home "$repo_root"; do
    source_device="$(
        findmnt -n -o SOURCE --target "$protected_path" 2>/dev/null || true
    )"
    if [[ "$source_device" == /dev/* ]]; then
        protected+=(--protected "$(readlink -f "$source_device")")
    fi
done

lsblk --json --bytes --paths \
    -o NAME,KNAME,PATH,PKNAME,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL,MOUNTPOINTS \
    > "$topology"
metadata="$(
    uv_run_locked "$uv_bin" python "$helper" validate \
        --topology "$topology" --target "$device" \
        --image-bytes "$image_bytes" "${protected[@]}" --allow-mounted
)"
fingerprint_before="$(
    LC_ALL=C lsblk -dn -b -P \
        -o PATH,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL "$device"
)"
{
    printf 'metadata=%s\n' "$metadata"
    printf 'fingerprint=%s\n' "$fingerprint_before"
    lsblk --bytes --paths \
        -o NAME,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL,MOUNTPOINTS "$device"
} | tee "$flash_root/${profile}-selected-device.log"

mapfile -t mounted < <(
    uv_run_locked "$uv_bin" python "$helper" mounts \
        --topology "$topology" --target "$device"
)
for mounted_device in "${mounted[@]}"; do
    umount "$mounted_device"
done

lsblk --json --bytes --paths \
    -o NAME,KNAME,PATH,PKNAME,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL,MOUNTPOINTS \
    > "$topology"
fingerprint_after="$(
    LC_ALL=C lsblk -dn -b -P \
        -o PATH,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL "$device"
)"
require_unchanged_device \
    "$fingerprint_before" "$fingerprint_after" "before write"
uv_run_locked "$uv_bin" python "$helper" validate \
    --topology "$topology" --target "$device" \
    --image-bytes "$image_bytes" "${protected[@]}" >/dev/null

bmaptool copy --bmap "$bmap" "$image" "$device"
sync
blockdev --rereadpt "$device"
udevadm settle --timeout=30

boot_partition="$(
    uv_run_locked "$uv_bin" python "$helper" partition \
        --device "$device" --number 1
)"
root_partition="$(
    uv_run_locked "$uv_bin" python "$helper" partition \
        --device "$device" --number 2
)"
[[ -b "$boot_partition" && -b "$root_partition" ]] || \
    rpi5_die "expected two partitions after flashing"
[[ "$(lsblk -n -o FSTYPE "$root_partition")" == "ext4" ]] || \
    rpi5_die "root partition is not ext4"

mount -o ro "$boot_partition" "$boot_mount"
[[ -f "$boot_mount/config.txt" ]] || rpi5_die "config.txt missing"
[[ -f "$boot_mount/cmdline.txt" ]] || rpi5_die "cmdline.txt missing"
grep -Eq \
    '(^|[[:space:]])root=/dev/sda2([[:space:]]|$)' \
    "$boot_mount/cmdline.txt" || \
    rpi5_die "boot command line does not select /dev/sda2"
[[ -f "$boot_mount/kernel_2712.img" ]] || \
    rpi5_die "Pi 5 kernel missing"
find "$boot_mount" -name bcm2712-rpi-5-b.dtb -print -quit |
    grep -q . || rpi5_die "Pi 5 device tree missing"
umount "$boot_mount"

mount -o ro "$root_partition" "$root_mount"
[[ "$(cat "$root_mount/etc/rpi5-build-id")" == "$build_id" ]] || \
    rpi5_die "root filesystem build ID mismatch"
umount "$root_mount"

sync
blockdev --flushbufs "$device"
fingerprint_final="$(
    LC_ALL=C lsblk -dn -b -P \
        -o PATH,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL "$device"
)"
require_unchanged_device \
    "$fingerprint_before" "$fingerprint_final" "after write"
serial="$(lsblk -dn -o SERIAL "$device" | tr -cd 'A-Za-z0-9._-')"
[[ -n "$serial" ]] || serial="unknown-serial"
vendor="$(lsblk -dn -o VENDOR "$device" | tr -cd 'A-Za-z0-9._ -')"
model="$(lsblk -dn -o MODEL "$device" | tr -cd 'A-Za-z0-9._ -')"
transport="$(lsblk -dn -o TRAN "$device" | tr -cd 'A-Za-z0-9._-')"
size_bytes="$(lsblk -dn -b -o SIZE "$device" | tr -cd '0-9')"
[[ "$transport" == "usb" && "$size_bytes" =~ ^[1-9][0-9]*$ ]] || \
    rpi5_die "target identity became invalid after write"
written_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '{"build_id":"%s","profile":"%s","device":"%s","transport":"%s","size_bytes":%s,"vendor":"%s","model":"%s","serial":"%s","image_sha256":"%s","written_at":"%s"}\n' \
    "$build_id" "$profile" "$device" "$transport" "$size_bytes" \
    "$vendor" "$model" "$serial" \
    "$(sha256sum "$image" | awk '{print $1}')" "$written_at" \
    > "$flash_root/${profile}-${serial}.json"
touch "$flash_marker"
printf 'PASS flash build_id=%s profile=%s device=%s serial=%s; buffers flushed, safe to disconnect\n' \
    "$build_id" "$profile" "$device" "$serial"
