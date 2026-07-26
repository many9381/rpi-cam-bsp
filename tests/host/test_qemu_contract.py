from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
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
        for relative in ("pyproject.toml", "uv.lock", "tests/host/qemu_listener.py"):
            source = REPO_ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        self.real_uv = shutil.which("uv")
        if self.real_uv is None:
            self.fail("uv is required for the locked listener helper")
        self.real_timeout = shutil.which("timeout")
        if self.real_timeout is None:
            self.fail("timeout is required for the bounded guest-check helper")
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
if [[ "$command" == "${FAKE_HANG_COMMAND:-}" ]]; then
  printf '%s\n' "$$" > "$QEMU_CONTROL/guest-hang-pid"
  trap '' TERM INT
  while :; do sleep 1; done
fi
if [[ "$command" == *'authenticationmethods'* ]]; then
  filter="${command#*| }"
  printf '%s\n' "authenticationmethods ${FAKE_AUTHENTICATION_METHODS:-publickey}" |
    bash -c "$filter"
  exit $?
fi
if [[ "$all" == *" root@127.0.0.1 "* ]]; then
  [[ "${FAKE_ROOT_LOGIN_SUCCEEDS:-0}" == "1" ]] && exit 0
  exit 255
fi
if [[ "$all" == *" -o PubkeyAuthentication=no "* ]]; then
  [[ "${FAKE_NO_KEY_LOGIN_SUCCEEDS:-0}" == "1" ]] && exit 0
  exit 255
