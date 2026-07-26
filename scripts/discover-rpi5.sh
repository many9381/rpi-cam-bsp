#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

usage() {
    printf 'Usage: %s [--hostname NAME] [--timeout SEC] [--previous-ip IP] [--lease-file PATH] [--mac MAC] [--port PORT] [--state-file PATH]\n' "$0"
}

require_option_value() {
    if (( $# < 2 )) || [[ -z "${2:-}" ]]; then
        usage >&2
        exit 2
    fi
}

repo_root="$(rpi5_repo_root)"
hostname="rpi5-minimal"
timeout_seconds="300"
previous_ip=""
lease_file=""
mac=""
port="22"
state_file="$repo_root/.state/last-rpi5-ip"
poll_seconds="${RPI5_DISCOVERY_POLL_SECONDS:-5}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hostname)
            require_option_value "$@"
            hostname="$2"
            shift 2
            ;;
        --timeout)
            require_option_value "$@"
            timeout_seconds="$2"
            shift 2
            ;;
        --previous-ip)
            require_option_value "$@"
            previous_ip="$2"
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
        --port)
            require_option_value "$@"
            port="$2"
            shift 2
            ;;
        --state-file)
            require_option_value "$@"
            state_file="$2"
            shift 2
            ;;
        --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

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

[[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] ||
    rpi5_die "timeout must be a positive integer"
[[ "$port" =~ ^[1-9][0-9]*$ ]] ||
    rpi5_die "invalid SSH port"
(( 10#$port <= 65535 )) || rpi5_die "invalid SSH port"
valid_hostname "$hostname" || rpi5_die "invalid hostname"
if [[ -n "$previous_ip" ]]; then
    valid_ipv4 "$previous_ip" || rpi5_die "invalid previous IP"
fi
if [[ -n "$mac" ]]; then
    [[ "$mac" =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]] ||
        rpi5_die "invalid MAC address"
fi
if [[ -n "$lease_file" && (! -f "$lease_file" || ! -r "$lease_file") ]]; then
    rpi5_die "lease file is not a readable regular file: $lease_file"
fi
[[ "$poll_seconds" =~ ^([0-9]+([.][0-9]+)?|[.][0-9]+)$ &&
        ! "$poll_seconds" =~ ^0*([.]0*)?$ ]] ||
    rpi5_die "poll interval must be a positive number"

rpi5_require_cmd timeout
rpi5_require_cmd avahi-resolve-host-name
rpi5_require_cmd ssh-keyscan

declare -A attempted=()
deadline=$((SECONDS + timeout_seconds))

run_before_deadline() {
    local remaining=$((deadline - SECONDS))

    (( remaining > 0 )) || return 124
    timeout --kill-after=1s "${remaining}s" "$@"
}

cache_candidate() {
    local candidate="$1"
    local directory=""
    local temporary=""

    directory="$(dirname -- "$state_file")"
    mkdir -p -- "$directory" || return 1
    temporary="$(mktemp -- "${state_file}.tmp.XXXXXX")" || return 1
    if ! printf '%s\n' "$candidate" > "$temporary" ||
            ! chmod 0600 -- "$temporary" ||
            ! mv -f -- "$temporary" "$state_file"; then
        rm -f -- "$temporary"
        return 1
    fi
}

try_candidate() {
    local candidate="${1:-}"
    local host_key=""

    [[ -n "$candidate" ]] || return 0
    valid_ipv4 "$candidate" || return 0
    [[ -z "${attempted[$candidate]+present}" ]] || return 0
    attempted["$candidate"]=1
    printf 'Probing %s:%s\n' "$candidate" "$port" >&2
    host_key=""
    if host_key="$(
        run_before_deadline ssh-keyscan -T 3 -p "$port" "$candidate" 2>/dev/null
    )" &&
            [[ -n "$host_key" ]]; then
        cache_candidate "$candidate" ||
            rpi5_die "could not update discovery state: $state_file"
        printf '%s\n' "$candidate"
        exit 0
    fi
}

while (( SECONDS < deadline )); do
    attempted=()
    mdns_name="${hostname%.local}.local"
    mdns_ip="$(
        run_before_deadline avahi-resolve-host-name -4 "$mdns_name" \
            2>/dev/null || true
    )"
    mdns_ip="$(awk 'NR == 1 {print $2}' <<< "$mdns_ip")"
    try_candidate "$mdns_ip"
    try_candidate "$previous_ip"
    if [[ -f "$state_file" && -r "$state_file" ]]; then
        try_candidate "$(head -n 1 "$state_file")"
    fi
    if [[ -n "$lease_file" ]]; then
        while IFS= read -r lease_ip; do
            try_candidate "$lease_ip"
        done < <(
            awk -v host="${hostname%.local}" -v wanted_mac="$mac" '
                $4 == host ||
                (wanted_mac != "" && tolower($2) == tolower(wanted_mac)) {
                    print $3
                }
            ' "$lease_file"
        )
    fi
    printf 'No reachable SSH endpoint for %s yet\n' "$hostname" >&2
    run_before_deadline sleep "$poll_seconds" || true
done

rpi5_die "no reachable $hostname SSH endpoint within ${timeout_seconds}s"
