from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

from support import REPO_ROOT, run


REVISION = "0123456789ab"
FULL_REVISION = "0123456789abcdef0123456789abcdef01234567"
BUILD_ID = f"20260725T120000Z-{REVISION}"


class BuildContractTest(unittest.TestCase):
    """Execution contracts for the build and evidence shell entry points."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="build-contract-")
        self.root = Path(self.temporary.name) / "checkout"
        self.root.mkdir()
        (self.root / "scripts" / "lib").mkdir(parents=True)
        (self.root / "keys").mkdir()
        (self.root / "keys" / "rpi5_admin.pub").write_text(
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest build-contract\\n",
            encoding="utf-8",
        )
        for relative in (
            "scripts/build.sh",
            "scripts/collect-artifacts.sh",
            "scripts/lib/common.sh",
        ):
            source = REPO_ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        self.calls = self.root / "calls.log"
        self.fake_bin = self.root / "fake-bin"
        self.fake_bin.mkdir()
        self._write_executable(
            self.root / "scripts" / "host-preflight.sh",
            "#!/usr/bin/env bash\nprintf 'preflight %s\\n' \"$*\" >> \"$TEST_CALLS\"\n",
        )
        self._write_executable(
            self.fake_bin / "git",
            """#!/usr/bin/env bash
printf 'git %s\\n' "$*" >> "$TEST_CALLS"
if [[ " $* " == *" rev-parse "* ]]; then
    if [[ " $* " == *" --short=12 "* ]]; then
        printf '%s\\n' "$FAKE_REVISION"
    else
        printf '%s\\n' "$FAKE_FULL_REVISION"
    fi
fi
""",
        )
        self._write_executable(
            self.fake_bin / "uv",
            """#!/usr/bin/env bash
printf 'uv args=%s work=%s build=%s\\n' "$*" "${KAS_WORK_DIR:-}" "${KAS_BUILD_DIR:-}" >> "$TEST_CALLS"
if [[ "${FAIL_FOR_ALL_REPOS:-}" == "1" && " $* " == *" kas for-all-repos "* ]]; then
    exit 1
elif [[ " $* " == " run --locked kas --version " ]]; then
    printf 'kas 5.4\\n'
elif [[ " $* " == *" kas for-all-repos "* ]]; then
    printf 'z-layer zzz\\n'
    printf 'a-layer aaa\\n'
