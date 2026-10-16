"""Regression for active-but-stalled service falsely passing capture acceptance."""
import importlib.util
import os
import subprocess
import tempfile
from pathlib import Path
import unittest

from support import REPO_ROOT

spec = importlib.util.spec_from_file_location('capture_health', REPO_ROOT / 'scripts/lib/camera_capture_health.py')
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


def sample(**changes):
    result = dict(build='20261015T121728Z-e664cb9647e7', profile='rpi5-camera-hailo',
                  serial='5090bb4b8a34a361', boot='boot-one', pid=302, active='active',
                  root='/dev/sda2|/dev/sda|usb|abc', cfe=1000, isp=500, errors=0)
    result.update(changes)
    return result


class CaptureAcceptanceTest(unittest.TestCase):
    def check(self, before, after):
        return health.evaluate(before, after, build=sample()['build'],
                               profile=sample()['profile'], serial=sample()['serial'])

    def test_real_capture_progress_passes_without_claiming_fps_or_ai(self):
        result = self.check(sample(), sample(cfe=1200, isp=600))
        self.assertEqual(result['cfe_delta'], 200)
        self.assertEqual(result['isp_delta'], 100)

    def test_service_active_alone_cannot_pass(self):
        for changes in ({}, {'cfe': 1200}, {'isp': 600}, {'cfe': 1, 'isp': 600}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.check(sample(), sample(**changes))

    def test_timeout_is_failure_even_after_frames_resume(self):
        with self.assertRaises(ValueError):
            self.check(sample(), sample(cfe=1200, isp=600, errors=1))

    def test_identity_or_process_change_cannot_be_counted_as_progress(self):
        for changes in ({'boot':'boot-two'}, {'pid':303}, {'root':'/dev/mmcblk0p2|/dev/mmcblk0|mmc|abc'},
                        {'serial':'another-board'}, {'build':'another-build'}, {'active':'inactive'},
                        {'pid':0}, {'profile':'rpi5-camera'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.check(sample(), sample(cfe=1200, isp=600, **changes))

    def test_missing_or_duplicate_counters_fail_closed(self):
        raw = 'build=abc\ncfe=200\nisp=100\npid=302\nerrors=0\n'
        self.assertEqual(health.parse_snapshot(raw)['cfe'], 200)
        for invalid in (raw + 'cfe=201\n', raw.replace('isp=100\n', ''), raw.replace('errors=0', 'errors=oops')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                health.parse_snapshot(invalid)


class CaptureLogPrivacyTest(unittest.TestCase):
    def test_only_current_process_capture_error_count_leaves_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sudo = root / 'sudo'
            sudo.write_text("#!/bin/sh\ncat <<'LOG'\n"
                            "host camera-firmware[302]: Camera frontend has timed out!\n"
                            "host camera-firmware[301]: Camera frontend has timed out!\n"
                            "host camera-firmware[302]: private-token-must-not-leave-device\n"
                            "host unrelated[302]: Camera frontend has timed out!\nLOG\n")
            sudo.chmod(0o755)
            env = dict(os.environ, PATH=f"{directory}:" + os.environ['PATH'])
            command = 'set -euo pipefail; pid=302; ' + health.CAPTURE_ERROR_COUNT
            result = subprocess.run(['bash', '-c', command], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'errors=1\n')
            sudo.write_text('#!/bin/sh\nexit 1\n')
            denied = subprocess.run(['bash', '-c', command], env=env, capture_output=True, text=True)
            self.assertNotEqual(denied.returncode, 0, 'journal access failure must not pass as zero errors')


class CaptureCommandTest(unittest.TestCase):
    def test_cli_records_pass_or_failure_and_requires_pinned_ssh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ssh = root / 'ssh'
            ssh.write_text('''#!/usr/bin/env python3
import os, pathlib, sys
assert 'StrictHostKeyChecking=yes' in sys.argv
assert 'GlobalKnownHostsFile=/dev/null' in sys.argv
assert '-F' in sys.argv and '/dev/null' in sys.argv
if os.environ.get('DENY_SSH'): sys.exit(255)
path = pathlib.Path(os.environ['SAMPLE_COUNTER'])
n = int(path.read_text()) if path.exists() else 0
path.write_text(str(n + 1))
print('build=20261015T121728Z-e664cb9647e7')
print('profile=rpi5-camera-hailo')
print('serial=5090bb4b8a34a361')
print('boot=stable-boot')
print('root=/dev/sda2|/dev/sda|usb|uuid')
print('pid=302')
print('active=active')
print('errors=0')
print('cfe=' + str(1000 + n * 200))
print('isp=' + str(500 + n * 100))
''')
            ssh.chmod(0o755)
            known = root / 'known_hosts'
            known.write_text('pinned test host\n')
            output = root / 'result.json'
            command = ['bash', str(REPO_ROOT / 'scripts/test-camera-runtime.sh'),
                       '--host', '192.0.2.5', '--build-id', sample()['build'],
                       '--serial', sample()['serial'], '--known-hosts', str(known),
                       '--interval', '1', '--output', str(output)]
            env = dict(os.environ, PATH=f"{root}:" + os.environ['PATH'], SAMPLE_COUNTER=str(root / 'count'))
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            import json
            self.assertEqual(json.loads(output.read_text())['status'], 'PASS')
            # A failed rerun must overwrite the earlier PASS, not leave stale evidence.
            env['DENY_SSH'] = '1'
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(output.read_text())['status'], 'FAIL')
            known.unlink()
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('pinned', json.loads(output.read_text())['error'])
