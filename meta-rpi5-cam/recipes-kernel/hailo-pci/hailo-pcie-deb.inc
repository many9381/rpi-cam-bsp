# Driver sources and chip firmware share this exact, Git-ignored input.
FILESEXTRAPATHS:prepend := "${RPI5_CAM_LAYERDIR}/recipes-kernel/hailo-pci/files:"
HAILO_DEB_FILE = "hailort-pcie-driver_${PV}_all.deb"
HAILO_DEB_SHA256 = "3d13d833cfafe1231f42ead9b02f1c08348fa640fd282119e57baa848b31618b"

inherit hailo-local-deb
