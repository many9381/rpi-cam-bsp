SUMMARY = "Camera firmware with HTTPS management and secure RTSP streaming"
HOMEPAGE = "https://github.com/many9381/rpi-cam-hailo"
# The application has no license grant. Its bundled dependencies retain their
# own licenses; this declaration does not grant redistribution of the app.
LICENSE = "CLOSED & MIT & BSD-3-Clause & OFL-1.1"
LIC_FILES_CHKSUM = " \
    file://${UNPACKDIR}/drogon/LICENSE;md5=7c71438272f01c6d2953c9d598d080ff \
    file://${UNPACKDIR}/trantor/License;md5=f75eb2190741670ca42949a36ebab4ed \
    file://vendor/stb/LICENSE;md5=984f6efd5e88275dd103d489cc99f6d9 \
    file://vendor/fonts/OFL.txt;md5=5c64af38e3f89f2ae508311c57e5f0f6 \
"

require camera-firmware-source.inc

# These are separate Git worktrees: upstream verifies their exact HEAD/tree
# identities and cleanliness before archiving and applying its four patches.
SRC_URI += " \
    git://github.com/drogonframework/drogon.git;protocol=https;branch=master;name=drogon;destsuffix=drogon \
    git://github.com/an-tao/trantor.git;protocol=https;branch=master;name=trantor;destsuffix=trantor \
    file://0001-cmake-support-packaged-web-and-target-installation.patch \
    file://0002-cmake-check-source-content-not-cached-file-stats.patch \
    file://0005-dhcp-setup-and-optional-management-ip-policy.patch \
    file://0006-rtsp-protect-existing-sessions-before-authentication.patch \
    file://0007-setup-session-recovery-and-error-messages.patch \
    file://0008-camera-capture-health-and-bounded-recovery.patch \
    file://0009-quality-gate-and-plain-bootstrap-peers.patch \
    file://0010-avoid-intermediate-metadata-and-error-copies.patch \
    file://camera-firmware.service \
    file://app.yaml.example \
    file://app-hailo.yaml.example \
    file://${@__import__('os').path.basename(d.getVar('CF_INTEGRITY_PUBLIC_KEY_INPUT'))};subdir=deployment-key \
"
SRCREV_drogon = "f215cb15a0f53abd0ca7ee8b95ed8c9c3b40d262"
SRCREV_trantor = "79e1ffc59aa1b9c8226c2988fe2e1185e97cd795"
SRCREV_FORMAT = "firmware_drogon_trantor"

inherit cmake pkgconfig systemd useradd deploy

COMPATIBLE_HOST = "aarch64.*-linux"

DEPENDS = " \
    git-native patch-native openssl-native \
    openssl sqlite3 yaml-cpp jsoncpp jpeg util-linux zlib \
    libcamera gstreamer1.0 gstreamer1.0-plugins-base \
    gstreamer1.0-rtsp-server libsrtp x264 rpidistro-ffmpeg \
"

PACKAGECONFIG ??= ""
PACKAGECONFIG[hailo] = "-DCF_WITH_HAILORT=ON,-DCF_WITH_HAILORT=OFF,hailort,camera-firmware-models"

CF_APP_CONFIG_EXAMPLE = "${@bb.utils.contains('PACKAGECONFIG', 'hailo', 'app-hailo.yaml.example', 'app.yaml.example', d)}"

# build.sh prepares the host identity; only this PUBLIC PEM is a build input.
# Direct kas users must run camera_identity.py prepare once beforehand.
CF_INTEGRITY_PUBLIC_KEY_INPUT ?= "${RPI_CAM_HAILO_LAYERDIR}/../keys/camera-firmware/integrity-public.pem"
FILESEXTRAPATHS:prepend := "${@__import__('os').path.dirname(d.getVar('CF_INTEGRITY_PUBLIC_KEY_INPUT'))}:"
CF_INTEGRITY_PUBLIC_KEY_FILE = "${UNPACKDIR}/deployment-key/${@__import__('os').path.basename(d.getVar('CF_INTEGRITY_PUBLIC_KEY_INPUT'))}"

