# Camera Module 3 Wide Validation

## Development runtime check after boot

An active `camera-firmware.service` is insufficient evidence of working capture.
After initial setup, use the common read-only check below, with the expected
image build ID, board serial and an already verified SSH host-key file:

```bash
./scripts/test-camera-runtime.sh \
  --host 198.51.100.60 --profile rpi5-camera-hailo \
  --build-id "$(cat .state/active-build-id)" \
  --serial 5090bb4b8a34a361 \
  --known-hosts .state/pi-known-hosts \
  --output .state/camera-runtime-health.json
```

Use the serial and pinned key of the actual target. This command never refreshes
a changed host key or restarts the service. It requires the same USB root, boot
and application PID across a five-second observation, increasing RP1 CFE and
PiSP interrupt counters, and zero capture timeout/requeue/recovery errors for
that process in the current boot. Missing counters or journal permissions fail
the check. Privileged journals are reduced to an error count on the Pi; raw
journal content is not transferred. Counters are not exact frame counts or FPS.

Run this check after each reboot in development image acceptance, then confirm
browser video and Hailo ready status, increasing processed frames and detection
labels/confidence. It does not produce the formal wired/minimal hardware PASS
below and does not require a QEMU build.

The capture supervisor reports `starting` until the first usable frame. No first
frame within 10 seconds, or no subsequent frame for 5 seconds, stops the runtime
graph and schedules up to three recovery attempts five seconds apart. Management
HTTP remains available. A full minute of healthy capture resets the retry budget;
an explicit runtime start or settings apply also begins a new budget. Exhaustion
leaves an error with manual retry available. Stop/protection restrictions cancel
pending recovery; automatic recovery uses the same protection gate as manual
runtime controls. Timeouts identify a capture failure, not its physical cause.

## Formal camera acceptance

The camera image can be built before phase-1 hardware validation. Standard
flashing and camera acceptance require phase-1 hardware PASS for the same
build ID. An explicit `flash-ssd.sh --allow-unvalidated-hardware` permits
development flashing before that hardware record exists; image COMPLETE and
all device/checksum/write checks still apply. QEMU validation is optional. It records
`hardware_gate_bypassed: true` in the flash metadata and does not create a
hardware PASS. During the acceptance sequence, keep the validated minimal
system powered until the clean poweroff step below.

## Build and inspect the camera image

```bash
BUILD_ID="$(cat .state/active-build-id)"
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera build
CAMERA_MANIFEST=("artifacts/$BUILD_ID/rpi5-camera/manifests/"*.manifest)
test "${#CAMERA_MANIFEST[@]}" -eq 1
grep -Eq '^libcamera-apps ' "${CAMERA_MANIFEST[0]}"
grep -Eq '^rpidistro-ffmpeg ' "${CAMERA_MANIFEST[0]}"
grep -Eq '^x264 ' "${CAMERA_MANIFEST[0]}"
test -f "artifacts/$BUILD_ID/rpi5-camera/COMPLETE"

# Check actual DT driver aliases and module dependencies in the built rootfs.
# Use rpi5-camera-hailo in the path for the Hailo profile.
python3 tests/host/verify_camera_rootfs.py \
  build/kas-work/build/rpi5-camera/tmp/work/raspberrypi5-poky-linux/rpi5-camera-image/1.0/rootfs
```

The camera images explicitly install `rpi5-camera-support`: the downstream
RP1 CFE and PiSP backend, DesignWare I2C controller, IMX708 sensor and DW9807
autofocus modules. Their transitive module dependencies are packaged too.
The Pi 5 DT compatible `raspberrypi,rp1-cfe` requires `rp1-cfe-downstream`
with the pinned 6.18 kernel; the separate `rp1-cfe` module targets the
`raspberrypi,rp1-cfe-upstream` compatible. A camera overlay and libcamera
alone do not install these modules in this minimal image.

The userspace library must also match that downstream driver. The layer pins
Raspberry Pi libcamera `0.6.0+rpt20251202` at commit
`f0e40f1c50bd0afe65727d6e407d0dcb42666ada`, keeping the 0.6 client ABI.
Upstream libcamera 0.6.0 expects different CFE entity names, CSI pads and
routing interfaces. With the downstream kernel it can report
`Unable to acquire a CFE instance` even when the sensor and media devices
probe correctly. The rootfs check verifies downstream CFE names in the actual
packaged library, in addition to kernel modules and permissions. See
[the account-preserving runtime repair](usb-ssd-bringup.md) for an existing SSD.

