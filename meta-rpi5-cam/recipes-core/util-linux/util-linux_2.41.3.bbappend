FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Skip privileged hooks after helper/syscall failure while preserving mount-stage
# no-op cases (bind/move) and releasing loop devices when post hooks are skipped.
SRC_URI += "file://CVE-2026-76642.patch"

# Preserve authorized target identity and restrict unsafe post-mount fallbacks.
# The image fix does not change build-host or SDK mount tools.
SRC_URI:append:class-target = " file://CVE-2026-53612-53613.patch"
