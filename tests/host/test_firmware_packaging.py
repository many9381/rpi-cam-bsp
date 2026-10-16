import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT


class FirmwarePackagingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.unpack = self.root / "unpack"
        self.destination = self.root / "image"
        self.unpack.mkdir()
        dist = self.source / "web/dist"
        dist.mkdir(parents=True)
        for name in ("index.html", "app.js", "styles.css"):
            (dist / name).write_text(f"test asset: {name}\n")
        # A build-host package must never leak into the target image.
        modules = self.source / "web/node_modules"
        modules.mkdir()
        (modules / "build-host-only").write_text("not a target asset")
        self.recipe_dir = REPO_ROOT / "meta-rpi-cam-hailo/recipes-camera/camera-firmware"
        self.assertTrue(
            self.recipe_dir.is_dir(),
            f"dedicated firmware recipe directory is missing: {self.recipe_dir}",
        )

    def install(self) -> subprocess.CompletedProcess:
        recipe = (self.recipe_dir / "camera-firmware-web_git.bb").read_text()
        match = re.search(r"^do_install\(\) \{\n(.*?)^\}", recipe, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        for name, value in {
            "S": self.source,
            "UNPACKDIR": self.unpack,
            "D": self.destination,
            "datadir": "/usr/share",
        }.items():
            body = body.replace("${" + name + "}", str(value))
        return subprocess.run(["bash", "-eu", "-c", body], capture_output=True, text=True)

    def test_installs_only_web_assets_and_third_party_notices(self) -> None:
        """Run the recipe's real install body; don't replace it with a mock."""
        notices = self.recipe_dir / "files/web-third-party-notices.txt"
        shutil.copyfile(notices, self.unpack / notices.name)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.destination / "usr/share/camera-firmware"
        self.assertEqual(
            {str(path.relative_to(installed)) for path in installed.rglob("*") if path.is_file()},
            {"web/index.html", "web/app.js", "web/styles.css", "licenses/web-third-party-notices.txt"},
        )
        self.assertEqual((installed / "licenses" / notices.name).read_bytes(), notices.read_bytes())

    def test_missing_notices_fail_installation(self) -> None:
        """A distributable bundle must not silently omit its notices."""
        result = self.install()
        self.assertNotEqual(result.returncode, 0)

    def test_firmware_declares_dynamically_loaded_media_plugins(self) -> None:
        """Shlib dependency scanning cannot discover GStreamer factories."""
        recipe = (self.recipe_dir / "camera-firmware_git.bb").read_text()
        dependencies = recipe.partition('RDEPENDS:${PN} += "')[2].partition('"')[0].split()
        required = {
            "glib-networking",
            "gstreamer1.0-plugins-base-app",
            "gstreamer1.0-plugins-good-isomp4",
            "gstreamer1.0-plugins-good-rtp",
            "gstreamer1.0-plugins-good-rtpmanager",
            "gstreamer1.0-plugins-good-udp",
            "gstreamer1.0-plugins-bad-srtp",
            "gstreamer1.0-plugins-bad-videoparsersbad",
        }
        self.assertFalse(required.difference(dependencies), required.difference(dependencies))


if __name__ == "__main__":
    unittest.main()
