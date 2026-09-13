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
    file://camera-firmware.service \
    file://app.yaml.example \
"
SRCREV_drogon = "f215cb15a0f53abd0ca7ee8b95ed8c9c3b40d262"
SRCREV_trantor = "79e1ffc59aa1b9c8226c2988fe2e1185e97cd795"
SRCREV_FORMAT = "firmware_drogon_trantor"

inherit cmake pkgconfig systemd useradd

DEPENDS = " \
    git-native patch-native openssl-native \
    openssl sqlite3 yaml-cpp jsoncpp jpeg util-linux zlib \
    libcamera gstreamer1.0 gstreamer1.0-plugins-base \
    gstreamer1.0-rtsp-server libsrtp x264 rpidistro-ffmpeg \
"

PACKAGECONFIG ??= ""
PACKAGECONFIG[hailo] = "-DCF_WITH_HAILORT=ON,-DCF_WITH_HAILORT=OFF,hailort"

# Supply a production public key through a bbappend SRC_URI and point this at
# its unpacked path. Private signing keys must never be build inputs. The
# upstream development public key is explicit here for provisioning-only images.
CF_INTEGRITY_PUBLIC_KEY_FILE ?= "${S}/config/integrity/dev-public-key.pem"

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

do_install:append() {
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/camera-firmware.service \
        ${D}${systemd_system_unitdir}/camera-firmware.service
    sed -i -e 's|@BINDIR@|${bindir}|g' -e 's|@SYSCONFDIR@|${sysconfdir}|g' \
        ${D}${systemd_system_unitdir}/camera-firmware.service

    # Deliberately install an example only. The unit requires the operator's
    # app.yaml and cannot boot the unauthenticated development configuration.
    install -d -m 0750 ${D}${sysconfdir}/camera-firmware
    chown root:camera-firmware ${D}${sysconfdir}/camera-firmware
    install -m 0644 ${UNPACKDIR}/app.yaml.example \
        ${D}${sysconfdir}/camera-firmware/app.yaml.example
    sed -i -e 's|@DATADIR@|${datadir}|g' -e 's|@SYSCONFDIR@|${sysconfdir}|g' \
        ${D}${sysconfdir}/camera-firmware/app.yaml.example

    install -d ${D}${datadir}/camera-firmware/licenses
    install -m 0644 ${UNPACKDIR}/drogon/LICENSE \
        ${D}${datadir}/camera-firmware/licenses/drogon-MIT.txt
    install -m 0644 ${UNPACKDIR}/trantor/License \
        ${D}${datadir}/camera-firmware/licenses/trantor-BSD-3-Clause.txt
    install -m 0644 ${S}/vendor/stb/LICENSE \
        ${D}${datadir}/camera-firmware/licenses/stb.txt
    install -m 0644 ${S}/vendor/fonts/OFL.txt \
        ${D}${datadir}/camera-firmware/licenses/NanumGothic-OFL-1.1.txt
}

FILES:${PN} += " \
    ${libdir}/gstreamer-1.0/gstcfsecuresrtp.so \
    ${datadir}/camera-firmware/licenses \
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
