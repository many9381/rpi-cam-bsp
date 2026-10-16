FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Accepted upstream correction for stale IFS state after expansion errors.
SRC_URI += "file://CVE-2026-38754.patch"

# Verified ownership correction proposed on the official BusyBox list.
SRC_URI += "file://CVE-2026-38753.patch"
