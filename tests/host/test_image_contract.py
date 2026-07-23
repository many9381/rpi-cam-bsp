import unittest

from support import read


class ImageContractTest(unittest.TestCase):
    def test_minimal_image_has_remote_admin_and_no_debug_features(self) -> None:
        recipe = read(
            "meta-rpi5-cam/recipes-core/images/rpi5-minimal-image.bb"
        )
        for package in (
            "device-config",
            "systemd-networkd",
            "openssh-sftp-server",
            "avahi-daemon",
            "sudo",
            "iproute2",
            "util-linux",
            "procps",
            "ethtool",
        ):
            self.assertIn(package, recipe)
        self.assertIn("ssh-server-openssh", recipe)
        self.assertIn("usermod -p '!' root", recipe)
        removed_features = next(
            line
            for line in recipe.splitlines()
            if line.startswith("IMAGE_FEATURES:remove =")
        )
        for feature in (
            "debug-tweaks",
            "allow-empty-password",
            "empty-root-password",
            "allow-root-login",
            "serial-autologin-root",
        ):
            self.assertIn(feature, removed_features)
        self.assertIn('IMAGE_ROOTFS_SIZE = "1048576"', recipe)
        self.assertIn('IMAGE_ROOTFS_EXTRA_SPACE = "524288"', recipe)

    def test_camera_image_is_a_narrow_extension(self) -> None:
        recipe = read(
            "meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bb"
        )
        self.assertIn("require rpi5-minimal-image.bb", recipe)
        for package in (
            "libcamera-apps",
            "libcamera",
            "v4l-utils",
            "media-ctl",
            "rpidistro-ffmpeg",
            "file",
        ):
            self.assertIn(package, recipe)
        for excluded in ("opencv", "tensorflow", "gstreamer", "weston", "qtbase"):
            self.assertNotIn(excluded, recipe.lower())
        self.assertIn('IMAGE_ROOTFS_SIZE = "4194304"', recipe)

    def test_camera_profile_enables_camera_only_commercial_features(self) -> None:
        camera = read("kas/rpi5-camera.yml")
        minimal = read("kas/rpi5-minimal.yml")
        qemu = read("kas/qemuarm64-minimal.yml")

        self.assertIn('RASPBERRYPI_CAMERA_V3 = "1"', camera)
        self.assertIn('PACKAGECONFIG:append:pn-libcamera-apps = " libav"', camera)
        self.assertIn('PACKAGECONFIG:append:pn-rpidistro-ffmpeg = " x264"', camera)
        self.assertIn('LICENSE_FLAGS_ACCEPTED += " commercial"', camera)
        self.assertNotIn("LICENSE_FLAGS_ACCEPTED", minimal)
        self.assertNotIn("LICENSE_FLAGS_ACCEPTED", qemu)


if __name__ == "__main__":
    unittest.main()
