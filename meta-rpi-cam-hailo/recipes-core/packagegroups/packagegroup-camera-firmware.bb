SUMMARY = "Camera firmware and optional Hailo-8 support"
LICENSE = "MIT"

# The Hailo group contains a machine-specific kernel module and libraries whose
# runtime package names depend on the target ABI.
PACKAGE_ARCH = "${MACHINE_ARCH}"

inherit packagegroup

PACKAGES = "${PN} ${PN}-hailo"

RDEPENDS:${PN} = "camera-firmware"
RDEPENDS:${PN}-hailo = "hailort hailort-cli hailort-gstreamer hailo-pci hailo-firmware"
