#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/remote.sh"

host="127.0.0.1"
port="2222"
timeout_seconds="180"
key="$(rpi5_repo_root)/keys/rpi5_admin"
evidence_dir=""
build_id=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-id) build_id="$2"; shift 2 ;;
        --host) host="$2"; shift 2 ;;
        --port) port="$2"; shift 2 ;;
        --timeout) timeout_seconds="$2"; shift 2 ;;
        --key) key="$2"; shift 2 ;;
        --evidence-dir) evidence_dir="$2"; shift 2 ;;
        *) rpi5_die "unknown QEMU guest argument: $1" ;;
    esac
done

rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"
rpi5_validate_key_pair "$key"
[[ -n "$evidence_dir" ]] || \
    evidence_dir="$(rpi5_repo_root)/artifacts/$build_id/qemu-test"
mkdir -p "$evidence_dir"
known_hosts="$evidence_dir/known_hosts"
rpi5_remote_init "$host" "$port" "$key" "$known_hosts"
rpi5_wait_ssh "$timeout_seconds" || rpi5_die "QEMU SSH did not become ready"
rpi5_remote 'systemctl --failed --no-pager' \
    > "$evidence_dir/systemd-failed.log" 2>&1 || true
rpi5_remote 'sudo -n /usr/bin/journalctl -b --no-pager' \
    > "$evidence_dir/journal.log" 2>&1 || true

ssh_log="$evidence_dir/ssh-checks.log"
: > "$ssh_log"
check_exact() {
    local label="$1"
    local expected="$2"
    local command="$3"
    local output
    output="$(rpi5_remote "$command")"
    printf '%s=%s\n' "$label" "$output" | tee -a "$ssh_log"
    [[ "$output" == "$expected" ]] || \
        rpi5_die "$label expected '$expected' but got '$output'"
}

check_exact architecture aarch64 'uname -m'
check_exact build_id "$build_id" 'cat /etc/rpi5-build-id'
check_exact systemd running 'systemctl is-system-running'
check_exact networkd active 'systemctl is-active systemd-networkd.service'
check_exact sshd active 'systemctl is-active sshd.service'
check_exact password_authentication no "sshd -T | awk '\$1 == \"passwordauthentication\" { print \$2 }'"
check_exact kbd_interactive_authentication no "sshd -T | awk '\$1 == \"kbdinteractiveauthentication\" { print \$2 }'"
check_exact permit_root_login no "sshd -T | awk '\$1 == \"permitrootlogin\" { print \$2 }'"
check_exact authentication_methods publickey "sshd -T | awk '
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
'"
check_exact allow_users rpiadmin "sshd -T | awk '\$1 == \"allowusers\" { print \$2 }'"
check_exact account_locked L "passwd -S rpiadmin | awk '\$1 == \"rpiadmin\" { print \$2 }'"

rpi5_remote "ip -4 -o address show scope global | grep -Eq 'inet 10\\.0\\.2\\.'"
rpi5_remote "printf '%s' '$build_id' > /var/tmp/qemu-rw-test && grep -Fx '$build_id' /var/tmp/qemu-rw-test && rm /var/tmp/qemu-rw-test" \
    >> "$ssh_log"

root_ssh=(
    ssh -p "$port" -i "$key" -o BatchMode=yes -o ConnectTimeout=5
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known_hosts"
    "root@$host" true
)
if "${root_ssh[@]}" >> "$ssh_log" 2>&1; then
    rpi5_die "root SSH login unexpectedly succeeded"
fi

password_only=(
    ssh -p "$port" -o BatchMode=yes -o ConnectTimeout=5
    -o PubkeyAuthentication=no
    -o PreferredAuthentications=password,keyboard-interactive
    -o NumberOfPasswordPrompts=0
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known_hosts"
    "rpiadmin@$host" true
)
if "${password_only[@]}" >> "$ssh_log" 2>&1; then
    rpi5_die "non-key SSH login unexpectedly succeeded"
fi

printf '{"build_id":"%s","architecture":"aarch64","systemd":"running","network":"active","ssh":"key-only","account":"locked"}\n' \
    "$build_id" > "$evidence_dir/result.json"
touch "$evidence_dir/guest-PASS"
rpi5_remote 'sudo -n /usr/bin/systemctl poweroff'
