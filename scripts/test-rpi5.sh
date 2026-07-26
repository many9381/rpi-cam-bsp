#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/remote.sh"

usage() {
    printf 'Usage: %s --build-id ID --host IP [--hostname NAME] [--port PORT] [--key PATH] [--lease-file PATH] [--mac MAC]\n' "$0"
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
hostname="rpi5-minimal"
port="22"
key="$repo_root/keys/rpi5_admin"
lease_file=""
mac=""

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

current_revision="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
[[ "$build_id" == *"-$current_revision" ]] ||
    rpi5_die "build ID revision does not match HEAD $current_revision"
rpi5_validate_key_pair "$key"
rpi5_require_pass "$repo_root/artifacts/$build_id/qemu-test/PASS" "QEMU"
rpi5_require_pass \
    "$repo_root/artifacts/$build_id/rpi5-minimal/COMPLETE" "minimal image"
rpi5_require_pass \
    "$repo_root/artifacts/$build_id/flash/rpi5-minimal-PASS" "minimal flash"

evidence="$repo_root/artifacts/$build_id/rpi5-test"
[[ ! -e "$evidence/PASS" ]] || rpi5_die "phase-1 PASS already exists"
mkdir -p "$evidence"
: > "$evidence/reboots.log"

known_hosts="$evidence/known_hosts"
connected=0

collect_diagnostics() {
    (( connected == 1 )) || return 0
    rpi5_remote 'sudo -n /usr/bin/journalctl -b --no-pager' \
        > "$evidence/journal-current.log" 2>&1 || true
    rpi5_remote 'sudo -n /usr/bin/journalctl -b -1 --no-pager' \
        > "$evidence/journal-previous.log" 2>&1 || true
    rpi5_remote 'sudo -n /usr/bin/dmesg' \
        > "$evidence/dmesg.log" 2>&1 || true
    rpi5_remote \
        'lsblk -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,FSTYPE,UUID,MOUNTPOINTS' \
        > "$evidence/lsblk.log" 2>&1 || true
    rpi5_remote 'findmnt --real' \
        > "$evidence/findmnt.log" 2>&1 || true
    rpi5_remote 'networkctl status --no-pager' \
        > "$evidence/networkctl.log" 2>&1 || true
}

on_exit() {
    local status=$?

    trap - EXIT
    if (( status != 0 )); then
        collect_diagnostics
    fi
    exit "$status"
}
trap on_exit EXIT

connect_current_host() {
    local timeout_seconds="$1"

    rpi5_remote_init "$host" "$port" "$key" "$known_hosts"
    rpi5_wait_ssh "$timeout_seconds" ||
        rpi5_die "key-only SSH did not become ready on $host"
    connected=1
}

remote_exact() {
    local label="$1"
    local expected="$2"
    local command="$3"
    local log="$4"
    local output=""

    output="$(rpi5_remote "$command")"
    printf '%s=%s\n' "$label" "$output" | tee -a "$log"
    [[ "$output" == "$expected" ]] ||
        rpi5_die "$label expected '$expected' but got '$output'"
}

assert_denied_logins() {
    local log="$1"
    local -a root_ssh=(
        ssh -p "$port" -i "$key"
        -o BatchMode=yes
        -o IdentitiesOnly=yes
        -o PasswordAuthentication=no
        -o KbdInteractiveAuthentication=no
        -o ConnectTimeout=5
        -o StrictHostKeyChecking=yes
        -o UserKnownHostsFile="$known_hosts"
        "root@$host" true
    )
    local -a password_only=(
        ssh -p "$port"
        -o BatchMode=yes
        -o PubkeyAuthentication=no
        -o PreferredAuthentications=password,keyboard-interactive
        -o NumberOfPasswordPrompts=0
        -o ConnectTimeout=5
        -o StrictHostKeyChecking=yes
        -o UserKnownHostsFile="$known_hosts"
        "rpiadmin@$host" true
    )

    if "${root_ssh[@]}" >> "$log" 2>&1; then
        rpi5_die "root SSH login unexpectedly succeeded"
    fi
    if "${password_only[@]}" >> "$log" 2>&1; then
        rpi5_die "non-key SSH login unexpectedly succeeded"
    fi
}

declare -A observed_boot_ids=()
checked_boot_id=""
expected_root_uuid=""

check_boot() {
    local cycle="$1"
    local log="$evidence/boot-${cycle}.log"
    local model=""
    local wired_interface=""
    local root_info=""
    local root_source=""
    local root_disk=""
    local transport=""
    local root_uuid=""
    local boot_id=""

    : > "$log"
    remote_exact architecture aarch64 'uname -m' "$log"
    model="$(rpi5_remote "tr -d '\\000' </proc/device-tree/model")"
    printf 'model=%s\n' "$model" | tee -a "$log"
    [[ "$model" == *"Raspberry Pi 5"* ]] ||
        rpi5_die "unexpected board model"
    remote_exact build_id "$build_id" 'cat /etc/rpi5-build-id' "$log"
    remote_exact systemd running 'systemctl is-system-running --wait' "$log"
    remote_exact networkd active \
        'systemctl is-active systemd-networkd.service' "$log"
    remote_exact sshd active 'systemctl is-active sshd.socket' "$log"

    rpi5_remote \
        "ip -4 -o address show scope global | grep -Eq 'inet [0-9]'" \
        >> "$log"
    wired_interface="$(
        rpi5_remote "ip -4 route show default | awk 'NR == 1 {print \$5}'"
    )"
    [[ "$wired_interface" == eth* || "$wired_interface" == en* ]] ||
        rpi5_die "default route is not on a wired interface"
    remote_exact ethernet_carrier 1 \
        "cat /sys/class/net/$wired_interface/carrier" "$log"
    printf 'default_interface=%s\n' "$wired_interface" | tee -a "$log"

    root_info="$(rpi5_remote '
        root_source=$(findmnt -n -o SOURCE /)
        parent=$(lsblk -no PKNAME "$root_source" | head -n 1)
        transport=$(lsblk -dn -o TRAN "/dev/$parent" | tr -d "[:space:]")
        root_uuid=$(lsblk -no UUID "$root_source" | tr -d "[:space:]")
        printf "%s|%s|%s|%s" \
            "$root_source" "/dev/$parent" "$transport" "$root_uuid"
    ')"
    IFS='|' read -r root_source root_disk transport root_uuid <<< "$root_info"
    printf 'root_source=%s root_disk=%s transport=%s root_uuid=%s\n' \
        "$root_source" "$root_disk" "$transport" "$root_uuid" | tee -a "$log"
    [[ "$root_source" == "/dev/sda2" ]] ||
        rpi5_die "root is not /dev/sda2"
    [[ "$root_disk" == "/dev/sda" ]] ||
        rpi5_die "root disk is not /dev/sda"
    [[ "$transport" == "usb" ]] ||
        rpi5_die "root disk transport is not usb"
    [[ -n "$root_uuid" ]] || rpi5_die "root filesystem UUID is empty"
    if [[ "$cycle" == "initial" ]]; then
        expected_root_uuid="$root_uuid"
    elif [[ "$root_uuid" != "$expected_root_uuid" ]]; then
        rpi5_die "root filesystem changed across reboot"
    fi
    if rpi5_remote "lsblk -ndo NAME | grep -Eq '^mmcblk'"; then
        rpi5_die "microSD must be removed during normal acceptance"
    fi
    rpi5_remote \
        "findmnt -n -o OPTIONS / | tr ',' '\\n' | grep -Fx rw" >> "$log"
    rpi5_remote \
        "printf '%s' '$build_id' > /var/tmp/rpi5-rw-test && \
        grep -Fx '$build_id' /var/tmp/rpi5-rw-test && \
        rm /var/tmp/rpi5-rw-test" >> "$log"

    remote_exact password_authentication no \
        "sudo -n /usr/sbin/sshd -T | awk \
        '\$1 == \"passwordauthentication\" { print \$2 }'" "$log"
    remote_exact kbd_interactive_authentication no \
        "sudo -n /usr/sbin/sshd -T | awk \
        '\$1 == \"kbdinteractiveauthentication\" { print \$2 }'" "$log"
    remote_exact permit_root_login no \
        "sudo -n /usr/sbin/sshd -T | awk \
        '\$1 == \"permitrootlogin\" { print \$2 }'" "$log"
    remote_exact authentication_methods publickey \
        "sudo -n /usr/sbin/sshd -T | awk '
        \$1 == \"authenticationmethods\" {
            count += 1
            line = \$0
            if (sub(/^[[:space:]]*[^[:space:]]+[[:space:]]+/, \"\", line) != 1 ||
                    line == \"\") {
                invalid = 1
            } else if (count == 1) {
                value = line
            }
        }
        END {
            if (count != 1 || invalid) {
                exit 1
            }
            print value
        }
        '" "$log"
    remote_exact allow_users rpiadmin \
        "sudo -n /usr/sbin/sshd -T | awk \
        '\$1 == \"allowusers\" { print \$2 }'" "$log"
    remote_exact account_locked L \
        "passwd -S rpiadmin | awk \
        '\$1 == \"rpiadmin\" { print \$2 }'" "$log"
    assert_denied_logins "$log"

    boot_id="$(rpi5_remote 'cat /proc/sys/kernel/random/boot_id')"
    [[ "$boot_id" =~ ^[0-9a-f-]{36}$ ]] || rpi5_die "invalid boot ID"
    [[ -z "${observed_boot_ids[$boot_id]+present}" ]] ||
        rpi5_die "boot ID did not change"
    observed_boot_ids["$boot_id"]=1
    printf 'boot_id=%s\n' "$boot_id" | tee -a "$log"
    checked_boot_id="$boot_id"
}

