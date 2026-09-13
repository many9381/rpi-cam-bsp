SUMMARY = "Camera firmware, operator tools and optional Hailo-8 support"
LICENSE = "MIT"

inherit packagegroup

PACKAGES = "${PN} ${PN}-hailo"

RDEPENDS:${PN} = "camera-firmware codex-cli"
RDEPENDS:${PN}-hailo = "hailort hailort-cli hailo-pci hailo-firmware"
