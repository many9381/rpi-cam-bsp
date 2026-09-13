import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import traceback
import unittest

from support import REPO_ROOT


HELPER = REPO_ROOT / "meta-rpi5-cam/lib/rpi5cam/wifi_config.py"


class WifiConfigTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), "rootfs-only Wi-Fi provisioner is missing")
        spec = importlib.util.spec_from_file_location("wifi_config", HELPER)
        self.wifi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.wifi)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.secret = self.root / "wifi.json"
        self.rootfs = self.root / "rootfs"
        self.output = self.rootfs / "etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
        # Deliberately synthetic, never use deployment credentials in tests.
        self.data = {"ssid": "Test AP", "psk": "a1" * 32, "country": "kr"}

    def save(self):
        self.secret.write_text(json.dumps(self.data), encoding="utf-8")
        self.secret.chmod(0o600)

    def install(self):
        return self.wifi.install_wifi_config(self.secret, self.rootfs)

    def test_installs_raw_psk_and_country_with_private_permissions(self):
        self.save()
        self.assertTrue(self.install())
        self.assertEqual(self.output.read_text(),
                         "ctrl_interface=DIR=/run/wpa_supplicant GROUP=root\n"
                         "update_config=0\ncountry=KR\n\nnetwork={\n"
                         "    ssid=54657374204150\n"
                         "    psk=" + "a1" * 32 + "\n"
                         "    key_mgmt=WPA-PSK\n    proto=RSN\n}\n")
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)

    def test_ssid_is_encoded_as_data_not_config_directives(self):
        self.data["ssid"] = 'a"\n}\nnetwork={'
        self.save()
        self.install()
        self.assertIn("ssid=61220a7d0a6e6574776f726b3d7b\n", self.output.read_text())
        self.assertEqual(self.output.read_text().count("network={"), 1)

    def test_missing_credentials_disable_autoconnect_and_remove_stale_config(self):
        self.assertFalse(self.install())
        self.assertFalse(self.output.exists())
        self.save()
        self.install()
        self.secret.unlink()
        self.assertFalse(self.install())
        self.assertFalse(self.output.exists())

    def test_updated_credentials_replace_previous_config(self):
        self.save()
        self.install()
        self.data["psk"] = "b2" * 32
        self.save()
        self.install()
        self.assertNotIn("a1" * 32, self.output.read_text())
        self.assertIn("b2" * 32, self.output.read_text())

    def test_invalid_values_fail_without_disclosing_credentials(self):
        for key, value in [("ssid", ""), ("ssid", "한" * 11), ("ssid", 123),
                           ("psk", "test-passphrase"), ("psk", "g" * 64),
                           ("psk", None), ("country", "K1"), ("country", "KR\n"),
                           ("country", 123), ("unexpected", "private-marker")]:
            with self.subTest(key=key, value=value):
                self.data = {"ssid": "private-ap-marker", "psk": "c3" * 32, "country": "KR"}
                self.data[key] = value
                self.save()
                with self.assertRaises(ValueError) as caught:
                    self.install()
                message = "".join(traceback.format_exception(caught.exception))
                for private in ("private-ap-marker", "c3" * 32, "private-marker", "test-passphrase"):
                    self.assertNotIn(private, message)
                self.assertFalse(self.output.exists())

    def test_malformed_json_error_is_redacted(self):
        self.secret.write_text('{"private-ap-marker": invalid-json}')
        self.secret.chmod(0o600)
        with self.assertRaises(ValueError) as caught:
            self.install()
        self.assertNotIn("private-ap-marker", "".join(traceback.format_exception(caught.exception)))

    def test_oversized_input_is_not_silently_truncated(self):
        self.save()
        with self.secret.open("a") as source:
            source.write(" " * 4096 + "invalid trailing content")
        with self.assertRaises(ValueError):
            self.install()

    def test_checksum_paths_cannot_inject_entries_or_expand_globs(self):
        for path in ("/tmp/wifi:True", "/tmp/wifi*.json", "/tmp/wifi?.json",
                     "/tmp/wifi[1].json", "/tmp/wifi config.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.wifi.rootfs_checksums("raspberrypi5", path, HELPER)

    def test_rejects_readable_by_others_and_nonregular_inputs(self):
        self.save()
        self.secret.chmod(0o644)
        with self.assertRaises(ValueError):
            self.install()
        self.secret.unlink()
        self.secret.mkdir()
        with self.assertRaises(ValueError):
            self.install()
        self.secret.rmdir()
        os.mkfifo(self.secret, 0o600)
        with self.assertRaises(ValueError):
            self.install()
        self.secret.unlink()
        self.secret.symlink_to(self.root / "missing.json")
        with self.assertRaises(ValueError):
            self.install()

    def test_ssid_utf8_byte_boundary_and_uppercase_psk(self):
        self.data.update(ssid="한" * 10 + "ab", psk="AB" * 32)
        self.save()
        self.install()
        self.assertIn("psk=" + "ab" * 32, self.output.read_text())
        self.data["ssid"] += "c"
        self.save()
        with self.assertRaises(ValueError):
            self.install()

    def test_does_not_follow_destination_directory_symlink(self):
        self.save()
        self.rootfs.mkdir()
        self.rootfs.joinpath("etc").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse((self.root / "wpa_supplicant").exists())

    def test_checksum_inputs_track_add_remove_and_leave_qemu_independent(self):
        expected = f" {self.secret}:False {HELPER}:True"
        self.assertEqual(self.wifi.rootfs_checksums("raspberrypi5", self.secret, HELPER), expected)
        self.save()
        self.assertEqual(self.wifi.rootfs_checksums("raspberrypi5", self.secret, HELPER),
                         f" {self.secret}:True {HELPER}:True")
        self.secret.chmod(0o644)
        with self.assertRaises(ValueError):
            self.wifi.rootfs_checksums("raspberrypi5", self.secret, HELPER)
        self.assertEqual(self.wifi.rootfs_checksums("qemuarm64", self.secret, HELPER), "")


if __name__ == "__main__":
    unittest.main()
