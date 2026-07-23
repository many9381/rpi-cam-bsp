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
        self.assertIn('IMAGE_FEATURES:remove = "debug-tweaks', recipe)

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


if __name__ == "__main__":
    unittest.main()