The camera profiles use `camera_auto_detect=1` and disable the BSP's forced
`dtoverlay=imx708`. On Pi 5, firmware detects the official Camera Module 3 on
either CAM/DISP connector. A manual `dtoverlay=imx708` without `,cam0` only
selects connector 1; a camera on connector 0 then fails sensor probing even
when every driver is installed. See the
[Raspberry Pi camera configuration documentation](https://github.com/raspberrypi/documentation/blob/master/documentation/asciidoc/computers/camera/rpicam_configuration.adoc).
Do not combine the manual sensor overlay with auto-detection. Inspect the
generated `tmp/deploy/images/raspberrypi5/bootfiles/config.txt`, and inspect
`/boot/config.txt` separately on the running Pi: a source change alone does
not update an installed SSD. Third-party modules may need their vendor's
explicit overlay instructions.

`70-rpi5-camera-dma.rules` grants DMA heap access to the existing `video`
group with mode `0660`, so the camera service and `rpiadmin` can allocate
capture buffers. It does not grant world access or change sudo privileges.
On the Pi, `rpicam-hello --list-cameras` should enumerate IMX708 without
`Could not open any dmaHeap device`. Rootfs verification does not establish
physical camera connection, successful capture, or application runtime start.
If the IMX708 chip-ID read fails with `-5` and DW9807 I2C operations fail
with `-121`, the sensor/actuator did not respond on the selected bus. Check
port selection and the ribbon connection before changing web credentials or
adding unrelated packages. Shut down and disconnect power before moving a
camera ribbon. A successful driver package check is not a successful sensor
probe.

Request a clean remote poweroff before touching the SSD:

```bash
RPI_IP="$(./scripts/discover-rpi5.sh --hostname rpi5-minimal --timeout 300)"
ssh-keyscan -T 3 -H "$RPI_IP" > .state/rpi5-poweroff-known-hosts
ssh -i keys/rpi5_admin -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=.state/rpi5-poweroff-known-hosts \
  "rpiadmin@$RPI_IP" sudo -n /usr/bin/systemctl poweroff
```

## Reflash the same SSD

This is **Hands-on SSD session 2 of 2**. After the Pi is fully powered off,
move only the SSD to the x86 host. Re-identify the whole device instead of
reusing an earlier `/dev` name.

```bash
BUILD_ID="$(cat .state/active-build-id)"
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS
read -r -p 'Exact whole USB SSD device: ' TARGET_DEVICE
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS \
  "$TARGET_DEVICE"
read -r -p "Type ERASE:$TARGET_DEVICE:$BUILD_ID: " CONFIRMATION
test "$CONFIRMATION" = "ERASE:$TARGET_DEVICE:$BUILD_ID"
UV_RELEASE_SHA256="8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa78821cf85091b4b"
UV_ARCHIVE="$(pwd -P)/.state/uv-release/uv-x86_64-unknown-linux-gnu.tar.gz"
test -f "$UV_ARCHIVE"
test ! -L "$UV_ARCHIVE"
printf '%s  %s\n' "$UV_RELEASE_SHA256" "$UV_ARCHIVE" |
  sha256sum --check --strict
sudo UV_ARCHIVE="$UV_ARCHIVE" ./scripts/flash-ssd.sh \
  --build-id "$BUILD_ID" --profile rpi5-camera \
  --device "$TARGET_DEVICE" --confirm "$CONFIRMATION"
test -f "artifacts/$BUILD_ID/flash/rpi5-camera-PASS"
```

Reconnect the unchanged camera assembly and newly flashed SSD, reconnect power,
then run camera acceptance:

```bash
BUILD_ID="$(cat .state/active-build-id)"
RPI_IP="$(./scripts/discover-rpi5.sh --hostname rpi5-camera --timeout 300)"
./scripts/test-camera.sh --build-id "$BUILD_ID" --host "$RPI_IP" \
  --wide-label-confirmed
test -f "artifacts/$BUILD_ID/camera-test/PASS"
(cd "artifacts/$BUILD_ID/camera-test/samples" &&
  sha256sum --check SHA256SUMS)
```

Expected: IMX708 enumeration and modes, autofocus JPEG, a retrieved 10-second
1920x1080 30 fps H.264 video in MP4 encoded through libav/libx264, matching transfer
hashes, temperature below 85 C, and another JPEG after one reboot. Software
identifies IMX708; the operator confirms the Wide lens from the physical label.

Root identity is checked before capture and again after reboot. On this Yocto
image, unprivileged `lsblk -no UUID` can return an empty value. The read-only
`scripts/lib/camera_root_identity.sh` probe then resolves the unique existing
`/dev/disk/by-uuid` symlink pointing to the actual mounted root device. Missing,
ambiguous or malformed UUIDs fail the check. The existing USB disk, root
partition, build/profile, SSH identity and unchanged-UUID requirements still
apply. This host-side probe change needs no image rebuild or additional target
sudo privileges. It does not bypass the phase-1 hardware prerequisite above.

Reserve a maintenance window: acceptance interrupts application streaming while
it takes direct sensor captures and reboots the Pi. The camera image must include
`rpi5-camera-support` with its camera-only sudo policy permitting exactly
`sudo -n /usr/bin/systemctl stop camera-firmware.service` and
`sudo -n /usr/bin/systemctl start camera-firmware.service`. The script records
the initial stable `active` or `inactive` state in `service.log`, stops an active
application before capture, and verifies restoration before reboot and before
writing PASS. It handles normal exit and INT, TERM and HUP failures through the
same restoration path. An application initially inactive is never started by
the script; if automatic boot startup activates it, acceptance stops it again.
Do not run acceptance concurrently with another camera client or service
administrator.

`ffprobe.json` records the container and stream metadata plus decoded frame
count; `video-validation.json` records the validated measurements. Acceptance
requires H.264, 1920x1080, MP4 timestamps, both reported rates within 0.5 fps of
30, 285–315 decoded frames, duration 9.5–10.5 seconds, and a frame count consistent
with average rate and duration. Missing or malformed metadata fails acceptance.
The sample is `samples/imx708-wide-1080p30.mp4`; the script never supplies an
assumed input rate to manufacture timestamps from a raw H.264 stream.

Keep SSH access available throughout the run. The first connection establishes
the saved SSH host key; recovery pins that key even if DHCP changes the address,
and rechecks the build ID, profile and root UUID. If the Pi becomes unreachable,
its identity cannot be verified, or restoration fails, acceptance produces no
PASS and requires operator recovery. SIGKILL or loss of the host cannot run an
exit trap; inspect `service.log` and restore the recorded service state after
reconnecting to the verified device.

Before any image leaves internal development, apply the
[H.264 licensing gate](../licensing/camera-h264.md). Store results according to
the [evidence schema](../evidence-schema.md).
