from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import unittest

from support import REPO_ROOT, run


REVISION = "0123456789ab"
BUILD_ID = f"20260725T120000Z-{REVISION}"


class QemuContractTest(unittest.TestCase):
    """Execution contracts for the key-only QEMU smoke gate."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qemu-contract-")
        self.root = Path(self.temporary.name) / "checkout"
        (self.root / "scripts" / "lib").mkdir(parents=True)
        (self.root / "keys").mkdir()
        shutil.copy2(REPO_ROOT / "scripts/lib/common.sh", self.root / "scripts/lib/common.sh")
        self.key = self.root / "keys/rpi5_admin"
        self.key.write_text("private\n", encoding="utf-8")
        self.key.chmod(0o600)
        (self.root / "keys/rpi5_admin.pub").write_text(
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest qemu-contract\n",
            encoding="utf-8",
        )
        self.fake_bin = self.root / "fake-bin"
        self.fake_bin.mkdir()
        self.calls = self.root / "calls.log"
        self.control = self.root / "control"
        self.control.mkdir()
        self._write_executable(
            self.fake_bin / "git",
            "#!/usr/bin/env bash\n"
            "if [[ \" $* \" == *\" rev-parse \"* ]]; then printf '%s\\n' \"$FAKE_REVISION\"; fi\n",
        )
        self._write_executable(self.fake_bin / "ssh-keygen", "#!/usr/bin/env bash\nexit 0\n")
        self._write_executable(
            self.fake_bin / "ssh-keyscan",
            "#!/usr/bin/env bash\nprintf 'qemu-host ssh-ed25519 AAAATEST\\n'\n",
        )
        self._write_executable(
            self.fake_bin / "ssh",
            """#!/usr/bin/env bash
printf 'ssh %s\\n' "$*" >> "$TEST_CALLS"
all=" $* "
command="${!#}"
if [[ "$all" == *" root@127.0.0.1 "* ]]; then exit 255; fi
if [[ "$all" == *" -o PubkeyAuthentication=no "* ]]; then exit 255; fi
case "$command" in
  true) exit 0 ;;
  'uname -m') printf '%s\\n' "${FAKE_ARCHITECTURE:-aarch64}" ;;
  'cat /etc/rpi5-build-id') printf '%s\\n' "$FAKE_BUILD_ID" ;;
  'systemctl is-system-running') printf 'running\\n' ;;
  'systemctl is-active systemd-networkd.service'|'systemctl is-active sshd.service') printf 'active\\n' ;;
  'systemctl --failed --no-pager') printf '0 loaded units listed.\\n' ;;
  'sudo -n /usr/bin/journalctl -b --no-pager') printf 'journal\\n' ;;
  *'ip -4 -o address show scope global'*) exit 0 ;;
  *'/var/tmp/qemu-rw-test'*) printf '%s\\n' "$RPI5_BUILD_ID" ;;
  *'/etc/ssh/sshd_config.d/20-rpi5.conf'*) printf 'PasswordAuthentication no\\nPermitRootLogin no\\n' ;;
  *'systemctl poweroff'*) touch "$QEMU_CONTROL/powered-off" ;;
esac
""",
        )
        self._write_executable(
            self.fake_bin / "scp",
            "#!/usr/bin/env bash\nprintf 'scp %s\\n' \"$*\" >> \"$TEST_CALLS\"\nexit 0\n",
        )
        self._write_executable(
            self.fake_bin / "ss",
            "#!/usr/bin/env bash\nexit 0\n",
        )
        self._write_executable(
            self.fake_bin / "uv",
            """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "$TEST_CALLS"
if [[ " $* " != *" kas shell "* ]]; then exit 0; fi
printf '%s\\n' "$$" > "$QEMU_CONTROL/qemu-pid"
child=""
cleanup() {
  status="$?"
  [[ -n "$child" ]] && kill "$child" 2>/dev/null || true
  [[ -n "$child" ]] && wait "$child" 2>/dev/null || true
  touch "$QEMU_CONTROL/terminated"
  trap - EXIT
  exit "$status"
}
trap cleanup TERM INT EXIT
sleep 600 &
child="$!"
printf '%s\\n' "$child" > "$QEMU_CONTROL/qemu-child-pid"
if [[ "${FAKE_QEMU_MODE:-poweroff}" == "ignore" ]]; then
  while :; do sleep 1; done
