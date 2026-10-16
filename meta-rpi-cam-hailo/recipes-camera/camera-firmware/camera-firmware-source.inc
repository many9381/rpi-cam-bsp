# Both the application and web assets must come from the same reviewed commit.
# A local Git transport can be selected without using externalsrc or changing
# the source revision, for example git:///absolute/path;protocol=file;branch=master.
CAMERA_FIRMWARE_GIT_URI ?= "git://git@github.com/many9381/rpi-cam-hailo.git;protocol=ssh;branch=master"
CAMERA_FIRMWARE_SRCREV = "a6364ff4c8161334fdf89b54b8d2eeb4ec55a32c"

SRC_URI = "${CAMERA_FIRMWARE_GIT_URI};name=firmware"
SRCREV_firmware = "${CAMERA_FIRMWARE_SRCREV}"
SRCREV_FORMAT = "firmware"
PV = "0+git"
