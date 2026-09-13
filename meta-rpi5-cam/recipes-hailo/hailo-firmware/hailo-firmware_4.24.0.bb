SUMMARY = "Hailo-8 device firmware"
HOMEPAGE = "https://github.com/hailo-ai/hailort-drivers"
LICENSE = "LicenseRef-Hailo-Firmware"
LIC_FILES_CHKSUM = "file://hailo-firmware-${PV}-LICENSE;md5=263ee034adc02556d59ab1ebdaea2cda"
NO_GENERIC_LICENSE[LicenseRef-Hailo-Firmware] = "hailo-firmware-${PV}-LICENSE"

HAILO_FIRMWARE_URI = "https://hailo-hailort.s3.eu-west-2.amazonaws.com/Hailo8/${PV}/FW"
SRC_URI = " \
    ${HAILO_FIRMWARE_URI}/hailo8_fw.${PV}.bin;name=firmware \
    ${HAILO_FIRMWARE_URI}/LICENSE;name=license;downloadfilename=hailo-firmware-${PV}-LICENSE \
"
SRC_URI[firmware.sha256sum] = "3ebeb209987bb0e484353be23774d3893908de84069016c4e37361c871d8433a"
SRC_URI[license.sha256sum] = "ca96445e6e33ae0a82170ea847b0925c864492f0cbb6342d42c54fd647133608"
S = "${UNPACKDIR}"

inherit allarch

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${nonarch_base_libdir}/firmware/hailo
    install -m 0644 ${S}/hailo8_fw.${PV}.bin ${D}${nonarch_base_libdir}/firmware/hailo/hailo8_fw.bin
    install -m 0644 ${S}/hailo-firmware-${PV}-LICENSE ${D}${nonarch_base_libdir}/firmware/hailo/LICENSE
}

FILES:${PN} = "${nonarch_base_libdir}/firmware/hailo"
