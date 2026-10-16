# Raspberry Pi 5 Camera Firmware

This repository cross-builds a pinned Yocto 6.0 (`wrynose`) firmware on an
x86_64 Ubuntu 24.04 host. The supported target is a Raspberry Pi 5 booting
from a USB SSD with Camera Module 3 Wide (IMX708), headless autofocus still
capture, and software H.264 encoding.

The camera image also packages the separately maintained `rpi-cam-hailo`
C++20 application, its React web assets and secure streaming dependencies.
Platform and hardware support live in `meta-rpi5-cam/`; the visible
`meta-rpi-cam-hailo/` layer owns the application, web, secure examples and
optional local model packaging. The C++ application is cross-built for
AArch64, while the static web and model packages are CPU-independent.
`kas/rpi5-camera-hailo.yml` adds Hailo-8 support and requires the local HailoRT
4.24.0 Debian packages plus a checksum-pinned HEF; the standard camera profile
does not select them. The Debian inputs live in the platform layer's recipe
`files/` directories and are Git-ignored. The source
checkout and model are ignored by Git, and recipes retain immutable pins. See the
[firmware integration runbook](docs/runbooks/camera-firmware.md) for source
access, model selection, offline web builds and automatic SSD provisioning.
Camera builds prepare a local signing identity; SSD installation adds device
TLS/SRTP material and a signed configuration so the app starts on first boot.
Complete the administrator setup once at `https://<current-Pi-IP>:8443/`.
The default `public_host: null` installation accepts direct HTTPS access at
the Pi's current Ethernet/Wi-Fi address, so a future DHCP address need not be
registered in advance. New web setup leaves management IP restrictions off;
the optional allow-list contains client addresses, not the Pi's address.
Bootstrap certificate trust/name limitations and optional restrictions are
explained in [device provisioning](docs/runbooks/camera-firmware.md#device-provisioning).
See [current validation and dependency records](docs/runbooks/camera-firmware.md#current-validated-image-and-dependency-records)
for the accepted image and its package/SPDX evidence.

Both camera variants also include the latest stable Codex CLI and its sandbox/search
tools for interactive use over SSH. When installing a camera image,
`scripts/flash-ssd.sh` automatically restores the invoking user's current Codex
login onto the SSD after image writing. Credentials stay outside the image,
build caches and Git. A valid host login is required before erasing the SSD;
`--skip-codex-auth` explicitly installs without personal credentials. For an
already running Pi, `scripts/provision-codex-auth.sh` restores the login over
SSH. See [Codex on the camera](docs/runbooks/codex.md).

Camera images also include an editable Git checkout at
`/home/rpiadmin/rpi-cam-hailo`, owned by `rpiadmin` and pinned to the packaged
application revision. Set `RPI_CAM_HAILO_DEV_REPO=0` when building to omit this
separate development package. See [development checkout](docs/runbooks/camera-firmware.md#optional-development-repository-in-rpiadmins-home).

All Raspberry Pi images support optional Wi-Fi automatic connection using a
Git-ignored local configuration. See [Wi-Fi provisioning](docs/runbooks/wifi.md)
before building: provisioned images contain the Wi-Fi key and must stay private.
QEMU remains wired-only.

## Working directory

Work from this repository root. The checked-in layers (`meta-rpi5-cam/` and
`meta-rpi-cam-hailo/`), kas profiles (`kas/`), scripts and tests are real files
here, not links into a hidden worktree. Create branches in this checkout; do
not create or switch to another worktree for ongoing development unless
explicitly requested.

The previous `.worktrees/yocto-implementation` checkout is retained only for
its existing build outputs and acceptance evidence. Do not copy its PASS
markers into a new build or treat them as validation of changed recipes.
The local single-build SSD launcher remains pinned to that historical build;
it is not a launcher for newly generated root-checkout images.

Git-excluded local compiler-validation recipes remain local-only. Remove
those overrides before a release build. Private SSH/Wi-Fi inputs belong in
the ignored `keys/` directory and must never be staged.

## Supported route

Image generation can run independently of runtime acceptance:

```bash
./scripts/build.sh rpi5-camera-hailo build
```

This uses `.state/active-build-id`; for a new run, create an ID with
`scripts/new-build-id.sh` and pass `--build-id "$BUILD_ID"` explicitly.
`build.sh` checks the host and builds the selected profile without requiring
QEMU or hardware PASS records. Flashing and acceptance have separate checks.

After building, install the latest completed Hailo camera image onto the
registered USB SSD with the same command every time:

```bash
./scripts/install-ssd.sh
```

Run as the normal build user; the script requests sudo only for disk writing.
It identifies the SSD using `keys/ssd-target.json`, unmounts and writes the
SSD, and verifies its mounted filesystems,
restores the current Codex login, then unmounts it. `--check` runs read-only
preflight. Installation never builds or runs QEMU; QEMU validation is optional
and must be invoked separately. See [automatic development installation](docs/runbooks/usb-ssd-bringup.md#automatic-development-installation).

The formal release acceptance route below includes a minimal-image stage.
Routine integrated Hailo development builds and installations do not require
repeating that stage or building QEMU. Keep validation evidence tied to the
actual image build ID; earlier Pi results do not validate a newly built image.

Use one unchanged Git revision and build ID for the complete release acceptance run:

1. Prepare the host. Run the optional QEMU check only when wanted.
2. Build and safely flash the minimal Raspberry Pi image.
3. Pass USB-boot, network, SSH, and three-reboot acceptance.
4. Build and safely flash the camera image.
5. Pass IMX708, JPEG, H.264, thermal, transfer, and reboot acceptance.

That release route has two planned hands-on SSD sessions: the initial minimal
image flash/assembly and the later camera image reflash. The current development
baseline has passed physical camera and Hailo inference checks; each final
integrated image still needs its own installation and hardware acceptance.

Follow these documents in order:

1. [Build setup and optional QEMU validation](docs/runbooks/build-qemu.md)
2. [USB SSD build and flash](docs/runbooks/usb-ssd-bringup.md)
3. [Remote Raspberry Pi validation](docs/runbooks/remote-validation.md)
4. [Camera Module 3 Wide validation](docs/runbooks/camera-validation.md)
5. [Camera firmware provisioning and streaming](docs/runbooks/camera-firmware.md)

[EEPROM recovery](docs/runbooks/eeprom-recovery.md) is an exception path, not
part of normal boot. Before publishing any camera image, apply the
[H.264 licensing gate](docs/licensing/camera-h264.md). Evidence handling is
defined by the [evidence schema](docs/evidence-schema.md).

## Git policy

`develop` is the integration branch. Start each independently testable unit
from current `develop` as `feature/SCOPE`, commit at functional boundaries,
and write every commit message in English with a Conventional Commit subject.
`master` receives only a fully accepted and explicitly approved release
baseline.

Generated builds, private/public login keys, images, raw evidence, IP
addresses, and device identifiers are never committed. Only the sanitized JSON
record allowed by the evidence schema is eligible for Git.
