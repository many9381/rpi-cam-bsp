SUMMARY = "Hailo-8 PCIe kernel driver"
HOMEPAGE = "https://github.com/hailo-ai/hailort-drivers"
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://hailort/drivers/linux/pcie/src/pcie.c;beginline=1;endline=1;md5=50d2ba0afecd20f74c12a4bdbcfcfe61"

require hailo-pcie-deb.inc

SRC_URI = " \
    file://0001-deb-use-target-kernel-configuration.patch \
    file://60-hailo.rules \
"
S = "${UNPACKDIR}/deb/usr/src/hailort-pcie-driver"
B = "${S}/hailort/drivers/linux/pcie"

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
    install -d ${D}${sysconfdir}/modprobe.d
    install -m 0644 ${UNPACKDIR}/deb/etc/modprobe.d/hailo_pci.conf ${D}${sysconfdir}/modprobe.d/
}

FILES:${PN} += "${nonarch_base_libdir}/udev/rules.d/60-hailo.rules ${sysconfdir}/modprobe.d/hailo_pci.conf"
CONFFILES:${PN} = "${sysconfdir}/modprobe.d/hailo_pci.conf"
