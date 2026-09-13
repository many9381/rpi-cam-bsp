# Camera firmware Yocto integration

The camera application in the separate `rpi-cam-hailo` checkout is the firmware
to package. Keep that checkout out of this repository and do not modify it.
The existing Yocto implementation worktree is the integration base.

## Source and build boundary

Fetch `many9381/rpi-cam-hailo` at
`ba503a1fbc4ed68c1fd29aace7214a5c330d7021`. Recipes must permit an explicit
local Git transport override for offline/private-source development while
retaining the same revision. Do not use floating revisions or externalsrc.
Preserve the firmware's checks of the exact Drogon 1.9.0 and Trantor 1.5.20
source identities and its four source hardening patches.

Build the C++20 application with the Yocto toolchain and build the React web
assets with `nodejs-native`. The target needs compiled assets, not Node.js.
The pinned BitBake disables npm/npmsw fetchers: generate normal HTTPS fetch
entries with SHA-512 checksums from the source package lock, populate a private
npm cache from those fetched archives, and run npm offline with scripts disabled
during dependency installation. Only the explicit web build script executes.
Verify the source lock hash before building. No compile/configure task gets
network permission.

## Packages and runtime

Provide `camera-firmware`, its web assets and helper executables, and the custom
GStreamer SRTP module. Reuse the existing OpenSSL, SQLite, yaml-cpp, jsoncpp,
JPEG, GStreamer, libsrtp, x264 and Raspberry Pi FFmpeg recipes. Address the
libcamera 0.7 Raspberry Pi API requirement in the firmware profile as needed.

Install a systemd service and a documented example configuration. Require a
device configuration at `/etc/camera-firmware/app.yaml` before starting; do not
silently start the reference development configuration with authentication off.
Device TLS, integrity signing keys/manifests, management origin and HEF models
remain operator-provisioned. No private keys or shared media keys enter recipes.

Add the application package to the camera image. Preserve the minimal and QEMU
images and the existing hardware validation gates. Offer Hailo-8 as a separate
kas overlay, with the application PACKAGECONFIG, HailoRT, PCIe module and chip
firmware all on 4.24.0. Use pinned official sources with license checksums.

The user confirmed this separate-profile option on 2026-09-13. Hailo support
must not become a dependency of the standard camera or minimal/QEMU images.

## Verification

Run the existing host suite, behavior tests for the npm lock generator and
new profile routing, and real BitBake parsing/dependency resolution for both
camera variants and the existing minimal/QEMU profiles. Exercise fetch, patch,
configure and compilation where available resources allow. Record precisely
which stages ran; hardware acceptance and flashing are outside this change.

## Alternatives considered

A copied application tree would duplicate ownership and violate the requested
Git boundary. Untracked externalsrc would make patches and source identity
dependent on workstation state. Pinned Git recipes keep that boundary explicit
and permit a local transport without changing the build inputs.
