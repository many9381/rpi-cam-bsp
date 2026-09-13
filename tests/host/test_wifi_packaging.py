import configparser
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT


class WifiPackagingTest(unittest.TestCase):
    def test_installs_device_triggered_service_and_optional_dhcp_without_secrets(self):
        recipe = REPO_ROOT / "meta-rpi5-cam/recipes-connectivity/rpi5-wifi/rpi5-wifi.bb"
        self.assertTrue(recipe.is_file(), "Wi-Fi recipe is missing")
        body = re.search(r"^do_install\(\) \{\n(.*?)^\}", recipe.read_text(), re.M | re.S).group(1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for key, value in {"D": root, "UNPACKDIR": recipe.parent / "files",
                               "sysconfdir": "/etc", "sbindir": "/usr/sbin",
                               "systemd_system_unitdir": "/usr/lib/systemd/system"}.items():
                body = body.replace("${" + key + "}", str(value))
            result = subprocess.run(["bash", "-eu", "-c", body], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()},
                             {"etc/systemd/network/25-wireless.network",
                              "usr/lib/systemd/system/rpi5-wifi.service"})
            network = configparser.ConfigParser()
            network.read(root / "etc/systemd/network/25-wireless.network")
            self.assertEqual(network["Match"]["Name"], "wlan0")
            self.assertEqual(network["Network"]["DHCP"], "yes")
            self.assertEqual(network["Link"]["RequiredForOnline"], "no")
            self.assertGreater(int(network["DHCPv4"]["RouteMetric"]), 100)
            self.assertGreater(int(network["IPv6AcceptRA"]["RouteMetric"]), 1024)
            service = configparser.ConfigParser(interpolation=None)
            service.read(root / "usr/lib/systemd/system/rpi5-wifi.service")
            self.assertEqual(service["Install"]["WantedBy"], "sys-subsystem-net-devices-wlan0.device")
            self.assertEqual(service["Unit"]["ConditionPathExists"],
                             "/etc/wpa_supplicant/wpa_supplicant-wlan0.conf")
            self.assertIn("-c /etc/wpa_supplicant/wpa_supplicant-wlan0.conf", service["Service"]["ExecStart"])
            self.assertEqual(service["Service"]["Restart"], "on-failure")
            self.assertIn("/usr/sbin/rfkill unblock wlan", service["Service"]["ExecStartPre"])


if __name__ == "__main__":
    unittest.main()
