#!/usr/bin/env bash
set -euo pipefail
exec python3 "$(dirname "$0")/lib/camera_capture_health.py" "$@"
