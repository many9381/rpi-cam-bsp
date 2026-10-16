from __future__ import annotations

import json
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
            "scripts/lib/build_provenance.py",
            "scripts/lib/camera_identity.py",
            "scripts/lib/codex_flash_auth.py",
            "scripts/lib/codex_auth.py",
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
if [[ " $* " == *" ls-files "* || " $* " == *" ls-tree "* ]]; then
    if [[ " $* " != *" --others "* ]]; then
        printf '%s\\0' scripts/build.sh scripts/collect-artifacts.sh scripts/lib/common.sh scripts/lib/build_provenance.py
    fi
elif [[ " $* " == *" rev-parse "* ]]; then
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
if [[ " $* " == *" kas build "* ]]; then
    test -f "$KAS_WORK_DIR/../../artifacts/$RPI5_BUILD_ID/${KAS_BUILD_DIR##*/}/provenance/inputs.json" || exit 91
fi
if [[ "${FAIL_FOR_ALL_REPOS:-}" == "1" && " $* " == *" kas for-all-repos "* ]]; then
    exit 1
elif [[ " $* " == " --version " ]]; then
    printf 'uv 0.11.31\\n'
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
        environment.pop("RPI5_CI_CONTAINER", None)
        environment.pop("CAMERA_FIRMWARE_MODEL_DIR", None)
        environment.pop("CAMERA_FIRMWARE_GIT_URI", None)
        environment.pop("RPI_CAM_HAILO_DEV_REPO", None)
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

    def _active_build(self, value: str = BUILD_ID) -> Path:
        path = self.root / ".state/active-build-id"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value + "\n", encoding="utf-8")
        return path

    def test_help_explains_build_id_and_active_build_without_external_work(self) -> None:
        result = self._run("bash", "scripts/build.sh", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[--build-id ID]", result.stdout)
        self.assertIn(".state/active-build-id", result.stdout)
        self.assertIn("rpi5-camera-hailo build", result.stdout)
        self.assertEqual(self._calls(), "")
        self.assertFalse((self.root / "artifacts").exists())

    def test_profile_in_build_id_position_has_actionable_error(self) -> None:
        for profile in ("qemu", "rpi5-minimal", "rpi5-camera", "rpi5-camera-hailo"):
            with self.subTest(profile=profile):
                result = self._run("bash", "scripts/build.sh", "--build-id", profile, "build")
                self.assertEqual(result.returncode, 2)
                self.assertIn("is a profile, not a build ID", result.stderr)
                self.assertIn(f"{profile} build", result.stderr)
                self.assertEqual(self._calls(), "")
                self.assertFalse((self.root / "artifacts").exists())

    def test_short_form_uses_active_build_for_each_profile(self) -> None:
        self._active_build()
        for profile in ("qemu", "rpi5-minimal", "rpi5-camera", "rpi5-camera-hailo"):
            with self.subTest(profile=profile):
                result = self._run("bash", "scripts/build.sh", profile, "parse")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(BUILD_ID, result.stderr)
                self.assertTrue((self.root / "artifacts" / BUILD_ID / profile / "parse.log").is_file())
                self.assertIn(f"build={self.root}/build/kas-work/build/{profile}", self._calls())

    def test_missing_active_build_explains_explicit_build_id(self) -> None:
        result = self._run("bash", "scripts/build.sh", "rpi5-camera-hailo", "build")
        self.assertEqual(result.returncode, 2)
        self.assertIn("active build ID is missing", result.stderr)
        self.assertIn("--build-id", result.stderr)
        self.assertEqual(self._calls(), "")
        self.assertFalse((self.root / ".state").exists())
        self.assertFalse((self.root / "artifacts").exists())

    def test_invalid_active_build_is_rejected_without_external_work(self) -> None:
        for value in ("", "rpi5-camera-hailo", "../../outside", BUILD_ID + "\n" + BUILD_ID):
            with self.subTest(value=value):
                self._active_build(value)
                result = self._run("bash", "scripts/build.sh", "rpi5-camera-hailo", "build")
                self.assertEqual(result.returncode, 2)
                self.assertIn("invalid build ID", result.stderr)
                self.assertEqual(self._calls(), "")
                self.assertFalse((self.root / "artifacts").exists())

    def test_explicit_build_id_takes_precedence_over_active_build(self) -> None:
        active = self._active_build("20260725T120000Z-deadbeefcafe")
        original = active.read_bytes()
        result = self._run("bash", "scripts/build.sh", "--build-id", BUILD_ID, "qemu", "parse")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "artifacts" / BUILD_ID / "qemu/parse.log").is_file())
        self.assertEqual(active.read_bytes(), original)

    def test_short_form_preserves_revision_check(self) -> None:
        self._active_build("20260725T120000Z-deadbeefcafe")
        result = self._run("bash", "scripts/build.sh", "qemu", "parse")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match HEAD", result.stderr)
        self.assertNotIn("preflight", self._calls())
        self.assertNotIn("uv args=", self._calls())
        self.assertFalse((self.root / "artifacts").exists())

    def test_malformed_arguments_fail_before_reading_active_build(self) -> None:
        for arguments in ((), ("--build-id",), ("--build-id", BUILD_ID),
                          ("--build-id", BUILD_ID, "qemu"), ("qemu",),
                          ("unknown", "build"), ("qemu", "unknown"),
                          ("qemu", "build", "extra")):
            with self.subTest(arguments=arguments):
                result = self._run("bash", "scripts/build.sh", *arguments)
                self.assertEqual(result.returncode, 2)
                self.assertIn("ERROR:", result.stderr)
                self.assertNotIn("unbound variable", result.stderr)
                self.assertEqual(self._calls(), "")
                self.assertFalse((self.root / "artifacts").exists())

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
                "rpi5-camera-image" if profile in ("rpi5-camera", "rpi5-camera-hailo") else "rpi5-minimal-image",
                f"kas/{profile}.yml",
            )
        return (
            "bash", "scripts/collect-artifacts.sh", "--build-id", BUILD_ID,
            "--profile", profile, "--config", config, "--machine", machine,
            "--image", image,
        )

    def _snapshot(self, profile: str = "qemu") -> Path:
        out = self.root / "artifacts" / BUILD_ID / profile / "provenance"
        result = self._run("python3", "scripts/lib/build_provenance.py", "snapshot",
                           "--repo", str(self.root), "--out", str(out), "--profile", profile)
        self.assertEqual(result.returncode, 0, result.stderr)
        return out

    def _create_vendor_inputs(self) -> None:
        for name in (
            "meta-rpi5-cam/recipes-hailo/hailort/files/hailort_4.24.0_arm64.deb",
            "meta-rpi5-cam/recipes-kernel/hailo-pci/files/hailort-pcie-driver_4.24.0_all.deb",
            "rpi-cam-hailo/vendor/models/yolo_model.hef",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"vendor fixture")

    def _create_qemu_outputs(self) -> Path:
        deploy = self.root / "build/kas-work/build/qemu/tmp/deploy/images/qemuarm64"
        deploy.mkdir(parents=True)
        (deploy / "rpi5-minimal-image-qemuarm64.rootfs.ext4").write_bytes(b"rootfs")
        (deploy / "Image").write_bytes(b"kernel")
        (deploy / "rpi5-minimal-image-qemuarm64.rootfs.manifest").write_text(
            "package-a\\n", encoding="utf-8"
        )
        licenses = (
            self.root
            / "build/kas-work/build/qemu/tmp/deploy/licenses/qemuarm64/"
            "rpi5-minimal-image-qemuarm64.rootfs-20260726013314"
        )
        licenses.mkdir(parents=True)
        (licenses / "LICENSE.manifest").write_text("MIT\\n", encoding="utf-8")
        license_link = licenses.parent / "rpi5-minimal-image-qemuarm64.rootfs"
        license_link.symlink_to(licenses.name, target_is_directory=True)
        stale = (
            licenses.parent
            / "rpi5-minimal-image-qemuarm64.rootfs-20260726012334"
        )
        stale.mkdir()
        (stale / "STALE").write_text("old build\n", encoding="utf-8")
        sbom = deploy / "actual-image.spdx.json"
        sbom.write_text('{"SPDXID":"SPDXRef-DOCUMENT"}\n')
        (deploy / "rpi5-minimal-image-qemuarm64.rootfs.spdx.json").symlink_to(sbom.name)
        self._snapshot()
        return deploy

    def test_parse_uses_profile_specific_locked_kas_environment(self) -> None:
        """Catches a profile mapping or KAS build-directory regression."""
        expected = {
            "qemu": "kas/qemuarm64-minimal.yml",
            "rpi5-minimal": "kas/rpi5-minimal.yml",
            "rpi5-camera": "kas/rpi5-camera.yml",
            "rpi5-camera-hailo": "kas/rpi5-camera-hailo.yml",
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

    def test_ci_container_mode_is_forwarded_only_when_explicitly_enabled(self) -> None:
        """Catches silently running a CI build with native-host preflight rules."""
        cases = (
            ({}, False),
            ({"RPI5_CI_CONTAINER": "0"}, False),
            ({"RPI5_CI_CONTAINER": "1"}, True),
        )
        for environment, expect_container in cases:
            with self.subTest(environment=environment):
                self.calls.unlink(missing_ok=True)
                result = self._run(
                    "bash",
                    "scripts/build.sh",
                    "--build-id",
                    BUILD_ID,
                    "qemu",
                    "parse",
                    **environment,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                preflight_calls = [
                    line
                    for line in self._calls().splitlines()
                    if line.startswith("preflight ")
                ]
                self.assertEqual(len(preflight_calls), 1)
                self.assertEqual(
                    preflight_calls[0].endswith(" --container"),
                    expect_container,
                    preflight_calls[0],
                )

    def test_all_profiles_build_without_qemu_or_hardware_pass(self) -> None:
        """Image generation must reach kas and collection without runtime tests."""
        self._active_build()
        self._create_vendor_inputs()
        self._write_executable(
            self.root / "scripts/collect-artifacts.sh",
            '#!/usr/bin/env bash\nprintf "collector %s\\n" "$*" >> "$TEST_CALLS"\n',
        )
        for profile in ("qemu", "rpi5-minimal", "rpi5-camera", "rpi5-camera-hailo"):
            for explicit in (True, False):
                with self.subTest(profile=profile, explicit=explicit):
                    self.calls.unlink(missing_ok=True)
                    arguments = ("--build-id", BUILD_ID) if explicit else ()
                    result = self._run("bash", "scripts/build.sh", *arguments, profile, "build")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    calls = self._calls()
                    config = "kas/qemuarm64-minimal.yml" if profile == "qemu" else f"kas/{profile}.yml"
                    self.assertIn("preflight --incremental --key", calls)
                    self.assertIn(f"uv args=run --locked kas build {config} ", calls)
                    self.assertIn(f"collector --build-id {BUILD_ID} --profile {profile} ", calls)
                    self.assertTrue((self.root / "artifacts" / BUILD_ID / profile / "build.log").is_file())
                    self.assertFalse(list((self.root / "artifacts").rglob("PASS")))
                    self.assertFalse((self.root / "artifacts" / BUILD_ID / "qemu-test").exists())
                    self.assertFalse((self.root / "artifacts" / BUILD_ID / "rpi5-test").exists())

    def test_build_still_stops_on_host_preflight_failure(self) -> None:
        self._write_executable(
            self.root / "scripts/host-preflight.sh",
            '#!/usr/bin/env bash\nprintf "host preflight failed\\n" >&2\nexit 1\n',
        )
        result = self._run("bash", "scripts/build.sh", "--build-id", BUILD_ID, "rpi5-camera-hailo", "build")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("host preflight failed", result.stderr)
        self.assertNotIn("uv args=", self._calls())
        self.assertFalse((self.root / "artifacts").exists())

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
        sums = (out / "checksums/SHA256SUMS").read_text().splitlines()
        names = [line.split("  ", 1)[1] for line in sums]
        self.assertEqual(names, sorted(names))
        expected_names = {str(path.relative_to(out)) for subtree in ("images", "manifests", "provenance")
                          for path in (out / subtree).rglob("*") if path.is_file()}
        self.assertEqual(set(names), expected_names)
        self.assertIn(f"{checksum}  images/rpi5-minimal-image-qemuarm64.rootfs.ext4", sums)
        checked = subprocess.run(["sha256sum", "-c", "checksums/SHA256SUMS"], cwd=out,
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        sbom = out / "manifests/image.spdx.json"
        self.assertFalse(sbom.is_symlink())
        self.assertEqual(sbom.read_text(), '{"SPDXID":"SPDXRef-DOCUMENT"}\n')
        self.assertTrue((out / "security").is_dir())
        self.assertFalse((out / "security/PASS").exists())
        metadata = (out / "manifests" / "build-metadata.json").read_text(encoding="utf-8")
        self.assertIn(f'"build_id":"{BUILD_ID}"', metadata)
        self.assertIn(f'"project_revision":"{FULL_REVISION}"', metadata)
        tool_metadata = json.loads(metadata)
        self.assertIn("uv 0.11.31", tool_metadata["uv_version"])
        self.assertTrue(tool_metadata["python_version"].startswith("Python 3."))
        licenses = out / "licenses"
        self.assertTrue(
            (
                licenses
                / "rpi5-minimal-image-qemuarm64.rootfs-20260726013314"
                / "LICENSE.manifest"
            ).is_file()
        )
        self.assertFalse(
            (
                licenses
                / "rpi5-minimal-image-qemuarm64.rootfs-20260726012334"
            ).exists()
        )
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
        self._create_vendor_inputs()
        for profile, image in (
            ("rpi5-minimal", "rpi5-minimal-image"),
            ("rpi5-camera", "rpi5-camera-image"),
            ("rpi5-camera-hailo", "rpi5-camera-image"),
        ):
            with self.subTest(profile=profile):
                build = self.root / "build/kas-work/build" / profile
                deploy = build / "tmp/deploy/images/raspberrypi5"
                deploy.mkdir(parents=True)
                (deploy / f"{image}-raspberrypi5.rootfs.wic.bz2").write_bytes(b"disk")
                (deploy / f"{image}-raspberrypi5.rootfs.wic.bmap").write_text("bmap\n", encoding="utf-8")
                (deploy / f"{image}-raspberrypi5.rootfs.manifest").write_text("package-a\n", encoding="utf-8")
                if profile != "rpi5-minimal":
                    (deploy / "camera-firmware-integrity-public.pem").write_text("fixture public key\n")
                licenses = (
                    build / "tmp/deploy/licenses/raspberrypi5"
                    / f"{image}-raspberrypi5.rootfs-20260726012334"
                )
                licenses.mkdir(parents=True)
                (licenses / "LICENSE.manifest").write_text("MIT\n", encoding="utf-8")
                (licenses.parent / f"{image}-raspberrypi5.rootfs").symlink_to(
                    licenses.name, target_is_directory=True,
                )

                (deploy / f"{image}-raspberrypi5.rootfs.spdx.json").write_text('{"SPDXID":"SPDXRef-DOCUMENT"}\n')
                self._snapshot(profile)
                result = self._run(*self._collector_arguments(profile))

                self.assertEqual(result.returncode, 0, result.stderr)
                out = self.root / "artifacts" / BUILD_ID / profile / "images"
                self.assertEqual((out / f"{image}-raspberrypi5.rootfs.wic.bz2").read_bytes(), b"disk")
                self.assertEqual((out / f"{image}-raspberrypi5.rootfs.wic.bmap").read_text(encoding="utf-8"), "bmap\n")
                self.assertTrue((out.parent / "COMPLETE").is_file())
                metadata = json.loads((out.parent / "manifests/build-metadata.json").read_text(encoding="utf-8"))
                self.assertEqual(metadata["profile"], profile)
                self.assertEqual(metadata["image"], image)
                if profile != "rpi5-minimal":
                    public = out.parent / "manifests/camera-integrity-public.pem"
                    self.assertTrue(public.is_file(), "camera build must export its actual signing public key")
                    self.assertEqual(public.read_text(), "fixture public key\n")
                    checksums = (out.parent / "checksums/SHA256SUMS").read_text()
                    self.assertIn("manifests/camera-integrity-public.pem", checksums)

    def test_camera_parse_prepares_local_signing_identity_before_bitbake(self) -> None:
        result = self._run("bash", "scripts/build.sh", "--build-id", BUILD_ID,
                           "rpi5-camera-hailo", "parse")
        self.assertEqual(result.returncode, 0, result.stderr)
        private = self.root / "keys/camera-firmware/integrity-private.pem"
        self.assertTrue(private.is_file(), "camera builds need a local signing identity")
        self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
        self.assertIn("bitbake -p", self._calls())

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
            "qemuarm64/rpi5-minimal-image-qemuarm64.rootfs-20260726013314"
        )
        (source_licenses / "OBSOLETE").write_text("old\n", encoding="utf-8")

        first = self._run(*self._collector_arguments(), FAIL_FOR_ALL_REPOS="1")

        self.assertNotEqual(first.returncode, 0)
        output_licenses = (
            self.root / "artifacts" / BUILD_ID / "qemu" / "licenses"
            / "rpi5-minimal-image-qemuarm64.rootfs-20260726013314"
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

    def test_collector_requires_provenance_before_clearing_outputs(self) -> None:
        self._create_qemu_outputs()
        out = self.root / "artifacts" / BUILD_ID / "qemu"
        shutil.rmtree(out / "provenance")
        (out / "images").mkdir()
        (out / "images/keep").write_text("keep")
        result = self._run(*self._collector_arguments())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source provenance missing", result.stderr)
        self.assertEqual((out / "images/keep").read_text(), "keep")
        self.assertFalse((out / "COMPLETE").exists())

    def test_collector_requires_image_spdx_without_sealing_evidence(self) -> None:
        deploy = self._create_qemu_outputs()
        (deploy / "rpi5-minimal-image-qemuarm64.rootfs.spdx.json").unlink()
        result = self._run(*self._collector_arguments())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("image SPDX missing", result.stderr)
        out = self.root / "artifacts" / BUILD_ID / "qemu"
        self.assertFalse((out / "COMPLETE").exists())
        self.assertTrue((out / "provenance/sources.tar").is_file())

    def test_changed_source_blocks_collection_before_clearing_existing_outputs(self) -> None:
        self._create_qemu_outputs()
        out = self.root / "artifacts" / BUILD_ID / "qemu"
        (out / "images").mkdir()
        (out / "images/keep").write_text("keep existing attempt")
        path = self.root / "scripts/build.sh"
        path.write_text(path.read_text() + "\n# changed after kas started\n")
        result = self._run(*self._collector_arguments())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("changed", result.stderr)
        self.assertEqual((out / "images/keep").read_text(), "keep existing attempt")
        self.assertFalse((out / "COMPLETE").exists())

    def test_build_snapshots_before_kas_and_refuses_changed_input_retry(self) -> None:
        self._create_qemu_outputs()
        shutil.rmtree(self.root / "artifacts" / BUILD_ID / "qemu/provenance")
        result = self._run("bash", "scripts/build.sh", "--build-id", BUILD_ID, "qemu", "build",
                           FAIL_FOR_ALL_REPOS="1")
        self.assertNotEqual(result.returncode, 0)
        out = self.root / "artifacts" / BUILD_ID / "qemu"
        original = (out / "provenance/inputs.json").read_bytes()
        path = self.root / "scripts/build.sh"
        path.write_text(path.read_text() + "\n# changed inputs\n")
        self.calls.unlink()
        result = self._run("bash", "scripts/build.sh", "--build-id", BUILD_ID, "qemu", "build")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fresh build ID", result.stderr)
        self.assertNotIn("uv args=run --locked kas build", self._calls())
        self.assertEqual((out / "provenance/inputs.json").read_bytes(), original)
        self.assertFalse((out / "COMPLETE").exists())

    def test_collector_records_actual_codex_package_version(self) -> None:
        deploy = self._create_qemu_outputs()
        (deploy / "rpi5-minimal-image-qemuarm64.rootfs.manifest").write_text(
            "codex-cli aarch64 0.999.0-r0\nother aarch64 1.0-r0\n")
        result = self._run(*self._collector_arguments())
        self.assertEqual(result.returncode, 0, result.stderr)
        out = self.root / "artifacts" / BUILD_ID / "qemu"
        resolved = json.loads((out / "manifests/resolved-packages.json").read_text())
        self.assertEqual(resolved["codex-cli"], [{"architecture": "aarch64", "version": "0.999.0-r0"}])

    def test_scripts_are_valid_bash(self) -> None:
        """Catches syntax errors that prevent either shell entry point from starting."""
        for path in ("scripts/build.sh", "scripts/collect-artifacts.sh"):
            result = run("bash", "-n", path)
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
