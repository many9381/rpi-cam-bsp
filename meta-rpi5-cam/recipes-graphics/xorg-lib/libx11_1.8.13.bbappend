FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Official XKB, XIM attribute/trigger-key and locale-reader bounds corrections.
SRC_URI += "file://CVE-2026-88806.patch file://CVE-2026-94283-94285.patch"
