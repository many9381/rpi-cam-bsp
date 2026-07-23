import re
import unittest

from support import read


class LayerContractTest(unittest.TestCase):
    def test_layer_targets_only_wrynose(self) -> None:
        layer = read("meta-rpi5-cam/conf/layer.conf")
        self.assertIn('LAYERSERIES_COMPAT_rpi5cam = "wrynose"', layer)
        self.assertIn('LAYERDEPENDS_rpi5cam = "core"', layer)
        self.assertIn("addpylib ${LAYERDIR}/lib rpi5cam", layer)

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

    def test_recipe_validates_exported_values_before_install(self) -> None:
        recipe = read(
            "meta-rpi5-cam/recipes-core/device-config/device-config.bb"
        )
        self.assertIn("export RPI5_ADMIN_SSH_PUBKEY", recipe)
        self.assertIn("export RPI5_BUILD_ID", recipe)
        self.assertIn("python do_validate_device_config()", recipe)
        self.assertRegex(
            recipe,
            r"addtask validate_device_config .* before do_install",
        )

        install = recipe.split("do_install() {", maxsplit=1)[1].split(
            "\n}", maxsplit=1
        )[0]
        self.assertNotRegex(
            recipe,
            r"\$\{RPI5_(?:ADMIN_SSH_PUBKEY|BUILD_ID)\}",
        )
        without_safe_references = recipe
        for variable in ("RPI5_ADMIN_SSH_PUBKEY", "RPI5_BUILD_ID"):
            safe_reference = f'"${variable}"'
            self.assertIn(safe_reference, install)
            without_safe_references = without_safe_references.replace(
                safe_reference,
                "",
            )
        self.assertNotRegex(
            without_safe_references,
            r"\$(?:\{)?RPI5_(?:ADMIN_SSH_PUBKEY|BUILD_ID)",
        )

    def test_recipe_uses_restrictive_install_modes(self) -> None:
        recipe = read(
            "meta-rpi5-cam/recipes-core/device-config/device-config.bb"
        )
        self.assertIn("install -d -m 0700 ${D}/home/rpiadmin/.ssh", recipe)
        self.assertIn(
            "chown -R rpiadmin:rpiadmin ${D}/home/rpiadmin",
            recipe,
        )
        self.assertIn(
            "chmod 0600 ${D}/home/rpiadmin/.ssh/authorized_keys",
            recipe,
        )
        self.assertIn(
            "install -m 0600 ${UNPACKDIR}/sshd_config.d-rpi5.conf",
            recipe,
        )
        self.assertIn(
            "install -m 0440 ${UNPACKDIR}/rpi5-admin-sudoers",
            recipe,
        )
        self.assertIn(
            "install -m 0644 ${UNPACKDIR}/20-wired.network",
            recipe,
        )
        self.assertIn(
            "install -m 0644 ${UNPACKDIR}/journald.conf.d-rpi5.conf",
            recipe,
        )
        self.assertIn(
            "install -d -m 2755 ${D}${localstatedir}/log/journal",
            recipe,
        )
        self.assertIn(
            "install -d -m 0750 ${D}${sysconfdir}/sudoers.d",
            recipe,
        )
        self.assertIn(
            "chmod 0644 ${D}${sysconfdir}/rpi5-build-id",
            recipe,
        )

    def test_device_package_provides_required_runtime_services(self) -> None:
        recipe = read(
            "meta-rpi5-cam/recipes-core/device-config/device-config.bb"
        )
        dependencies = re.search(
            r'RDEPENDS:\$\{PN\}\s*=\s*"([^"]+)"',
            recipe,
        )
        self.assertIsNotNone(dependencies)
        self.assertEqual(
            set(dependencies.group(1).split()),
            {"avahi-daemon", "openssh-sshd", "sudo", "systemd-networkd"},
        )

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
        self.assertIn('/usr/bin/dmesg ""', sudoers)
        self.assertNotRegex(sudoers, r"/usr/bin/dmesg(?:,|$)")


if __name__ == "__main__":
    unittest.main()
