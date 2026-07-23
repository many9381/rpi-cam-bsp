#!/usr/bin/env bash

rpi5_repo_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P
}

rpi5_die() {
    printf 'ERROR: %s\n' "$*" >&2
    return 1
}

rpi5_require_cmd() {
    command -v "$1" >/dev/null 2>&1 || rpi5_die "required command not found: $1"
}

rpi5_validate_build_id() {
    [[ "${1:-}" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]]
}

rpi5_validate_key_pair() {
    local private_key="$1"
    local public_key="${private_key}.pub"
    [[ -f "$private_key" ]] || rpi5_die "private key missing: $private_key"
    [[ -f "$public_key" ]] || rpi5_die "public key missing: $public_key"
    [[ "$(wc -l < "$public_key")" -eq 1 ]] || \
        rpi5_die "public key must contain exactly one line"
    grep -Eq '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/=]+( .*)?$' \
        "$public_key" || rpi5_die "unsupported public key format"
    ssh-keygen -l -f "$public_key" >/dev/null || rpi5_die "ssh-keygen rejected public key"
    [[ "$(stat -c '%a' "$private_key")" == "600" ]] || \
        rpi5_die "private key mode must be 600"
}

rpi5_require_pass() {
    local marker="$1"
    local label="$2"
    [[ -f "$marker" ]] || rpi5_die "$label PASS marker missing: $marker"
}
