#!/usr/bin/env bash
# Run inside a configured rpi5-camera-hailo kas shell, from its build directory:
# bash /path/to/project/tests/integration/check-camera-sources.sh
# Uses actual recipe QA, fetching, unpacking and patching to catch compatibility
# errors before compiling the image. Requires network or cached sources.
set -euo pipefail

bitbake -k -c patch \
    hailort hailo-pci hailo-firmware camera-firmware camera-firmware-web \
    libcamera-apps
