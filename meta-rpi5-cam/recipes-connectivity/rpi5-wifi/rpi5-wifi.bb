SUMMARY = "Raspberry Pi 5 optional Wi-Fi automatic connection"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://25-wireless.network file://rpi5-wifi.service file://rpi5-wifi.conf"
S = "${UNPACKDIR}"
COMPATIBLE_MACHINE = "^raspberrypi5$"
PACKAGE_ARCH = "${MACHINE_ARCH}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "rpi5-wifi.service"
SYSTEMD_AUTO_ENABLE = "enable"

# linux-firmware 20260410 supplies Pi 5 NVRAM and the Cypress binary/CLM
# through bcm43455. Include the Cypress notice explicitly as well.
# Kernel 6.18 selects CYW/WCC by SDIO ID and request_module() loads the
# vendor implementation; module dependency scanning does not pull these in.
RDEPENDS:${PN} = " \
    wpa-supplicant wpa-supplicant-cli systemd-networkd iw util-linux-rfkill \
    kernel-module-brcmfmac kernel-module-brcmfmac-wcc kernel-module-brcmfmac-cyw \
    linux-firmware-bcm43455 \
    linux-firmware-cypress-license wireless-regdb-static \
"

do_install() {
    install -d ${D}${sysconfdir}/systemd/network ${D}${systemd_system_unitdir} ${D}${sysconfdir}/modprobe.d
    install -m 0644 ${UNPACKDIR}/rpi5-wifi.conf ${D}${sysconfdir}/modprobe.d/rpi5-wifi.conf
    install -m 0644 ${UNPACKDIR}/25-wireless.network ${D}${sysconfdir}/systemd/network/25-wireless.network
    sed -e 's|@SBINDIR@|${sbindir}|g' -e 's|@SYSCONFDIR@|${sysconfdir}|g' \
        ${UNPACKDIR}/rpi5-wifi.service > ${D}${systemd_system_unitdir}/rpi5-wifi.service
    chmod 0644 ${D}${systemd_system_unitdir}/rpi5-wifi.service
}

FILES:${PN} = "${sysconfdir}/systemd/network/25-wireless.network ${systemd_system_unitdir}/rpi5-wifi.service ${sysconfdir}/modprobe.d/rpi5-wifi.conf"
CONFFILES:${PN} = "${sysconfdir}/modprobe.d/rpi5-wifi.conf"