fi
while [[ ! -e "$QEMU_CONTROL/powered-off" ]]; do sleep 0.05; done
if [[ "${FAKE_QEMU_LEAVE_CHILD:-0}" == "1" ]]; then
  trap - EXIT
  exit "${FAKE_QEMU_EXIT:-0}"
fi
exit "${FAKE_QEMU_EXIT:-0}"
""",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_executable(self, path: Path, contents: str) -> None:
        path.write_text(contents, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _copy_entrypoints(self) -> None:
        for relative in (
            "scripts/lib/remote.sh",
            "scripts/test-qemu-guest.sh",
            "scripts/test-qemu.sh",
        ):
            source = REPO_ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    def _environment(self, **extra: str) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("UV_PROJECT_ENVIRONMENT", None)
        environment.update(
            {
                "PATH": f"{self.fake_bin}:{environment['PATH']}",
                "TEST_CALLS": str(self.calls),
                "QEMU_CONTROL": str(self.control),
                "FAKE_REVISION": REVISION,
                "FAKE_BUILD_ID": BUILD_ID,
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

    def _guest(self, **extra: str) -> subprocess.CompletedProcess[str]:
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        return self._run(
            "bash", "scripts/test-qemu-guest.sh", "--build-id", BUILD_ID,
            "--key", str(self.key), "--evidence-dir", str(evidence), **extra,
        )

    def _ready_launcher(self) -> None:
        (self.root / "artifacts" / BUILD_ID / "qemu").mkdir(parents=True, exist_ok=True)
        (self.root / "artifacts" / BUILD_ID / "qemu/COMPLETE").touch()

    def _launcher(self, **extra: str) -> subprocess.CompletedProcess[str]:
        return self._run("bash", "scripts/test-qemu.sh", "--build-id", BUILD_ID, **extra)

    def _expired_clock_environment(self) -> Path:
        path = self.root / "expired-clock.sh"
        path.write_text(
            "kill() {\n"
            "    if [[ \"${1:-}\" == \"-0\" ]]; then\n"
            "        SECONDS=9999\n"
            "        return 0\n"
            "    fi\n"
            "    builtin kill \"$@\"\n"
            "}\n",
            encoding="utf-8",
        )
        return path

    def _wait_for(self, path: Path, timeout: float = 3) -> None:
        deadline = time.monotonic() + timeout
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(path.exists(), f"timed out waiting for {path}")

    def _wait_for_process_exit(self, pid: int, timeout: float = 3) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.02)
        self.fail(f"process {pid} survived launcher cleanup")

    def test_remote_wait_refreshes_known_host_and_uses_strict_key_only_ssh(self) -> None:
        """Catches accepting an unknown host or relaxing SSH authentication options."""
        self._copy_entrypoints()
        known_hosts = self.root / "known_hosts"
        result = self._run(
            "bash", "-c",
            "source scripts/lib/remote.sh; "
            f"rpi5_remote_init 127.0.0.1 2222 {self.key} {known_hosts}; "
            "rpi5_wait_ssh 1; rpi5_remote true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("qemu-host ssh-ed25519", known_hosts.read_text(encoding="utf-8"))
        calls = self.calls.read_text(encoding="utf-8")
        self.assertIn("StrictHostKeyChecking=yes", calls)
        self.assertIn("BatchMode=yes", calls)
        self.assertIn(f"UserKnownHostsFile={known_hosts}", calls)
        self.assertIn(f"-i {self.key}", calls)

    def test_guest_success_writes_complete_evidence_only_after_all_checks(self) -> None:
        """Catches a guest checker that promotes PASS without executing its assertions."""
        self._copy_entrypoints()
        result = self._guest()
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((evidence / "guest-PASS").is_file())
        self.assertIn('"architecture":"aarch64"', (evidence / "result.json").read_text())
        self.assertIn('"systemd":"running"', (evidence / "result.json").read_text())
        self.assertIn('"ssh":"key-only"', (evidence / "result.json").read_text())
        self.assertTrue((evidence / "systemd-failed.log").is_file())
        self.assertTrue((evidence / "journal.log").is_file())
        self.assertTrue((self.control / "powered-off").is_file())

    def test_guest_failure_never_writes_guest_pass_or_powers_off(self) -> None:
        """Catches marking an invalid guest successful after an assertion failure."""
        self._copy_entrypoints()
        result = self._guest(FAKE_ARCHITECTURE="x86_64")
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("architecture expected 'aarch64' but got 'x86_64'", result.stderr)
        self.assertFalse((evidence / "guest-PASS").exists())
        self.assertFalse((self.control / "powered-off").exists())

    def test_launcher_rejects_uv_override_and_head_mismatch_before_evidence(self) -> None:
        """Catches launching kas or creating qemu-test evidence before early gates."""
        self._copy_entrypoints()
        self._ready_launcher()
        override = self._launcher(UV_PROJECT_ENVIRONMENT="/tmp/override")
        self.assertNotEqual(override.returncode, 0)
        self.assertIn("UV_PROJECT_ENVIRONMENT must be unset or empty", override.stderr)
        self.assertFalse((self.root / "artifacts" / BUILD_ID / "qemu-test").exists())
        self.assertFalse(self.calls.exists())
        mismatch = self._launcher(FAKE_REVISION="deadbeefcafe")
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("does not match HEAD deadbeefcafe", mismatch.stderr)
        self.assertFalse((self.root / "artifacts" / BUILD_ID / "qemu-test").exists())
        self.assertFalse(self.calls.exists())

    def test_launcher_preserves_final_pass_and_replaces_stale_transient_pass(self) -> None:
        """Catches overwriting completed evidence or promoting stale failed-attempt state."""
        self._copy_entrypoints()
        self._ready_launcher()
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        evidence.mkdir()
        final = evidence / "PASS"
        final.write_text("immutable\n", encoding="utf-8")
        blocked = self._launcher()
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("QEMU PASS already exists", blocked.stderr)
        self.assertEqual(final.read_text(encoding="utf-8"), "immutable\n")
        self.assertFalse(self.calls.exists())
        final.unlink()
        stale = evidence / "guest-PASS"
        stale.write_text("stale\n", encoding="utf-8")
        result = self._launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(final.is_file())
        self.assertEqual(final.read_text(encoding="utf-8"), "")
        self.assertFalse(stale.exists())

    def test_launcher_failure_paths_do_not_promote_pass_and_terminate_qemu_group(self) -> None:
        """Catches leaked QEMU groups or PASS promotion after guest or QEMU failure."""
        self._copy_entrypoints()
        for name, extra in (
            ("guest", {"FAKE_ARCHITECTURE": "x86_64"}),
            ("qemu", {"FAKE_QEMU_EXIT": "42", "FAKE_QEMU_LEAVE_CHILD": "1"}),
        ):
            with self.subTest(name=name):
                self._ready_launcher()
                result = self._launcher(**extra)
                evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((evidence / "PASS").exists())
                if name == "guest":
                    self._wait_for(self.control / "terminated")
                else:
                    child_pid = int((self.control / "qemu-child-pid").read_text())
                    self._wait_for_process_exit(child_pid)
                shutil.rmtree(evidence, ignore_errors=True)
                (self.control / "powered-off").unlink(missing_ok=True)
                (self.control / "terminated").unlink(missing_ok=True)

    def test_launcher_kills_refusing_qemu_after_poweroff_without_promoting_pass(self) -> None:
        """Catches the timeout path leaking a QEMU process group or sealing PASS."""
        self._copy_entrypoints()
        self._ready_launcher()
        result = self._launcher(
            FAKE_QEMU_MODE="ignore",
            BASH_ENV=str(self._expired_clock_environment()),
        )
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("QEMU did not exit within 30 seconds", result.stderr)
        self.assertFalse((evidence / "PASS").exists())
        self._wait_for(self.control / "terminated")

    def test_qemu_scripts_are_valid_bash(self) -> None:
        """Catches syntax errors in any entry point before a runtime gate starts."""
        self._copy_entrypoints()
        for path in (
            "scripts/lib/remote.sh",
            "scripts/test-qemu-guest.sh",
            "scripts/test-qemu.sh",
        ):
            result = self._run("bash", "-n", path)
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
