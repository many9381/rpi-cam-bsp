from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

from support import REPO_ROOT, read, run


EXPECTED_IMAGE = (
    "ghcr.io/siemens/kas/kas@"
    "sha256:11f076b79b84f57cb7d933941ff619f09a7c17e562e1643d13836d5f8d0a92f3"
)
EXPECTED_WRAPPER_SHA = (
    "9707355d1eba19e334e663ab9fcf6881ac323aed16ff7f4fd7e217f879a3894c"
)
EXPECTED_BUILD_ID = "20260726T120000Z-0123456789ab"


class CiContractTest(unittest.TestCase):
    """Execution and provenance contracts for the provider-neutral CI entry point."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ci-contract-")
        self.root = Path(self.temporary.name) / "checkout"
        self.fake_bin = self.root / "fake-bin"
        self.calls = self.root / "calls.log"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_executable(self, path: Path, contents: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _prepare_checkout(self) -> None:
        self.fake_bin.mkdir(parents=True)
        (self.root / "scripts" / "lib").mkdir(parents=True)
        (self.root / "ci").mkdir()
        (self.root / "keys").mkdir()
        (self.root / ".venv").mkdir()
        for relative in (
            "ci/container.env",
            "ci/pipeline.sh",
            "scripts/lib/common.sh",
        ):
            source = REPO_ROOT / relative
            destination = self.root / relative
            shutil.copy2(source, destination)

        self._write_executable(
            self.fake_bin / "uv",
            """#!/usr/bin/env bash
printf 'uv %s\n' "$*" >> "$CI_CALLS"
if [[ "${1:-}" == "--version" ]]; then
    printf 'uv 0.11.31\n'
fi
""",
        )
        self._write_executable(
            self.fake_bin / "ssh-keygen",
            """#!/usr/bin/env bash
printf 'ssh-keygen %s\n' "$*" >> "$CI_CALLS"
key_path=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-f" ]]; then
        key_path="$2"
        break
    fi
    shift
done
[[ -n "$key_path" ]] || exit 2
printf 'private\n' > "$key_path"
printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest ci\n' > "${key_path}.pub"
""",
        )
        self._write_executable(
            self.root / "scripts" / "new-build-id.sh",
            f"""#!/usr/bin/env bash
printf 'new-build-id\n' >> "$CI_CALLS"
printf '%s\n' '{EXPECTED_BUILD_ID}'
""",
        )
        self._write_executable(
            self.root / "scripts" / "build.sh",
            """#!/usr/bin/env bash
printf 'build container=%s args=%s\n' "${RPI5_CI_CONTAINER:-}" "$*" >> "$CI_CALLS"
""",
        )
        self._write_executable(
            self.root / "scripts" / "test-qemu.sh",
            """#!/usr/bin/env bash
printf 'test-qemu container=%s args=%s\n' "${RPI5_CI_CONTAINER:-}" "$*" >> "$CI_CALLS"
""",
        )
        for command in (
            "bmaptool",
            "flash-ssd.sh",
            "lsblk",
            "sudo",
            "test-camera.sh",
            "test-rpi5.sh",
        ):
            self._write_executable(
                self.fake_bin / command,
                f"""#!/usr/bin/env bash
