#!/usr/bin/env bash

rpi5_remote_init() {
    local host="$1"
    local port="$2"
    local key="$3"
    local known_hosts="$4"
    local user="${5:-rpiadmin}"

    RPI5_REMOTE_HOST="$host"
    RPI5_REMOTE_PORT="$port"
    RPI5_REMOTE_KEY="$key"
    RPI5_KNOWN_HOSTS="$known_hosts"
    RPI5_REMOTE_USER="$user"
    RPI5_SSH=(
        ssh -p "$port" -i "$key"
        -o BatchMode=yes
        -o ConnectTimeout=5
        -o ServerAliveInterval=10
        -o ServerAliveCountMax=2
        -o StrictHostKeyChecking=yes
        -o UserKnownHostsFile="$known_hosts"
        "$user@$host"
    )
    RPI5_SCP=(
        scp -P "$port" -i "$key"
        -o BatchMode=yes
        -o ConnectTimeout=5
        -o StrictHostKeyChecking=yes
        -o UserKnownHostsFile="$known_hosts"
    )
}

rpi5_refresh_host_key() {
    local temporary="${RPI5_KNOWN_HOSTS}.new"
    if ssh-keyscan -T 3 -H -p "$RPI5_REMOTE_PORT" "$RPI5_REMOTE_HOST" \
        > "$temporary" 2>/dev/null && [[ -s "$temporary" ]]; then
        mv "$temporary" "$RPI5_KNOWN_HOSTS"
        return 0
    fi
    rm -f "$temporary"
    return 1
}

rpi5_wait_ssh() {
    local timeout_seconds="$1"
    local deadline=$((SECONDS + timeout_seconds))
    while (( SECONDS < deadline )); do
        if rpi5_refresh_host_key && "${RPI5_SSH[@]}" true >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

rpi5_remote() {
    "${RPI5_SSH[@]}" "$@"
}

rpi5_copy_from() {
    local remote_path="$1"
    local local_path="$2"
    "${RPI5_SCP[@]}" \
        "$RPI5_REMOTE_USER@$RPI5_REMOTE_HOST:$remote_path" "$local_path"
}
