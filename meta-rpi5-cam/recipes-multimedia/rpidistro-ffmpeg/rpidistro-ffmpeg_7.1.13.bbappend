# The inherited recipe's 7.1.13 label actually packaged FFmpeg 7.1.3.
# Correct the version while keeping RPM upgrades monotonic with an epoch.
# Retain PE for subsequent updates until downstream package migration permits it.
PE = "1"
PV = "7.1.5"
CVE_VERSION = "7.1.5"
SRCREV = "2fe08f3bd52c6e795df8353d29deb89596b5099d"

# Upstream removed nine form-feed bytes; the LGPL 2.1 text is otherwise identical.
LIC_FILES_CHKSUM:remove = "file://COPYING.LGPLv2.1;md5=bd7a443320af8c812e4c18d1b79df004"
LIC_FILES_CHKSUM:append = " file://COPYING.LGPLv2.1;md5=eed22b3456132611e3d4aa7a7ec64dac"

# Keep Raspberry Pi's downstream codec support ahead of the existing OE patches.
SRC_URI:remove = "file://ffmpeg-7.1.2-rpi_28.patch"
SRC_URI:prepend = "file://ffmpeg-7.1.5-rpi_29.patch "

# Narrow upstream memory-safety fixes for enabled codecs, parsers and muxers.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += " \
    file://CVE-2026-64830.patch \
    file://CVE-2026-64835.patch \
    file://CVE-2026-65703.patch \
    file://CVE-2026-65704.patch \
    file://CVE-2026-66039.patch \
    file://CVE-2026-70628.patch \
    file://CVE-2026-70632.patch \
    file://CVE-2026-75141.patch \
    file://CVE-2026-75142.patch \
    file://CVE-2026-75144.patch \
    file://CVE-2026-65706.patch \
    file://CVE-2026-107676.patch \
    file://CVE-2026-107695.patch \
    file://CVE-2026-107697.patch \
    file://CVE-2026-64833.patch \
    file://CVE-2026-64834.patch \
    file://CVE-2026-66037.patch \
    file://CVE-2026-66038.patch \
    file://CVE-2026-70629.patch \
    file://CVE-2026-70630.patch \
    file://CVE-2026-70631.patch \
    file://0001-drm-let-device-callback-own-failure-cleanup.patch \
    file://0002-hls-release-detached-segments-on-parse-failure.patch \
    file://CVE-2026-107696.patch \
    file://CVE-2026-58049.patch \
    file://CVE-2026-65705.patch \
    file://CVE-2026-66036.patch \
    file://0003-encryption-init-release-list-iteratively.patch \
    file://0004-encryption-init-handle-missing-key-array.patch \
    file://0005-encryption-init-append-serialized-records.patch \
"
