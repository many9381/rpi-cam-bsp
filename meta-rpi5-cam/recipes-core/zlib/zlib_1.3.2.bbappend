FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Upstream has not yet released the non-blocking gzwrite fix in a new version.
SRC_URI += "file://0001-Fix-buffer-overflow-bug-in-non-blocking-gzwrite.patch"
