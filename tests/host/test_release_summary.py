from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from support import REPO_ROOT


sys.path.insert(0, str(REPO_ROOT / "scripts"))
import release_summary  # noqa: E402


PINS = {
    "bitbake": "fae9db3168dbff1b8c76fe9c6726a9687ff97514",
    "openembedded-core": "b5a6cada82d7ffb362bda9081c354dcc0b6ee264",
    "meta-yocto": "824795b885b25e074a2880fbcd54e1a6c875d47d",
    "meta-openembedded": "d97b5602d7f64422c94b7311466cda7f6b1962d5",
    "meta-raspberrypi": "f62c67921474370829d24a4fa01ef88543f3906b",
}
REVISION = "0123456789abcdef0123456789abcdef01234567"
BUILD_ID = "20260722T120000Z-0123456789ab"
COMPLETED_AT = "2026-07-22T12:00:00Z"
MINIMAL_IMAGE = "rpi5-minimal-image-raspberrypi5.rootfs.wic.bz2"
CAMERA_IMAGE = "rpi5-camera-image-raspberrypi5.rootfs.wic.bz2"


class ReleaseSummaryTest(unittest.TestCase):
    def write_json(self, path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def fixture(self, root: Path) -> None:
        lock = root / "kas/lock.yml"
        lock.parent.mkdir(parents=True)
        lock.write_text(
            "header:\n  version: 19\noverrides:\n  repos:\n"
            + "".join(
                f"    {name}:\n      commit: {commit}\n"
                for name, commit in PINS.items()
            ),
            encoding="utf-8",
        )

        base = root / "artifacts" / BUILD_ID
        for marker in release_summary.REQUIRED_MARKERS:
            path = base / marker
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

        for profile, image, digest in (
            ("rpi5-minimal", MINIMAL_IMAGE, "a" * 64),
            ("rpi5-camera", CAMERA_IMAGE, "b" * 64),
        ):
            self.write_json(
                base / profile / "manifests/build-metadata.json",
                {
                    "build_id": BUILD_ID,
                    "project_revision": REVISION,
                    "raw_log_path": f"/private/{profile}/console.log",
                },
            )
            sums = base / profile / "checksums/SHA256SUMS"
            sums.parent.mkdir(parents=True, exist_ok=True)
            bmap = image.removesuffix(".bz2") + ".bmap"
            sums.write_text(
                f"{digest}  images/{image}\n"
                f"{'c' * 64}  images/{bmap}\n",
                encoding="utf-8",
            )

        revisions = base / "rpi5-camera/manifests/layer-revisions.txt"
        revisions.write_text(
            "".join(f"{name} {commit}\n" for name, commit in PINS.items()),
            encoding="utf-8",
        )
        self.write_json(
            base / "rpi5-test/result.json",
            {
                "build_id": BUILD_ID,
                "reboots": 3,
                "result": "PASS",
                "ip_address": "192.0.2.10",
                "mac_address": "dc:a6:32:00:00:01",
                "user_name": "private-operator",
            },
        )
        self.write_json(
            base / "camera-test/result.json",
            {
                "build_id": BUILD_ID,
                "sensor": "imx708",
                "lens_variant": "wide-operator-verified",
                "h264": "libx264-1920x1080-30fps",
                "result": "PASS",
                "device_serial": "private-device-serial",
                "operator_notes": "private-free-form-notes",
                "sample_media": "/private/capture.h264",
            },
        )

    def build(self, root: Path) -> dict[str, object]:
        return release_summary.build_record(
            root,
            BUILD_ID,
            REVISION,
            COMPLETED_AT,
        )

    def expected_record(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "build_id": BUILD_ID,
            "project_revision": REVISION,
            "source_revisions": PINS,
            "images": {
                "rpi5_minimal": {
                    "filename": MINIMAL_IMAGE,
                    "sha256": "a" * 64,
                },
                "rpi5_camera": {
                    "filename": CAMERA_IMAGE,
                    "sha256": "b" * 64,
                },
            },
            "validation": {
                "qemu": "PASS",
                "rpi5": "PASS",
                "reboots": 3,
                "camera": "PASS",
                "sensor": "imx708",
                "lens_variant": "wide-operator-verified",
                "h264": "libx264-1920x1080-30fps",
            },
            "validation_completed_at": COMPLETED_AT,
        }

    def test_builds_exact_sanitized_record_from_complete_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)

            record = self.build(root)

            self.assertEqual(record, self.expected_record())
            serialized = json.dumps(record)
            for forbidden_value in (
                "192.0.2.10",
                "dc:a6:32:00:00:01",
                "private-operator",
                "private-device-serial",
                "private-free-form-notes",
                "/private/capture.h264",
                "/private/rpi5-minimal/console.log",
            ):
                self.assertNotIn(forbidden_value, serialized)

    def test_requires_regular_non_symlink_gate_markers(self) -> None:
        for marker_mode in ("missing", "symlink"):
            with self.subTest(marker_mode=marker_mode):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    self.fixture(root)
                    marker = (
                        root / "artifacts" / BUILD_ID / "camera-test/PASS"
                    )
                    marker.unlink()
                    if marker_mode == "symlink":
                        target = root / "marker-target"
                        target.touch()
                        marker.symlink_to(target)

                    with self.assertRaisesRegex(ValueError, "required marker"):
                        self.build(root)

    def test_requires_exact_unique_source_revision_set(self) -> None:
        for revision_mode in ("mismatch", "missing", "extra", "duplicate"):
            with self.subTest(revision_mode=revision_mode):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    self.fixture(root)
                    revisions = (
                        root
                        / "artifacts"
                        / BUILD_ID
                        / "rpi5-camera/manifests/layer-revisions.txt"
                    )
                    lines = revisions.read_text(encoding="utf-8").splitlines()
                    if revision_mode == "mismatch":
                        lines[0] = f"bitbake {'f' * 40}"
                    elif revision_mode == "missing":
                        lines.pop()
                    elif revision_mode == "extra":
                        lines.append(f"unexpected-layer {'c' * 40}")
                    else:
                        lines.append(lines[0])
                    revisions.write_text("\n".join(lines) + "\n", encoding="utf-8")

                    with self.assertRaisesRegex(
                        ValueError, "source revision"
                    ):
                        self.build(root)

    def test_rejects_invalid_identity_metadata_and_utc_timestamp(self) -> None:
        cases = (
            ("bad-build-id", REVISION, COMPLETED_AT),
            (BUILD_ID, "f" * 40, COMPLETED_AT),
            (BUILD_ID, REVISION.upper(), COMPLETED_AT),
            (BUILD_ID, REVISION, "2026-07-22T12:00:00+00:00"),
            (BUILD_ID, REVISION, "2026-02-30T12:00:00Z"),
        )
        for build_id, revision, completed_at in cases:
            with self.subTest(
                build_id=build_id,
                revision=revision,
                completed_at=completed_at,
            ):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    self.fixture(root)
                    with self.assertRaises(ValueError):
                        release_summary.build_record(
                            root,
                            build_id,
                            revision,
                            completed_at,
                        )

        for profile, field, replacement in (
            ("rpi5-minimal", "build_id", "20260722T120001Z-0123456789ab"),
            ("rpi5-camera", "project_revision", "f" * 40),
        ):
            with self.subTest(profile=profile, field=field):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    self.fixture(root)
                    metadata_path = (
                        root
                        / "artifacts"
                        / BUILD_ID
                        / profile
                        / "manifests/build-metadata.json"
                    )
                    metadata = json.loads(
                        metadata_path.read_text(encoding="utf-8")
                    )
                    metadata[field] = replacement
                    self.write_json(metadata_path, metadata)

                    with self.assertRaisesRegex(ValueError, profile):
                        self.build(root)

    def test_rejects_failed_or_weakened_hardware_results(self) -> None:
        cases = (
            (
                "rpi5-test/result.json",
                "build_id",
                "20260722T120001Z-0123456789ab",
            ),
            ("rpi5-test/result.json", "reboots", 2),
            ("rpi5-test/result.json", "result", "FAIL"),
            (
                "camera-test/result.json",
                "build_id",
                "20260722T120001Z-0123456789ab",
            ),
            ("camera-test/result.json", "sensor", "imx219"),
            (
                "camera-test/result.json",
                "lens_variant",
                "wide-unverified",
            ),
            (
                "camera-test/result.json",
                "h264",
                "hardware-h264-1920x1080-30fps",
            ),
            ("camera-test/result.json", "result", "FAIL"),
        )
        for relative_path, field, replacement in cases:
            with self.subTest(path=relative_path, field=field):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    self.fixture(root)
                    result_path = (
                        root / "artifacts" / BUILD_ID / relative_path
                    )
                    result = json.loads(
                        result_path.read_text(encoding="utf-8")
                    )
                    result[field] = replacement
                    self.write_json(result_path, result)

                    with self.assertRaises(ValueError):
                        self.build(root)

    def test_requires_profile_specific_wic_checksum(self) -> None:
        cases = (
            (
                "rpi5-minimal",
                f"{'a' * 64}  images/{CAMERA_IMAGE}\n",
            ),
            (
                "rpi5-camera",
                f"{'B' * 64}  images/{CAMERA_IMAGE}\n",
            ),
            (
                "rpi5-camera",
                f"{'b' * 64}  images/{CAMERA_IMAGE}\n"
                f"{'c' * 64}  images/extra.wic.bz2\n",
            ),
        )
        for profile, contents in cases:
            with self.subTest(profile=profile, contents=contents):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    self.fixture(root)
                    checksums = (
                        root
                        / "artifacts"
                        / BUILD_ID
                        / profile
                        / "checksums/SHA256SUMS"
                    )
                    checksums.write_text(contents, encoding="utf-8")

                    with self.assertRaisesRegex(ValueError, "checksum"):
                        self.build(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            checksums = (
                root
                / "artifacts"
                / BUILD_ID
                / "rpi5-minimal/checksums/SHA256SUMS"
            )
            contents = checksums.read_text(encoding="utf-8")
            checksums.unlink()
            target = root / "external-checksums"
            target.write_text(contents, encoding="utf-8")
            checksums.symlink_to(target)

            with self.assertRaisesRegex(ValueError, "checksum"):
                self.build(root)

    def test_release_record_write_is_deterministic_and_non_overwriting(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "artifacts/releases" / f"{BUILD_ID}.json"
            record = self.expected_record()

            release_summary.write_record(output, record)

            self.assertEqual(
                output.read_text(encoding="utf-8"),
                json.dumps(record, indent=2, sort_keys=True) + "\n",
            )
            with self.assertRaises(FileExistsError):
                release_summary.write_record(output, {"schema_version": 999})
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                record,
            )


if __name__ == "__main__":
    unittest.main()
