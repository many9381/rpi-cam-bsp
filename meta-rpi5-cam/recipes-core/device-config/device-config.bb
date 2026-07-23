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

do_install() {
    key_lines="$(printf '%s\n' "${RPI5_ADMIN_SSH_PUBKEY}" | wc -l)"
    if [ "$key_lines" -ne 1 ] || \
       ! printf '%s\n' "${RPI5_ADMIN_SSH_PUBKEY}" | \
         grep -Eq '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/=]+( .*)?$'; then
        bbfatal "RPI5_ADMIN_SSH_PUBKEY must contain one valid OpenSSH public key"
    fi

    if ! printf '%s\n' "${RPI5_BUILD_ID}" | \
         grep -Eq '^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{7,40}$'; then
        bbfatal "RPI5_BUILD_ID must be UTC timestamp plus Git SHA"
    fi

    install -d -m 0700 ${D}/home/rpiadmin/.ssh
    printf '%s\n' "${RPI5_ADMIN_SSH_PUBKEY}" \
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

    printf '%s\n' "${RPI5_BUILD_ID}" > ${D}${sysconfdir}/rpi5-build-id
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

RDEPENDS:${PN} = "openssh-sshd sudo systemd-networkd"
