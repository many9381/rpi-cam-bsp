# Only a path is stored in BitBake metadata. Never export credentials or use
# SRC_URI for them: do_install/package/sstate must remain secret-free.
RPI5_WIFI_CONFIG_FILE ??= "${RPI5_CAM_LAYERDIR}/../keys/wifi.json"

python __anonymous() {
    from rpi5cam.wifi_config import rootfs_checksums

    try:
        checksums = rootfs_checksums(
            d.getVar("MACHINE"), d.getVar("RPI5_WIFI_CONFIG_FILE"),
            d.getVar("RPI5_CAM_LAYERDIR") + "/lib/rpi5cam/wifi_config.py")
    except ValueError as error:
        bb.fatal(str(error))
    if checksums:
        d.appendVarFlag("do_rootfs", "file-checksums", checksums)
        d.appendVar("ROOTFS_POSTPROCESS_COMMAND", " rpi5_provision_wifi;")
}

python rpi5_provision_wifi() {
    from rpi5cam.wifi_config import install_wifi_config

    try:
        enabled = install_wifi_config(d.getVar("RPI5_WIFI_CONFIG_FILE"),
                                      d.getVar("IMAGE_ROOTFS"), d.getVar("sysconfdir"))
    except (ValueError, OSError):
        # Do not include input, exception context or generated config in logs.
        bb.fatal("Wi-Fi provisioning failed; check local JSON fields and mode 0600")
    bb.note("Local Wi-Fi configuration installed" if enabled else
            "No local Wi-Fi configuration; automatic association disabled")
}
