RPI_CAM_HAILO_DEV_REPO ?= "1"
IMAGE_INSTALL:append = "${@' rpi-cam-hailo-devrepo' if d.getVar('RPI_CAM_HAILO_DEV_REPO') != '0' else ''}"

# Export the exact public key embedded in this image for pre-erase validation.
do_image_complete[depends] += "camera-firmware:do_deploy"
