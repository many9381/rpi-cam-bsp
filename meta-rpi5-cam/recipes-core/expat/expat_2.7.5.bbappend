FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Preserve the libexpat.so.1 ABI and pre-2.9 optional APIs while taking the
# 2.8 security series. Keep the inherited OE CMake packaging and ptest setup.
PV = "2.8.5"
CVE_VERSION = "2.8.5"
SRC_URI[sha256sum] = "952c03c33a6b337f12dae7a9b0f9dee86f867550d35c994d6bdaaddd37dc8454"

# The release contains the inherited attribute/hash-flooding backports.
SRC_URI:remove = "file://CVE-2026-45186-01.patch file://CVE-2026-45186-02.patch file://CVE-2026-45186-03.patch file://CVE-2026-45186-04.patch file://CVE-2026-45186-05.patch file://CVE-2026-45186-06.patch file://CVE-2026-45186-07.patch file://CVE-2026-41080-1.patch file://CVE-2026-41080-2.patch"
SRC_URI += "file://CVE-2026-102633.patch file://CVE-2026-77214.patch"
