SUMMARY = "Headless Raspberry Pi 5 Camera Module 3 Wide image"
DESCRIPTION = "Extends rpi5-minimal-image with IMX708 still capture and software H.264 recording."

require rpi5-minimal-image.bb

IMAGE_INSTALL:append = " \
    libcamera-apps \
    libcamera \
    v4l-utils \
    media-ctl \
    rpidistro-ffmpeg \
    file \
"

IMAGE_ROOTFS_SIZE = "4194304"
