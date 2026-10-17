#!/usr/bin/env bash
# Start a fresh integrated Raspberry Pi camera/Hailo image build.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./scripts/build-image.sh

Generate a new build ID and build the rpi5-camera-hailo image.
GCC and target development tools are excluded by default.
Set RPI5_LOCAL_BUILDTOOLS=1 to include them for development.

Each invocation starts a new build record. To retry an interrupted build,
use scripts/build.sh --build-id ID rpi5-camera-hailo build with the printed
ID and the same environment options.
EOF
}

if [[ $# -eq 1 && ( "$1" == --help || "$1" == -h ) ]]; then
    usage
    exit 0
fi
if [[ $# -ne 0 ]]; then
    usage >&2
    exit 2
fi

source "$(dirname "$0")/lib/common.sh"
repo_root="$(rpi5_repo_root)"
build_id="$("$repo_root/scripts/new-build-id.sh")"
export RPI5_LOCAL_BUILDTOOLS="${RPI5_LOCAL_BUILDTOOLS:-0}"
printf 'New build ID: %s\n' "$build_id"
exec "$repo_root/scripts/build.sh" --build-id "$build_id" rpi5-camera-hailo build
