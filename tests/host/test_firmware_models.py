import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

from support import REPO_ROOT


MODEL_BYTES = b"firmware model fixture\n"
MODEL_SHA256 = "f5ac6678a9d20a795bc9fc56fa7b0adc5327cdd22140750dc33d12a2862c900d"


def recipe_function(recipe: str, name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}\(\) \{{\n(.*?)^\}}",
        recipe,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"recipe function is missing: {name}")
    return match.group(1)


def expand_bitbake_variables(body: str, values: dict[str, Path | str]) -> str:
    for name, value in values.items():
        body = body.replace("${" + name + "}", str(value))
    return body


class FirmwareModelRecipeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.unpack = self.root / "unpack"
        self.destination = self.root / "image"
        self.unpack.mkdir()
        self.recipe_path = (
            REPO_ROOT
            / "meta-rpi-cam-hailo/recipes-camera/camera-firmware-models/camera-firmware-models_1.0.bb"
        )
        self.assertTrue(
            self.recipe_path.is_file(),
            f"firmware model recipe is missing: {self.recipe_path}",
        )

    def validate_and_install(self) -> subprocess.CompletedProcess[str]:
        recipe = self.recipe_path.read_text(encoding="utf-8")
        body = recipe_function(recipe, "do_validate_model")
        body += recipe_function(recipe, "do_install")
        body = expand_bitbake_variables(
            body,
            {
                "UNPACKDIR": self.unpack,
                "D": self.destination,
                "datadir": "/usr/share",
                "CF_MODEL_SHA256": MODEL_SHA256,
            },
        )
        script = 'bbfatal() { printf "%s\\n" "$*" >&2; exit 1; }\n' + body
        return subprocess.run(
            ["bash", "-eu", "-c", script], capture_output=True, text=True
        )

    def installed_model(self) -> Path:
        return self.destination / "usr/share/camera-firmware/models/yolo_model.hef"

    def test_installs_verified_model_bytes_read_only(self) -> None:
        """Changing the copy path, bytes, or mode must fail this boundary test."""
        (self.unpack / "yolo_model.hef").write_bytes(MODEL_BYTES)

        result = self.validate_and_install()

        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.installed_model()
        self.assertEqual(installed.read_bytes(), MODEL_BYTES)
        self.assertEqual(stat.S_IMODE(installed.stat().st_mode), 0o644)

    def test_rejects_model_with_changed_bytes_before_installing(self) -> None:
        """Removing checksum validation must allow this changed fixture and fail the test."""
        (self.unpack / "yolo_model.hef").write_bytes(MODEL_BYTES + b"changed")

        result = self.validate_and_install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256", result.stderr)
        self.assertFalse(self.installed_model().exists())

    def test_rejects_missing_model_before_installing(self) -> None:
        """Removing the explicit source check must lose the clear diagnostic."""
        result = self.validate_and_install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing", result.stderr.lower())
        self.assertFalse(self.installed_model().exists())

    def test_missing_optional_model_skips_recipe_without_local_fetch_uri(self) -> None:
        """An unconditional file URI must make standard camera metadata fail this test."""
        recipe = self.recipe_path.read_text(encoding="utf-8")
        selector = re.search(
            r"^def camera_firmware_model_src_uri\(d\):\n(?:    .*\n)+",
            recipe,
            re.MULTILINE,
        )
        self.assertIsNotNone(selector)
        anonymous = recipe_function(recipe, "python __anonymous")

        class SkipRecipe(Exception):
            pass

        class Parse:
            def __init__(self) -> None:
                self.dependencies: list[str] = []

            def mark_dependency(self, _data, path: str) -> None:
                self.dependencies.append(path)

        Parse.SkipRecipe = SkipRecipe

        class BitBake:
            parse = Parse()

        missing = self.root / "private-models/yolo_model.hef"

        class Data:
            def expand(self, _expression: str) -> str:
                return str(missing)

        namespace = {"bb": BitBake}
        exec(selector.group(0), namespace)
        self.assertEqual(namespace["camera_firmware_model_src_uri"](Data()), "")
        with self.assertRaisesRegex(SkipRecipe, "missing.*yolo_model.hef"):
            exec(textwrap.dedent(anonymous), {"bb": BitBake, "d": Data()})
        self.assertEqual(BitBake.parse.dependencies, [str(missing), str(missing)])


class FirmwareHailoExampleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.unpack = self.root / "unpack"
        self.destination = self.root / "image"
        self.unpack.mkdir()
        self.recipe_dir = REPO_ROOT / "meta-rpi-cam-hailo/recipes-camera/camera-firmware"
        self.assertTrue(
            self.recipe_dir.is_dir(),
            f"dedicated firmware recipe directory is missing: {self.recipe_dir}",
        )

    def install_hailo_example(self) -> tuple[subprocess.CompletedProcess[str], Path]:
        public_key = self.unpack / "integrity-public.pem"
        public_key.write_text("fixture public key\n")
        for source in ("camera-firmware.service", "app-hailo.yaml.example"):
            shutil.copyfile(self.recipe_dir / "files" / source, self.unpack / source)
        for relative in ("vendor/stb/LICENSE", "vendor/fonts/OFL.txt"):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture license: {relative}\n", encoding="utf-8")
        for relative in ("drogon/LICENSE", "trantor/License"):
            path = self.unpack / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture license: {relative}\n", encoding="utf-8")

        recipe = (self.recipe_dir / "camera-firmware_git.bb").read_text(encoding="utf-8")
        body = recipe_function(recipe, "do_install:append")
        body = expand_bitbake_variables(
            body,
            {
                "S": self.source,
                "UNPACKDIR": self.unpack,
                "D": self.destination,
                "systemd_system_unitdir": "/usr/lib/systemd/system",
                "bindir": "/usr/bin",
                "sysconfdir": "/etc",
                "datadir": "/usr/share",
                "CF_APP_CONFIG_EXAMPLE": "app-hailo.yaml.example",
                "CF_INTEGRITY_PUBLIC_KEY_FILE": public_key,
            },
        )
        # Ownership is the only side effect requiring target account metadata;
        # keep the real recipe install and substitution behavior under test.
        script = "chown() { :; }\n" + body
        result = subprocess.run(
            ["bash", "-eu", "-c", script], capture_output=True, text=True
        )
        return result, self.destination / "etc/camera-firmware"

    def installed_hailo_config(self) -> tuple[dict, Path]:
        result, config_dir = self.install_hailo_example()
        self.assertEqual(result.returncode, 0, result.stderr)
        example = config_dir / "app.yaml.example"
        config = yaml.safe_load(example.read_text(encoding="utf-8"))
        self.assertIsInstance(config, dict)
        return config, config_dir

    def test_hailo_example_selects_packaged_object_detection_model(self) -> None:
        """A wrong model schema or path must fail after installing the real example."""
        config, _ = self.installed_hailo_config()

        self.assertEqual(config["camera"]["ai"]["enabled"], True)
        self.assertEqual(config["camera"]["ai"]["model_ids"], ["objects"])
        self.assertEqual(
            config["ai"],
            {
                "enabled": True,
                "backend": "hailo",
                "models": [
                    {
                        "id": "objects",
                        "kind": "object_detection",
                        "hef_path": "/usr/share/camera-firmware/models/yolo_model.hef",
                        "input": {
                            "width": 640,
                            "height": 640,
                            "format": "rgb8",
                            "letterbox": True,
                        },
                        "confidence_threshold": 0.40,
                        "labels": "coco80",
                    }
                ],
            },
        )

    def test_hailo_example_keeps_security_and_client_auth_enabled(self) -> None:
        """Copying insecure upstream development defaults must fail this test."""
        config, _ = self.installed_hailo_config()

        self.assertEqual(config["http"]["tls"]["enabled"], True)
        self.assertEqual(
            config["http"]["tls"]["allow_development_self_signed_tls"], False
        )
        self.assertEqual(config["security"]["enabled"], True)
        self.assertEqual(config["secure_rtsp"]["enabled"], True)
        self.assertEqual(config["secure_rtsp"]["control_tls"], True)
        self.assertEqual(config["secure_rtsp"]["media_srtp"], True)
        self.assertEqual(
            config["secure_rtsp"]["allow_development_self_signed_tls"], False
        )
        self.assertEqual(config["secure_rtsp"]["client_auth"]["enabled"], True)

    def test_hailo_install_leaves_active_configuration_absent(self) -> None:
        """Installing an active app.yaml must fail the provisioning boundary."""
        _, config_dir = self.installed_hailo_config()

        self.assertFalse((config_dir / "app.yaml").exists())


if __name__ == "__main__":
    unittest.main()
