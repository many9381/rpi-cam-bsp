#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/remote.sh"

usage() {
    printf 'Usage: %s --build-id ID --host IP --wide-label-confirmed [--hostname NAME] [--port PORT] [--key PATH] [--lease-file PATH] [--mac MAC]\n' "$0"
}

require_option_value() {
    if (( $# < 2 )) || [[ -z "${2:-}" ]]; then
        usage >&2
        exit 2
    fi
}

valid_ipv4() {
    local address="$1"
    local octet=""
    local -a octets=()

    [[ "$address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
    IFS=. read -r -a octets <<< "$address"
    for octet in "${octets[@]}"; do
        (( 10#$octet <= 255 )) || return 1
    done
}

valid_hostname() {
    local name="${1%.local}"
    local label=""
    local -a labels=()

    [[ -n "$name" && "${#name}" -le 253 ]] || return 1
    IFS=. read -r -a labels <<< "$name"
    for label in "${labels[@]}"; do
        [[ -n "$label" && "${#label}" -le 63 ]] || return 1
        [[ "$label" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]] ||
            return 1
    done
}

repo_root="$(rpi5_repo_root)"
build_id=""
host=""
hostname="rpi5-camera"
port="22"
key="$repo_root/keys/rpi5_admin"
lease_file=""
mac=""
wide_label_confirmed=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-id)
            require_option_value "$@"
            build_id="$2"
            shift 2
            ;;
        --host)
            require_option_value "$@"
            host="$2"
            shift 2
            ;;
        --wide-label-confirmed)
            wide_label_confirmed=1
            shift
            ;;
        --hostname)
            require_option_value "$@"
            hostname="$2"
            shift 2
            ;;
        --port)
            require_option_value "$@"
            port="$2"
            shift 2
            ;;
        --key)
            require_option_value "$@"
            key="$2"
            shift 2
            ;;
        --lease-file)
            require_option_value "$@"
            lease_file="$2"
            shift 2
            ;;
        --mac)
            require_option_value "$@"
            mac="$2"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"
