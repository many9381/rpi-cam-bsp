FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Preserve the 2.15.2 recipe/ABI and backport the reviewed 2.15.4 security series.
# The regexp parser length check precedes its allocation-failure correction.
SRC_URI += "file://CVE-2026-86137.patch file://CVE-2026-86138.patch file://CVE-2026-86139.patch file://CVE-2026-86140.patch file://CVE-2026-86141.patch file://CVE-2026-86142.patch file://CVE-2026-86143.patch file://CVE-2026-86144.patch"
