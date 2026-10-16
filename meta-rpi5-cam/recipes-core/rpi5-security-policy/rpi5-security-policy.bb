SUMMARY = "Camera image network and core-dump policy"
DESCRIPTION = "Rejects IPv4 timestamp requests/replies, drops IPv6 unicast in link multicast frames, and discards process core dumps."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://90-rpi5-security.conf \
    file://rpi5-security.modules.conf \
    file://rpi5-security.nft \
    file://rpi5-security-policy.service \
    file://systemd-networkd-security.conf \
    file://rpi5-security-status \
    file://rpi5-security-sudoers \
"
S = "${UNPACKDIR}"

inherit systemd features_check
REQUIRED_DISTRO_FEATURES = "systemd ipv6"
COMPATIBLE_MACHINE = "^raspberrypi5$"
SYSTEMD_SERVICE:${PN} = "rpi5-security-policy.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -d ${D}${libdir}/sysctl.d ${D}${libdir}/modules-load.d
    install -m 0644 ${UNPACKDIR}/90-rpi5-security.conf ${D}${libdir}/sysctl.d/
    install -m 0644 ${UNPACKDIR}/rpi5-security.modules.conf \
        ${D}${libdir}/modules-load.d/rpi5-security.conf
    install -d ${D}${datadir}/rpi5-security-policy
    install -m 0644 ${UNPACKDIR}/rpi5-security.nft \
        ${D}${datadir}/rpi5-security-policy/firewall.nft
    install -d ${D}${systemd_system_unitdir}/systemd-networkd.service.d
    install -m 0644 ${UNPACKDIR}/rpi5-security-policy.service ${D}${systemd_system_unitdir}/
    install -m 0644 ${UNPACKDIR}/systemd-networkd-security.conf \
        ${D}${systemd_system_unitdir}/systemd-networkd.service.d/20-rpi5-security.conf
    sed -i -e 's|@SBINDIR@|${sbindir}|g' -e 's|@DATADIR@|${datadir}|g' \
        ${D}${systemd_system_unitdir}/rpi5-security-policy.service
    install -d ${D}${libexecdir}
    install -d -m 0750 ${D}${sysconfdir}/sudoers.d
    install -m 0755 ${UNPACKDIR}/rpi5-security-status ${D}${libexecdir}/
    sed -i 's|@SBINDIR@|${sbindir}|g' ${D}${libexecdir}/rpi5-security-status
    install -m 0440 ${UNPACKDIR}/rpi5-security-sudoers \
        ${D}${sysconfdir}/sudoers.d/rpi5-security-status
    sed -i 's|@LIBEXECDIR@|${libexecdir}|g' ${D}${sysconfdir}/sudoers.d/rpi5-security-status
}

FILES:${PN} += " \
    ${libdir}/sysctl.d/90-rpi5-security.conf \
    ${libdir}/modules-load.d/rpi5-security.conf \
    ${systemd_system_unitdir}/systemd-networkd.service.d/20-rpi5-security.conf \
"
RDEPENDS:${PN} = " \
    nftables kernel-module-nf-tables kernel-module-nfnetlink kernel-module-ipv6 \
    systemd systemd-networkd sudo \
"
