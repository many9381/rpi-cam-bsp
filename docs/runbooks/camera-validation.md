# Camera Module 3 Wide Validation

Phase-1 hardware PASS must exist for the same build ID. Keep the validated
minimal system powered while the x86 host builds the camera image.

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
```

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
1920x1080 30 fps H.264 stream encoded through libav/libx264, matching transfer
hashes, temperature below 85 C, and another JPEG after one reboot. Software
identifies IMX708; the operator confirms the Wide lens from the physical label.

Before any image leaves internal development, apply the
[H.264 licensing gate](../licensing/camera-h264.md). Store results according to
the [evidence schema](../evidence-schema.md).
