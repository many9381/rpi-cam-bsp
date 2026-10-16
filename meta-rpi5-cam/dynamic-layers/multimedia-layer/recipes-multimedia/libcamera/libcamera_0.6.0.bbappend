# The Raspberry Pi 6.18 DT selects rp1-cfe-downstream. Upstream libcamera
# 0.6 targets different CFE entity names and CSI pad/routing APIs, so it
# cannot enumerate this driver's cameras even when the sensor probes.
# Keep the 0.6 client ABI and use Raspberry Pi's matching pipeline/IPA code.
SRC_URI:remove:rpi = "git://git.libcamera.org/libcamera/libcamera.git;protocol=https;branch=master;tag=v${PV}"
SRC_URI:prepend:rpi = "git://github.com/raspberrypi/libcamera.git;protocol=https;branch=main;tag=v0.6.0+rpt20251202 "
SRCREV:rpi = "f0e40f1c50bd0afe65727d6e407d0dcb42666ada"
PKGV:rpi = "${PV}+rpt20251202"
PR:append:rpi = ".rpi1"
