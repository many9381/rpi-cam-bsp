import os
from pathlib import Path
import pwd
import grp
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

from support import REPO_ROOT


RECIPE = REPO_ROOT / "meta-rpi-cam-hailo/recipes-camera/camera-firmware/rpi-cam-hailo-devrepo_git.bb"


class FirmwareDevRepoTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(RECIPE.is_file(), "development repository recipe is missing")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "unpacked-source"
        self.destination = self.root / "image"
        self.target = self.destination / "home/rpiadmin/rpi-cam-hailo"
        self.environment = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
        self.git("init", "--initial-branch=master", "--template=", str(self.source))
        self.git("-C", str(self.source), "config", "user.name", "Fixture Developer")
        self.git("-C", str(self.source), "config", "user.email", "fixture@example.invalid")
        (self.source / "README.md").write_text("initial commit\n")
        self.git("-C", str(self.source), "add", "README.md")
        self.git("-C", str(self.source), "commit", "-m", "first")
        self.first = self.git("-C", str(self.source), "rev-parse", "HEAD").stdout.strip()
        (self.source / ".gitignore").write_text("auth.json\nnode_modules/\n")
        (self.source / "README.md").write_text("selected revision\n")
        self.git("-C", str(self.source), "add", ".")
        self.git("-C", str(self.source), "commit", "-m", "selected")
        self.revision = self.git("-C", str(self.source), "rev-parse", "HEAD").stdout.strip()
        # Local settings, hooks, ignored files and uncommitted modifications
        # must never be copied into the installed development checkout.
        self.git("-C", str(self.source), "config", "credential.helper", "fixture-secret-helper")
        hooks = self.source / ".git/hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "post-checkout").write_text("fixture-secret-hook")
        (self.source / "auth.json").write_text("fixture-secret-auth")
        (self.source / "node_modules").mkdir()
        (self.source / "node_modules/host-only").touch()
        (self.source / "README.md").write_text("uncommitted change\n")

    def git(self, *arguments):
        result = subprocess.run(["git", *arguments], capture_output=True, text=True, env=self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def install(self, revision=None, security_patches=()):
        match = re.search(r"^do_install\(\) \{\n(.*?)^\}", RECIPE.read_text(), re.M | re.S)
        self.assertIsNotNone(match)
        body = match.group(1)
        for key, value in {"S": self.source, "D": self.destination,
                           "CAMERA_FIRMWARE_SRCREV": revision or self.revision,
                           "UNPACKDIR": self.root,
                           "CF_DEV_SECURITY_PATCHES": " ".join(security_patches)}.items():
            body = body.replace("${" + key + "}", str(value))
        # Rootless harness: use this process's real account for the final chown.
        owner = pwd.getpwuid(os.getuid()).pw_name + ":" + grp.getgrgid(os.getgid()).gr_name
        body = body.replace("rpiadmin:rpiadmin", owner)
        return subprocess.run(["bash", "-eu", "-c", body], capture_output=True, text=True,
                              env=self.environment)

    def test_installs_pinned_writable_repo_with_history_without_host_state(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / ".git").is_dir())
        self.assertEqual(self.git("-C", str(self.target), "rev-parse", "HEAD").stdout.strip(), self.revision)
        self.assertEqual(self.git("-C", str(self.target), "rev-parse", "HEAD^").stdout.strip(), self.first)
        self.assertEqual(self.git("-C", str(self.target), "branch", "--show-current").stdout.strip(), "master")
        self.assertEqual(self.git("-C", str(self.target), "status", "--porcelain").stdout, "")
        self.assertEqual((self.target / "README.md").read_text(), "selected revision\n")
        self.assertFalse((self.target / "auth.json").exists())
        self.assertFalse((self.target / "node_modules").exists())
        self.assertFalse((self.target / ".git/hooks/post-checkout").exists())
        config = (self.target / ".git/config").read_text()
        self.assertNotIn("fixture-secret", config)
        self.assertNotIn(str(self.source), config)
        self.assertEqual(self.git("-C", str(self.target), "remote", "get-url", "origin").stdout.strip(),
                         "git@github.com:many9381/rpi-cam-hailo.git")
        self.assertEqual(self.target.stat().st_uid, os.getuid())

    def test_repository_remains_complete_after_build_input_is_removed(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.target / ".git/objects/info/alternates").exists())
        self.assertFalse((self.target / ".git/FETCH_HEAD").exists())
        shutil.rmtree(self.source)
        self.git("-C", str(self.target), "fsck", "--full")
        self.git("-C", str(self.target), "show", "HEAD^:README.md")
        (self.target / "README.md").write_text("device edit\n")
        self.git("-C", str(self.target), "add", "README.md")
        self.git("-C", str(self.target), "-c", "user.name=Device Developer", "-c",
                 "user.email=device@example.invalid", "commit", "-m", "device edit")

    def test_missing_selected_commit_fails_installation(self):
        result = self.install("1" * 40)
        self.assertNotEqual(result.returncode, 0)

    def test_applies_reviewed_security_patch_without_copying_host_changes(self):
        patch = self.root / "security.patch"
        patch.write_text("--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n"
                         "-selected revision\n+security-patched revision\n")
        result = self.install(security_patches=(patch.name,))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "README.md").read_text(), "security-patched revision\n")
        self.assertEqual(self.git("-C", str(self.target), "show", "HEAD:README.md").stdout,
                         "selected revision\n")
        self.assertEqual(self.git("-C", str(self.target), "status", "--porcelain").stdout,
                         " M README.md\n")
        self.assertFalse((self.target / "auth.json").exists())

    def test_incompatible_security_patch_fails_installation(self):
        patch = self.root / "security.patch"
        patch.write_text("--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n"
                         "-unrelated revision\n+security-patched revision\n")
        result = self.install(security_patches=(patch.name,))
        self.assertNotEqual(result.returncode, 0)

    def test_dev_package_is_separate_and_uses_existing_account_and_source_pin(self):
        recipe = RECIPE.read_text()
        self.assertIn("require camera-firmware-source.inc", recipe)
        self.assertIn('USERADD_DEPENDS = "device-config"', recipe)
        self.assertIn('RDEPENDS:${PN} = "git device-config"', recipe)
        self.assertIn('FILES:${PN} = "/home/rpiadmin/rpi-cam-hailo"', recipe)
        group = (REPO_ROOT / "meta-rpi-cam-hailo/recipes-core/packagegroups/packagegroup-camera-firmware.bb").read_text()
        self.assertNotIn("rpi-cam-hailo-devrepo", group)

    def test_camera_toggle_is_exposed_and_other_images_do_not_select_repo(self):
        camera = yaml.safe_load((REPO_ROOT / "kas/rpi5-camera.yml").read_text())
        self.assertIn("RPI_CAM_HAILO_DEV_REPO", camera["env"])
        self.assertIn('RPI_CAM_HAILO_DEV_REPO ?= "1"', camera["local_conf_header"]["rpi5-camera"])
        append = (REPO_ROOT / "meta-rpi-cam-hailo/recipes-core/images/rpi5-camera-image.bbappend").read_text()
        self.assertIn("RPI_CAM_HAILO_DEV_REPO", append)
        self.assertIn("rpi-cam-hailo-devrepo", append)
        for profile in ("base.yml", "rpi5-minimal.yml", "qemuarm64-minimal.yml"):
            self.assertNotIn("RPI_CAM_HAILO_DEV_REPO", (REPO_ROOT / "kas" / profile).read_text())


if __name__ == "__main__":
    unittest.main()
