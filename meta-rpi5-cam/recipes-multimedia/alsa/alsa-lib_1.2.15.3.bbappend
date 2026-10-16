FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Official maintenance corrections for installed public library APIs.
SRC_URI += "file://CVE-2026-56109.patch file://CVE-2026-90781.patch"

# Ownership-safe adaptation of the upstream sparse multi-binding proposal.
SRC_URI += "file://CVE-2026-96675.patch"
