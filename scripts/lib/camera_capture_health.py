"""Read-only Pi capture acceptance. No credentials, raw journals or service changes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
CAPTURE_ERROR_COUNT = r'''
# Only a count leaves the Pi. A failed privileged read fails this probe.
sudo -n /usr/bin/journalctl -b --no-pager |
awk -v pid="$pid" 'index($0,"camera-firmware[" pid "]:") &&
 /Camera frontend has timed out|Dequeue timer.*expired|failed to requeue libcamera request|camera capture unhealthy: E_CAMERA_/ {n++}
 END {printf "errors=%d\n",n+0}'
'''
PROBE = r'''
set -eu
set -o pipefail
printf 'build='; cat /etc/rpi5-build-id
printf 'profile='; cat /etc/rpi5-camera-profile
printf 'serial='; tr -d '\000' </proc/device-tree/serial-number; printf '\n'
printf 'boot='; cat /proc/sys/kernel/random/boot_id
printf 'root='; camera_root_identity /dev/disk/by-uuid
printf 'active='; systemctl show camera-firmware.service -p ActiveState --value
pid=$(systemctl show camera-firmware.service -p MainPID --value)
case "$pid" in ''|*[!0-9]*) exit 1 ;; esac
printf 'pid=%s\n' "$pid"
awk '/rp1-cfe|pispbe/ {
  total=0; for(i=2;i<=NF && $i ~ /^[0-9]+$/;i++) total+=$i;
  if ($0 ~ /rp1-cfe/) printf "cfe=%.0f\n",total;
  if ($0 ~ /pispbe/) printf "isp=%.0f\n",total;
}' /proc/interrupts
''' + CAPTURE_ERROR_COUNT


def parse_snapshot(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        key, separator, value = line.partition('=')
        if not separator or key in result:
            raise ValueError('malformed or duplicate probe field')
        result[key] = value
    for key in ('pid', 'cfe', 'isp', 'errors'):
        value = result.get(key, '')
        if not re.fullmatch(r'[0-9]+', value):
            raise ValueError(f'missing/invalid {key}')
        result[key] = int(value)
    return result


def evaluate(before: dict, after: dict, *, build: str, profile: str, serial: str) -> dict:
    for data in (before, after):
        for key, expected in (('build', build), ('profile', profile), ('serial', serial), ('active', 'active')):
            if data.get(key) != expected:
                raise ValueError(f'{key} mismatch')
        if data.get('pid', 0) <= 0 or not data.get('boot'):
            raise ValueError('missing running process/boot identity')
        root = data.get('root', '').split('|')
        if len(root) != 4 or root[:3] != ['/dev/sda2', '/dev/sda', 'usb'] or not root[3]:
            raise ValueError('unexpected root filesystem')
        if data['errors'] != 0:
            raise ValueError('capture timeout/requeue failure in current process')
    for key in ('boot', 'pid', 'root'):
        if before[key] != after[key]:
            raise ValueError(f'{key} changed during observation')
    deltas = {f'{key}_delta': after[key] - before[key] for key in ('cfe', 'isp')}
    if any(delta <= 0 for delta in deltas.values()):
        raise ValueError('capture/ISP counters did not both increase')
    return deltas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--profile', choices=('rpi5-camera', 'rpi5-camera-hailo'), default='rpi5-camera-hailo')
    parser.add_argument('--known-hosts', required=True, type=Path)
    parser.add_argument('--key', type=Path, default=REPO / 'keys/rpi5_admin')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--host-key-alias')
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', args.host):
        parser.error('invalid SSH host')
    if not 1 <= args.interval <= 30 or not 1 <= args.port <= 65535:
        parser.error('interval must be 1..30 seconds and port 1..65535')
    result = {'status': 'FAIL', 'scope': 'CFE/ISP progress and capture errors only; UI/AI confirmation remains required'}
    try:
        if not args.known_hosts.is_file() or not args.known_hosts.stat().st_size:
            raise ValueError('existing pinned known-hosts file required')
        ssh = ['ssh', '-F', '/dev/null', '-p', str(args.port), '-i', str(args.key),
               '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ForwardAgent=no',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'GlobalKnownHostsFile=/dev/null',
               '-o', f'UserKnownHostsFile={args.known_hosts.resolve()}', '-o', 'ConnectTimeout=5',
               '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2']
        if args.host_key_alias:
            ssh += ['-o', f'HostKeyAlias={args.host_key_alias}']
        command = (REPO / 'scripts/lib/camera_root_identity.sh').read_text() + PROBE
        def snapshot():
            remote = subprocess.run(ssh + [f'rpiadmin@{args.host}', command],
                                    capture_output=True, text=True, timeout=30)
            if remote.returncode:
                raise ValueError('SSH or target probe failed (check pinned key, service and journal access)')
            return parse_snapshot(remote.stdout)
        before = snapshot()
        result['before'] = before
        time.sleep(args.interval)
        after = snapshot()
        result['after'] = after
        result.update(evaluate(before, after, build=args.build_id, profile=args.profile, serial=args.serial))
        result.update(status='PASS', interval_seconds=args.interval)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result['error'] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Capture runtime check: {result['status']} ({args.output})")
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
