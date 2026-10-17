SUMMARY = "Optional C and C++ build tools for Raspberry Pi development"
DESCRIPTION = "Target compilers, standard headers, linker inputs and build tools; selected only by RPI5_LOCAL_BUILDTOOLS."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

PACKAGE_ARCH = "${TUNE_PKGARCH}"
inherit packagegroup

# Target-side tools only. Runtime libgcc/libstdc++ dependencies remain owned
# by their consumers independently of this optional development package group.
RDEPENDS:${PN} = " \
    packagegroup-core-buildessential \
    virtual-libc-dev \
    libgcc-dev \
    cmake \
    ninja \
"
