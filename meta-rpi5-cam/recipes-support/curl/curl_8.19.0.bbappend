# Official signed release, verified with curl's published release key.
# https://curl.se/changes.html and https://curl.se/docs/security.html
PV = "8.22.0"
SRC_URI[sha256sum] = "f7ef3ae8a22e521f289803fe93543eb64c329b58aa73a9e224dfd915a2a5f4f7"

# These fixes are already present in 8.22.0. Retain the OE ptest timeout,
# refreshed for the upstream test harness's whitespace/context changes.
SRC_URI:remove = "file://CVE-2026-6276.patch file://CVE-2026-5773.patch file://mbedtls.patch"
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Upstream removed librtmp support, including --without-librtmp. Leaving the
# inherited flag emits an unknown configure option even when RTMP is disabled.
unset PACKAGECONFIG[rtmpdump]
