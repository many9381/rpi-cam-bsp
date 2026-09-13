# Camera application packaging and provisioning

The Yocto camera image includes the firmware implemented in the separate
`many9381/rpi-cam-hailo` repository. Work from the Yocto implementation checkout
(in this workspace, `.worktrees/yocto-implementation`). Keep the reference
`rpi-cam-hailo/` directory out of Git; it is not a submodule or a vendored tree.

## Package composition

| Package | Purpose |
|---|---|
| `camera-firmware` | C++20 executable, integrity/digest helper CLIs, custom SRTP plugin, service and configuration example |
| `camera-firmware-web` | Prebuilt React UI under `/usr/share/camera-firmware/web` |
| `packagegroup-camera-firmware` | Application and Codex operator tools, included by `rpi5-camera-image` |
| `packagegroup-camera-firmware-hailo` | Optional HailoRT library/CLI, matching PCIe driver and chip firmware |

The recipes reuse `libcamera`, `gstreamer1.0`, `gstreamer1.0-plugins-base`,
`gstreamer1.0-rtsp-server`, `libsrtp`, `x264`, `rpidistro-ffmpeg`, `openssl`,
`sqlite3`, `yaml-cpp`, `jsoncpp`, `jpeg`, and the existing toolchain. Runtime
dependencies include GStreamer's app, H.264 parser, MP4 muxer, UDP, SRTP,
RTP and RTP manager plugins and the GIO TLS implementation. The camera profile
enables the stock SRTP plugin for the RTSP server's incoming RTCP decoder;
the application still uses its custom secure encoder. The main C++ program serves the web
assets itself; Node.js is a build-host dependency only.

The pinned BSP's libcamera 0.6.0 provider is retained with the Raspberry Pi
PiSP pipeline. Its inspected APIs include those used by the application;
the application's Raspberry Pi OS README lists 0.7. Target compilation and
IMX708 operation still require validation against this Yocto baseline.

## Immutable application sources

| Source | Revision |
|---|---|
| Camera application | `ba503a1fbc4ed68c1fd29aace7214a5c330d7021` |
| Drogon 1.9.0 | `f215cb15a0f53abd0ca7ee8b95ed8c9c3b40d262` |
| Trantor 1.5.20 | `79e1ffc59aa1b9c8226c2988fe2e1185e97cd795` |
| HailoRT 4.24.0 | `63adffec12da88f1e7cfdc07f2e07681671e83e8` |
| Hailo PCIe 4.24.0 | `2789e0ff8b75ffdbaf8f7235f55aef3c06a2ed24` |

The application defaults to the same GitHub SSH origin as the reference
checkout. The build user needs read access. Both camera profiles forward an
optional transport override, including when using the gated build wrapper:

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

The CMake integration patch only affects the fetched build tree. It separates
the web build, selects Hailo explicitly, adds installation targets and supplies
the installed GStreamer plugin directory. The upstream exact Git HEAD/tree
checks and four Drogon/Trantor hardening patches remain active.

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
  > meta-rpi5-cam/recipes-camera/camera-firmware/camera-firmware-npm.inc
uv run --locked python scripts/firmware_npm_lock.py \
  /absolute/path/to/rpi-cam-hailo/web/package-lock.json \
  --check meta-rpi5-cam/recipes-camera/camera-firmware/camera-firmware-npm.inc
```

Also review the bundled runtime dependency licenses and regenerate
`files/web-third-party-notices.txt` from their exact archive contents when
updating the lock. Its checksum is declared in the web recipe, and the file is
installed under `/usr/share/camera-firmware/licenses/` alongside the app notices.

Hailo recipes likewise fetch their exact third-party sources before configure.
A private `hailo-protobuf-native` package builds the matching host protoc;
target protobuf code and the native generator never share an architecture.
The PCIe module is built against the Yocto kernel, and the matching chip
firmware is installed as `/usr/lib/firmware/hailo/hailo8_fw.bin` on usrmerge.
HEF models are not bundled. The device node is restricted to root/video.

## Build and acceptance

Keep the existing one-revision/build-ID sequence: complete QEMU and phase-1
Raspberry Pi acceptance first. Select one camera variant:

```bash
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera parse
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera build
# Or select Hailo-8 support:
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo parse
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo build
```

Use the [SSD runbook](usb-ssd-bringup.md) with the selected `--profile`.
`flash-ssd.sh` requires the same QEMU and phase-1 hardware gates for both camera
variants. Pass `--profile rpi5-camera-hailo` to `test-camera.sh` for the Hailo
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

The installed service is enabled but has
`ConditionPathExists=/etc/camera-firmware/app.yaml`. An image with only the
example configuration keeps the service inactive. It does not run the upstream
development configuration with security disabled.

Provision the device through an authorized manufacturing/offline root context
or a deployment recipe. The base image's diagnostic `rpiadmin` sudo policy does
not grant arbitrary writes under `/etc`.

1. Embed the deployment Ed25519 public key at build time using a bbappend:

   ```bitbake
   FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
   SRC_URI += "file://integrity-public-key.pem"
   CF_INTEGRITY_PUBLIC_KEY_FILE = "${UNPACKDIR}/integrity-public-key.pem"
   ```

   The reference development public key is the recipe's explicit default for
   provisioning-only images. Its private key is not in this repository.
   Installing another public key on the device cannot change the embedded key.
2. Use `/etc/camera-firmware/app.yaml.example` as the schema reference and set
   the real HTTPS browser origin and device paths. Install the final YAML as
   `root:camera-firmware`, mode `0640`.
3. Provision per-device TLS material. Both certificate and private key must be
   regular, non-hard-linked files owned by the `camera-firmware` service UID.
   Use certificate mode `0644` and private-key mode `0600`; merely granting
   group-read permission on a root-owned private key fails upstream validation.
4. Provision SRTP key material, digest credentials using `rtsp-digest-credential`,
   and any reviewed Hailo HEF files/catalog. Keep secret files readable only by
   the service account. The runtime state directory is
   `/var/lib/camera-firmware/security`.
5. Use `camera-firmware-integrity` to create a manifest covering the installed
   executable, final YAML and actual boot kernel image. Sign it off-device with
   the private key matching the embedded public key, then install manifest and
   signature at the configured paths. Re-sign after changing those artifacts.
6. Start `camera-firmware.service` and complete the application's setup flow.
   Verify HTTPS on 8443, the UI/live stream and authenticated RTSPS on 8555.
   With Hailo hardware, also inspect the driver/device and use `hailortcli` with
   the deployed model to validate inference before enabling it in the YAML.

The application runs as `camera-firmware` with video/render access; systemd owns
its mode-0700 state directory. No private signing key, static shared SRTP key,
HEF model or per-device TLS secret is included in the source recipes.

## Distribution review

The application source has no license grant, so it is packaged as `CLOSED`
alongside declarations/notices for bundled third-party components. This does
not grant redistribution rights. The existing H.264 licensing gate still
applies; Hailo chip firmware carries its own license included in the package.
