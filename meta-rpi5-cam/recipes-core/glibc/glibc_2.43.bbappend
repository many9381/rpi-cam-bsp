FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Keep the OE 2.43 source pin/ABI; fix resolver aborts on truncated search lists.
SRC_URI += "file://CVE-2026-8674.patch"

# Ordered glibc 2.43 stable backports, including DNS formatter prerequisites.
SRC_URI += "file://0001-stable-72351055.patch file://0002-stable-20b3e871.patch file://0003-stable-713998bf.patch file://0004-stable-0afa34ad.patch file://0005-stable-2890b35c.patch file://0006-stable-4070d808.patch file://0007-stable-dae425b5.patch file://0008-stable-349297a4.patch file://0009-stable-1d7d1a16.patch file://0010-stable-c46f7b2f.patch file://0011-stable-e64ae5a5.patch file://0012-stable-c9225a3e.patch file://0013-stable-3a418da6.patch file://0014-stable-8759917d.patch file://0015-stable-533e1c95.patch"
