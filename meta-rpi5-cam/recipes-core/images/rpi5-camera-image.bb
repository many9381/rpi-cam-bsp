SUMMARY = "Headless Raspberry Pi 5 Camera Module 3 Wide image"
DESCRIPTION = "Extends rpi5-minimal-image with IMX708 still capture and software H.264 recording."

require rpi5-minimal-image.bb

IMAGE_INSTALL:append = " \
    rpi5-camera-support \
    rpi5-security-policy \
    libcamera-apps \
    libcamera \
    v4l-utils \
    media-ctl \
    rpidistro-ffmpeg \
    file \
    packagegroup-camera-firmware \
"

EXTRA_USERS_PARAMS:append = " usermod -a -G video,render rpiadmin;"

IMAGE_ROOTFS_SIZE = "4194304"

# The two variants share the image recipe and may share a project build ID.
# Capture acceptance must also identify which variant is actually booted.
RPI5_CAMERA_PROFILE ?= "rpi5-camera"
ROOTFS_POSTPROCESS_COMMAND += "write_camera_profile; "

write_camera_profile() {
    case "${RPI5_CAMERA_PROFILE}" in
        rpi5-camera|rpi5-camera-hailo) ;;
        *) bbfatal "unsupported camera profile: ${RPI5_CAMERA_PROFILE}" ;;
    esac
    install -d ${IMAGE_ROOTFS}${sysconfdir}
    printf '%s\n' "${RPI5_CAMERA_PROFILE}" > ${IMAGE_ROOTFS}${sysconfdir}/rpi5-camera-profile
}
