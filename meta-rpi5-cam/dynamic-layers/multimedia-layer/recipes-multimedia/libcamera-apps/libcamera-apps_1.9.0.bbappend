FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://0001-explicitly-copy-camera-model-string-views.patch"

# libav support installs its runtime encoder as a loadable plugin.
FILES:${PN} += "${libdir}/rpicam-apps-encoder"
