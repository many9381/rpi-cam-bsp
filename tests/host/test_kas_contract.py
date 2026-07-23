import unittest

import yaml

from support import REPO_ROOT


PINS = {
    "bitbake": ("2.18", "fae9db3168dbff1b8c76fe9c6726a9687ff97514"),
    "openembedded-core": ("wrynose", "b5a6cada82d7ffb362bda9081c354dcc0b6ee264"),
    "meta-yocto": ("wrynose", "824795b885b25e074a2880fbcd54e1a6c875d47d"),
    "meta-openembedded": ("wrynose", "d97b5602d7f64422c94b7311466cda7f6b1962d5"),
    "meta-raspberrypi": ("wrynose", "f62c67921474370829d24a4fa01ef88543f3906b"),
}


def load(name: str) -> dict:
    with (REPO_ROOT / "kas" / name).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


class KasContractTest(unittest.TestCase):
    def test_branches_and_lock_commits_match(self) -> None:
        base = load("base.yml")
        lock = load("lock.yml")
        for repo, (branch, commit) in PINS.items():
            self.assertEqual(base["repos"][repo]["branch"], branch)
            self.assertEqual(lock["overrides"]["repos"][repo]["commit"], commit)

    def test_base_uses_split_repositories_and_shared_cache(self) -> None:
        base = load("base.yml")
        self.assertNotIn("poky", base["repos"])
        self.assertEqual(base["repos"]["bitbake"]["layers"], {})
        self.assertIn("meta", base["repos"]["openembedded-core"]["layers"])
        self.assertIn("meta-poky", base["repos"]["meta-yocto"]["layers"])
        conf = base["local_conf_header"]["base"]
        self.assertIn('DL_DIR = "${TOPDIR}/../downloads"', conf)
        self.assertIn('SSTATE_DIR = "${TOPDIR}/../sstate-cache"', conf)
        self.assertNotIn("debug-tweaks", conf)

    def test_qemu_profile_is_hardware_independent(self) -> None:
        data = load("qemuarm64-minimal.yml")
        self.assertEqual(data["machine"], "qemuarm64")
        self.assertEqual(data["target"], "rpi5-minimal-image")
        self.assertNotIn("repos", data)
        conf = data["local_conf_header"]["qemu"]
        self.assertIn("127.0.0.1:2222-:22", conf)

    def test_pi_profile_boots_from_usb_ssd(self) -> None:
        data = load("rpi5-minimal.yml")
        self.assertEqual(data["machine"], "raspberrypi5")
        self.assertIn(".", data["repos"]["meta-raspberrypi"]["layers"])
        conf = data["local_conf_header"]["rpi5-minimal"]
        self.assertIn('BOOT_MEDIA = "usb"', conf)
        self.assertIn('CMDLINE_ROOT_PARTITION = "/dev/sda2"', conf)
        self.assertIn('IMAGE_FSTYPES = "wic.bz2 wic.bmap"', conf)

    def test_camera_profile_enables_exact_dependencies(self) -> None:
        data = load("rpi5-camera.yml")
        self.assertEqual(
            set(data["repos"]["meta-openembedded"]["layers"]),
            {"meta-oe", "meta-python", "meta-multimedia"},
        )
        conf = data["local_conf_header"]["rpi5-camera"]
        for required in (
            'RASPBERRYPI_CAMERA_V3 = "1"',
            'PACKAGECONFIG:append:pn-libcamera-apps = " libav"',
            'PACKAGECONFIG:append:pn-rpidistro-ffmpeg = " x264"',
            'LICENSE_FLAGS_ACCEPTED += " commercial"',
        ):
            self.assertIn(required, conf)


if __name__ == "__main__":
    unittest.main()
