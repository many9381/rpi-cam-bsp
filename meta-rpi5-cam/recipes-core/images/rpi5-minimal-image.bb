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

# Pi 5's detected 4-pin fan uses this modular driver. Our minimal image does
# not select packagegroup-machine-base, so the BSP's kernel-modules
# recommendation in MACHINE_EXTRA_RRECOMMENDS does not install it for us.
IMAGE_INSTALL:append:raspberrypi5 = " kernel-module-pwm-fan"

EXTRA_USERS_PARAMS = "usermod -p '!' root;"