remaining_cycle_seconds() {
    local remaining=$((cycle_deadline - SECONDS))

    if (( remaining <= 0 )); then
        rpi5_die "reboot $reboot_number exceeded 120 seconds"
        return 1
    fi
    printf '%s\n' "$remaining"
}

connect_current_host 20
check_boot initial
initial_boot_id="$checked_boot_id"

reboot_1=""
reboot_2=""
reboot_3=""
for reboot_number in 1 2 3; do
    started="$SECONDS"
    cycle_deadline=$((started + 120))
    rpi5_remote 'sudo -n /usr/bin/systemctl reboot' >/dev/null 2>&1 || true
    connected=0

    disconnected=0
    down_deadline=$((started + 60))
    (( down_deadline < cycle_deadline )) || down_deadline="$cycle_deadline"
    while (( SECONDS < down_deadline )); do
        remaining="$(remaining_cycle_seconds)"
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
    (( disconnected == 1 )) || rpi5_die "Pi never left the network"

    remaining="$(remaining_cycle_seconds)"
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

    remaining="$(remaining_cycle_seconds)"
    connect_current_host "$remaining"
    check_boot "reboot-$reboot_number"
    current_boot_id="$checked_boot_id"
    printf -v "reboot_$reboot_number" '%s' "$current_boot_id"
    elapsed=$((SECONDS - started))
    (( elapsed <= 120 )) ||
        rpi5_die "reboot $reboot_number exceeded 120 seconds"
    printf 'reboot=%s elapsed_seconds=%s host=%s\n' \
        "$reboot_number" "$elapsed" "$host" | tee -a "$evidence/reboots.log"
done

collect_diagnostics
result_temporary="$evidence/result.json.tmp"
printf '{"build_id":"%s","reboots":3,"initial_boot_id":"%s","reboot_boot_ids":["%s","%s","%s"],"result":"PASS"}\n' \
    "$build_id" "$initial_boot_id" "$reboot_1" "$reboot_2" "$reboot_3" \
    > "$result_temporary"
mv -f -- "$result_temporary" "$evidence/result.json"
touch "$evidence/PASS"
trap - EXIT
printf 'PASS rpi5 build_id=%s host=%s reboots=3\n' "$build_id" "$host"
