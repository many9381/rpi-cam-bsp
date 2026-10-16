#!/usr/bin/env bash
# Run inside a configured camera-profile kas shell, from its build directory:
# bash /path/to/project/tests/integration/check-camera-dependencies.sh
# Metadata-only: does not compile an image or bypass runtime/hardware gates.
set -euo pipefail

bitbake -g rpi5-camera-image

# Both firmware and camera tools must resolve to the same Pi FFmpeg provider.
if ! grep -Fxq rpidistro-ffmpeg pn-buildlist; then
    printf 'FAIL: Raspberry Pi FFmpeg is absent from the camera graph\n' >&2
    exit 1
fi
if grep -Fxq ffmpeg pn-buildlist; then
    printf 'FAIL: generic FFmpeg conflicts with Raspberry Pi FFmpeg\n' >&2
    exit 1
fi

# A provider graph alone can miss scheduling failures such as dependency loops.
bitbake -n rpi5-camera-image
