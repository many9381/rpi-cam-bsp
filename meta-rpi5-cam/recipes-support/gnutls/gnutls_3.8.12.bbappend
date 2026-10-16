FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Preserve OCSP certificate selection and DNS label constraint semantics.
SRC_URI += "file://CVE-2026-3832.patch file://CVE-2026-3833.patch"

# Complete the private DTLS fragment-length and sequence consistency backport.
SRC_URI += "file://CVE-2026-33845.patch"
