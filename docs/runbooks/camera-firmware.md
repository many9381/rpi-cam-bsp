# Camera application packaging and provisioning

The Yocto camera image includes the firmware implemented in the separate
`many9381/rpi-cam-hailo` repository. Work from the project root, where the
`meta-rpi5-cam/` platform layer, dedicated `meta-rpi-cam-hailo/` application
layer, `kas/` profiles and `scripts/` are checked out. Keep the reference
`rpi-cam-hailo/` directory out of Git; it is not a submodule or a vendored tree.

## Current validated image and dependency records

As of 2026-10-16, Hailo image `20261016T111625Z-e664cb9647e7` has completed
SSD installation, initial setup and three Wi-Fi reboot cycles, with normal
video and Hailo inference confirmed in the web UI. See the firmware checkout's
[image build record](../../rpi-cam-hailo/docs/security/static-warning-image-2026-10-16.md)
and [deployment record](../../rpi-cam-hailo/docs/security/static-warning-deployment-validation-2026-10-16.md).
Those reports are maintained in the separate firmware repository; the links
resolve when it is checked out at `rpi-cam-hailo/` in this workspace.

The [October 16 source snapshot](validated-snapshot-2026-10-16.md) preserves
both repositories under local tag `validated-20261016T111625Z` and explains
its relationship to this image and the unchanged firmware recipe pin.

Use the selected build's private
`artifacts/<build-id>/rpi5-camera-hailo/` directory for dependency evidence:

| Relative path | Purpose |
|---|---|
| `manifests/rpi5-camera-image-raspberrypi5.rootfs.manifest` | Installed package names, architectures and versions |
| `manifests/image.spdx.json` | SPDX document collected from the actual image build |
| `manifests/layer-revisions.txt` | Upstream layer revisions |
| `provenance/inputs.json`, `provenance/sources.tar` | Local recipe, patch and script inputs with hashes |
| `checksums/SHA256SUMS` | Image, manifest and provenance checksums |
| `security/static-warning-deployment-2026-10-16/` | Installation/device acceptance evidence for the build above |

