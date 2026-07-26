from __future__ import annotations

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


class RaspberryPiAcceptanceContractTest(unittest.TestCase):
    def test_help_is_non_mutating_and_script_is_valid_bash(self) -> None:
        """Catches help processing that reaches hardware gates or invalid Bash."""
        self.assertTrue(
            os.access(REPO_ROOT / "scripts/test-rpi5.sh", os.X_OK),
            "test-rpi5.sh must be executable",
        )
        help_result = run("bash", "scripts/test-rpi5.sh", "--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Usage:", help_result.stdout)
        self.assertEqual(help_result.stderr, "")

        syntax = run("bash", "-n", "scripts/test-rpi5.sh")
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_truncated_value_options_print_usage_without_nounset_errors(self) -> None:
        """Catches reading a missing CLI value under nounset."""
        for option in (
            "--build-id",
            "--host",
            "--hostname",
            "--port",
            "--key",
            "--lease-file",
            "--mac",
        ):
            with self.subTest(option=option):
                result = run("bash", "scripts/test-rpi5.sh", option)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Usage:", result.stderr)
                self.assertNotIn("unbound variable", result.stderr)

    def test_invalid_inputs_fail_before_keys_or_evidence_are_read(self) -> None:
        """Catches malformed operator input reaching hardware prerequisites."""
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
                    ("--build-id", build_id, "--host", "999.0.0.1"),
                    "invalid initial host",
                ),
                (
                    (
                        "--build-id",
                        build_id,
                        "--host",
                        "192.0.2.10",
                        "--port",
                        "65536",
                    ),
                    "invalid SSH port",
                ),
                (
                    (
                        "--build-id",
                        build_id,
                        "--host",
                        "192.0.2.10",
                        "--hostname",
                        "bad/name",
                    ),
                    "invalid hostname",
                ),
                (
                    (
                        "--build-id",
                        build_id,
                        "--host",
                        "192.0.2.10",
                        "--mac",
                        "not-a-mac",
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
                    ),
                    "lease file is not a readable regular file",
                ),
            )
            for arguments, expected_error in cases:
                with self.subTest(arguments=arguments):
                    result = run("bash", "scripts/test-rpi5.sh", *arguments)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected_error, result.stderr)
                    self.assertNotIn("private key missing", result.stderr)
                    self.assertNotIn("PASS marker missing", result.stderr)


class RaspberryPiAcceptanceExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="rpi5-contract-")
        self.root = Path(self.temporary.name) / "checkout"
        (self.root / "scripts/lib").mkdir(parents=True)
        (self.root / "keys").mkdir()
        for relative in (
            "scripts/test-rpi5.sh",
            "scripts/discover-rpi5.sh",
            "scripts/lib/common.sh",
            "scripts/lib/remote.sh",
        ):
            source = REPO_ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        self.key = self.root / "keys/rpi5_admin"
        self.key.write_text("private\n", encoding="utf-8")
        self.key.chmod(0o600)
        (self.root / "keys/rpi5_admin.pub").write_text(
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest rpi5-contract\n",
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

    def _acceptance(self, build_id: str = BUILD_ID) -> subprocess.CompletedProcess[str]:
        return self._run(
            "bash",
            "scripts/test-rpi5.sh",
            "--build-id",
            build_id,
            "--host",
            "192.0.2.10",
        )

    def _marker(self, relative: str) -> Path:
        marker = self.root / "artifacts" / BUILD_ID / relative
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return marker

    def _ready_prerequisites(self) -> None:
        for relative in (
            "qemu-test/PASS",
            "rpi5-minimal/COMPLETE",
            "flash/rpi5-minimal-PASS",
        ):
            self._marker(relative)

    def _reset_runtime(self) -> tuple[Path, Path]:
        control = self.root / "control"
        evidence = self.root / "artifacts" / BUILD_ID / "rpi5-test"
        shutil.rmtree(control, ignore_errors=True)
        shutil.rmtree(evidence, ignore_errors=True)
        control.mkdir()
        self.calls.unlink(missing_ok=True)
        return control, evidence

    def _run_ready_acceptance(
        self,
        **extra: str,
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        control, evidence = self._reset_runtime()
        environment = {
            "RPI5_CONTROL": str(control),
            "RPI5_EVIDENCE": str(evidence),
            "FAKE_BUILD_ID": BUILD_ID,
        }
        environment.update(extra)
        result = self._run(
            "bash",
            "scripts/test-rpi5.sh",
            "--build-id",
            BUILD_ID,
            "--host",
            "192.0.2.10",
            **environment,
        )
        return result, control, evidence

    def _install_success_commands(self) -> None:
        self._write_executable(
            self.fake_bin / "ssh-keyscan",
            """#!/usr/bin/env bash
printf 'ssh-keyscan %s\n' "$*" >> "$TEST_CALLS"
if [[ -f "$RPI5_CONTROL/down-pending" ]]; then
  rm -f "$RPI5_CONTROL/down-pending"
  exit 1
fi
printf 'rpi5-host ssh-ed25519 AAAATEST\n'
""",
        )
        self._write_executable(
            self.fake_bin / "ssh",
            """#!/usr/bin/env bash
printf 'ssh %s\n' "$*" >> "$TEST_CALLS"
all=" $* "
command="${!#}"
if [[ "$all" == *" root@"* ]]; then
  [[ "${FAKE_ALLOW_ROOT:-0}" == "1" ]] || exit 255
fi
if [[ "$all" == *" -o PubkeyAuthentication=no "* ]]; then
  [[ "${FAKE_ALLOW_PASSWORD:-0}" == "1" ]] || exit 255
fi
case "$command" in
  true) exit 0 ;;
  'uname -m') printf '%s\n' "${FAKE_ARCHITECTURE:-aarch64}" ;;
  *'/proc/device-tree/model'*)
    printf '%s\n' "${FAKE_MODEL:-Raspberry Pi 5 Model B Rev 1.0}"
    ;;
  'cat /etc/rpi5-build-id') printf '%s\n' "$FAKE_BUILD_ID" ;;
  'systemctl is-system-running'|'systemctl is-system-running --wait')
    printf '%s\n' "${FAKE_SYSTEMD:-running}"
    ;;
  'systemctl is-active systemd-networkd.service') printf 'active\n' ;;
  'systemctl is-active sshd.socket') printf 'active\n' ;;
  *'ip -4 -o address show scope global'*) printf '2: eth0 inet 192.0.2.10/24\n' ;;
  *'ip -4 route show default'*)
    printf '%s\n' "${FAKE_DEFAULT_INTERFACE:-eth0}"
    ;;
  *'/sys/class/net/'*'/carrier'*) printf '1\n' ;;
  *'root_source=$(findmnt'*)
    root_info="${FAKE_ROOT_INFO:-/dev/sda2|/dev/sda|usb|ROOT-UUID}"
    if [[ "${FAKE_CHANGE_ROOT_UUID:-0}" == "1" &&
          -f "$RPI5_CONTROL/boot-index" &&
          "$(<"$RPI5_CONTROL/boot-index")" -gt 0 ]]; then
      root_info='/dev/sda2|/dev/sda|usb|CHANGED-ROOT-UUID'
    fi
    printf '%s\n' "$root_info"
    ;;
  *'lsblk -ndo NAME'*)
    [[ "${FAKE_MMC_PRESENT:-0}" == "1" ]] || exit 1
    printf 'mmcblk0\n'
    ;;
  *'findmnt -n -o OPTIONS /'*) printf 'rw\n' ;;
  *'/var/tmp/rpi5-rw-test'*) printf '%s\n' "$FAKE_BUILD_ID" ;;
  *'passwordauthentication'*)
    printf '%s\n' "${FAKE_PASSWORD_AUTHENTICATION:-no}"
    ;;
  *'kbdinteractiveauthentication'*) printf 'no\n' ;;
  *'permitrootlogin'*) printf 'no\n' ;;
  *'authenticationmethods'*) printf 'publickey\n' ;;
  *'allowusers'*) printf 'rpiadmin\n' ;;
  *'passwd -S rpiadmin'*) printf '%s\n' "${FAKE_ACCOUNT_STATUS:-L}" ;;
  'cat /proc/sys/kernel/random/boot_id')
    index=0
    [[ ! -f "$RPI5_CONTROL/boot-index" ]] ||
      index="$(<"$RPI5_CONTROL/boot-index")"
    [[ "${FAKE_REPEAT_BOOT_ID:-0}" != "1" ]] || index=0
    printf '00000000-0000-4000-8000-%012d\n' "$index"
    ;;
  'sudo -n /usr/bin/systemctl reboot')
    index=0
    [[ ! -f "$RPI5_CONTROL/boot-index" ]] ||
      index="$(<"$RPI5_CONTROL/boot-index")"
    printf '%s\n' "$((index + 1))" > "$RPI5_CONTROL/boot-index"
    touch "$RPI5_CONTROL/down-pending"
    ;;
  'sudo -n /usr/bin/journalctl -b --no-pager'|\
  'sudo -n /usr/bin/journalctl -b -1 --no-pager'|\
  'sudo -n /usr/bin/dmesg'|\
  'lsblk -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,FSTYPE,UUID,MOUNTPOINTS'|\
  'findmnt --real'|\
  'networkctl status --no-pager')
    [[ ! -e "$RPI5_EVIDENCE/PASS" ]] ||
      touch "$RPI5_CONTROL/pass-before-diagnostics"
    printf 'diagnostic %s\n' "$command"
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
count=0
[[ ! -f "$RPI5_CONTROL/discovery-count" ]] ||
  count="$(<"$RPI5_CONTROL/discovery-count")"
count=$((count + 1))
printf '%s\n' "$count" > "$RPI5_CONTROL/discovery-count"
if [[ -n "${FAKE_DISCOVERED_HOST:-}" ]]; then
  printf '%s\n' "$FAKE_DISCOVERED_HOST"
else
  printf '192.0.2.%s\n' "$((10 + count))"
fi
""",
        )

    def test_success_checks_initial_boot_and_exactly_three_recoveries(self) -> None:
        """Catches promotion without complete USB, network, SSH, and reboot checks."""
        self._ready_prerequisites()
        self._install_success_commands()
        result, control, evidence = self._run_ready_acceptance()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((evidence / "PASS").is_file())
        self.assertFalse((control / "pass-before-diagnostics").exists())
        self.assertEqual(
            sorted(path.name for path in evidence.glob("boot-*.log")),
            [
                "boot-initial.log",
                "boot-reboot-1.log",
                "boot-reboot-2.log",
                "boot-reboot-3.log",
            ],
        )
        self.assertEqual(
            (evidence / "reboots.log").read_text(encoding="utf-8").count(
                "elapsed_seconds="
            ),
            3,
        )
        summary = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["build_id"], BUILD_ID)
        self.assertEqual(summary["reboots"], 3)
        self.assertEqual(len(set(summary["reboot_boot_ids"])), 3)
        self.assertNotIn(summary["initial_boot_id"], summary["reboot_boot_ids"])
        calls = self.calls.read_text(encoding="utf-8")
        self.assertEqual(calls.count("sudo -n /usr/bin/systemctl reboot"), 3)
        discovery_calls = [
            line for line in calls.splitlines() if line.startswith("discover ")
        ]
        self.assertEqual(len(discovery_calls), 3)
        for call in discovery_calls:
            match = re.search(r" --timeout ([0-9]+)(?: |$)", call)
            self.assertIsNotNone(match, call)
            self.assertIn(int(match.group(1)), range(1, 121))
        for expected in (
            "systemctl is-active sshd.socket",
            "sudo -n /usr/sbin/sshd -T",
            "authenticationmethods",
            "passwd -S rpiadmin",
            "root_source=$(findmnt",
            "findmnt -n -o OPTIONS /",
            "journalctl -b -1 --no-pager",
        ):
            self.assertIn(expected, calls)
        for diagnostic in (
            "journal-current.log",
            "journal-previous.log",
            "dmesg.log",
            "lsblk.log",
            "findmnt.log",
            "networkctl.log",
        ):
            self.assertTrue((evidence / diagnostic).is_file(), diagnostic)

    def test_failed_acceptance_is_fail_closed_and_collects_diagnostics(self) -> None:
        """Catches unsafe promotion when a required boot invariant is false."""
        self._ready_prerequisites()
        self._install_success_commands()
        cases = (
            ("FAKE_ARCHITECTURE", "x86_64", "architecture expected"),
            ("FAKE_MODEL", "Raspberry Pi 4 Model B", "unexpected board model"),
            ("FAKE_SYSTEMD", "degraded", "systemd expected"),
            (
                "FAKE_DEFAULT_INTERFACE",
                "wlan0",
                "default route is not on a wired interface",
            ),
            (
                "FAKE_ROOT_INFO",
                "/dev/mmcblk0p2|/dev/mmcblk0|mmc|ROOT-UUID",
                "root is not /dev/sda2",
            ),
            (
                "FAKE_ROOT_INFO",
                "/dev/sda2|/dev/sda|sata|ROOT-UUID",
                "root disk transport is not usb",
            ),
            ("FAKE_MMC_PRESENT", "1", "microSD must be removed"),
            (
                "FAKE_PASSWORD_AUTHENTICATION",
                "yes",
                "password_authentication expected",
            ),
            ("FAKE_ACCOUNT_STATUS", "P", "account_locked expected"),
            ("FAKE_ALLOW_ROOT", "1", "root SSH login unexpectedly succeeded"),
            (
                "FAKE_ALLOW_PASSWORD",
                "1",
                "non-key SSH login unexpectedly succeeded",
            ),
        )

        for variable, value, expected_error in cases:
            with self.subTest(variable=variable, value=value):
                result, _, evidence = self._run_ready_acceptance(
                    **{variable: value},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse((evidence / "PASS").exists())
                self.assertTrue((evidence / "journal-current.log").is_file())

    def test_recovery_rejects_changed_media_repeated_boot_and_bad_discovery(
        self,
    ) -> None:
        """Catches reboot recovery that did not return to the accepted system."""
        self._ready_prerequisites()
        self._install_success_commands()
        for variable, expected_error in (
            ("FAKE_CHANGE_ROOT_UUID", "root filesystem changed across reboot"),
            ("FAKE_REPEAT_BOOT_ID", "boot ID did not change"),
            ("FAKE_DISCOVERED_HOST", "discovery returned an invalid IPv4 address"),
        ):
            with self.subTest(variable=variable):
                value = "not-an-ip" if variable == "FAKE_DISCOVERED_HOST" else "1"
                result, _, evidence = self._run_ready_acceptance(
                    **{variable: value},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse((evidence / "PASS").exists())

    def test_reboot_budget_expiry_stops_before_discovery(self) -> None:
        """Catches a command substitution continuing after its deadline error."""
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
        self.assertIn("reboot 1 exceeded 120 seconds", result.stderr)
        self.assertFalse((evidence / "PASS").exists())
        calls = self.calls.read_text(encoding="utf-8")
        self.assertNotIn("discover ", calls)

    def test_existing_pass_is_immutable_and_prevents_network_access(self) -> None:
        """Catches accidental reruns that overwrite accepted evidence."""
        self._ready_prerequisites()
        self._install_success_commands()
        evidence = self.root / "artifacts" / BUILD_ID / "rpi5-test"
        evidence.mkdir()
        pass_marker = evidence / "PASS"
        pass_marker.write_text("accepted\n", encoding="utf-8")

        result = self._acceptance()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("phase-1 PASS already exists", result.stderr)
        self.assertEqual(pass_marker.read_text(encoding="utf-8"), "accepted\n")
        self.assertFalse(self.calls.exists())

    def test_revision_key_and_prerequisite_gates_precede_evidence_and_network(self) -> None:
        """Catches hardware work starting before immutable prerequisites pass."""
        evidence = self.root / "artifacts" / BUILD_ID / "rpi5-test"

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
            ("qemu-test/PASS", "QEMU PASS marker missing"),
            ("rpi5-minimal/COMPLETE", "minimal image PASS marker missing"),
            ("flash/rpi5-minimal-PASS", "minimal flash PASS marker missing"),
        ):
            result = self._acceptance()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(expected, result.stderr)
            self.assertFalse(evidence.exists())
            self.assertFalse(self.calls.exists())
            self._marker(marker)


if __name__ == "__main__":
    unittest.main()
