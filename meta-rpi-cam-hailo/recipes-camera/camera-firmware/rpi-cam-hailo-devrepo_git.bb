SUMMARY = "Optional rpi-cam-hailo Git checkout for development on the Pi"
DESCRIPTION = "Independent, editable checkout of the firmware's pinned upstream revision with reviewed security patches in rpiadmin's home."
HOMEPAGE = "https://github.com/many9381/rpi-cam-hailo"
LICENSE = "CLOSED & MIT & OFL-1.1"
LIC_FILES_CHKSUM = " \
    file://vendor/stb/LICENSE;md5=984f6efd5e88275dd103d489cc99f6d9 \
    file://vendor/fonts/OFL.txt;md5=5c64af38e3f89f2ae508311c57e5f0f6 \
"

require camera-firmware-source.inc

# Apply these after recreating the checkout: do_patch changes would be lost
# when the pristine pinned commit is fetched into the installed repository.
CF_DEV_SECURITY_PATCHES = " \
    0004-security-fix-web-dependency-and-sbom-hashes.patch \
    0005-dhcp-setup-and-optional-management-ip-policy.patch \
    0006-rtsp-protect-existing-sessions-before-authentication.patch \
    0007-setup-session-recovery-and-error-messages.patch \
    0008-camera-capture-health-and-bounded-recovery.patch \
    0009-quality-gate-and-plain-bootstrap-peers.patch \
    0010-avoid-intermediate-metadata-and-error-copies.patch \
"
SRC_URI += " \
    file://0004-security-fix-web-dependency-and-sbom-hashes.patch;apply=no \
    file://0005-dhcp-setup-and-optional-management-ip-policy.patch;apply=no \
    file://0006-rtsp-protect-existing-sessions-before-authentication.patch;apply=no \
    file://0007-setup-session-recovery-and-error-messages.patch;apply=no \
    file://0008-camera-capture-health-and-bounded-recovery.patch;apply=no \
    file://0009-quality-gate-and-plain-bootstrap-peers.patch;apply=no \
    file://0010-avoid-intermediate-metadata-and-error-copies.patch;apply=no \
"

inherit allarch useradd

DEPENDS += "git-native"
USERADD_DEPENDS = "device-config"
RDEPENDS:${PN} = "git device-config"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    # Recreate Git metadata instead of copying the fetcher's alternates,
    # host configuration, hooks, credentials or uncommitted working files.
    export GIT_CONFIG_NOSYSTEM=1
    export GIT_CONFIG_GLOBAL=/dev/null
    export GIT_TERMINAL_PROMPT=0
    dev_git() {
        git -c core.logAllRefUpdates=false -c core.hooksPath=/dev/null "$@"
    }
    workspace="${D}/home/rpiadmin/rpi-cam-hailo"
    install -d "$workspace"
    dev_git init --initial-branch=master --template= "$workspace"
    dev_git -C "$workspace" -c protocol.file.allow=always fetch \
        --no-tags --no-write-fetch-head "${S}" "${CAMERA_FIRMWARE_SRCREV}"
    dev_git -C "$workspace" checkout -B master "${CAMERA_FIRMWARE_SRCREV}"
    dev_git -C "$workspace" remote add origin git@github.com:many9381/rpi-cam-hailo.git
    dev_git -C "$workspace" update-ref refs/remotes/origin/master "${CAMERA_FIRMWARE_SRCREV}"
    dev_git -C "$workspace" branch --set-upstream-to=origin/master master
    test ! -e "$workspace/.git/objects/info/alternates"
    dev_git -C "$workspace" fsck --full
    # Keep the upstream commit/history intact. Reviewed layer fixes remain
    # visible in git diff; no unrelated build-host working files are copied.
    for security_patch in ${CF_DEV_SECURITY_PATCHES}; do
        dev_git -C "$workspace" apply --whitespace=error "${UNPACKDIR}/$security_patch"
    done
    # RPM includes parent directories too; match device-config's home owner.
    chown -hR rpiadmin:rpiadmin "${D}/home/rpiadmin"
}

FILES:${PN} = "/home/rpiadmin/rpi-cam-hailo"
