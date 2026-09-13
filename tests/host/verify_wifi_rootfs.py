"""Read-only integration check: python tests/host/verify_wifi_rootfs.py ROOTFS.

Run after bitbake -c rootfs rpi5-minimal-image; never prints Wi-Fi credentials.
This checks image contents, not real-radio association or DHCP.
"""

from pathlib import Path
import stat
import sys


def verify(root):
    modules = {p.name for p in (root / "usr/lib/modules").rglob("*.ko*")}
    for name in ("brcmfmac", "brcmfmac-wcc", "brcmfmac-cyw", "brcmutil", "cfg80211"):
        assert any(p == name + ".ko" or p.startswith(name + ".ko.") for p in modules), (
            "Missing Wi-Fi kernel module: " + name)
    for file in ("brcm/brcmfmac43455-sdio.bin", "brcm/brcmfmac43455-sdio.clm_blob",
                 "brcm/brcmfmac43455-sdio.raspberrypi,5-model-b.txt",
                 "regulatory.db", "regulatory.db.p7s", "LICENCE.cypress"):
        assert (root / "usr/lib/firmware" / file).is_file(), "Missing firmware: " + file
    unit = root / "usr/lib/systemd/system/rpi5-wifi.service"
    enabled = root / "etc/systemd/system/sys-subsystem-net-devices-wlan0.device.wants/rpi5-wifi.service"
    assert unit.is_file(), "Wi-Fi service missing"
    assert enabled.is_symlink(), "Wi-Fi device activation missing"
    # Absolute symlinks refer to the target filesystem, not the host.
    link = enabled.readlink()
    resolved = root / link.relative_to("/") if link.is_absolute() else enabled.parent / link
    assert resolved.resolve() == unit.resolve(), "Wi-Fi activation points to wrong unit"
    for name in ("wpa_supplicant", "rfkill"):
        path = root / "usr/sbin" / name
        if path.is_symlink() and path.readlink().is_absolute():
            path = root / path.readlink().relative_to("/")
        assert path.is_file(), "Missing service executable: " + name
    config = root / "etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
    assert config.is_file(), "Provisioned config missing"
    assert stat.S_IMODE(config.stat().st_mode) == 0o600, "Unsafe config mode"
    assert stat.S_IMODE(config.parent.stat().st_mode) == 0o700, "Unsafe config directory mode"
    print("Wi-Fi rootfs modules, firmware, activation and private config: PASS")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: verify_wifi_rootfs.py ROOTFS")
    verify(Path(sys.argv[1]))
