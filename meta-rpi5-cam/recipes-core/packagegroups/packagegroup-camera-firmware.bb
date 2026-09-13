SUMMARY = "Camera firmware application and optional Hailo-8 support"
LICENSE = "MIT"

inherit packagegroup

PACKAGES = "${PN} ${PN}-hailo"

RDEPENDS:${PN} = "camera-firmware"
RDEPENDS:${PN}-hailo = "hailort hailort-cli hailo-pci hailo-firmware"