fi
""",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_executable(self, path: Path, contents: str) -> None:
        path.write_text(contents, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _environment(self, **extra: str) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("UV_PROJECT_ENVIRONMENT", None)
        environment.update(
            {
                "PATH": f"{self.fake_bin}:{environment['PATH']}",
                "TEST_CALLS": str(self.calls),
                "FAKE_REVISION": REVISION,
                "FAKE_FULL_REVISION": FULL_REVISION,
            },
        )
        environment.update(extra)
        return environment

    def _run(self, *arguments: str, **extra_environment: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            arguments,
            cwd=self.root,
            env=self._environment(**extra_environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _calls(self) -> str:
        return self.calls.read_text(encoding="utf-8") if self.calls.exists() else ""

    def _collector_arguments(self, profile: str = "qemu") -> tuple[str, ...]:
        if profile == "qemu":
            machine, image, config = (
                "qemuarm64",
                "rpi5-minimal-image",
                "kas/qemuarm64-minimal.yml",
            )
        else:
            machine, image, config = (
                "raspberrypi5",
                f"rpi5-{'camera' if profile == 'rpi5-camera' else 'minimal'}-image",
                f"kas/{profile}.yml",
            )
        return (
            "bash", "scripts/collect-artifacts.sh", "--build-id", BUILD_ID,
            "--profile", profile, "--config", config, "--machine", machine,
            "--image", image,
        )

    def _create_qemu_outputs(self) -> Path:
        deploy = self.root / "build/kas-work/build/qemu/tmp/deploy/images/qemuarm64"
        deploy.mkdir(parents=True)
        (deploy / "rpi5-minimal-image-qemuarm64.rootfs.ext4").write_bytes(b"rootfs")
        (deploy / "Image").write_bytes(b"kernel")
        (deploy / "rpi5-minimal-image-qemuarm64.rootfs.manifest").write_text(
            "package-a\\n", encoding="utf-8"
        )
        licenses = self.root / "build/kas-work/build/qemu/tmp/deploy/licenses/rpi5-minimal-image-qemuarm64"
        licenses.mkdir(parents=True)
        (licenses / "LICENSE.manifest").write_text("MIT\\n", encoding="utf-8")
        return deploy

    def test_parse_uses_profile_specific_locked_kas_environment(self) -> None:
        """Catches a profile mapping or KAS build-directory regression."""
        expected = {
            "qemu": "kas/qemuarm64-minimal.yml",
            "rpi5-minimal": "kas/rpi5-minimal.yml",
            "rpi5-camera": "kas/rpi5-camera.yml",
        }
        for profile, config in expected.items():
            with self.subTest(profile=profile):
                result = self._run(
                    "bash", "scripts/build.sh", "--build-id", BUILD_ID, profile, "parse"
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self._calls()
                self.assertIn("preflight --incremental --key", calls)
                self.assertIn(
                    f"uv args=run --locked kas shell {config} -c bitbake -p "
                    f"work={self.root}/build/kas-work "
                    f"build={self.root}/build/kas-work/build/{profile}",
                    calls,
                )

    def test_hardware_gates_block_all_external_work_and_artifact_mutation(self) -> None:
        """Catches moving a hardware PASS check after preflight or kas starts."""
        cases = (
            ("rpi5-minimal", "QEMU PASS marker missing"),
            ("rpi5-camera", "phase-1 hardware PASS marker missing"),
        )
        (self.root / "artifacts" / BUILD_ID / "qemu-test").mkdir(parents=True)
        (self.root / "artifacts" / BUILD_ID / "qemu-test" / "PASS").touch()
        for profile, message in cases:
            with self.subTest(profile=profile):
                if profile == "rpi5-minimal":
                    shutil.rmtree(self.root / "artifacts" / BUILD_ID / "qemu-test")
                result = self._run(
                    "bash", "scripts/build.sh", "--build-id", BUILD_ID, profile, "build"
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn("preflight", self._calls())
                self.assertNotIn("uv args=", self._calls())
                self.assertFalse((self.root / "artifacts" / BUILD_ID / profile).exists())
                if profile == "rpi5-minimal":
                    (self.root / "artifacts" / BUILD_ID / "qemu-test").mkdir()
                    (self.root / "artifacts" / BUILD_ID / "qemu-test" / "PASS").touch()

    def test_uv_override_is_rejected_before_preflight_or_uv_for_both_entrypoints(self) -> None:
        """Catches an override check that runs only after uv has been invoked."""
        commands = (
            ("build", ("bash", "scripts/build.sh", "--build-id", BUILD_ID, "qemu", "parse")),
            ("collector", self._collector_arguments()),
        )
        for name, command in commands:
            with self.subTest(entrypoint=name):
                result = self._run(*command, UV_PROJECT_ENVIRONMENT="/tmp/not-local")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("UV_PROJECT_ENVIRONMENT must be unset or empty", result.stderr)
                self.assertNotIn("preflight", self._calls())
                self.assertNotIn("uv args=", self._calls())

    def test_head_mismatch_is_rejected_without_creating_evidence(self) -> None:
        """Catches accepting a valid-looking BUILD_ID from a different revision."""
        stale = "20260725T120000Z-deadbeefcafe"
        commands = (
            ("build", ("bash", "scripts/build.sh", "--build-id", stale, "qemu", "parse")),
            ("collector", (
                "bash", "scripts/collect-artifacts.sh", "--build-id", stale,
                "--profile", "qemu", "--config", "kas/qemuarm64-minimal.yml",
                "--machine", "qemuarm64", "--image", "rpi5-minimal-image",
            )),
        )
        for name, command in commands:
            with self.subTest(entrypoint=name):
                result = self._run(*command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("does not match HEAD", result.stderr)
                self.assertNotIn("preflight", self._calls())
                self.assertNotIn("uv args=", self._calls())
                self.assertFalse((self.root / "artifacts" / stale).exists())

    def test_completed_evidence_is_never_overwritten(self) -> None:
        """Catches writing a log or collected file after COMPLETE already exists."""
        profile_out = self.root / "artifacts" / BUILD_ID / "qemu"
        profile_out.mkdir(parents=True)
        (profile_out / "COMPLETE").touch()
        (profile_out / "parse.log").write_text("keep me\\n", encoding="utf-8")
        commands = (
            ("build", ("bash", "scripts/build.sh", "--build-id", BUILD_ID, "qemu", "parse")),
            ("collector", self._collector_arguments()),
        )
        for name, command in commands:
            with self.subTest(entrypoint=name):
                result = self._run(*command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("evidence already complete", result.stderr)
                self.assertEqual((profile_out / "parse.log").read_text(encoding="utf-8"), "keep me\\n")
                self.assertNotIn("preflight", self._calls())
                self.assertNotIn("uv args=", self._calls())

    def test_collector_writes_complete_deterministic_qemu_evidence(self) -> None:
        """Catches a collector that omits required evidence or marks it complete early."""
        deploy = self._create_qemu_outputs()
        result = self._run(*self._collector_arguments())
        self.assertEqual(result.returncode, 0, result.stderr)
        out = self.root / "artifacts" / BUILD_ID / "qemu"
        self.assertTrue((out / "COMPLETE").is_file())
        self.assertEqual((out / "images" / "Image").read_bytes(), b"kernel")
        self.assertEqual(
            (out / "manifests" / "layer-revisions.txt").read_text(encoding="utf-8"),
            "a-layer aaa\nz-layer zzz\n",
        )
        checksum = hashlib.sha256(
            (deploy / "rpi5-minimal-image-qemuarm64.rootfs.ext4").read_bytes()
        ).hexdigest()
        self.assertEqual(
            (out / "checksums" / "SHA256SUMS").read_text(encoding="utf-8"),
            f"{hashlib.sha256(b'kernel').hexdigest()}  images/Image\n"
            f"{checksum}  images/rpi5-minimal-image-qemuarm64.rootfs.ext4\n",
        )
        metadata = (out / "manifests" / "build-metadata.json").read_text(encoding="utf-8")
        self.assertIn(f'"build_id":"{BUILD_ID}"', metadata)
        self.assertIn(f'"project_revision":"{FULL_REVISION}"', metadata)
        self.assertIn("uv args=run --locked kas for-all-repos", self._calls())
        self.assertIn("uv args=run --locked kas --version", self._calls())

    def test_collector_requires_outputs_before_marking_evidence_complete(self) -> None:
        """Catches touching COMPLETE when a required deploy output is absent."""
        self._create_qemu_outputs()
        missing = self.root / "build/kas-work/build/qemu/tmp/deploy/images/qemuarm64/Image"
        missing.unlink()
        result = self._run(*self._collector_arguments())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required artifact missing", result.stderr)
        self.assertFalse((self.root / "artifacts" / BUILD_ID / "qemu" / "COMPLETE").exists())
        self.assertNotIn("uv args=", self._calls())

    def test_collector_preserves_hardware_disk_image_and_bmap(self) -> None:
        """Catches collecting a hardware build without its flash image or bmap."""
        profile = "rpi5-minimal"
        image = "rpi5-minimal-image"
        deploy = self.root / "build/kas-work/build/rpi5-minimal/tmp/deploy/images/raspberrypi5"
        deploy.mkdir(parents=True)
        (deploy / f"{image}-raspberrypi5.rootfs.wic.bz2").write_bytes(b"disk")
        (deploy / f"{image}-raspberrypi5.rootfs.wic.bmap").write_text("bmap\n", encoding="utf-8")
        (deploy / f"{image}-raspberrypi5.rootfs.manifest").write_text("package-a\n", encoding="utf-8")
        licenses = self.root / "build/kas-work/build/rpi5-minimal/tmp/deploy/licenses/rpi5-minimal-image-raspberrypi5"
        licenses.mkdir(parents=True)
        (licenses / "LICENSE.manifest").write_text("MIT\n", encoding="utf-8")

        result = self._run(*self._collector_arguments(profile))

        self.assertEqual(result.returncode, 0, result.stderr)
        out = self.root / "artifacts" / BUILD_ID / profile / "images"
        self.assertEqual((out / f"{image}-raspberrypi5.rootfs.wic.bz2").read_bytes(), b"disk")
        self.assertEqual((out / f"{image}-raspberrypi5.rootfs.wic.bmap").read_text(encoding="utf-8"), "bmap\n")
        self.assertTrue((out.parent / "COMPLETE").is_file())

    def test_failed_build_log_sink_prevents_collection_and_completion(self) -> None:
        """Catches ignoring tee failures after a successful kas build command."""
        self._create_qemu_outputs()
        self._write_executable(
            self.fake_bin / "tee",
            "#!/usr/bin/env bash\ncat >/dev/null\nexit 1\n",
        )

        result = self._run(
            "bash", "scripts/build.sh", "--build-id", BUILD_ID, "qemu", "build"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uv args=run --locked kas build kas/qemuarm64-minimal.yml", self._calls())
        self.assertNotIn("uv args=run --locked kas for-all-repos", self._calls())
        self.assertFalse((self.root / "artifacts" / BUILD_ID / "qemu" / "COMPLETE").exists())

    def test_collector_rejects_traversal_profile_before_artifact_mutation(self) -> None:
        """Catches constructing an artifact path from an unvalidated profile."""
        result = self._run(
            "bash", "scripts/collect-artifacts.sh", "--build-id", BUILD_ID,
            "--profile", "../escaped", "--config", "kas/qemuarm64-minimal.yml",
            "--machine", "qemuarm64", "--image", "rpi5-minimal-image",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown profile", result.stderr)
        self.assertFalse((self.root / "artifacts").exists())
        self.assertNotIn("uv args=", self._calls())

    def test_collector_rejects_mismatched_profile_tuple_before_artifact_mutation(self) -> None:
        """Catches collecting evidence with config, machine, or image from another profile."""
        result = self._run(
            "bash", "scripts/collect-artifacts.sh", "--build-id", BUILD_ID,
            "--profile", "qemu", "--config", "kas/rpi5-camera.yml",
            "--machine", "raspberrypi5", "--image", "rpi5-camera-image",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("collector arguments do not match profile", result.stderr)
        self.assertFalse((self.root / "artifacts").exists())
        self.assertNotIn("uv args=", self._calls())

    def test_incomplete_collection_retry_does_not_seal_stale_license_files(self) -> None:
        """Catches merging changed license evidence into an incomplete prior attempt."""
        self._create_qemu_outputs()
        source_licenses = (
            self.root
            / "build/kas-work/build/qemu/tmp/deploy/licenses/"
            "rpi5-minimal-image-qemuarm64"
        )
        (source_licenses / "OBSOLETE").write_text("old\n", encoding="utf-8")

        first = self._run(*self._collector_arguments(), FAIL_FOR_ALL_REPOS="1")

        self.assertNotEqual(first.returncode, 0)
        output_licenses = (
            self.root / "artifacts" / BUILD_ID / "qemu" / "licenses"
            / "rpi5-minimal-image-qemuarm64"
        )
        self.assertTrue((output_licenses / "OBSOLETE").is_file())
        self.assertFalse((output_licenses.parent.parent / "COMPLETE").exists())
        (source_licenses / "OBSOLETE").unlink()
        (source_licenses / "LICENSE.manifest").write_text("Apache-2.0\n", encoding="utf-8")

        second = self._run(*self._collector_arguments())

        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertFalse((output_licenses / "OBSOLETE").exists())
        self.assertEqual(
            (output_licenses / "LICENSE.manifest").read_text(encoding="utf-8"),
            "Apache-2.0\n",
        )
        self.assertTrue((output_licenses.parent.parent / "COMPLETE").is_file())

    def test_scripts_are_valid_bash(self) -> None:
        """Catches syntax errors that prevent either shell entry point from starting."""
        for path in ("scripts/build.sh", "scripts/collect-artifacts.sh"):
            result = run("bash", "-n", path)
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
