import unittest

from support import read


class LayerContractTest(unittest.TestCase):
    def test_layer_targets_only_wrynose(self) -> None:
        layer = read("meta-rpi5-cam/conf/layer.conf")
        self.assertIn('LAYERSERIES_COMPAT_rpi5cam = "wrynose"', layer)
        self.assertIn('LAYERDEPENDS_rpi5cam = "core"', layer)

    def test_device_recipe_creates_locked_admin_and_injects_key(self) -> None:
        recipe = read(
            "meta-rpi5-cam/recipes-core/device-config/device-config.bb"
        )
        self.assertIn("inherit useradd", recipe)
        self.assertIn("--password '!' rpiadmin", recipe)
        self.assertIn("RPI5_ADMIN_SSH_PUBKEY", recipe)
        self.assertIn("authorized_keys", recipe)
        self.assertIn("RPI5_BUILD_ID", recipe)
        self.assertNotIn("keys/rpi5_admin.pub", recipe)

    def test_sshd_policy_is_key_only_and_non_root(self) -> None:
        policy = read(
            "meta-rpi5-cam/recipes-core/device-config/files/"
            "sshd_config.d-rpi5.conf"
        )
        self.assertIn("PasswordAuthentication no", policy)
        self.assertIn("KbdInteractiveAuthentication no", policy)
        self.assertIn("PermitRootLogin no", policy)
        self.assertIn("AllowUsers rpiadmin", policy)

    def test_wired_network_uses_dhcp_and_mdns(self) -> None:
        network = read(
            "meta-rpi5-cam/recipes-core/device-config/files/20-wired.network"
        )
        self.assertIn("Name=eth* en*", network)
        self.assertIn("DHCP=yes", network)
        self.assertIn("MulticastDNS=yes", network)

    def test_sudo_does_not_grant_an_unbounded_shell(self) -> None:
        sudoers = read(
            "meta-rpi5-cam/recipes-core/device-config/files/rpi5-admin-sudoers"
        )
        self.assertNotIn("ALL=(ALL) NOPASSWD: ALL", sudoers)
        self.assertIn("/usr/bin/systemctl reboot", sudoers)
        self.assertIn("/usr/bin/systemctl poweroff", sudoers)


if __name__ == "__main__":
    unittest.main()
