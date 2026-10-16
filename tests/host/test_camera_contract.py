from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT, run


REVISION = "0123456789ab"
BUILD_ID = f"20990101T000000Z-{REVISION}"
SAMPLE_CONTENT = b"camera-sample\n"
SAMPLE_SHA256 = hashlib.sha256(SAMPLE_CONTENT).hexdigest()
VIDEO_METADATA = {
    "streams": [{"codec_name": "h264", "width": 1920, "height": 1080,
                 "r_frame_rate": "30/1", "avg_frame_rate": "30/1",
                 "nb_read_frames": "300", "duration": "10.000000"}],
    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "10.000000"},
}


class CameraAcceptanceContractTest(unittest.TestCase):
    def test_help_is_non_mutating_and_script_is_valid_bash(self) -> None:
        """Catches help processing that reaches hardware or invalid Bash."""
        script = REPO_ROOT / "scripts/test-camera.sh"
        self.assertTrue(os.access(script, os.X_OK), "test-camera.sh must be executable")

        help_result = run("bash", "scripts/test-camera.sh", "--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Usage:", help_result.stdout)
        self.assertIn("--wide-label-confirmed", help_result.stdout)
        self.assertEqual(help_result.stderr, "")

        syntax = run("bash", "-n", "scripts/test-camera.sh")
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_truncated_value_options_print_usage_without_nounset_errors(self) -> None:
        """Catches reading a missing CLI value under nounset."""
        for option in (
            "--build-id",
            "--host",
            "--profile",
            "--hostname",
            "--port",
            "--key",
            "--lease-file",
            "--mac",
        ):
            with self.subTest(option=option):
                result = run("bash", "scripts/test-camera.sh", option)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Usage:", result.stderr)
                self.assertNotIn("unbound variable", result.stderr)

    def test_invalid_inputs_and_missing_attestation_fail_before_keys(self) -> None:
        """Catches malformed or unattested runs reaching hardware prerequisites."""
        revision = run("git", "rev-parse", "--short=12", "HEAD").stdout.strip()
        build_id = f"20990101T000000Z-{revision}"
        with tempfile.TemporaryDirectory() as temporary:
            missing_lease = Path(temporary) / "missing.leases"
            cases = (
                (
                    ("--build-id", "invalid", "--host", "192.0.2.10"),
                    "invalid build ID",
                ),
                (
                    (
                        "--build-id",
                        build_id,
                        "--host",
                        "999.0.0.1",
                        "--wide-label-confirmed",
                    ),
                    "invalid initial host",
                ),
                (
                    (
                        "--build-id",
                        build_id,
                        "--host",
                        "192.0.2.10",
                        "--hostname",
                        "bad/name",
                        "--wide-label-confirmed",
                    ),
                    "invalid hostname",
                ),
                (
                    (
                        "--build-id",
                        build_id,
                        "--host",
                        "192.0.2.10",
                        "--port",
                        "65536",
                        "--wide-label-confirmed",
                    ),
                    "invalid SSH port",
                ),
                (
                    (
                        "--build-id",
                        build_id,
                        "--host",
                        "192.0.2.10",
                        "--mac",
                        "not-a-mac",
                        "--wide-label-confirmed",
                    ),
                    "invalid MAC address",
                ),
                (
                    (
                        "--build-id",
                        build_id,
                        "--host",
                        "192.0.2.10",
                        "--lease-file",
                        str(missing_lease),
                        "--wide-label-confirmed",
                    ),
                    "lease file is not a readable regular file",
                ),
                (
                    ("--build-id", build_id, "--host", "192.0.2.10"),
                    "confirm the physical Camera Module 3 Wide label",
                ),
            )

            for arguments, expected_error in cases:
                with self.subTest(arguments=arguments):
                    result = run("bash", "scripts/test-camera.sh", *arguments)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected_error, result.stderr)
                    self.assertNotIn("private key missing", result.stderr)
                    self.assertNotIn("PASS marker missing", result.stderr)


class CameraAcceptanceExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="camera-contract-")
        self.root = Path(self.temporary.name) / "checkout"
        (self.root / "scripts/lib").mkdir(parents=True)
        (self.root / "keys").mkdir()
        for relative in (
            "scripts/test-camera.sh",
            "scripts/discover-rpi5.sh",
            "scripts/lib/common.sh",
            "scripts/lib/remote.sh",
            "scripts/lib/camera_video.py",
            "scripts/lib/camera_root_identity.sh",
        ):
            source = REPO_ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        self.key = self.root / "keys/rpi5_admin"
        self.key.write_text("private\n", encoding="utf-8")
        self.key.chmod(0o600)
        (self.root / "keys/rpi5_admin.pub").write_text(
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest camera-contract\n",
            encoding="utf-8",
        )
        self.fake_bin = self.root / "fake-bin"
        self.fake_bin.mkdir()
        self.calls = self.root / "calls.log"
        self._write_executable(
            self.fake_bin / "git",
            "#!/usr/bin/env bash\n"
            "if [[ \" $* \" == *\" rev-parse \"* ]]; then "
            "printf '%s\\n' \"$FAKE_REVISION\"; fi\n",
        )
        self._write_executable(
            self.fake_bin / "ssh-keygen",
            "#!/usr/bin/env bash\nexit 0\n",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_executable(self, path: Path, contents: str) -> None:
        path.write_text(contents, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _environment(self, **extra: str) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.fake_bin}:{environment['PATH']}",
                "TEST_CALLS": str(self.calls),
                "FAKE_REVISION": REVISION,
            },
        )
        environment.update(extra)
        return environment

    def _run(self, *arguments: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            arguments,
            cwd=self.root,
            env=self._environment(**extra),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _acceptance(
        self, build_id: str = BUILD_ID, profile: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            "bash",
            "scripts/test-camera.sh",
            "--build-id",
            build_id,
            "--host",
            "192.0.2.20",
            "--wide-label-confirmed",
            *(("--profile", profile) if profile is not None else ()),
        )

    def _marker(self, relative: str) -> Path:
        marker = self.root / "artifacts" / BUILD_ID / relative
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return marker

    def _ready_prerequisites(self, profile: str = "rpi5-camera") -> None:
        for relative in (
            "rpi5-test/PASS",
            f"{profile}/COMPLETE",
            f"flash/{profile}-PASS",
        ):
            self._marker(relative)

    def _reset_runtime(self, profile: str = "rpi5-camera") -> tuple[Path, Path]:
        control = self.root / "control"
        evidence_name = "camera-hailo-test" if profile == "rpi5-camera-hailo" else "camera-test"
        evidence = self.root / "artifacts" / BUILD_ID / evidence_name
        shutil.rmtree(control, ignore_errors=True)
        shutil.rmtree(evidence, ignore_errors=True)
        control.mkdir()
        self.calls.unlink(missing_ok=True)
        return control, evidence

    def _run_ready_acceptance(
        self,
        profile: str | None = None,
        **extra: str,
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        control, evidence = self._reset_runtime(profile or "rpi5-camera")
        environment = {
            "CAMERA_CONTROL": str(control),
            "CAMERA_EVIDENCE": str(evidence),
            "FAKE_BUILD_ID": BUILD_ID,
            "FAKE_PROFILE": profile or "rpi5-camera",
            "FAKE_SAMPLE_SHA": SAMPLE_SHA256,
            "FAKE_FFPROBE": json.dumps(VIDEO_METADATA),
        }
        environment.update(extra)
        result = self._run(
            "bash",
            "scripts/test-camera.sh",
            "--build-id",
            BUILD_ID,
            "--host",
            "192.0.2.20",
            "--wide-label-confirmed",
            *(("--profile", profile) if profile is not None else ()),
            **environment,
        )
        return result, control, evidence

    def _install_success_commands(self) -> None:
        self._write_executable(
            self.fake_bin / "ssh-keyscan",
            """#!/usr/bin/env bash
printf 'ssh-keyscan %s\n' "$*" >> "$TEST_CALLS"
if [[ -f "$CAMERA_CONTROL/down-pending" ]]; then
  rm -f "$CAMERA_CONTROL/down-pending"
  exit 1
fi
printf 'camera-host ssh-ed25519 AAAATEST\n'
""",
        )
        self._write_executable(
            self.fake_bin / "scp",
            """#!/usr/bin/env bash
printf 'scp %s\n' "$*" >> "$TEST_CALLS"
destination="${!#}"
printf 'camera-sample\n' > "$destination"
""",
        )
        self._write_executable(
            self.fake_bin / "ssh",
            """#!/usr/bin/env bash
printf 'ssh %s\n' "$*" >> "$TEST_CALLS"
command="${!#}"
if [[ "${FAKE_CHANGE_HOST_KEY:-0}" == 1 && -f "$CAMERA_CONTROL/boot-index" &&
      "$*" == *'HostKeyAlias=192.0.2.20'* ]]; then
  printf 'REMOTE HOST IDENTIFICATION HAS CHANGED\n' >&2
  exit 255
fi
case "$command" in
  true) exit 0 ;;
  'systemctl show camera-firmware.service --property=ActiveState --value')
    if [[ -f "$CAMERA_CONTROL/boot-index" && "${FAKE_POST_STATE_QUERY_FAIL:-}" != '' ]]; then
      if [[ "$FAKE_POST_STATE_QUERY_FAIL" == persistent ||
            ! -f "$CAMERA_CONTROL/state-query-failed" ]]; then
        touch "$CAMERA_CONTROL/state-query-failed"
        exit 81
      fi
    fi
    if [[ ! -f "$CAMERA_CONTROL/service-state" ]]; then
      printf '%s\n' "${FAKE_INITIAL_SERVICE:-active}" > "$CAMERA_CONTROL/service-state"
    fi
    cat "$CAMERA_CONTROL/service-state"
    ;;
  'sudo -n /usr/bin/systemctl stop camera-firmware.service')
    [[ "${FAKE_STOP_FAIL:-0}" != 1 ]] || exit 1
    printf 'inactive\n' > "$CAMERA_CONTROL/service-state"
    ;;
  'sudo -n /usr/bin/systemctl start camera-firmware.service')
    [[ "${FAKE_START_FAIL:-0}" != 1 ]] || exit 1
    printf 'active\n' > "$CAMERA_CONTROL/service-state"
    ;;
  'cat /etc/rpi5-build-id')
    printf '%s\n' "${FAKE_REMOTE_BUILD_ID:-$FAKE_BUILD_ID}"
    ;;
  'cat /etc/rpi5-camera-profile')
    remote_profile="${FAKE_REMOTE_PROFILE-$FAKE_PROFILE}"
    if [[ "${FAKE_CHANGE_REMOTE_PROFILE:-0}" == "1" &&
          -f "$CAMERA_CONTROL/boot-index" &&
          "$(<"$CAMERA_CONTROL/boot-index")" -gt 0 ]]; then
      remote_profile='rpi5-camera'
    fi
    printf '%s\n' "$remote_profile"
    ;;
  'systemctl is-system-running --wait')
    printf '%s\n' "${FAKE_SYSTEMD:-running}"
    ;;
  *'root_source=$(findmnt'*)
    root_info="${FAKE_ROOT_INFO:-/dev/sda2|/dev/sda|usb|CAMERA-ROOT-UUID}"
    if [[ "${FAKE_CHANGE_ROOT_UUID:-0}" == "1" &&
          -f "$CAMERA_CONTROL/boot-index" &&
          "$(<"$CAMERA_CONTROL/boot-index")" -gt 0 ]]; then
      root_info='/dev/sda2|/dev/sda|usb|CHANGED-CAMERA-ROOT-UUID'
    fi
    printf '%s\n' "$root_info"
    ;;
  'cat /proc/sys/kernel/random/boot_id')
    index=0
    [[ ! -f "$CAMERA_CONTROL/boot-index" ]] ||
      index="$(<"$CAMERA_CONTROL/boot-index")"
    [[ "${FAKE_REPEAT_BOOT_ID:-0}" != "1" ]] || index=0
    printf '10000000-0000-4000-8000-%012d\n' "$index"
    ;;
  'sudo -n /usr/bin/dmesg')
    printf '%s\n' "${FAKE_DMESG:-imx708 unicam cfe camera pipeline}"
    ;;
  'media-ctl -p')
    printf '%s\n' \
      "${FAKE_MEDIA:-entity 1: imx708 10-001a (1 pad, 1 link)}"
    ;;
  'v4l2-ctl --list-devices') printf 'rp1-cfe (platform:1f00128000.csi)\n' ;;
  'rpicam-hello --version') printf 'rpicam-apps build 1.9.0\n' ;;
  'rpicam-hello --list-cameras')
    camera_list="${FAKE_CAMERA_LIST:-0 : imx708 [4608x2592 2304x1296]}"
    if [[ "${FAKE_POST_CAMERA_MISSING:-0}" == "1" &&
          -f "$CAMERA_CONTROL/boot-index" &&
          "$(<"$CAMERA_CONTROL/boot-index")" -gt 0 ]]; then
      camera_list='No cameras available'
    fi
    printf '%s\n' "$camera_list"
    ;;
  'cat /sys/class/thermal/thermal_zone0/temp')
    printf '%s\n' "${FAKE_TEMPERATURE:-55000}"
    ;;
  'cat /proc/loadavg') printf '0.10 0.20 0.30 1/100 100\n' ;;
  *'rpicam-still --nopreview --autofocus-mode auto --timeout 2s'*)
    if [[ "${FAKE_ENFORCE_SERVICE:-0}" == 1 ]]; then
      [[ -f "$CAMERA_CONTROL/service-state" &&
         "$(<"$CAMERA_CONTROL/service-state")" == inactive ]] || exit 71
    fi
    if [[ "${FAKE_POST_CAPTURE_ONLY:-0}" != 1 || -f "$CAMERA_CONTROL/boot-index" ]]; then
      [[ "${FAKE_CAPTURE_FAIL:-0}" != 1 ]] || exit 72
      if [[ "${FAKE_CAPTURE_SIGNAL:-}" != '' ]]; then
        kill -s "$FAKE_CAPTURE_SIGNAL" "$PPID"
        exit 73
      fi
    fi
    printf 'still captured\n'
    ;;
  *'JPEG image data'*) printf 'JPEG image data, JFIF standard 1.01\n' ;;
  *'rpicam-vid --nopreview --timeout 10s'*)
    printf 'video captured\n'
    ;;
  *'ffprobe -v error'*)
    printf '%s\n' "$FAKE_FFPROBE"
    ;;
  *'sha256sum '*)
    printf '%s\n' "${FAKE_REMOTE_SHA:-$FAKE_SAMPLE_SHA}"
    ;;
  *'rm -f /var/tmp/imx708-'*) exit 0 ;;
  'sudo -n /usr/bin/systemctl reboot')
    index=0
    [[ ! -f "$CAMERA_CONTROL/boot-index" ]] ||
      index="$(<"$CAMERA_CONTROL/boot-index")"
    printf '%s\n' "$((index + 1))" > "$CAMERA_CONTROL/boot-index"
    printf '%s\n' "${FAKE_REBOOT_SERVICE:-active}" > "$CAMERA_CONTROL/service-state"
    touch "$CAMERA_CONTROL/down-pending"
    ;;
  'sudo -n /usr/bin/journalctl -b --no-pager'|\
  'sudo -n /usr/bin/journalctl -b -1 --no-pager')
    [[ ! -e "$CAMERA_EVIDENCE/PASS" ]] ||
      touch "$CAMERA_CONTROL/pass-before-diagnostics"
    printf 'camera diagnostic journal\n'
    ;;
  *) printf 'unexpected remote command: %s\n' "$command" >&2; exit 97 ;;
esac
""",
        )
        self._write_executable(
            self.root / "scripts/discover-rpi5.sh",
            """#!/usr/bin/env bash
set -euo pipefail
printf 'discover %s\n' "$*" >> "$TEST_CALLS"
printf '%s\n' "${FAKE_DISCOVERED_HOST:-192.0.2.21}"
""",
        )

    def test_success_captures_samples_and_revalidates_after_one_reboot(
        self,
    ) -> None:
        """Catches promotion without complete IMX708 capture and recovery."""
        self._ready_prerequisites()
        self._install_success_commands()

        result, control, evidence = self._run_ready_acceptance()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((evidence / "PASS").is_file())
        self.assertFalse((control / "pass-before-diagnostics").exists())
        attestation = (evidence / "operator-wide-label.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("camera_module=Camera Module 3 Wide", attestation)
        self.assertIn("label_confirmed_by_operator=yes", attestation)
        samples = evidence / "samples"
        self.assertEqual(
            sorted(path.name for path in samples.iterdir()),
            [
                "SHA256SUMS",
                "imx708-initial.jpg",
                "imx708-post-reboot.jpg",
                "imx708-wide-1080p30.mp4",
            ],
        )
        checksum_result = subprocess.run(
            ["sha256sum", "--check", "SHA256SUMS"],
            cwd=samples,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(checksum_result.returncode, 0, checksum_result.stderr)
        self.assertEqual(
            (evidence / "health.log").read_text(encoding="utf-8").count(
                "temperature_millic="
            ),
            3,
        )
        summary = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["build_id"], BUILD_ID)
        self.assertEqual(summary["sensor"], "imx708")
        self.assertEqual(summary["lens_variant"], "wide-operator-verified")
        self.assertEqual(summary["h264"], "libx264-1920x1080-30fps")
        self.assertEqual(summary["result"], "PASS")

        calls = self.calls.read_text(encoding="utf-8")
        self.assertEqual(calls.count("sudo -n /usr/bin/systemctl reboot"), 1)
        discovery_calls = [
            line for line in calls.splitlines() if line.startswith("discover ")
        ]
        self.assertEqual(len(discovery_calls), 1)
        timeout_match = re.search(
            r" --timeout ([0-9]+)(?: |$)",
            discovery_calls[0],
        )
        self.assertIsNotNone(timeout_match, discovery_calls[0])
        self.assertIn(int(timeout_match.group(1)), range(1, 121))
        normalized_calls = re.sub(r"\s+", " ", calls)
        for expected in (
            "rpicam-hello --list-cameras",
            "rpicam-still --nopreview --autofocus-mode auto --timeout 2s",
            "rpicam-vid --nopreview --timeout 10s --width 1920 --height 1080",
            "--codec libav --libav-format mp4 --libav-video-codec libx264",
            "ffprobe -v error",
            "media-ctl -p",
            "sha256sum",
            "journalctl -b -1 --no-pager",
            "HostKeyAlias=192.0.2.20",
        ):
            self.assertIn(expected, normalized_calls)
        for diagnostic in (
            "diagnostic-journal.log",
            "diagnostic-journal-previous.log",
            "diagnostic-dmesg.log",
            "diagnostic-rpicam-version.log",
            "diagnostic-camera-list.log",
            "diagnostic-media-topology.log",
        ):
            self.assertTrue((evidence / diagnostic).is_file(), diagnostic)

    def test_active_service_is_released_for_both_captures_and_restored(self) -> None:
        """Catches captures racing the application, including after reboot."""
        self._ready_prerequisites()
        self._install_success_commands()
        result, control, evidence = self._run_ready_acceptance(FAKE_ENFORCE_SERVICE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((control / "service-state").read_text().strip(), "active")
        calls = self.calls.read_text()
        self.assertEqual(calls.count("systemctl stop camera-firmware.service"), 2)
        self.assertEqual(calls.count("systemctl start camera-firmware.service"), 2)
        self.assertTrue((evidence / "PASS").is_file())

    def test_failed_or_interrupted_capture_restores_initially_active_service(self) -> None:
        """Catches cleanup omitted on command failure, INT, HUP or TERM."""
        self._ready_prerequisites()
        self._install_success_commands()
        cases = [{"FAKE_CAPTURE_FAIL": "1"}, {"FAKE_CAPTURE_SIGNAL": "TERM"},
                 {"FAKE_CAPTURE_SIGNAL": "INT"}, {"FAKE_CAPTURE_SIGNAL": "HUP"}]
        cases += [dict(extra, FAKE_POST_CAPTURE_ONLY="1") for extra in cases]
        for extra in cases:
            with self.subTest(extra=extra):
                result, control, evidence = self._run_ready_acceptance(**extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue((control / "service-state").is_file())
                self.assertEqual((control / "service-state").read_text().strip(), "active")
                self.assertIn("systemctl start camera-firmware.service", self.calls.read_text())
                self.assertFalse((evidence / "PASS").exists())

    def test_initially_inactive_service_is_never_started_even_after_autostart(self) -> None:
        """Catches cleanup or reboot restoration starting an operator-stopped app."""
        self._ready_prerequisites()
        self._install_success_commands()
        result, control, evidence = self._run_ready_acceptance(
            FAKE_INITIAL_SERVICE="inactive", FAKE_ENFORCE_SERVICE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((control / "service-state").read_text().strip(), "inactive")
        self.assertNotIn("systemctl start camera-firmware.service", self.calls.read_text())
        self.assertTrue((evidence / "PASS").exists())

    def test_failed_service_restore_prevents_pass(self) -> None:
        """Catches successful captures concealing a failed service restoration."""
        self._ready_prerequisites()
        self._install_success_commands()
        result, _, evidence = self._run_ready_acceptance(FAKE_START_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("camera service restoration failed", result.stderr)
        self.assertFalse((evidence / "PASS").exists())

    def test_multiline_root_identity_fails_before_service_control(self) -> None:
        """Catches read consuming a valid first line and hiding trailing identity data."""
        self._ready_prerequisites()
        self._install_success_commands()
        result, _, evidence = self._run_ready_acceptance(
            FAKE_ROOT_INFO="/dev/sda2|/dev/sda|usb|CAMERA-ROOT-UUID\nhidden-data")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((evidence / "PASS").exists())
        calls = self.calls.read_text()
        self.assertNotIn("systemctl stop camera-firmware.service", calls)
        self.assertNotIn("systemctl start camera-firmware.service", calls)

    def test_post_reboot_state_query_failure_keeps_restoration_obligation(self) -> None:
        """Catches cleanup remaining disarmed if the first post-boot query fails."""
        self._ready_prerequisites()
        self._install_success_commands()
        for failure in ("transient", "persistent"):
            with self.subTest(failure=failure):
                result, control, evidence = self._run_ready_acceptance(
                    FAKE_INITIAL_SERVICE="inactive", FAKE_POST_STATE_QUERY_FAIL=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((evidence / "PASS").exists())
                self.assertNotIn("systemctl start camera-firmware.service", self.calls.read_text())
                if failure == "transient":
                    self.assertEqual((control / "service-state").read_text().strip(), "inactive")
                    self.assertEqual((evidence / "service.log").read_text().count("restored_state=inactive"), 2)
                else:
                    self.assertIn("camera service restoration failed; operator recovery required", result.stderr)

    def test_signal_before_post_reboot_release_restores_initially_inactive_service(self) -> None:
        """Catches the interruption gap between verified reconnect and release."""
        self._ready_prerequisites()
        self._install_success_commands()
        signal_script = self.root / "before-release-signal.sh"
        signal_script.write_text(
            "trap 'if [[ \"${BASH_COMMAND:-}\" == release_camera_service && "
            "-f \"$CAMERA_CONTROL/boot-index\" ]]; then "
            "kill -\"$FAKE_BEFORE_RELEASE_SIGNAL\" \"$$\"; fi' DEBUG\n", encoding="utf-8")
        for signal_name, expected_status in (("INT", 130), ("TERM", 143), ("HUP", 129)):
            with self.subTest(signal=signal_name):
                result, control, evidence = self._run_ready_acceptance(
                    FAKE_INITIAL_SERVICE="inactive", FAKE_BEFORE_RELEASE_SIGNAL=signal_name,
                    BASH_ENV=str(signal_script))
                self.assertEqual(result.returncode, expected_status, result.stderr)
                self.assertEqual((control / "service-state").read_text().strip(), "inactive")
                self.assertNotIn("systemctl start camera-firmware.service", self.calls.read_text())
                self.assertFalse((evidence / "PASS").exists())

    def test_unverified_recovery_warns_without_service_control(self) -> None:
        """Catches stale pre-boot identity authorizing cleanup on a different root."""
        self._ready_prerequisites()
        self._install_success_commands()
        for extra in ({"FAKE_CHANGE_ROOT_UUID": "1"}, {"FAKE_DISCOVERED_HOST": "not-an-ip"}):
            with self.subTest(extra=extra):
                result, control, evidence = self._run_ready_acceptance(
                    FAKE_INITIAL_SERVICE="inactive", **extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((control / "service-state").read_text().strip(), "active")
                self.assertIn("camera service restoration failed; operator recovery required", result.stderr)
                post_reboot_calls = self.calls.read_text().split("systemctl reboot", 1)[1]
                self.assertNotIn("systemctl stop camera-firmware.service", post_reboot_calls)
                self.assertNotIn("systemctl start camera-firmware.service", post_reboot_calls)
                self.assertFalse((evidence / "PASS").exists())

    def test_failed_stop_prevents_direct_capture(self) -> None:
        """Catches capture proceeding after stop permission or operation failure."""
        self._ready_prerequisites()
        self._install_success_commands()
        result, control, evidence = self._run_ready_acceptance(FAKE_STOP_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((control / "service-state").read_text().strip(), "active")
        self.assertNotIn("rpicam-still --nopreview", self.calls.read_text())
        self.assertFalse((evidence / "PASS").exists())

    def test_reboot_key_change_cannot_replace_initial_host_identity(self) -> None:
        """Catches ssh-keyscan silently trusting a replacement device on recovery."""
        self._ready_prerequisites()
        self._install_success_commands()
        timewarp = self.root / "timewarp.sh"
        timewarp.write_text(
            "set -T\ntrap 'case \"${BASH_COMMAND:-}\" in \"sleep 2\") "
            "SECONDS=$((SECONDS + 121));; esac' DEBUG\n", encoding="utf-8")
        result, _, evidence = self._run_ready_acceptance(
            FAKE_CHANGE_HOST_KEY="1", BASH_ENV=str(timewarp))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pinned SSH identity", result.stderr)
        self.assertFalse((evidence / "PASS").exists())
        calls = self.calls.read_text()
        self.assertEqual(sum(line.startswith("ssh-keyscan ") for line in calls.splitlines()), 2)

    def test_inactive_service_remains_inactive_after_failed_capture(self) -> None:
        """Catches failure cleanup starting an initially stopped service."""
        self._ready_prerequisites()
        self._install_success_commands()
        for post_only in ("0", "1"):
            with self.subTest(post_reboot=post_only):
                result, control, evidence = self._run_ready_acceptance(
                    FAKE_INITIAL_SERVICE="inactive", FAKE_CAPTURE_FAIL="1",
                    FAKE_POST_CAPTURE_ONLY=post_only)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((control / "service-state").read_text().strip(), "inactive")
                self.assertNotIn("systemctl start camera-firmware.service", self.calls.read_text())
                self.assertFalse((evidence / "PASS").exists())

    def test_invalid_video_metadata_is_rejected_and_service_restored(self) -> None:
        """Catches absent timestamps, empty streams and unverified video shape."""
        self._ready_prerequisites()
        self._install_success_commands()
        cases = ["not JSON", "{}", '{"streams": []}']
        for field, value in (("codec_name", "hevc"), ("width", 1280), ("height", 720),
                             ("r_frame_rate", "0/0"), ("avg_frame_rate", "0/0"),
                             ("nb_read_frames", "0"), ("nb_read_frames", "N/A"),
                             ("duration", "N/A"), ("duration", "0"),
                             ("duration", "1.0"), ("duration", "NaN")):
            metadata = json.loads(json.dumps(VIDEO_METADATA))
            metadata["streams"][0][field] = value
            cases.append(json.dumps(metadata))
        for field in ("duration", "nb_read_frames", "avg_frame_rate", "r_frame_rate"):
            metadata = json.loads(json.dumps(VIDEO_METADATA))
            del metadata["streams"][0][field]
            cases.append(json.dumps(metadata))
        for field, value in (("duration", "N/A"), ("duration", "8"),
                             ("format_name", "h264")):
            metadata = json.loads(json.dumps(VIDEO_METADATA))
            metadata["format"][field] = value
            cases.append(json.dumps(metadata))
        for value in cases:
            with self.subTest(metadata=value):
                result, control, evidence = self._run_ready_acceptance(FAKE_FFPROBE=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid camera video metadata", result.stderr)
                self.assertEqual((control / "service-state").read_text().strip(), "active")
                self.assertFalse((evidence / "PASS").exists())

    def test_hailo_capture_uses_separate_evidence_and_records_profile(self) -> None:
        """Catches Hailo capture overwriting or consuming normal camera PASS."""
        self._ready_prerequisites("rpi5-camera-hailo")
        self._install_success_commands()
        standard_pass = self._marker("camera-test/PASS")
        standard_pass.write_text("standard accepted\n", encoding="utf-8")

        result, _, evidence = self._run_ready_acceptance(profile="rpi5-camera-hailo")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence.name, "camera-hailo-test")
        self.assertTrue((evidence / "PASS").is_file())
        self.assertEqual(standard_pass.read_text(encoding="utf-8"), "standard accepted\n")
        summary = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["profile"], "rpi5-camera-hailo")
        self.assertEqual(summary["result"], "PASS")
        self.assertNotIn("hailo_inference", summary)

        repeated = self._acceptance(profile="rpi5-camera-hailo")
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("camera PASS already exists", repeated.stderr)

    def test_hailo_profile_requires_its_own_build_and_flash(self) -> None:
        """Catches normal camera markers being accepted for the variant."""
        self._ready_prerequisites()
        for marker, expected in (
            ("rpi5-camera-hailo/COMPLETE", "camera image PASS marker missing"),
            ("flash/rpi5-camera-hailo-PASS", "camera flash PASS marker missing"),
        ):
            result = self._acceptance(profile="rpi5-camera-hailo")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(expected, result.stderr)
            self.assertFalse(self.calls.exists())
            self.assertFalse((self.root / "artifacts" / BUILD_ID / "camera-hailo-test").exists())
            self._marker(marker)

    def test_unknown_camera_profile_stops_before_network(self) -> None:
        """Catches unknown profiles falling through to standard evidence."""
        result = self._acceptance(profile="rpi5-minimal")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid camera profile", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_capture_rejects_wrong_or_absent_booted_profile(self) -> None:
        """Catches camera images with a shared build ID attesting another profile."""
        self._install_success_commands()
        for selected_profile, remote_profile in (
            ("rpi5-camera-hailo", "rpi5-camera"),
            ("rpi5-camera", "rpi5-camera-hailo"),
            ("rpi5-camera-hailo", ""),
        ):
            with self.subTest(selected=selected_profile, remote=remote_profile):
                self._ready_prerequisites(selected_profile)
                result, _, evidence = self._run_ready_acceptance(
                    profile=selected_profile, FAKE_REMOTE_PROFILE=remote_profile,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("camera image profile mismatch", result.stderr)
                self.assertFalse((evidence / "PASS").exists())

    def test_hailo_capture_rechecks_booted_profile_after_reboot(self) -> None:
        """Catches recovery into a different profile with the same build ID."""
        self._ready_prerequisites("rpi5-camera-hailo")
        self._install_success_commands()
        result, _, evidence = self._run_ready_acceptance(
            profile="rpi5-camera-hailo", FAKE_CHANGE_REMOTE_PROFILE="1",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("camera image profile mismatch", result.stderr)
        self.assertFalse((evidence / "PASS").exists())

    def test_failed_camera_invariant_is_fail_closed_with_diagnostics(self) -> None:
        """Catches unsafe promotion when a required camera invariant is false."""
        self._ready_prerequisites()
        self._install_success_commands()
        cases = (
            ("FAKE_REMOTE_BUILD_ID", "wrong-build", "build ID mismatch"),
            ("FAKE_SYSTEMD", "degraded", "systemd is not running"),
            (
                "FAKE_ROOT_INFO",
                "/dev/mmcblk0p2|/dev/mmcblk0|mmc|ROOT-UUID",
                "root is not /dev/sda2",
            ),
            ("FAKE_DMESG", "unicam cfe only", "no IMX708 evidence"),
            ("FAKE_DMESG", "imx708 only", "no camera pipeline evidence"),
            ("FAKE_MEDIA", "camera topology", "no IMX708 entity"),
            ("FAKE_CAMERA_LIST", "No cameras available", "not enumerated"),
            ("FAKE_CAMERA_LIST", "0 : imx708", "modes were not listed"),
            ("FAKE_TEMPERATURE", "85000", "temperature reached 85 C"),
            ("FAKE_FFPROBE", "{}", "invalid camera video metadata"),
            ("FAKE_REMOTE_SHA", "invalid", "invalid remote checksum"),
            ("FAKE_REMOTE_SHA", "0" * 64, "copy checksum mismatch"),
        )

        for variable, value, expected_error in cases:
            with self.subTest(variable=variable, value=value):
                result, _, evidence = self._run_ready_acceptance(
                    **{variable: value},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse((evidence / "PASS").exists())
                self.assertTrue((evidence / "diagnostic-journal.log").is_file())

    def test_recovery_rejects_wrong_system_after_reboot(self) -> None:
        """Catches reboot recovery that returns to a different camera system."""
        self._ready_prerequisites()
        self._install_success_commands()
        for variable, value, expected_error in (
            (
                "FAKE_CHANGE_ROOT_UUID",
                "1",
                "root filesystem changed across reboot",
            ),
            ("FAKE_REPEAT_BOOT_ID", "1", "camera reboot did not occur"),
            (
                "FAKE_POST_CAMERA_MISSING",
                "1",
                "IMX708 was not enumerated",
            ),
            (
                "FAKE_DISCOVERED_HOST",
                "not-an-ip",
                "discovery returned an invalid IPv4 address",
            ),
        ):
            with self.subTest(variable=variable):
                result, _, evidence = self._run_ready_acceptance(
                    **{variable: value},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse((evidence / "PASS").exists())

    def test_reboot_budget_expiry_stops_before_discovery(self) -> None:
        """Catches recovery continuing after its 120-second deadline."""
        self._ready_prerequisites()
        self._install_success_commands()
        timewarp = self.root / "timewarp.sh"
        timewarp.write_text(
            "trap 'case \"${BASH_COMMAND:-}\" in "
            "remaining=*) SECONDS=$((SECONDS + 121));; esac' DEBUG\n",
            encoding="utf-8",
        )

        result, _, evidence = self._run_ready_acceptance(
            BASH_ENV=str(timewarp),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("camera reboot exceeded 120 seconds", result.stderr)
        self.assertFalse((evidence / "PASS").exists())
        calls = self.calls.read_text(encoding="utf-8")
        self.assertNotIn("discover ", calls)

    def test_existing_pass_is_immutable_and_prevents_network_access(self) -> None:
        """Catches accidental reruns that overwrite accepted camera evidence."""
        self._ready_prerequisites()
        self._install_success_commands()
        evidence = self.root / "artifacts" / BUILD_ID / "camera-test"
        evidence.mkdir()
        pass_marker = evidence / "PASS"
        pass_marker.write_text("accepted\n", encoding="utf-8")

        result = self._acceptance()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("camera PASS already exists", result.stderr)
        self.assertEqual(pass_marker.read_text(encoding="utf-8"), "accepted\n")
        self.assertFalse(self.calls.exists())

    def test_revision_key_and_prerequisite_gates_precede_evidence_and_network(
        self,
    ) -> None:
        """Catches camera work starting before immutable prerequisites pass."""
        evidence = self.root / "artifacts" / BUILD_ID / "camera-test"

        mismatch = self._acceptance("20990101T000000Z-deadbeefcafe")
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("does not match HEAD", mismatch.stderr)
        self.assertFalse(evidence.exists())
        self.assertFalse(self.calls.exists())

        self.key.unlink()
        missing_key = self._acceptance()
        self.assertNotEqual(missing_key.returncode, 0)
        self.assertIn("private key missing", missing_key.stderr)
        self.assertFalse(evidence.exists())
        self.key.write_text("private\n", encoding="utf-8")
        self.key.chmod(0o600)

        for marker, expected in (
            ("rpi5-test/PASS", "phase-1 hardware PASS marker missing"),
            ("rpi5-camera/COMPLETE", "camera image PASS marker missing"),
            ("flash/rpi5-camera-PASS", "camera flash PASS marker missing"),
        ):
            result = self._acceptance()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(expected, result.stderr)
            self.assertFalse(evidence.exists())
            self.assertFalse(self.calls.exists())
            self._marker(marker)


if __name__ == "__main__":
    unittest.main()
