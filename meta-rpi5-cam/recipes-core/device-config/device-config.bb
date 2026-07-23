SUMMARY = "Raspberry Pi 5 headless device policy"
DESCRIPTION = "Installs the rpiadmin account, SSH policy, wired network, persistent journal, sudo policy, and build identity."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://20-wired.network \
    file://sshd_config.d-rpi5.conf \
    file://journald.conf.d-rpi5.conf \
    file://rpi5-admin-sudoers \
"

S = "${UNPACKDIR}"

inherit useradd

USERADD_PACKAGES = "${PN}"
USERADD_PARAM:${PN} = "--uid 1000 --home-dir /home/rpiadmin \
    --create-home --shell /bin/sh --user-group --password '!' rpiadmin"

RPI5_ADMIN_SSH_PUBKEY ??= ""
RPI5_BUILD_ID ??= "unversioned"
export RPI5_ADMIN_SSH_PUBKEY
export RPI5_BUILD_ID

python do_validate_device_config() {
    from rpi5cam.device_config_validation import (
        validate_build_id,
        validate_ssh_public_key,
    )

    try:
        validate_ssh_public_key(d.getVar("RPI5_ADMIN_SSH_PUBKEY"))
        validate_build_id(d.getVar("RPI5_BUILD_ID"))
    except ValueError as error:
        bb.fatal(str(error))
}
addtask validate_device_config after do_prepare_recipe_sysroot before do_install

do_install() {
    install -d -m 0700 ${D}/home/rpiadmin/.ssh
    printf '%s\n' "$RPI5_ADMIN_SSH_PUBKEY" \
        > ${D}/home/rpiadmin/.ssh/authorized_keys
    chmod 0600 ${D}/home/rpiadmin/.ssh/authorized_keys
    chown -R rpiadmin:rpiadmin ${D}/home/rpiadmin

    install -d -m 0755 ${D}${sysconfdir}/systemd/network
    install -m 0644 ${UNPACKDIR}/20-wired.network \
        ${D}${sysconfdir}/systemd/network/20-wired.network

    install -d -m 0755 ${D}${sysconfdir}/ssh/sshd_config.d
    install -m 0600 ${UNPACKDIR}/sshd_config.d-rpi5.conf \
        ${D}${sysconfdir}/ssh/sshd_config.d/20-rpi5.conf

    install -d -m 0755 ${D}${sysconfdir}/systemd/journald.conf.d
    install -m 0644 ${UNPACKDIR}/journald.conf.d-rpi5.conf \
        ${D}${sysconfdir}/systemd/journald.conf.d/20-rpi5.conf
    install -d -m 2755 ${D}${localstatedir}/log/journal

    install -d -m 0750 ${D}${sysconfdir}/sudoers.d
    install -m 0440 ${UNPACKDIR}/rpi5-admin-sudoers \
        ${D}${sysconfdir}/sudoers.d/rpi5-admin

    printf '%s\n' "$RPI5_BUILD_ID" > ${D}${sysconfdir}/rpi5-build-id
    chmod 0644 ${D}${sysconfdir}/rpi5-build-id
}

FILES:${PN} += " \
    /home/rpiadmin \
    ${sysconfdir}/rpi5-build-id \
    ${sysconfdir}/ssh/sshd_config.d/20-rpi5.conf \
    ${sysconfdir}/sudoers.d/rpi5-admin \
    ${sysconfdir}/systemd/journald.conf.d/20-rpi5.conf \
    ${sysconfdir}/systemd/network/20-wired.network \
    ${localstatedir}/log/journal \
"

CONFFILES:${PN} = " \
    ${sysconfdir}/ssh/sshd_config.d/20-rpi5.conf \
    ${sysconfdir}/sudoers.d/rpi5-admin \
    ${sysconfdir}/systemd/journald.conf.d/20-rpi5.conf \
    ${sysconfdir}/systemd/network/20-wired.network \
"

RDEPENDS:${PN} = "avahi-daemon openssh-sshd sudo systemd-networkd"
