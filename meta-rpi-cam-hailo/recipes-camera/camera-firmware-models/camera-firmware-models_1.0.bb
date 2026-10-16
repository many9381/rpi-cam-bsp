SUMMARY = "Reviewed Hailo object-detection model for camera firmware"
DESCRIPTION = "Packages a locally supplied, checksum-pinned HEF model."
LICENSE = "CLOSED"

inherit allarch

CAMERA_FIRMWARE_MODEL_DIR ?= "${RPI_CAM_HAILO_LAYERDIR}/../rpi-cam-hailo/vendor/models"
CF_MODEL_SHA256 = "eebaf6e491f8c182c095d2a2fd38d8fc6efbc55d595be1bbec75338f55751917"

FILESEXTRAPATHS:prepend := "${CAMERA_FIRMWARE_MODEL_DIR}:"

def camera_firmware_model_src_uri(d):
    import os
    model_path = d.expand("${CAMERA_FIRMWARE_MODEL_DIR}/yolo_model.hef")
    bb.parse.mark_dependency(d, model_path)
    return "file://yolo_model.hef" if os.path.isfile(model_path) else ""

SRC_URI = "${@camera_firmware_model_src_uri(d)}"
S = "${UNPACKDIR}"

python __anonymous() {
    import os
    model_path = d.expand("${CAMERA_FIRMWARE_MODEL_DIR}/yolo_model.hef")
    bb.parse.mark_dependency(d, model_path)
    if not os.path.isfile(model_path):
        raise bb.parse.SkipRecipe("camera-firmware-models: missing local model input: %s" % model_path)
}

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_validate_model() {
    model="${UNPACKDIR}/yolo_model.hef"
    if [ ! -f "$model" ]; then
        bbfatal "camera-firmware-models: missing unpacked model: $model"
    fi

    actual_sha256=$(sha256sum "$model" | cut -d ' ' -f 1)
    if [ "$actual_sha256" != "${CF_MODEL_SHA256}" ]; then
        bbfatal "camera-firmware-models: SHA-256 mismatch for $model (expected ${CF_MODEL_SHA256}, got $actual_sha256)"
    fi
}
addtask validate_model after do_unpack before do_install

do_install() {
    install -d "${D}${datadir}/camera-firmware/models"
    install -m 0644 "${UNPACKDIR}/yolo_model.hef" \
        "${D}${datadir}/camera-firmware/models/yolo_model.hef"
}

FILES:${PN} = "${datadir}/camera-firmware/models/yolo_model.hef"
