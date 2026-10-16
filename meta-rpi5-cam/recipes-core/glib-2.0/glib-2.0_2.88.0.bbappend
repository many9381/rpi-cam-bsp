FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Reject an offset at the end of untrusted GVariant tuple data before reading it.
SRC_URI += "file://CVE-2026-58010.patch"

# Compatible corrections from the official 2.88.1 maintenance release.
SRC_URI += "file://CVE-2026-58011.patch file://CVE-2026-58012.patch file://CVE-2026-58013.patch file://CVE-2026-58014.patch file://CVE-2026-58015.patch"

# Private GIO rejection-reason class/callback prerequisites for the SHA1 fix.
SRC_URI += "file://CVE-2026-58015-prerequisites.patch"
