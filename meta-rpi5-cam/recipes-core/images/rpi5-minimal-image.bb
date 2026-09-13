SUMMARY = "Headless Raspberry Pi 5 and QEMU validation image"
DESCRIPTION = "Minimal systemd image with wired DHCP, mDNS, key-only SSH, diagnostics, and persistent evidence."
LICENSE = "MIT"

IMAGE_INSTALL = " \
    packagegroup-core-boot \
    ${CORE_IMAGE_EXTRA_INSTALL} \
    device-config \
    systemd-networkd \
    openssh-sftp-server \
    avahi-daemon \
    sudo \
    iproute2 \
    util-linux \
    procps \
    ethtool \
"

IMAGE_FEATURES += "ssh-server-openssh"
IMAGE_FEATURES:remove = "debug-tweaks allow-empty-password empty-root-password allow-root-login serial-autologin-root"
IMAGE_LINGUAS = " "

IMAGE_ROOTFS_SIZE = "1048576"
IMAGE_ROOTFS_EXTRA_SPACE = "524288"

inherit core-image extrausers rpi5-wifi-provision

# The camera image requires this recipe; QEMU stays wired-only.
IMAGE_INSTALL:append:raspberrypi5 = " rpi5-wifi"

EXTRA_USERS_PARAMS = "usermod -p '!' root;"
