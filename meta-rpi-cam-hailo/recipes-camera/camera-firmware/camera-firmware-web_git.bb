SUMMARY = "Static web interface for the Raspberry Pi camera firmware"
DESCRIPTION = "Builds the pinned React application offline using native Node.js."
LICENSE = "CLOSED & MIT & ISC"
LIC_FILES_CHKSUM = "file://${UNPACKDIR}/web-third-party-notices.txt;md5=4369cc8da4ad2da34b1a31529cc521cc"

require camera-firmware-source.inc
require camera-firmware-npm.inc

SRC_URI += " \
    file://0003-web-update-source-map-js-security-fix.patch \
    file://0005-dhcp-setup-and-optional-management-ip-policy.patch \
    file://0007-setup-session-recovery-and-error-messages.patch \
    file://0008-camera-capture-health-and-bounded-recovery.patch \
    file://0009-quality-gate-and-plain-bootstrap-peers.patch \
    file://web-third-party-notices.txt \
"

inherit allarch

DEPENDS = "nodejs-native"

# No Node.js runtime or node_modules are installed on the camera.
export npm_config_cache = "${B}/npm-cache"
export npm_config_userconfig = "${B}/npm-userconfig"
export npm_config_globalconfig = "${B}/npm-globalconfig"
export npm_config_offline = "true"
export npm_config_audit = "false"
export npm_config_fund = "false"

do_configure() {
    actual_lock_hash=$(sha256sum "${S}/web/package-lock.json" | cut -d ' ' -f 1)
    if [ "$actual_lock_hash" != "${CF_NPM_LOCK_SHA256}" ]; then
        bbfatal "Firmware package-lock.json changed; regenerate camera-firmware-npm.inc"
    fi
    install -d "${B}/npm-cache"
    install -m 0644 /dev/null "${B}/npm-userconfig"
    install -m 0644 /dev/null "${B}/npm-globalconfig"
    for archive in ${CF_NPM_ARCHIVES}; do
        npm cache add --offline --ignore-scripts "$archive"
    done
    cd "${S}/web"
    npm ci --offline --ignore-scripts --include=dev --include=optional
}

do_compile() {
    cd "${S}/web"
    npm run build
}

do_install() {
    install -d "${D}${datadir}/camera-firmware/web"
    for asset in index.html app.js styles.css; do
        install -m 0644 "${S}/web/dist/$asset" "${D}${datadir}/camera-firmware/web/"
    done
    install -d "${D}${datadir}/camera-firmware/licenses"
    install -m 0644 "${UNPACKDIR}/web-third-party-notices.txt" \
        "${D}${datadir}/camera-firmware/licenses/"
}

FILES:${PN} = "${datadir}/camera-firmware/web ${datadir}/camera-firmware/licenses/web-third-party-notices.txt"