valid_ipv4 "$host" || rpi5_die "invalid initial host"
valid_hostname "$hostname" || rpi5_die "invalid hostname"
[[ "$port" =~ ^[1-9][0-9]*$ ]] || rpi5_die "invalid SSH port"
(( 10#$port <= 65535 )) || rpi5_die "invalid SSH port"
if [[ -n "$mac" ]]; then
    [[ "$mac" =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]] ||
        rpi5_die "invalid MAC address"
fi
if [[ -n "$lease_file" && (! -f "$lease_file" || ! -r "$lease_file") ]]; then
    rpi5_die "lease file is not a readable regular file: $lease_file"
fi
(( wide_label_confirmed == 1 )) ||
    rpi5_die "operator must confirm the physical Camera Module 3 Wide label"

current_revision="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
[[ "$build_id" == *"-$current_revision" ]] ||
    rpi5_die "build ID revision does not match HEAD $current_revision"
rpi5_validate_key_pair "$key"
rpi5_require_pass "$repo_root/artifacts/$build_id/qemu-test/PASS" "QEMU"
rpi5_require_pass \
    "$repo_root/artifacts/$build_id/rpi5-test/PASS" "phase-1 hardware"
rpi5_require_pass \
    "$repo_root/artifacts/$build_id/rpi5-camera/COMPLETE" "camera image"
rpi5_require_pass \
    "$repo_root/artifacts/$build_id/flash/rpi5-camera-PASS" "camera flash"

evidence="$repo_root/artifacts/$build_id/camera-test"
[[ ! -e "$evidence/PASS" ]] || rpi5_die "camera PASS already exists"
mkdir -p "$evidence/samples"
: > "$evidence/samples/SHA256SUMS"
: > "$evidence/health.log"
printf 'camera_module=Camera Module 3 Wide\nlabel_confirmed_by_operator=yes\nconfirmed_at=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$evidence/operator-wide-label.txt"

known_hosts="$evidence/known_hosts"
connected=0
expected_root_uuid=""

collect_camera_diagnostics() {
    (( connected == 1 )) || return 0
    rpi5_remote 'sudo -n /usr/bin/journalctl -b --no-pager' \
        > "$evidence/diagnostic-journal.log" 2>&1 || true
    rpi5_remote 'sudo -n /usr/bin/journalctl -b -1 --no-pager' \
        > "$evidence/diagnostic-journal-previous.log" 2>&1 || true
    rpi5_remote 'sudo -n /usr/bin/dmesg' \
        > "$evidence/diagnostic-dmesg.log" 2>&1 || true
    rpi5_remote 'rpicam-hello --version' \
        > "$evidence/diagnostic-rpicam-version.log" 2>&1 || true
    rpi5_remote 'rpicam-hello --list-cameras' \
        > "$evidence/diagnostic-camera-list.log" 2>&1 || true
    rpi5_remote 'media-ctl -p' \
        > "$evidence/diagnostic-media-topology.log" 2>&1 || true
}

on_camera_exit() {
    local status=$?

    trap - EXIT
    if (( status != 0 )); then
        collect_camera_diagnostics
    fi
    exit "$status"
}
trap on_camera_exit EXIT

connect_current_host() {
    local timeout_seconds="$1"
    local root_info=""
    local root_source=""
    local root_disk=""
    local transport=""
    local root_uuid=""
    local remote_build_id=""
    local system_state=""

    rpi5_remote_init "$host" "$port" "$key" "$known_hosts"
    rpi5_wait_ssh "$timeout_seconds" ||
        rpi5_die "camera image SSH did not become ready on $host"
    connected=1

    remote_build_id="$(rpi5_remote 'cat /etc/rpi5-build-id')"
    [[ "$remote_build_id" == "$build_id" ]] ||
        rpi5_die "camera image build ID mismatch"
    system_state="$(rpi5_remote 'systemctl is-system-running --wait')"
    [[ "$system_state" == "running" ]] ||
        rpi5_die "camera image systemd is not running"

    root_info="$(rpi5_remote '
        root_source=$(findmnt -n -o SOURCE /)
        parent=$(lsblk -no PKNAME "$root_source" | head -n 1)
        transport=$(lsblk -dn -o TRAN "/dev/$parent" | tr -d "[:space:]")
        root_uuid=$(lsblk -no UUID "$root_source" | tr -d "[:space:]")
        printf "%s|%s|%s|%s" \
            "$root_source" "/dev/$parent" "$transport" "$root_uuid"
    ')"
    IFS='|' read -r root_source root_disk transport root_uuid <<< "$root_info"
    [[ "$root_source" == "/dev/sda2" ]] ||
        rpi5_die "camera image root is not /dev/sda2"
    [[ "$root_disk" == "/dev/sda" ]] ||
        rpi5_die "camera image root disk is not /dev/sda"
    [[ "$transport" == "usb" ]] ||
        rpi5_die "camera image root disk transport is not usb"
    [[ -n "$root_uuid" ]] || rpi5_die "camera root filesystem UUID is empty"
    if [[ -z "$expected_root_uuid" ]]; then
        expected_root_uuid="$root_uuid"
    elif [[ "$root_uuid" != "$expected_root_uuid" ]]; then
        rpi5_die "camera root filesystem changed across reboot"
    fi
}

check_camera_list() {
    local label="$1"
    local log="$evidence/cameras-${label}.log"

    rpi5_remote 'rpicam-hello --list-cameras' > "$log" 2>&1
    grep -Eiq 'imx708' "$log" || rpi5_die "IMX708 was not enumerated"
    grep -Eq '[0-9]+x[0-9]+' "$log" ||
        rpi5_die "IMX708 sensor modes were not listed"
}

check_thermal() {
    local label="$1"
    local temperature=""
    local load=""

    temperature="$(rpi5_remote 'cat /sys/class/thermal/thermal_zone0/temp')"
    [[ "$temperature" =~ ^[0-9]+$ ]] ||
        rpi5_die "invalid thermal reading"
    (( temperature < 85000 )) || rpi5_die "SoC temperature reached 85 C"
    load="$(rpi5_remote 'cat /proc/loadavg')"
    printf '%s temperature_millic=%s load=%s\n' \
        "$label" "$temperature" "$load" | tee -a "$evidence/health.log"
}

copy_and_verify() {
    local remote_path="$1"
    local local_path="$2"
    local remote_sha=""
    local local_sha=""

    remote_sha="$(
        rpi5_remote "sha256sum $remote_path | awk '{print \$1}'"
    )"
    [[ "$remote_sha" =~ ^[0-9a-f]{64}$ ]] ||
        rpi5_die "invalid remote checksum for $remote_path"
    rpi5_copy_from "$remote_path" "$local_path"
    local_sha="$(sha256sum "$local_path" | awk '{print $1}')"
    [[ "$remote_sha" == "$local_sha" ]] ||
        rpi5_die "copy checksum mismatch for $remote_path"
    printf '%s  %s\n' "$local_sha" "$(basename "$local_path")" \
        >> "$evidence/samples/SHA256SUMS"
}

capture_still() {
    local label="$1"
    local remote_jpeg="/var/tmp/imx708-${label}.jpg"

    rpi5_remote \
        "rm -f $remote_jpeg; \
        rpicam-still --nopreview --autofocus-mode auto --timeout 2s \
        --output $remote_jpeg" > "$evidence/still-${label}.log" 2>&1
    rpi5_remote \
        "test -s $remote_jpeg && \
        file $remote_jpeg | grep -F 'JPEG image data'" \
        >> "$evidence/still-${label}.log"
    copy_and_verify \
        "$remote_jpeg" "$evidence/samples/imx708-${label}.jpg"
    rpi5_remote "rm -f $remote_jpeg"
}

remaining_reboot_seconds() {
    local remaining=$((reboot_deadline - SECONDS))

    if (( remaining <= 0 )); then
        rpi5_die "camera reboot exceeded 120 seconds"
        return 1
    fi
    printf '%s\n' "$remaining"
}

connect_current_host 20
rpi5_remote 'sudo -n /usr/bin/dmesg' > "$evidence/kernel.log"
grep -Eiq 'imx708' "$evidence/kernel.log" ||
    rpi5_die "kernel log has no IMX708 evidence"
grep -Eiq 'unicam|cfe' "$evidence/kernel.log" ||
    rpi5_die "kernel log has no camera pipeline evidence"
rpi5_remote 'media-ctl -p' > "$evidence/media-topology.log"
grep -Eiq 'imx708' "$evidence/media-topology.log" ||
    rpi5_die "media topology has no IMX708 entity"
rpi5_remote 'v4l2-ctl --list-devices' > "$evidence/video-devices.log"
rpi5_remote 'rpicam-hello --version' > "$evidence/rpicam-version.log" 2>&1
check_camera_list initial

initial_boot_id="$(rpi5_remote 'cat /proc/sys/kernel/random/boot_id')"
[[ "$initial_boot_id" =~ ^[0-9a-f-]{36}$ ]] ||
    rpi5_die "invalid initial camera boot ID"
check_thermal before-capture
capture_still initial

remote_video="/var/tmp/imx708-wide-1080p30.h264"
rpi5_remote \
    "rm -f $remote_video; \
    rpicam-vid --nopreview --timeout 10s \
    --width 1920 --height 1080 --framerate 30 \
    --codec libav --libav-format h264 --libav-video-codec libx264 \
    --output $remote_video" > "$evidence/video.log" 2>&1
rpi5_remote \
    "test -s $remote_video && \
    ffprobe -v error -select_streams v:0 \
    -show_entries stream=codec_name,width,height,r_frame_rate \
    -of csv=p=0 $remote_video" > "$evidence/ffprobe.log"
grep -Eq '^h264,1920,1080,(30/1|30)$' "$evidence/ffprobe.log" ||
    rpi5_die "H.264 stream is not 1920x1080 at 30 fps"
copy_and_verify \
    "$remote_video" "$evidence/samples/imx708-wide-1080p30.h264"
rpi5_remote "rm -f $remote_video"
check_thermal after-video

reboot_started="$SECONDS"
reboot_deadline=$((reboot_started + 120))
rpi5_remote 'sudo -n /usr/bin/systemctl reboot' >/dev/null 2>&1 || true
connected=0

disconnected=0
down_deadline=$((reboot_started + 60))
(( down_deadline < reboot_deadline )) || down_deadline="$reboot_deadline"
while (( SECONDS < down_deadline )); do
    remaining="$(remaining_reboot_seconds)"
    probe_timeout=3
    (( remaining < probe_timeout )) && probe_timeout="$remaining"
    if ! timeout --kill-after=1s "${probe_timeout}s" \
            ssh-keyscan -T "$probe_timeout" -p "$port" "$host" \
            >/dev/null 2>&1; then
        disconnected=1
        break
    fi
    sleep_seconds=2
    (( remaining < sleep_seconds )) && sleep_seconds="$remaining"
    timeout --kill-after=1s "${sleep_seconds}s" \
        sleep "$sleep_seconds" || true
done
(( disconnected == 1 )) || rpi5_die "camera Pi never left the network"

remaining="$(remaining_reboot_seconds)"
discovery=(
    "$repo_root/scripts/discover-rpi5.sh"
    --hostname "$hostname"
    --timeout "$remaining"
    --previous-ip "$host"
    --port "$port"
)
[[ -z "$lease_file" ]] || discovery+=(--lease-file "$lease_file")
[[ -z "$mac" ]] || discovery+=(--mac "$mac")
host="$("${discovery[@]}")"
valid_ipv4 "$host" || rpi5_die "discovery returned an invalid IPv4 address"

remaining="$(remaining_reboot_seconds)"
connect_current_host "$remaining"
recovery_elapsed=$((SECONDS - reboot_started))
(( recovery_elapsed <= 120 )) ||
    rpi5_die "camera reboot exceeded 120 seconds"
printf 'elapsed_seconds=%s host=%s\n' "$recovery_elapsed" "$host" \
    > "$evidence/reboot.log"

post_boot_id="$(rpi5_remote 'cat /proc/sys/kernel/random/boot_id')"
[[ "$post_boot_id" =~ ^[0-9a-f-]{36}$ ]] ||
    rpi5_die "invalid post-reboot camera boot ID"
[[ "$post_boot_id" != "$initial_boot_id" ]] ||
    rpi5_die "camera reboot did not occur"
check_camera_list post-reboot
capture_still post-reboot
check_thermal post-reboot

collect_camera_diagnostics
result_temporary="$evidence/result.json.tmp"
printf '{"build_id":"%s","sensor":"imx708","lens_variant":"wide-operator-verified","jpeg":"PASS","h264":"libx264-1920x1080-30fps","reboot_capture":"PASS","result":"PASS"}\n' \
    "$build_id" > "$result_temporary"
mv -f -- "$result_temporary" "$evidence/result.json"
touch "$evidence/PASS"
trap - EXIT
printf 'PASS camera build_id=%s sensor=imx708 host=%s\n' "$build_id" "$host"
