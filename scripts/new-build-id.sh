#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

repo_root="$(rpi5_repo_root)"
revision="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
printf '%s-%s\n' "$timestamp" "$revision"
