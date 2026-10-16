SUMMARY = "Pi 5 IMX708 drivers, DMA buffer access and camera acceptance permissions"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://70-rpi5-camera-dma.rules file://rpi5-camera-sudoers"
S = "${UNPACKDIR}"
COMPATIBLE_MACHINE = "^raspberrypi5$"
PACKAGE_ARCH = "${MACHINE_ARCH}"

# This image omits packagegroup-machine-base, so the BSP's broad
# kernel-modules recommendation is not installed. Select the camera path
# explicitly. Kernel 6.18's raspberrypi,rp1-cfe DT compatible binds to the
# downstream driver; rp1-cfe alone expects raspberrypi,rp1-cfe-upstream.
# The I2C controller is modular too and is not a sensor module dependency.
RDEPENDS:${PN} = " \
    kernel-module-i2c-designware-platform \
    kernel-module-rp1-cfe-downstream \
    kernel-module-pisp-be \
    kernel-module-imx708 \
    kernel-module-dw9807-vcm \
"

do_install() {
    install -d ${D}${nonarch_base_libdir}/udev/rules.d
    install -m 0644 ${UNPACKDIR}/70-rpi5-camera-dma.rules \
        ${D}${nonarch_base_libdir}/udev/rules.d/70-rpi5-camera-dma.rules
    install -d -m 0750 ${D}${sysconfdir}/sudoers.d
    install -m 0440 ${UNPACKDIR}/rpi5-camera-sudoers \
        ${D}${sysconfdir}/sudoers.d/rpi5-camera-acceptance
}

FILES:${PN} = " \
    ${nonarch_base_libdir}/udev/rules.d/70-rpi5-camera-dma.rules \
    ${sysconfdir}/sudoers.d/rpi5-camera-acceptance \
"
