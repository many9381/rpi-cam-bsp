SUMMARY = "Hailo-8 device firmware"
HOMEPAGE = "https://github.com/hailo-ai/hailort-drivers"
LICENSE = "LicenseRef-Hailo-Firmware"
LIC_FILES_CHKSUM = "file://usr/share/doc/hailort/hailo_firmware_eula;md5=c4d4dede4192ecc4fa9b00b8a9d4d477"
NO_GENERIC_LICENSE[LicenseRef-Hailo-Firmware] = "usr/share/doc/hailort/hailo_firmware_eula"

require recipes-kernel/hailo-pci/hailo-pcie-deb.inc

inherit allarch

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${nonarch_base_libdir}/firmware/hailo
    install -m 0644 ${S}/lib/firmware/hailo/hailo8_fw.${PV}.bin ${D}${nonarch_base_libdir}/firmware/hailo/hailo8_fw.bin
    install -m 0644 ${S}/usr/share/doc/hailort/hailo_firmware_eula ${D}${nonarch_base_libdir}/firmware/hailo/LICENSE
}

FILES:${PN} = "${nonarch_base_libdir}/firmware/hailo"