printf 'FORBIDDEN {command} %s\n' "$*" >> "$CI_CALLS"
exit 99
""",
            )

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("UV_PROJECT_ENVIRONMENT", None)
        environment.update(
            {
                "CI_CALLS": str(self.calls),
                "HOME": str(self.root / "home"),
                "PATH": f"{self.fake_bin}:{environment['PATH']}",
            },
        )
        return environment

    def _run_stage(self, stage: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.root / "ci" / "pipeline.sh"), stage],
            cwd=self.root,
            env=self._environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _call_lines(self, prefix: str) -> list[str]:
        if not self.calls.exists():
            return []
        return [
            line
            for line in self.calls.read_text(encoding="utf-8").splitlines()
            if line.startswith(prefix)
        ]

    def test_container_inputs_are_immutable(self) -> None:
        """Catches a mutable image tag or unreviewed kas dependency update."""
        values = dict(
            line.split("=", 1)
            for line in read("ci/container.env").splitlines()
            if line and not line.startswith("#")
        )
        self.assertEqual(values["KAS_VERSION"], "5.4")
        self.assertEqual(values["KAS_CONTAINER_IMAGE"], EXPECTED_IMAGE)
        self.assertEqual(
            values["KAS_CONTAINER_SCRIPT_SHA256"],
            EXPECTED_WRAPPER_SHA,
        )
        self.assertEqual(
            values["KAS_SOURCE_COMMIT"],
            "81bab5294be29de4b64adedce962d36184bfc66f",
        )

    def test_vendored_wrapper_matches_official_5_4_bytes(self) -> None:
        """Catches local edits or an unreviewed replacement of the launcher."""
        wrapper = REPO_ROOT / "ci" / "kas-container"
        digest = hashlib.sha256(wrapper.read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_WRAPPER_SHA)
        self.assertTrue(wrapper.stat().st_mode & stat.S_IXUSR)

    def test_pipeline_rejects_unknown_stage_before_bootstrap(self) -> None:
        """Catches a typo triggering installer or build side effects."""
        self._prepare_checkout()
        result = self._run_stage("unknown")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("{unit|qemu|rpi5-image}", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_unit_stage_runs_locked_tests_without_hardware_commands(self) -> None:
        """Catches unit CI gaining block-device or physical-hardware access."""
        self._prepare_checkout()
        result = self._run_stage("unit")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text(encoding="utf-8")
        self.assertIn(
            "uv run --locked python -m unittest discover "
            "-s tests/host -p test_*.py -v",
            calls,
        )
        self.assertNotIn("FORBIDDEN", calls)
        self.assertFalse((self.root / "keys" / "rpi5_admin").exists())
        self.assertFalse((self.root / "keys" / "rpi5_admin.pub").exists())

    def test_qemu_stage_uses_one_build_id_and_removes_ephemeral_key(self) -> None:
        """Catches a split QEMU evidence chain or a key left in the workspace."""
        self._prepare_checkout()
        result = self._run_stage("qemu")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self._call_lines("build "),
            [
                "build container=1 args=--build-id "
                f"{EXPECTED_BUILD_ID} qemu checkout",
                "build container=1 args=--build-id "
                f"{EXPECTED_BUILD_ID} qemu parse",
                "build container=1 args=--build-id "
                f"{EXPECTED_BUILD_ID} qemu build",
            ],
        )
        self.assertEqual(
            self._call_lines("test-qemu "),
            [
                "test-qemu container=1 args=--build-id "
                f"{EXPECTED_BUILD_ID}",
            ],
        )
        self.assertFalse((self.root / "keys" / "rpi5_admin").exists())
        self.assertFalse((self.root / "keys" / "rpi5_admin.pub").exists())
        self.assertNotIn(
            "FORBIDDEN",
            self.calls.read_text(encoding="utf-8"),
        )

    def test_rpi5_image_build_does_not_run_qemu(self) -> None:
        """Catches an unsolicited emulator build during a Pi-only CI job."""
        self._prepare_checkout()
        result = self._run_stage("rpi5-image")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self._call_lines("build "),
            [
                "build container=1 args=--build-id "
                f"{EXPECTED_BUILD_ID} rpi5-minimal build",
            ],
        )
        self.assertEqual(self._call_lines("test-qemu "), [])
        self.assertFalse((self.root / "keys" / "rpi5_admin").exists())
        self.assertFalse((self.root / "keys" / "rpi5_admin.pub").exists())
        self.assertNotIn(
            "FORBIDDEN",
            self.calls.read_text(encoding="utf-8"),
        )

    def test_build_stage_rejects_preexisting_ci_key_paths(self) -> None:
        """Catches CI reusing or overwriting a persisted operator key."""
        self._prepare_checkout()
        private_key = self.root / "keys" / "rpi5_admin"
        public_key = self.root / "keys" / "rpi5_admin.pub"
        private_key.write_text("keep-private\n", encoding="utf-8")
        public_key.write_text("keep-public\n", encoding="utf-8")

        result = self._run_stage("qemu")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CI key paths must be absent", result.stderr)
        self.assertEqual(
            private_key.read_text(encoding="utf-8"),
            "keep-private\n",
        )
        self.assertEqual(
            public_key.read_text(encoding="utf-8"),
            "keep-public\n",
        )
        self.assertEqual(self._call_lines("build "), [])

    def test_partial_key_generation_failure_removes_created_files(self) -> None:
        """Catches ssh-keygen failure leaving private material in CI state."""
        self._prepare_checkout()
        self._write_executable(
            self.fake_bin / "ssh-keygen",
            """#!/usr/bin/env bash
key_path=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-f" ]]; then
        key_path="$2"
        break
    fi
    shift
done
printf 'partial-private\n' > "$key_path"
printf 'partial-public\n' > "${key_path}.pub"
exit 1
""",
        )

        result = self._run_stage("qemu")

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "keys" / "rpi5_admin").exists())
        self.assertFalse((self.root / "keys" / "rpi5_admin.pub").exists())
        self.assertEqual(self._call_lines("build "), [])

    def test_pipeline_is_executable_valid_bash(self) -> None:
        """Catches a pipeline the CI shell cannot start."""
        pipeline = REPO_ROOT / "ci" / "pipeline.sh"
        self.assertTrue(pipeline.stat().st_mode & stat.S_IXUSR)
        result = run("bash", "-n", "ci/pipeline.sh")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
