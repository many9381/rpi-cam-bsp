"""Verify vendor input integrity and execute the real recipe install bodies."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from support import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "meta-rpi5-cam/lib"))


class HailoDebIntegrityTest(unittest.TestCase):
    def test_accepts_exact_bytes_and_rejects_modified_or_missing_input(self):
        from rpi5cam.local_deb import verify_sha256

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "vendor.deb"
            package.write_bytes(b"reviewed package\n")
            digest = "cac26372899b4e6f43d4dfee38e527d055e378adafc00c5b16a50fb077854570"
            verify_sha256(package, digest)
            package.write_bytes(b"different package\n")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                verify_sha256(package, digest)
            package.unlink()
            with self.assertRaisesRegex(ValueError, "missing local Debian package"):
                verify_sha256(package, digest)


class HailoDebInstallTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "deb"
        self.destination = self.root / "image"
        self.unpack = self.root / "unpack"
        self.unpack.mkdir()

    def payload(self, path, contents=b"vendor payload\n"):
        target = self.source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
        return target

    def install(self, relative, function="do_install", libdir="/usr/lib"):
        recipe = (REPO_ROOT / relative).read_text()
        match = re.search(r"^" + re.escape(function) + r"\(\) \{\n(.*?)^\}", recipe, re.M | re.S)
        self.assertIsNotNone(match, f"missing installation function in {relative}")
        body = match.group(1)
        for name, value in {
            "S": self.source, "UNPACKDIR": self.unpack, "D": self.destination,
            "PV": "4.24.0", "bindir": "/usr/bin", "libdir": libdir,
            "baselib": Path(libdir).name, "includedir": "/usr/include",
            "sysconfdir": "/etc", "datadir": "/usr/share",
            "systemd_system_unitdir": "/usr/lib/systemd/system",
            "nonarch_base_libdir": "/usr/lib",
        }.items():
            body = body.replace("${" + name + "}", str(value))
        return subprocess.run(["bash", "-eu", "-c", body], capture_output=True, text=True)

    def runtime_payload(self):
        for path in (
            "usr/lib/libhailort.so.4.24.0", "usr/bin/hailortcli", "usr/bin/hailort_service",
            "usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgsthailo.so",
            "usr/include/hailo/hailort.h", "usr/include/gstreamer-1.0/gst/hailo/include/hailo_gst.h",
            "usr/share/doc/hailort/copyright",
        ):
            self.payload(path)
        self.payload("usr/lib/cmake/HailoRT/HailoRTTargets-release.cmake",
                     b'IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/libhailort.so.4.24.0"\n')
        self.payload("lib/systemd/system/hailort.service",
                     b"[Service]\nExecStart=/usr/bin/hailort_service\n")
        self.payload("etc/default/hailort_service",
                     b'[Service]\nHAILORT_LOGGER_PATH="/var/log/hailo"\nHAILO_MONITOR=0\n')
        self.payload("DEBIAN/postinst", b"exit 99\n")

    def test_runtime_installs_libraries_headers_plugins_and_service_in_yocto_paths(self):
        self.runtime_payload()
        result = self.install("meta-rpi5-cam/recipes-hailo/hailort/hailort_4.24.0.bb", libdir="/usr/lib64")
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in (
            "usr/lib64/libhailort.so.4.24.0", "usr/bin/hailortcli", "usr/bin/hailort_service",
            "usr/lib64/gstreamer-1.0/libgsthailo.so", "usr/include/hailo/hailort.h",
            "usr/include/gstreamer-1.0/gst/hailo/include/hailo_gst.h",
            "usr/share/doc/hailort/copyright", "usr/lib/systemd/system/hailort.service",
        ):
            with self.subTest(path=path):
                self.assertTrue((self.destination / path).is_file())
        link = self.destination / "usr/lib64/libhailort.so"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.readlink(), Path("libhailort.so.4.24.0"))
        self.assertIn("/lib64/libhailort.so.4.24.0", (self.destination / "usr/lib64/cmake/HailoRT/HailoRTTargets-release.cmake").read_text())
        environment = (self.destination / "etc/default/hailort_service").read_text()
        self.assertNotIn("[Service]", environment)
        self.assertIn("HAILO_MONITOR=0", environment)
        self.assertFalse((self.destination / "DEBIAN").exists())
        self.assertFalse((self.destination / "usr/lib/aarch64-linux-gnu").exists())

    def test_firmware_installs_vendor_bytes_at_kernel_lookup_path_with_license(self):
        self.payload("lib/firmware/hailo/hailo8_fw.4.24.0.bin", b"reviewed firmware")
        self.payload("usr/share/doc/hailort/hailo_firmware_eula", b"vendor firmware license")
        result = self.install("meta-rpi5-cam/recipes-hailo/hailo-firmware/hailo-firmware_4.24.0.bb")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.destination / "usr/lib/firmware/hailo/hailo8_fw.bin").read_bytes(), b"reviewed firmware")
        self.assertEqual((self.destination / "usr/lib/firmware/hailo/LICENSE").read_bytes(), b"vendor firmware license")


if __name__ == "__main__":
    unittest.main()
