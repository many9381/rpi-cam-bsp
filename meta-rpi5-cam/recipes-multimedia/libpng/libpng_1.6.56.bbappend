FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Official maintenance corrections for installed public library APIs.
SRC_URI += "file://CVE-2026-34757-1.patch file://CVE-2026-34757-2.patch"
