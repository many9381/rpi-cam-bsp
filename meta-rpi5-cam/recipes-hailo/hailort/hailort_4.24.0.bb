SUMMARY = "Hailo-8 runtime, CLI and GStreamer plugin from the local ARM64 package"
HOMEPAGE = "https://github.com/hailo-ai/hailort"
LICENSE = "MIT & BSD-2-Clause & BSD-3-Clause & MPL-2.0 & BSL-1.0 & Apache-2.0 & Zlib"
LIC_FILES_CHKSUM = "file://usr/share/doc/hailort/copyright;md5=bdbc7f982b701bd5c908f8d9ad7f629e"

HAILO_DEB_FILE = "hailort_${PV}_arm64.deb"
HAILO_DEB_SHA256 = "9ac1a633cf8adb3e036544ddc2ac9568acacc31bef41a518da7e14343b4e5cc6"

inherit hailo-local-deb bin_package systemd

COMPATIBLE_HOST = "aarch64.*-linux"
COMPATIBLE_HOST:libc-musl = "null"
DEPENDS = "gcc-runtime glibc gstreamer1.0 gstreamer1.0-plugins-base"

# Preserve the vendor's stripped binaries. Other dependency/architecture QA
# remains active; vendor binaries were not linked with Yocto's LDFLAGS.
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INSANE_SKIP:${PN} += "already-stripped ldflags"
INSANE_SKIP:${PN}-cli += "already-stripped ldflags"
INSANE_SKIP:${PN}-gstreamer += "already-stripped ldflags"

PACKAGES =+ "${PN}-cli ${PN}-gstreamer"
FILES:${PN} = "${libdir}/libhailort.so.* ${bindir}/hailort_service ${systemd_system_unitdir}/hailort.service ${sysconfdir}/default/hailort_service"
FILES:${PN}-cli = "${bindir}/hailortcli"
FILES:${PN}-gstreamer = "${libdir}/gstreamer-1.0/libgsthailo.so"
FILES:${PN}-dev += "${libdir}/cmake/HailoRT"
RDEPENDS:${PN}-cli = "${PN} (= ${EXTENDPKGV})"
RDEPENDS:${PN}-gstreamer = "${PN} (= ${EXTENDPKGV})"

# The camera uses direct device access. Ship the vendor service for optional
# multi-process use, leaving activation to the operator.
SYSTEMD_SERVICE:${PN} = "hailort.service"
SYSTEMD_AUTO_ENABLE:${PN} = "disable"
CONFFILES:${PN} = "${sysconfdir}/default/hailort_service"

do_install() {
    install -d ${D}${libdir} ${D}${bindir} ${D}${includedir}
    install -m 0755 ${S}/usr/lib/libhailort.so.${PV} ${D}${libdir}/
    ln -s libhailort.so.${PV} ${D}${libdir}/libhailort.so
    install -m 0755 ${S}/usr/bin/hailortcli ${S}/usr/bin/hailort_service ${D}${bindir}/
    cp -R --no-preserve=ownership ${S}/usr/include/. ${D}${includedir}/

    install -d ${D}${libdir}/cmake/HailoRT ${D}${libdir}/gstreamer-1.0
    install -m 0644 ${S}/usr/lib/cmake/HailoRT/*.cmake ${D}${libdir}/cmake/HailoRT/
    sed -i 's|/lib/libhailort|/${baselib}/libhailort|g' ${D}${libdir}/cmake/HailoRT/*.cmake
    install -m 0644 ${S}/usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgsthailo.so ${D}${libdir}/gstreamer-1.0/

    install -d ${D}${systemd_system_unitdir} ${D}${sysconfdir}/default
    install -m 0644 ${S}/lib/systemd/system/hailort.service ${D}${systemd_system_unitdir}/
    install -m 0644 ${S}/etc/default/hailort_service ${D}${sysconfdir}/default/
    # EnvironmentFile accepts assignments, not the vendor's INI section header.
    sed -i '/^\[Service\]$/d' ${D}${sysconfdir}/default/hailort_service

    install -d ${D}${datadir}/doc/hailort
    install -m 0644 ${S}/usr/share/doc/hailort/copyright ${D}${datadir}/doc/hailort/
}
