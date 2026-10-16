"""Read-only camera driver check: python verify_camera_rootfs.py ROOTFS.

Checks actual packaged module files, dependency resolution and device aliases.
Hardware enumeration/capture still requires the physical Pi.
"""
from pathlib import Path
import shutil
import subprocess
import sys


def verify(root):
    versions = [p.name for p in (root / "usr/lib/modules").iterdir() if p.is_dir()]
    assert len(versions) == 1, "Expected exactly one target kernel module tree"
    modprobe = shutil.which("modprobe") or "/usr/sbin/modprobe"
    # These are the actual Pi 5 device-tree modaliases and Camera Module 3
    # sensor/actuator names. A .ko with the wrong compatible cannot bind.
    requests = {
        "of:NcsiT(null)Craspberrypi,rp1-cfe": "rp1-cfe-downstream",
        "of:Npisp_beT(null)Craspberrypi,pispbe": "pisp_be",
        "of:Ni2cT(null)Csnps,designware-i2c": "i2c-designware-platform",
        "imx708": "imx708",
        "dw9807-vcm": "dw9807-vcm",
    }
    for request, expected in requests.items():
        result = subprocess.run(
            [modprobe, "--dirname", str(root), "--set-version", versions[0],
             "--show-depends", request], capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Missing camera module/alias {request}: {result.stderr.strip()}"
        files = [Path(line.split()[1]) for line in result.stdout.splitlines()
                 if line.startswith("insmod ")]
        assert any(p.name.split(".ko")[0].replace("_", "-") == expected.replace("_", "-")
                   for p in files), f"Wrong driver selected for {request}"
        assert files and all(p.is_file() for p in files), f"Missing module dependency for {request}"
    rule = root / "usr/lib/udev/rules.d/70-rpi5-camera-dma.rules"
    assert rule.is_file(), "Missing video-group DMA heap access policy"
    rules = [line.strip() for line in rule.read_text().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    fields = dict(field.strip().split("=", 1) for field in rules[0].split(",")) if len(rules) == 1 else {}
    assert fields == {"SUBSYSTEM": '="dma_heap"', "GROUP": '"video"', "MODE": '"0660"'}, (
        "DMA heaps must be accessible to video group, without world access")
    library = root / "usr/lib/libcamera.so.0.6"
    assert library.is_file(), "Missing libcamera 0.6 runtime library"
    contents = library.read_bytes()
    for entity in (b"rp1-cfe-fe_image0", b"rp1-cfe-fe_stats", b"rp1-cfe-fe_config",
                   b"rp1-cfe-embedded"):
        assert entity + b"\0" in contents, (
            f"libcamera does not support the packaged downstream CFE entity {entity.decode()}")
    print("Camera rootfs: DT drivers, dependencies, IMX708/AF, DMA policy and downstream CFE userspace PASS")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: verify_camera_rootfs.py ROOTFS")
    verify(Path(sys.argv[1]).resolve())