The firmware's September 10 Debian inventory and `sbom/firmware.cdx.json`
describe the older Debian device, not these Yocto RPM packages. Its web SBOM
is separate lockfile evidence. See the
[firmware security index](../../rpi-cam-hailo/docs/security/README.md#current-yocto-image-evidence)
and [build provenance runbook](build-provenance.md) for scope and verification.
Keep generated image/provenance files private and outside Git. Updating these
operating documents does not require rebuilding or reinstalling the accepted
image; an image-affecting change needs its own build and acceptance evidence.

Long-duration operation/endurance testing is excluded by the user's decision
of 2026-10-12, reconfirmed on 2026-10-16. See the
[approved scope](../superpowers/plans/2026-10-12-security-remaining-followup.md#constraints-and-review-focus)
and the firmware's
[current exclusions](../../rpi-cam-hailo/docs/security/README.md#agreed-work-exclusions).
Do not list it as remaining or recommended work unless the user explicitly
changes that decision. Historical reports saying it was not performed remain
accurate evidence boundaries, not outstanding task assignments.

The [October 16 security consumer review](../../rpi-cam-hailo/docs/security/consumer-boundary-review-2026-10-16.md)
checked actual-image libevent/glibc callers and refreshed fourteen non-MOV
primary records. It justified no additional layer patch or rebuild. Retain
the residual findings with the report's explicit reopening conditions.
The reviewed libevent camera/`cam` and HailoRT fixed-pattern `glob` tasks are
completed with no current implementation action. Keep them out of active
remaining-work lists; the unchanged library advisory counts do not require
another patch, build or installation.

## Package composition

| Package | Purpose |
|---|---|
| `camera-firmware` | C++20 executable, integrity/digest helper CLIs, custom SRTP plugin, service and configuration example |
| `camera-firmware-web` | Prebuilt React UI under `/usr/share/camera-firmware/web` |
| `camera-firmware-models` | Hailo-only, checksum-pinned object-detection HEF under `/usr/share/camera-firmware/models` |
| `rpi-cam-hailo-devrepo` | Optional editable Git repository under `/home/rpiadmin/rpi-cam-hailo` |
| `packagegroup-camera-firmware` | Application and Codex operator tools, included by `rpi5-camera-image` |
| `packagegroup-camera-firmware-hailo` | Optional HailoRT library/CLI/GStreamer plugin, matching PCIe driver and chip firmware |

The recipes reuse `libcamera`, `gstreamer1.0`, `gstreamer1.0-plugins-base`,
`gstreamer1.0-rtsp-server`, `libsrtp`, `x264`, `rpidistro-ffmpeg`, `openssl`,
`sqlite3`, `yaml-cpp`, `jsoncpp`, `jpeg`, and the existing toolchain. Runtime
dependencies include GStreamer's app, H.264 parser, MP4 muxer, UDP, SRTP,
RTP and RTP manager plugins and the GIO TLS implementation. The camera profile
enables the stock SRTP plugin for the RTSP server's incoming RTCP decoder;
the application still uses its custom secure encoder. The main C++ program is
cross-compiled for AArch64 with the Yocto target toolchain and serves the web
assets itself; Node.js is a build-host dependency only. Static web assets and
the HEF data package are CPU-independent.

Both camera profiles select `rpidistro-ffmpeg` for the `ffmpeg` and `libav`
build dependencies and the `ffmpeg` runtime dependency. The `x264` CLI's
optional FFmpeg input support is disabled to avoid a circular dependency;
libx264 encoding remains enabled in FFmpeg. After configuring either camera
profile with kas, run `tests/integration/check-camera-dependencies.sh` with bash
inside that kas shell (use the script's absolute path). This checks the real
provider graph and dry-run task scheduling without compiling an image. It
does not replace real-device validation for acceptance. QEMU validation is optional.

The platform layer pins Raspberry Pi libcamera `0.6.0+rpt20251202` at
`f0e40f1c50bd0afe65727d6e407d0dcb42666ada`, retaining the 0.6 client ABI.
This fork matches the downstream RP1 CFE entity names, pads and routing in
the packaged kernel. Upstream libcamera 0.6.0 alone does not match that driver.
IMX708 capture, application encoding and web video were verified on the Pi
after the targeted runtime update on 2026-10-11. Repeat integrated acceptance
for each newly installed image; those results do not validate a later build ID.

The platform layer's multimedia append adapts libcamera-apps 1.9.0 to the
string-view model properties in libcamera 0.6 and packages its libav encoder
plugin. It is active only when the multimedia layer is present.

## Immutable application sources

| Source | Revision |
|---|---|
| Camera application | `a6364ff4c8161334fdf89b54b8d2eeb4ec55a32c` |
| Drogon 1.9.0 | `f215cb15a0f53abd0ca7ee8b95ed8c9c3b40d262` |
| Trantor 1.5.20 | `79e1ffc59aa1b9c8226c2988fe2e1185e97cd795` |

HailoRT, the PCIe driver and the chip firmware use the local, checksum-pinned
Debian inputs described below instead of Git/S3 downloads.

The application defaults to the same GitHub SSH origin as the reference
checkout. The build user needs read access. Both camera profiles forward an
optional transport override, including when using the build wrapper:

```bash
export CAMERA_FIRMWARE_GIT_URI='git:///absolute/path/to/rpi-cam-hailo;protocol=file;branch=master'
```

Alternatively, set it in an ignored kas overlay such as `.state/firmware-local.yml`:

```yaml
header:
  version: 19
local_conf_header:
  local-firmware-source: |
    CAMERA_FIRMWARE_GIT_URI = "git:///absolute/path/to/rpi-cam-hailo;protocol=file;branch=master"
```

For a local recipe check, compose the overlay with
`kas/rpi5-camera.yml:.state/firmware-local.yml`. Changing transport does not change the pinned
commit. Uncommitted source edits are not used. Do not commit local paths,
SSH credentials, private keys, `node_modules`, `dist` or application sources.

The CMake integration patches only affect the fetched build tree. They separate
the web build, select Hailo explicitly, add installation targets and supply
the installed GStreamer plugin directory. The upstream exact Git HEAD/tree
checks and four Drogon/Trantor hardening patches remain active.
Cleanliness checks compare file contents so license-collection hardlinks do
not falsely report modified sources.

## Optional development repository in rpiadmin's home

Both camera profiles include `rpi-cam-hailo-devrepo` by default for device-side
development. The separate package installs `/home/rpiadmin/rpi-cam-hailo`,
including `.git`, the pinned commit's reachable history, and an editable
`master` branch. All files belong to `rpiadmin`, so normal Git edits and
commits work without sudo. It uses the same `CAMERA_FIRMWARE_SRCREV` as the
application and web packages. After checkout, the recipe applies the reviewed
patches listed in `CF_DEV_SECURITY_PATCHES` in
`meta-rpi-cam-hailo/recipes-camera/camera-firmware/rpi-cam-hailo-devrepo_git.bb`:

| Patch | Development checkout changes |
|---|---|
| `0004` | Web dependency and SBOM hash correction |
| `0005` | DHCP setup and optional management IP restrictions |
| `0006` | RTSP session isolation before authentication |
| `0007` | Setup-session recovery and safe error messages |
| `0008` | Capture health, bounded recovery and web status |
| `0009` | Quality-gate source selection and plain bootstrap-peer validation |
| `0010` | Selected intermediate-copy reductions and rollback-error snapshot regressions |

These changes are visible in `git diff`; the commit and its history stay intact.
Patch `0010` is included in accepted image `20261016T111625Z-e664cb9647e7`;
its [image verification](../../rpi-cam-hailo/docs/security/static-warning-image-2026-10-16.md)
and [installation/device acceptance](../../rpi-cam-hailo/docs/security/static-warning-deployment-validation-2026-10-16.md)
both passed on October 16.
Yocto-only CMake/build integration patches are not applied to this checkout.
The recipes do not copy arbitrary host README or documentation edits either;
the device checkout contains only its pinned source and registered patches.

The recipe constructs a new repository from the fetched commit. It includes
no uncommitted host files, ignored models, `node_modules`, local hooks,
credentials or host Git settings. Its objects do not depend on the build
host's Git cache. `origin` is the canonical
`git@github.com:many9381/rpi-cam-hailo.git`, even when the build fetched from a
local transport override. Fetch/push access and commit author identity are
configured separately by the device developer.

To omit the entire development repository from a new image, set one variable:

```bash
RPI_CAM_HAILO_DEV_REPO=0 ./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo build
```

Use a new build ID as described below. The same switch works with
`rpi5-camera`; it can also be set to `0` in the camera kas profile or a local
kas overlay. The runtime application/package group does not depend on this
development package. Minimal and QEMU images do not include it.

On an installed Pi, the checkout can be removed as `rpiadmin` after saving
any local work:

```bash
rm -rf -- /home/rpiadmin/rpi-cam-hailo
```

Deleting that directory does not remove the installed camera application or
Codex login state. Direct edits in the checkout are separate from the
packaged service; compiling them on the Pi requires the relevant target
development tools and headers.

## Offline web and Hailo dependencies

The pinned BitBake has disabled `npm://` and `npmsw://` fetchers; see the
[BitBake fetching documentation](https://docs.yoctoproject.org/bitbake/dev/bitbake-user-manual/bitbake-user-manual-fetching.html).
`camera-firmware-npm.inc` instead declares ordinary HTTPS archives and their
SHA-512 values from `web/package-lock.json`. All dev and optional dependencies
are fetched; npm selects build-host native modules during installation.
Configure seeds a task-local cache and runs `npm ci --offline --ignore-scripts`.
Compile runs the explicit web build with networking disabled. The source lock's
SHA-256 must match the generated include before either step can succeed.

When deliberately updating the pinned application, regenerate and review the
fetch metadata from the exact new revision:

```bash
uv run --locked python scripts/firmware_npm_lock.py \
  /absolute/path/to/rpi-cam-hailo/web/package-lock.json \
  > meta-rpi-cam-hailo/recipes-camera/camera-firmware/camera-firmware-npm.inc
uv run --locked python scripts/firmware_npm_lock.py \
  /absolute/path/to/rpi-cam-hailo/web/package-lock.json \
  --check meta-rpi-cam-hailo/recipes-camera/camera-firmware/camera-firmware-npm.inc
```

Also review the bundled runtime dependency licenses and regenerate
`files/web-third-party-notices.txt` from their exact archive contents when
updating the lock. Its checksum is declared in the web recipe, and the file is
installed under `/usr/share/camera-firmware/licenses/` alongside the app notices.

Application dependencies retain named Git sources and immutable revisions.
To check recipe QA, fetch, unpack and patch before a full build, run
`bash /path/to/project/tests/integration/check-camera-sources.sh` inside the
configured `rpi5-camera-hailo` kas shell. This needs source access or a populated
download cache.

## Local Hailo Debian inputs

Before building `rpi5-camera-hailo`, place the two vendor packages here:

```text
meta-rpi5-cam/
  recipes-hailo/hailort/files/hailort_4.24.0_arm64.deb
  recipes-kernel/hailo-pci/files/hailort-pcie-driver_4.24.0_all.deb
```

Both filenames are excluded by the root `.gitignore`, including while they
are temporarily in the project root. Never force-add them. Recipes, patches
and checksum declarations are versioned; the vendor archives remain local.

| Input | SHA-256 |
|---|---|
| `hailort_4.24.0_arm64.deb` | `9ac1a633cf8adb3e036544ddc2ac9568acacc31bef41a518da7e14343b4e5cc6` |
| `hailort-pcie-driver_4.24.0_all.deb` | `3d13d833cfafe1231f42ead9b02f1c08348fa640fd282119e57baa848b31618b` |

`hailo-local-deb.bbclass` checks these digests before unpacking. Missing inputs
skip the affected recipes, so QEMU/minimal/standard-camera builds remain
independent; a Hailo build fails with a missing-provider explanation. Changed
archives fail checksum validation. Replace an archive only together with a
review of its contents and an intentional checksum update.

BitBake extracts the Debian data archives and creates ordinary Yocto RPM
packages. No `apt`, target-side `dpkg`, DKMS or Debian maintainer script is
needed. The original `.deb` archives are build inputs, not files copied into
the target image.

* `hailort` installs the prebuilt AArch64/glibc shared library and optional
  service. Headers, the linker symlink and CMake metadata enter its development
  package/sysroot for cross-building the camera application. `hailort-cli` and
  `hailort-gstreamer` install the CLI and plugin; the plugin moves from Debian's
  multiarch directory into Yocto's `${libdir}/gstreamer-1.0`.
* The vendor service is installed but disabled by default because the camera
  uses direct device access. Enable it explicitly only for applications
  configured for HailoRT's multi-process service.
* `hailo-pci` cross-builds the driver sources contained in the `all.deb`
  against the image's Yocto kernel. The archive does not contain a prebuilt
  `.ko`. The driver loads automatically; the existing root/video `0660` udev
  policy is retained instead of the vendor's broad device permissions.
* `hailo-firmware` takes the matching chip firmware and EULA from the same
  PCIe archive, installing `hailo8_fw.bin` under `${nonarch_base_libdir}/firmware/hailo`
  (`/usr/lib/firmware/hailo` with usrmerge).

Inside the configured Hailo kas shell, validate these packages independently
before building the image:

```bash
bitbake hailort hailo-pci hailo-firmware
```

This checks packaging and builds the kernel module; it does not establish
physical-device detection or working inference.

## Local Hailo model

The Hailo camera profile also selects `camera-firmware-models`. Its private
input defaults to
`rpi-cam-hailo/vendor/models/yolo_model.hef` from the project root and may be
overridden for both direct Kas and wrapper builds:

```bash
export CAMERA_FIRMWARE_MODEL_DIR=/absolute/path/to/reviewed-model-directory
```

The standard camera profile does not depend on the model package and remains
usable when this input is absent. A Hailo build fails clearly if the selected
input is missing or differs from the reviewed SHA-256
`eebaf6e491f8c182c095d2a2fd38d8fc6efbc55d595be1bbec75338f55751917`.
On an intentional model update, first establish its provenance, redistribution
rights and target compatibility, then calculate `sha256sum yolo_model.hef` and
update `CF_MODEL_SHA256` in
`meta-rpi-cam-hailo/recipes-camera/camera-firmware-models/camera-firmware-models_1.0.bb`
to that independently reviewed value. Never commit the HEF. The packaged path
is `/usr/share/camera-firmware/models/yolo_model.hef`; the package is declared
`CLOSED`, which grants no redistribution rights. No pose model is packaged.
This object-detection HEF was verified with Hailo-8 and HailoRT 4.24.0 on
2026-10-11: the authenticated dashboard reported `hailo / ready`, advancing
frame sequence numbers, and object labels with confidence scores. These are
functional inference results; they do not establish sustained throughput or
long-run stability, and must be rechecked after changing the image or model.

## Build and acceptance

Camera images can be built before QEMU or Raspberry Pi acceptance. For changed
image inputs, create a new build ID and select one camera variant. Resume an
existing ID only with unchanged captured inputs:

```bash
BUILD_ID="$(./scripts/new-build-id.sh)"
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera parse
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera build
# Or select Hailo-8 support:
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo parse
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo build
```

For routine Hailo development, connect the registered SSD and run
`./scripts/install-ssd.sh --check`, then `./scripts/install-ssd.sh`; the latter
writes the latest completed Hailo image and provisions it. See the
[SSD runbook](usb-ssd-bringup.md#automatic-development-installation) for image
selection and target checks. This path does not build or run QEMU.

The lower-level release/acceptance path uses the selected `--profile`:
Keep one unchanged revision/build ID for the subsequent acceptance sequence.
`flash-ssd.sh` requires phase-1 hardware acceptance by default for both camera
variants. QEMU validation is independent and optional. Development flashing may explicitly use
`--allow-unvalidated-hardware` before phase-1 acceptance, as described in the
SSD runbook. Pass `--profile rpi5-camera-hailo` to `test-camera.sh` for the Hailo
image; it stores capture evidence separately under `camera-hailo-test/`.
Default camera evidence and Hailo capture evidence cannot substitute for each
other. The optional release summary uses the same `--profile` value and records
that Hailo inference has not been tested; see the [evidence schema](../evidence-schema.md).
The root filesystem records the variant in `/etc/rpi5-camera-profile`;
acceptance verifies it before and after reboot, even when both variants share
the same project build ID.

These camera acceptance scripts operate `rpicam-*` directly. Provision/start
the application after capture acceptance, or stop the service before exclusive
camera tests. App streaming, setup/authentication, settings recovery, integrity
failures and Hailo inference are additional device acceptance checks.

## Device provisioning

Camera builds and the existing SSD installer now perform the offline preparation.
The first boot starts the HTTPS setup UI; the operator registers the permanent
administrator once in that UI. The app creates the corresponding RTSP Digest
credential itself. No common administrator password is put into the image.

1. `scripts/build.sh` prepares an Ed25519 signing identity once under
   Git-ignored `keys/camera-firmware/`. For direct kas use, first run:

   ```bash
   python3 scripts/lib/camera_identity.py prepare --repo "$PWD"
   ```

   `integrity-private.pem` stays on the build PC with mode `0600` in a `0700`
   directory. Back it up privately; losing it prevents provisioning images
   built with its matching public key. The recipe fetches **only**
   `integrity-public.pem`, embeds it in the executable and installs a public
   copy under `/usr/share/camera-firmware/`. A deployment can override the
   public input with `CF_INTEGRITY_PUBLIC_KEY_INPUT` in a bbappend.
2. Leave `public_host` in `keys/camera-firmware/device.json` as `null` for DHCP
   and direct Ethernet/Wi-Fi access. The app checks the browser's HTTPS origin
   against the actual server socket IP and port; it does not trust `Host` or
   forwarded headers to authorize an arbitrary origin. Set a stable IP or DNS
   name only when an additional explicit public URL is needed. Keep this file
   mode `0600`. An explicit value contains no scheme, port, path or wildcard.
   Changing this value before SSD installation does not require a rebuild;
   changing the embedded signing public key does.
3. Build the selected camera image and run `./scripts/install-ssd.sh` as usual.
   The installer compares the local key with the selected image's exported,
   checksummed public key **before erasing** the registered SSD. Old images
   without this public-key artifact are rejected. Low-level `flash-ssd.sh`
   offers `--skip-camera-provision` for deliberately inactive recovery images.
4. After writing the image, the installer mounts it and generates a distinct
   P-256 TLS key/certificate and 30-byte SRTP session key for this installation.
   The certificate is self-signed, valid for 365 days. An explicit `public_host`
   is its IP/DNS subject alternative name; automatic-address installs use
   `camera.local` as a bootstrap device identity. No DNS/mDNS service is implied.
   Direct IP access in that mode has both trust and certificate-name warnings;
   this change does not make the bootstrap certificate publicly trusted or
   automatically renew it. For strict certificate validation across DHCP
   changes, provision a stable DNS name and a trusted matching certificate.
5. The installer hashes the actual SSD executable, final configuration and
   `/boot/kernel_2712.img`, then signs the manifest on the PC with Ed25519.
   It installs TLS/SRTP material with the service account's ownership, publishes
   `/etc/camera-firmware/app.yaml` last, remounts read-only and verifies all
   material. The private signing key never enters the SSD, image or BitBake
   cache. Flash evidence records `camera_provisioned: true` only after success.
6. On first boot, systemd waits for `/boot` and starts `camera-firmware.service`.
   The service orders after `network.target` for shutdown coordination; it does
   not wait for `network-online.target`. HTTPS/RTSPS bind wildcard addresses and
   become reachable when a network interface acquires an address. Earlier units
   waited approximately 120 seconds for unplugged Ethernet even when Wi-Fi was
   already usable. Source updates affect the next image build; a libcamera-only
   SSD repair does not replace the installed service unit.
   Open `https://<current-Pi-IP>:8443` (or the configured DNS name), use the
   initial account shown by the app and finish the administrator/setup flow.
   New setup defaults management IP restrictions off: credentials and account
   roles remain mandatory. Enable the optional IP restriction only when wanted;
   existing initialized databases retain their previous restriction on upgrade.
   The displayed setup IP is the connecting PC's address, not an address to
   assign to the Pi. It is checked for the setup session and saved for optional
   restrictions; the allow-list does not block access while restrictions are off.
   Users → Access IPs lets an administrator change the policy with fresh
   authentication. Changes end existing sessions and refuse to enable a policy
   that would exclude the current administrator. A login session stays bound to
   its client's IP even with restrictions off. If that client changes address,
   sign in again. If the setup wizard reports an expired session, sign in again
   using the refreshed initial account and re-enter the administrator details.
   Verify UI/live video and RTSPS on
   port 8555. Hardware inference and performance remain separate acceptance
   checks; an enabled service does not prove camera/Hailo acceptance.

The generic WIC contains the secure example and public key, not active device
configuration or TLS/SRTP secrets. Directly writing it with another tool leaves
the service inactive because of `ConditionPathExists`. Normal SSD installation
supplies that configuration automatically. Reboot preserves app state; repeating
provisioning on an unchanged mounted installation verifies and preserves existing
keys. Reflashing replaces the filesystem and starts setup again.

The application runs as `camera-firmware` with video/render access and mode-0700
runtime state. `rpiadmin` does not receive arbitrary root write permissions.
Changes to the binary, base YAML or boot kernel require a fresh offline manifest
and signature. Updating mutable settings through the app uses its existing
settings store and does not require manually editing the signed base YAML.

## Distribution review

The application source has no license grant, so it is packaged as `CLOSED`
alongside declarations/notices for bundled third-party components. This does
not grant redistribution rights. The existing H.264 licensing gate still
applies; Hailo chip firmware carries its own license included in the package.

## Published network examples

Use documentation-only addresses in reports, examples, tests and patch
fixtures. Keep real site configuration in ignored local inputs. The
[privacy cleanup](../../rpi-cam-hailo/docs/security/privacy-cleanup-2026-10-16.md)
rewrote the affected history; the current source pin is the sanitized
counterpart of the original base. Existing production sources and patch order
are preserved. Older embedded development clones must not reintroduce the
original history when pushing changes.

The existing Pi checkout and the build PC's earlier validation/source clones
and Git download caches were refreshed on 2026-10-16. The Pi keeps the
sanitized recipe base and its seven applied patches; its installed application
and settings are unchanged. The unrelated linked worktree's local changes
were preserved. Existing private images and packages remain historical:
reinstalling an older image restores its older embedded checkout, which must
be refreshed before publication. Later builds use the sanitized source pin
and a fresh build ID. GitHub Support purge was excluded at the user's request;
see the linked privacy record for the retained server-object boundary.