EXTRA_OECMAKE = " \
    -DBUILD_TESTING=OFF \
    -DBUILD_SHARED_LIBS=OFF \
    -DBUILD_C-ARES=OFF \
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCF_BUILD_WEB=OFF \
    -DCF_SECURE_SRTP_PLUGIN_DIR=${libdir}/gstreamer-1.0 \
    -DCF_INTEGRITY_PUBLIC_KEY_FILE=${CF_INTEGRITY_PUBLIC_KEY_FILE} \
    -DCAMERA_FIRMWARE_DROGON_SOURCE_DIR=${UNPACKDIR}/drogon \
    -DCAMERA_FIRMWARE_TRANTOR_SOURCE_DIR=${UNPACKDIR}/trantor \
"

USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "--system camera-firmware; --system render"
USERADD_PARAM:${PN} = "--system --home-dir /var/lib/camera-firmware \
    --no-create-home --shell /sbin/nologin --gid camera-firmware \
    --groups video,render camera-firmware"

SYSTEMD_SERVICE:${PN} = "camera-firmware.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_configure:append() {
    # Drogon embeds include flags for runtime view compilation in this header.
    # Those paths belong to the target filesystem, not the build-host sysroot.
    sed -i -e '/^#define INCLUDING_DIRS /s|${RECIPE_SYSROOT}||g' \
        ${B}/_deps/camera-firmware-drogon-1.9.0-build/drogon/config.h
}

do_install:append() {
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/camera-firmware.service \
        ${D}${systemd_system_unitdir}/camera-firmware.service
    sed -i -e 's|@BINDIR@|${bindir}|g' -e 's|@SYSCONFDIR@|${sysconfdir}|g' \
        ${D}${systemd_system_unitdir}/camera-firmware.service

    # install-ssd.sh personalizes the SSD and publishes app.yaml after signing.
    # Generic images contain the example and public key, never device secrets.
    install -d -m 0750 ${D}${sysconfdir}/camera-firmware
    chown root:camera-firmware ${D}${sysconfdir}/camera-firmware
    install -m 0644 ${UNPACKDIR}/${CF_APP_CONFIG_EXAMPLE} \
        ${D}${sysconfdir}/camera-firmware/app.yaml.example
    sed -i -e 's|@DATADIR@|${datadir}|g' -e 's|@SYSCONFDIR@|${sysconfdir}|g' \
        ${D}${sysconfdir}/camera-firmware/app.yaml.example

    install -d ${D}${datadir}/camera-firmware/licenses
    install -m 0644 ${CF_INTEGRITY_PUBLIC_KEY_FILE} \
        ${D}${datadir}/camera-firmware/integrity-public-key.pem
    install -m 0644 ${UNPACKDIR}/drogon/LICENSE \
        ${D}${datadir}/camera-firmware/licenses/drogon-MIT.txt
    install -m 0644 ${UNPACKDIR}/trantor/License \
        ${D}${datadir}/camera-firmware/licenses/trantor-BSD-3-Clause.txt
    install -m 0644 ${S}/vendor/stb/LICENSE \
        ${D}${datadir}/camera-firmware/licenses/stb.txt
    install -m 0644 ${S}/vendor/fonts/OFL.txt \
        ${D}${datadir}/camera-firmware/licenses/NanumGothic-OFL-1.1.txt
}

do_deploy() {
    install -d ${DEPLOYDIR}
    install -m 0644 ${CF_INTEGRITY_PUBLIC_KEY_FILE} \
        ${DEPLOYDIR}/camera-firmware-integrity-public.pem
}
addtask deploy after do_install before do_build

FILES:${PN} += " \
    ${libdir}/gstreamer-1.0/gstcfsecuresrtp.so \
    ${datadir}/camera-firmware/licenses \
    ${datadir}/camera-firmware/integrity-public-key.pem \
    ${sysconfdir}/camera-firmware \
"
CONFFILES:${PN} = "${sysconfdir}/camera-firmware/app.yaml.example"

# Element factories are loaded at runtime and are not discovered by shlibdeps.
# GIO's GTlsCertificate implementation is supplied by glib-networking.
RDEPENDS:${PN} += " \
    camera-firmware-web glib-networking \
    gstreamer1.0-plugins-base-app \
    gstreamer1.0-plugins-good-isomp4 gstreamer1.0-plugins-good-udp \
    gstreamer1.0-plugins-good-rtp gstreamer1.0-plugins-good-rtpmanager \
    gstreamer1.0-plugins-bad-srtp gstreamer1.0-plugins-bad-videoparsersbad \
"