fi
case "$command" in
	  true)
	    if [[ "${FAKE_WAIT_FOR_LISTENER:-0}" == "1" ]]; then
	      deadline=$((SECONDS + 10))
	      while [[ ! -e "$QEMU_CONTROL/listener-ready" ]]; do
	        (( SECONDS < deadline )) || exit 88
	        sleep 0.01
	      done
	    fi
	    if [[ "${FAKE_WAIT_FOR_PROCESS_TREE:-0}" == "1" ]]; then
	      printf '%s\n' "$$" > "$QEMU_CONTROL/guest-wait-pid"
	      deadline=$((SECONDS + 10))
	      while [[ ! -e "$QEMU_CONTROL/process-tree-ready" ]]; do
	        (( SECONDS < deadline )) || exit 88
	        sleep 0.01
	      done
	    fi
	    exit 0
    ;;
  'uname -m') printf '%s\\n' "${FAKE_ARCHITECTURE:-aarch64}" ;;
  'cat /etc/rpi5-build-id') printf '%s\\n' "$FAKE_BUILD_ID" ;;
  'systemctl is-system-running') printf '%s\\n' "${FAKE_SYSTEMD:-running}" ;;
  'systemctl is-active systemd-networkd.service') printf '%s\\n' "${FAKE_NETWORKD:-active}" ;;
  'systemctl is-active sshd.service') printf '%s\\n' "${FAKE_SSHD:-active}" ;;
  *'passwordauthentication'*) printf '%s\\n' "${FAKE_PASSWORD_AUTHENTICATION:-no}" ;;
  *'kbdinteractiveauthentication'*) printf '%s\\n' "${FAKE_KBD_INTERACTIVE_AUTHENTICATION:-no}" ;;
  *'permitrootlogin'*) printf '%s\\n' "${FAKE_PERMIT_ROOT_LOGIN:-no}" ;;
  *'allowusers'*) printf '%s\\n' "${FAKE_ALLOW_USERS:-rpiadmin}" ;;
  *'passwd -S'*) printf '%s\\n' "${FAKE_ACCOUNT_LOCK:-L}" ;;
  'systemctl --failed --no-pager') printf '0 loaded units listed.\\n' ;;
  'sudo -n /usr/bin/journalctl -b --no-pager') printf 'journal\\n' ;;
  *'ip -4 -o address show scope global'*) [[ "${FAKE_NETWORK_EXIT:-0}" != "1" ]] ;;
  *'/var/tmp/qemu-rw-test'*)
    [[ "${FAKE_RW_EXIT:-0}" != "1" ]] || exit 1
    printf '%s\\n' "${FAKE_RW_VALUE:-$RPI5_BUILD_ID}"
    ;;
  *'/etc/ssh/sshd_config.d/20-rpi5.conf'*)
    [[ "${FAKE_POLICY_EXIT:-0}" != "1" ]] || exit 1
    printf 'PasswordAuthentication no\\nPermitRootLogin no\\n'
    ;;
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
            "#!/usr/bin/env bash\nexit \"${FAKE_SS_EXIT:-0}\"\n",
        )
        self._write_executable(
            self.fake_bin / "uv",
            """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "$TEST_CALLS"
if [[ " $* " != *" kas shell "* ]]; then exit 0; fi
printf '%s\\n' "$$" > "$QEMU_CONTROL/qemu-pid"
if [[ -n "${FAKE_QEMU_EXIT_IMMEDIATE:-}" ]]; then
  exit "$FAKE_QEMU_EXIT_IMMEDIATE"
fi
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
if [[ "${FAKE_QEMU_MODE:-poweroff}" == "term-resistant" ]]; then
  trap '' TERM INT
  "$RPI5_REAL_UV" run --locked --offline python tests/host/qemu_listener.py \
    --ready "$QEMU_CONTROL/listener-ready" \
    --runtime "$QEMU_CONTROL/listener-runtime" &
  listener="$!"
  printf '%s\\n' "$listener" > "$QEMU_CONTROL/qemu-listener-pid"
  while :; do sleep 1; done
fi
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
                "RPI5_REAL_UV": self.real_uv,
                "RPI5_REAL_TIMEOUT": self.real_timeout,
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
        images = self.root / "artifacts" / BUILD_ID / "qemu/images"
        images.mkdir(parents=True, exist_ok=True)
        (images / "rpi5-minimal-image-qemuarm64.rootfs.ext4").write_bytes(
            b"rootfs"
        )
        (self.root / "artifacts" / BUILD_ID / "qemu/COMPLETE").touch()

    def _launcher(self, **extra: str) -> subprocess.CompletedProcess[str]:
        return self._run("bash", "scripts/test-qemu.sh", "--build-id", BUILD_ID, **extra)

    def _start_launcher(self, **extra: str) -> subprocess.Popen[str]:
        return subprocess.Popen(
            ("bash", "scripts/test-qemu.sh", "--build-id", BUILD_ID),
            cwd=self.root,
            env=self._environment(**extra),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

    def _expired_qemu_shutdown_environment(self) -> Path:
        path = self.root / "expired-qemu-shutdown.sh"
        path.write_text(
            "RPI5_TEST_EXPIRE_QEMU_WAIT=1\n"
            "sleep() {\n"
            "    if (( RPI5_TEST_EXPIRE_QEMU_WAIT )); then\n"
            "        SECONDS=9999\n"
            "        RPI5_TEST_EXPIRE_QEMU_WAIT=0\n"
            "    fi\n"
            "    builtin sleep 0.01\n"
            "}\n",
            encoding="utf-8",
        )
        return path

    def _reap_order_environment(self) -> Path:
        path = self.root / "reap-order.sh"
        path.write_text(
            "RPI5_TEST_QEMU_KILLED=0\n"
            "RPI5_TEST_QEMU_REAPED=0\n"
            "kill() {\n"
            "    local qemu_pid=\"\"\n"
            "    [[ ! -f \"$QEMU_CONTROL/qemu-pid\" ]] || "
            "qemu_pid=\"$(<\"$QEMU_CONTROL/qemu-pid\")\"\n"
            "    if [[ \"${1:-}\" == \"-KILL\" && \"${3:-}\" == \"-$qemu_pid\" ]]; then\n"
            "        RPI5_TEST_QEMU_KILLED=1\n"
            "    fi\n"
            "    if [[ \"${1:-}\" == \"-0\" && \"${3:-}\" == \"-$qemu_pid\" ]] "
            "&& (( RPI5_TEST_QEMU_KILLED && ! RPI5_TEST_QEMU_REAPED )); then\n"
            "        return 0\n"
            "    fi\n"
            "    builtin kill \"$@\"\n"
            "}\n"
            "wait() {\n"
            "    local status=0\n"
            "    builtin wait \"$@\" || status=$?\n"
            "    if [[ -f \"$QEMU_CONTROL/qemu-pid\" "
            "&& \"${1:-}\" == \"$(<\"$QEMU_CONTROL/qemu-pid\")\" ]]; then\n"
            "        RPI5_TEST_QEMU_REAPED=1\n"
            "        touch \"$QEMU_CONTROL/leader-reaped\"\n"
            "    fi\n"
            "    return \"$status\"\n"
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

    def _wait_for_process_group_exit(self, pgid: int, timeout: float = 3) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.02)
        self.fail(f"process group {pgid} survived launcher cleanup")

    def _wait_for_port_2222_release(self, timeout: float = 3) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = subprocess.run(
                ("/usr/bin/ss", "-H", "-ltn", "sport = :2222"),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if not result.stdout.strip():
                return
            time.sleep(0.02)
        self.fail("localhost port 2222 survived launcher cleanup")

    def _kill_fake_qemu_group(self) -> None:
        pid_file = self.control / "qemu-pid"
        if not pid_file.exists():
            return
        try:
            os.killpg(int(pid_file.read_text()), 9)
        except ProcessLookupError:
            pass

    def _kill_process_group(self, pgid: int) -> None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _install_short_guest_timeout(self) -> None:
        self._write_executable(
            self.fake_bin / "timeout",
            """#!/usr/bin/env bash
if [[ "${1:-}" == "--foreground" && "${2:-}" == "--kill-after=10s" && "${3:-}" == "240s" ]]; then
  exec "$RPI5_REAL_TIMEOUT" "$1" "$2" 1s "${@:4}"
fi
exec "$RPI5_REAL_TIMEOUT" "$@"
""",
        )

    def _install_locked_environment(self) -> None:
        shutil.copytree(REPO_ROOT / ".venv", self.root / ".venv", symlinks=True)

    def _prepare_real_kas_fixture(self) -> tuple[str, Path]:
        self._install_locked_environment()
        kas_dir = self.root / "kas"
        kas_dir.mkdir()
        fixture_repo = self.root / "fixture-repo"
        fixture_repo.mkdir()
        fixture_bin = self.root / "runqemu-fixture-bin"
        fixture_bin.mkdir()
        (kas_dir / "qemuarm64-minimal.yml").write_text(
            "header:\n"
            "  version: 19\n"
            "repos:\n"
            "  fixture:\n"
            f"    path: {fixture_repo}\n"
            "    layers:\n"
            "      .: disabled\n"
            "env:\n"
            "  QEMU_CONTROL: null\n"
            "  RPI5_FIXTURE_ROOT: null\n"
            "  RPI5_REAL_UV: null\n",
            encoding="utf-8",
        )
        self._write_executable(
            fixture_repo / "oe-init-build-env",
            "#!/usr/bin/env bash\n"
            "mkdir -p \"$1/conf\"\n"
            "export BBPATH=\"$1\"\n"
            f"export PATH=\"{fixture_bin}:$PATH\"\n",
        )
        self._write_executable(
            fixture_bin / "runqemu",
            """#!/usr/bin/env bash
trap '' TERM INT
printf '%s\n' "$$" > "$QEMU_CONTROL/runqemu-pid"
pgid="$(ps -o pgid= -p "$$" | tr -d ' ')"
printf '%s\n' "$pgid" > "$QEMU_CONTROL/outer-pgid"
sleep 600 &
printf '%s\n' "$!" > "$QEMU_CONTROL/runqemu-sleep-pid"
(
  cd "$RPI5_FIXTURE_ROOT"
  exec "$RPI5_REAL_UV" run --locked --offline python \
    tests/host/qemu_listener.py \
    --ready "$QEMU_CONTROL/listener-ready" \
    --runtime "$QEMU_CONTROL/listener-runtime"
) &
printf '%s\n' "$!" > "$QEMU_CONTROL/listener-wrapper-pid"
while [[ ! -e "$QEMU_CONTROL/listener-ready" ]]; do sleep 0.01; done
ps -eo pid=,ppid=,pgid=,args= |
  awk -v pgid="$pgid" '$3 == pgid { print }' \
  > "$QEMU_CONTROL/process-tree.tsv"
touch "$QEMU_CONTROL/process-tree-ready"
while :; do sleep 1; done
""",
        )

        outer_bin = self.root / "outer-fixture-bin"
        outer_bin.mkdir()
        for command in ("ssh-keygen", "ssh-keyscan", "ssh", "scp"):
            shutil.copy2(self.fake_bin / command, outer_bin / command)

        (self.root / ".gitignore").write_text(
            ".venv/\n"
            ".uv-cache/\n"
            "artifacts/\n"
            "build/\n"
            "calls.log\n"
            "control/\n"
            "fake-bin/\n"
            "outer-fixture-bin/\n"
            "runqemu-fixture-bin/\n",
            encoding="utf-8",
        )
        git_commands = (
            ("git", "init", "-q"),
            ("git", "add", ".gitignore", "keys", "kas", "fixture-repo", "scripts",
             "pyproject.toml", "uv.lock", "tests/host/qemu_listener.py"),
            (
                "git", "-c", "user.name=QEMU Contract", "-c",
                "user.email=qemu-contract@example.invalid", "commit", "-q",
                "--no-gpg-sign", "-m", "test fixture",
            ),
        )
        for command in git_commands:
            result = subprocess.run(
                command,
                cwd=self.root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, (command, result.stderr))
        revision = subprocess.run(
            ("git", "rev-parse", "--short=12", "HEAD"),
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.strip()
        return f"20260725T120000Z-{revision}", outer_bin

    def _real_kas_environment(
        self,
        build_id: str,
        outer_bin: Path,
        **extra: str,
    ) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("UV_PROJECT_ENVIRONMENT", None)
        environment.pop("VIRTUAL_ENV", None)
        environment.update(
            {
                "PATH": (
                    f"{self.root / 'runqemu-fixture-bin'}:"
                    f"{outer_bin}:{environment['PATH']}"
                ),
                "TEST_CALLS": str(self.calls),
                "QEMU_CONTROL": str(self.control),
                "FAKE_BUILD_ID": build_id,
                "RPI5_REAL_UV": self.real_uv,
                "RPI5_FIXTURE_ROOT": str(self.root),
                "RPI5_RUNQEMU_FIXTURE_BIN": str(self.root / "runqemu-fixture-bin"),
                "UV_CACHE_DIR": str(self.root / ".uv-cache"),
                "UV_OFFLINE": "1",
            },
        )
        environment.update(extra)
        return environment

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
        self.assertIn("IdentitiesOnly=yes", calls)
        self.assertIn("PasswordAuthentication=no", calls)
        self.assertIn("KbdInteractiveAuthentication=no", calls)
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
        self.assertIn('"account":"locked"', (evidence / "result.json").read_text())
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

    def test_guest_rejects_additional_authentication_method_alternative(self) -> None:
        """Catches accepting publickey when sshd also permits a password alternative."""
        self._copy_entrypoints()
        result = self._guest(FAKE_AUTHENTICATION_METHODS="publickey password")
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        self.assertNotEqual(
            result.returncode,
            0,
            (
                f"guest-PASS={str((evidence / 'guest-PASS').exists()).lower()} "
                f"powered-off={str((self.control / 'powered-off').exists()).lower()}"
            ),
        )
        self.assertFalse((evidence / "guest-PASS").exists())
        self.assertFalse((self.control / "powered-off").exists())

    def test_each_guest_assertion_failure_blocks_pass_and_poweroff(self) -> None:
        """Catches independently weakened guest acceptance assertions."""
        cases = (
            ("architecture", {"FAKE_ARCHITECTURE": "x86_64"}),
            ("build-id", {"FAKE_BUILD_ID": "20260725T120000Z-deadbeefcafe"}),
            ("systemd", {"FAKE_SYSTEMD": "degraded"}),
            ("networkd", {"FAKE_NETWORKD": "inactive"}),
            ("sshd", {"FAKE_SSHD": "inactive"}),
            ("slirp-network", {"FAKE_NETWORK_EXIT": "1"}),
            ("writable-storage", {"FAKE_RW_EXIT": "1"}),
            ("password-authentication", {"FAKE_PASSWORD_AUTHENTICATION": "yes"}),
            (
                "kbd-interactive-authentication",
                {"FAKE_KBD_INTERACTIVE_AUTHENTICATION": "yes"},
            ),
            ("permit-root-login", {"FAKE_PERMIT_ROOT_LOGIN": "prohibit-password"}),
            ("authentication-methods", {"FAKE_AUTHENTICATION_METHODS": "any"}),
            ("allow-users", {"FAKE_ALLOW_USERS": "rpiadmin camera"}),
            ("account-lock", {"FAKE_ACCOUNT_LOCK": "P"}),
            ("root-login", {"FAKE_ROOT_LOGIN_SUCCEEDS": "1"}),
            ("non-key-login", {"FAKE_NO_KEY_LOGIN_SUCCEEDS": "1"}),
        )
        for name, extra in cases:
            with self.subTest(name=name):
                self._copy_entrypoints()
                result = self._guest(**extra)
                evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((evidence / "guest-PASS").exists())
                self.assertFalse((self.control / "powered-off").exists())
                shutil.rmtree(evidence, ignore_errors=True)

    def test_guest_uses_effective_sshd_policy_instead_of_static_dropin(self) -> None:
        """Catches trusting a drop-in that sshd could override or ignore."""
        self._copy_entrypoints()
        result = self._guest(FAKE_POLICY_EXIT="1")
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((evidence / "guest-PASS").is_file())
        calls = self.calls.read_text(encoding="utf-8")
        for setting in (
            "passwordauthentication",
            "kbdinteractiveauthentication",
            "permitrootlogin",
            "authenticationmethods",
            "allowusers",
        ):
            self.assertIn(setting, calls)
        self.assertIn("passwd -S rpiadmin", calls)

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

    def test_launcher_fails_closed_when_port_state_cannot_be_verified(self) -> None:
        """Catches treating an ss inspection error as proof port 2222 is free."""
        self._copy_entrypoints()
        self._ready_launcher()
        result = self._launcher(FAKE_SS_EXIT="2")
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not inspect localhost port 2222", result.stderr)
        self.assertFalse((evidence / "PASS").exists())
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

    def test_launcher_uses_collected_uncompressed_rootfs(self) -> None:
        """Catches runqemu auto-selecting a compressed rootfs it cannot boot."""
        self._copy_entrypoints()
        self._ready_launcher()

        result = self._launcher()

        self.assertEqual(result.returncode, 0, result.stderr)
        expected = (
            self.root
            / "artifacts"
            / BUILD_ID
            / "qemu/images/rpi5-minimal-image-qemuarm64.rootfs.ext4"
        )
        launch = (
            self.root
            / "artifacts"
            / BUILD_ID
            / "qemu-test/launch-command.txt"
        ).read_text(encoding="utf-8")
        self.assertIn(str(expected), launch)
        self.assertNotIn(".ext4.zst", launch)

    def test_launcher_reports_immediate_qemu_exit_without_guest_timeout(self) -> None:
        """Catches waiting for SSH after the QEMU launcher has already failed."""
        self._copy_entrypoints()
        self._ready_launcher()
        self._install_short_guest_timeout()
        started = time.monotonic()

        result = self._launcher(
            FAKE_QEMU_EXIT_IMMEDIATE="42",
            FAKE_HANG_COMMAND="uname -m",
        )

        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(result.returncode, 42, result.stderr)
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        self.assertFalse((evidence / "PASS").exists())
        self.assertFalse((evidence / "guest-PASS").exists())

    def test_launcher_failure_paths_do_not_promote_pass_and_terminate_qemu_group(self) -> None:
        """Catches leaked QEMU groups or PASS promotion after guest or QEMU failure."""
        self._copy_entrypoints()
        for name, extra in (
            ("guest", {"FAKE_ARCHITECTURE": "x86_64"}),
            ("qemu", {"FAKE_QEMU_EXIT": "42", "FAKE_QEMU_LEAVE_CHILD": "1"}),
        ):
            with self.subTest(name=name):
                self._ready_launcher()
                launcher_extra = dict(extra)
                result = self._launcher(**launcher_extra)
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

    def test_launcher_times_out_hung_guest_command_and_cleans_every_process(self) -> None:
        """Catches an SSH command escaping the whole-checker deadline and cleanup."""
        self._copy_entrypoints()
        self._ready_launcher()
        self._install_short_guest_timeout()
        try:
            result = self._launcher(FAKE_HANG_COMMAND="uname -m")
            evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertFalse((evidence / "PASS").exists())
            self.assertFalse((evidence / "guest-PASS").exists())
            guest_hang_pid = int((self.control / "guest-hang-pid").read_text())
            self._wait_for_process_exit(guest_hang_pid)
            qemu_pid = int((self.control / "qemu-pid").read_text())
            self._wait_for_process_exit(qemu_pid)
            self._wait_for_port_2222_release()
        finally:
            self._kill_fake_qemu_group()

    def _assert_direct_signal_cleanup(self, sent_signal: int, expected_status: int) -> None:
        self._copy_entrypoints()
        self._install_locked_environment()
        self._ready_launcher()
        launcher = self._start_launcher(
            FAKE_HANG_COMMAND="uname -m",
            FAKE_QEMU_MODE="term-resistant",
            FAKE_WAIT_FOR_LISTENER="1",
        )
        guest_pgid = None
        qemu_pgid = None
        try:
            self._wait_for(self.control / "listener-ready")
            self._wait_for(self.control / "guest-hang-pid")
            guest_pid = int((self.control / "guest-hang-pid").read_text())
            guest_pgid = os.getpgid(guest_pid)
            qemu_pid = int((self.control / "qemu-pid").read_text())
            qemu_pgid = os.getpgid(qemu_pid)
            launcher.send_signal(sent_signal)
            try:
                stdout, stderr = launcher.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                self._kill_process_group(launcher.pid)
                self._kill_process_group(guest_pgid)
                self._kill_process_group(qemu_pgid)
                launcher.communicate(timeout=3)
                self.fail(f"launcher did not finish cleanup after signal {sent_signal}")
            self.assertEqual(launcher.returncode, expected_status, (stdout, stderr))
            evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
            self.assertFalse((evidence / "PASS").exists())
            self._wait_for_process_exit(guest_pid)
            self._wait_for_process_group_exit(guest_pgid)
            self._wait_for_process_exit(qemu_pid)
            self._wait_for_process_group_exit(qemu_pgid)
            self._wait_for_port_2222_release()
        finally:
            self._kill_process_group(launcher.pid)
            if guest_pgid is not None:
                self._kill_process_group(guest_pgid)
            if qemu_pgid is not None:
                self._kill_process_group(qemu_pgid)
            self._kill_fake_qemu_group()

    def test_launcher_sigint_exits_130_after_full_cleanup(self) -> None:
        """Catches SIGINT bypassing EXIT cleanup or orphaning the guest checker."""
        self._assert_direct_signal_cleanup(signal.SIGINT, 130)

    def test_launcher_sigterm_exits_143_after_full_cleanup(self) -> None:
        """Catches SIGTERM bypassing EXIT cleanup or orphaning the guest checker."""
        self._assert_direct_signal_cleanup(signal.SIGTERM, 143)

    def test_launcher_real_uv_kas_path_cleans_complete_process_tree(self) -> None:
        """Catches a fake outer wrapper hiding uv/kas descendant or PGID leaks."""
        self._copy_entrypoints()
        build_id, outer_bin = self._prepare_real_kas_fixture()
        (self.root / "artifacts" / build_id / "qemu").mkdir(
            parents=True,
            exist_ok=True,
        )
        images = self.root / "artifacts" / build_id / "qemu/images"
        images.mkdir()
        (images / "rpi5-minimal-image-qemuarm64.rootfs.ext4").write_bytes(
            b"rootfs"
        )
        (self.root / "artifacts" / build_id / "qemu/COMPLETE").touch()
        (self.root / "build" / "kas-work" / "build").mkdir(parents=True)
        launcher = subprocess.Popen(
            ("bash", "scripts/test-qemu.sh", "--build-id", build_id),
            cwd=self.root,
            env=self._real_kas_environment(
                build_id,
                outer_bin,
                FAKE_ARCHITECTURE="x86_64",
                FAKE_WAIT_FOR_PROCESS_TREE="1",
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        outer_pgid = None
        guest_pgid = None
        fallback_pgids: set[int] = set()
        try:
            try:
                stdout, stderr = launcher.communicate(timeout=25)
            except subprocess.TimeoutExpired:
                evidence = self.root / "artifacts" / build_id / "qemu-test"
                console_path = evidence / "console.log"
                console = (
                    console_path.read_text(encoding="utf-8")
                    if console_path.is_file()
                    else "<no console>"
                )
                process_snapshot = subprocess.run(
                    ("ps", "-eo", "pid,ppid,pgid,sid,stat,args"),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                ).stdout
                fixture_processes = "\n".join(
                    line for line in process_snapshot.splitlines()
                    if str(self.root) in line
                )
                for line in fixture_processes.splitlines():
                    fields = line.split(maxsplit=5)
                    if len(fields) >= 3:
                        fallback_pgids.add(int(fields[2]))
                control_files = sorted(path.name for path in self.control.iterdir())
                if (self.control / "outer-pgid").is_file():
                    outer_pgid = int((self.control / "outer-pgid").read_text())
                if (self.control / "guest-wait-pid").is_file():
                    guest_pid = int((self.control / "guest-wait-pid").read_text())
                    guest_pgid = os.getpgid(guest_pid)
                self._kill_process_group(launcher.pid)
                if outer_pgid is not None:
                    self._kill_process_group(outer_pgid)
                if guest_pgid is not None:
                    self._kill_process_group(guest_pgid)
                for pgid in fallback_pgids:
                    self._kill_process_group(pgid)
                launcher.communicate(timeout=3)
                self.fail(
                    "real uv/kas launcher exceeded its bounded cleanup window\n"
                    f"control={control_files}\nconsole={console}\n"
                    f"processes={fixture_processes}"
                )
            self.assertNotEqual(launcher.returncode, 0, (stdout, stderr))
            evidence = self.root / "artifacts" / build_id / "qemu-test"
            self.assertFalse((evidence / "PASS").exists())
            console = (evidence / "console.log").read_text(encoding="utf-8")
            self.assertTrue(
                (self.control / "process-tree-ready").is_file(),
                (stdout, stderr, console),
            )
            tree = (self.control / "process-tree.tsv").read_text(encoding="utf-8")
            process_ids = {
                int(line.split(maxsplit=1)[0])
                for line in tree.splitlines()
                if line.strip()
            }
            outer_pgid = int((self.control / "outer-pgid").read_text())
            self.assertIn(outer_pgid, process_ids)
            self.assertGreaterEqual(len(process_ids), 5, tree)
            self.assertIn("uv run --locked kas shell kas/qemuarm64-minimal.yml", tree)
            self.assertIn("kas 5.4 started", console)
            for pid in process_ids:
                self._wait_for_process_exit(pid)
            self._wait_for_process_group_exit(outer_pgid)
            self._wait_for_port_2222_release()
        finally:
            self._kill_process_group(launcher.pid)
            if outer_pgid is not None:
                self._kill_process_group(outer_pgid)
            if guest_pgid is not None:
                self._kill_process_group(guest_pgid)
            for pgid in fallback_pgids:
                self._kill_process_group(pgid)

    def test_launcher_kills_term_resistant_listener_after_guest_failure(self) -> None:
        """Catches a bounded cleanup that leaves a port-2222 process group alive."""
        self._copy_entrypoints()
        self._install_locked_environment()
        self._ready_launcher()
        try:
            result = self._launcher(
                FAKE_ARCHITECTURE="x86_64",
                FAKE_QEMU_MODE="term-resistant",
                FAKE_WAIT_FOR_LISTENER="1",
                BASH_ENV=str(self._reap_order_environment()),
            )
            evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((evidence / "PASS").exists())
            self.assertTrue((self.control / "listener-ready").is_file())
            listener_runtime = self.control / "listener-runtime"
            self.assertTrue(listener_runtime.is_file())
            self.assertEqual(
                listener_runtime.read_text(encoding="utf-8").strip(),
                str(self.root / ".venv"),
            )
            self._wait_for_port_2222_release()
            listener_pid = int((self.control / "qemu-listener-pid").read_text())
            self._wait_for_process_exit(listener_pid)
            self.assertTrue((self.control / "leader-reaped").is_file())
        finally:
            self._kill_fake_qemu_group()

    def test_launcher_kills_refusing_qemu_after_poweroff_without_promoting_pass(self) -> None:
        """Catches the timeout path leaking a QEMU process group or sealing PASS."""
        self._copy_entrypoints()
        self._ready_launcher()
        result = self._launcher(
            FAKE_QEMU_MODE="ignore",
            BASH_ENV=str(self._expired_qemu_shutdown_environment()),
        )
        evidence = self.root / "artifacts" / BUILD_ID / "qemu-test"
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("QEMU did not exit within 30 seconds", result.stderr)
        self.assertFalse((evidence / "PASS").exists())
        qemu_pid = int((self.control / "qemu-pid").read_text())
        self._wait_for_process_exit(qemu_pid)

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
