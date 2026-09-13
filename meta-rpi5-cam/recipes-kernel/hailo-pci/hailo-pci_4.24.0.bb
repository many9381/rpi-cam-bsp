SUMMARY = "Hailo-8 PCIe kernel driver"
HOMEPAGE = "https://github.com/hailo-ai/hailort-drivers"
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://LICENSE;md5=39bba7d2cf0ba1036f2a6e2be52fe3f0"

SRC_URI = " \
    git://github.com/hailo-ai/hailort-drivers.git;protocol=https;branch=hailo8 \
    file://0001-use-target-kernel-configuration.patch \
    file://60-hailo.rules \
"
SRCREV = "2789e0ff8b75ffdbaf8f7235f55aef3c06a2ed24"
S = "${UNPACKDIR}/git"
B = "${S}/linux/pcie"

inherit module

# Call kbuild directly. Upstream's wrapper invokes host uname, depmod and DKMS;
# the module class supplies the target compiler, kernel output and install root.
EXTRA_OEMAKE += "-C ${STAGING_KERNEL_DIR} M=${B}"
MAKE_TARGETS = "modules"
KERNEL_MODULE_AUTOLOAD += "hailo_pci"
RDEPENDS:${PN} += "hailo-firmware (= ${EXTENDPKGV})"

do_install:append() {
    install -d ${D}${nonarch_base_libdir}/udev/rules.d
    install -m 0644 ${UNPACKDIR}/60-hailo.rules ${D}${nonarch_base_libdir}/udev/rules.d/60-hailo.rules
}

FILES:${PN} += "${nonarch_base_libdir}/udev/rules.d/60-hailo.rules"
