require gstreamer-security.inc

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://0001-rtsp-client-authenticate-before-session-association.patch"

# Verified against the official archive and its .sha256sum sidecar.
SRC_URI[sha256sum] = "59181ed21a5bc0533fb4f77cb7bc6005d89365e834b0c1294afb9ab5f7d96fe0"
