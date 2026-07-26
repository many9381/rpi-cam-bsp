# USB SSD Build and Flash

This is **Hands-on SSD session 1 of 2**. Disconnect unrelated removable drives
first. Never infer the target from `/dev/sdX` ordering, never invoke the `dd`
command, and stop on any identity mismatch.

The flashing tool independently rejects the host root/swap disks, partitions,
mounted targets, non-USB transport, undersized media, mismatched checksums,
missing gates, and an inexact confirmation string.

## Build the minimal image

```bash
BUILD_ID="$(cat .state/active-build-id)"
./scripts/build.sh --build-id "$BUILD_ID" rpi5-minimal build
test -f "artifacts/$BUILD_ID/rpi5-minimal/COMPLETE"
```

## Identify and flash exactly one whole USB SSD

Attach the intended SSD to the x86 host only for this operation:

```bash
BUILD_ID="$(cat .state/active-build-id)"
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS
read -r -p 'Exact whole USB SSD device (for example /dev/sdb): ' TARGET_DEVICE
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS \
  "$TARGET_DEVICE"
read -r -p "Type ERASE:$TARGET_DEVICE:$BUILD_ID: " CONFIRMATION
test "$CONFIRMATION" = "ERASE:$TARGET_DEVICE:$BUILD_ID"

UV_RELEASE_URL="https://releases.astral.sh/github/uv/releases/download/0.11.31/uv-x86_64-unknown-linux-gnu.tar.gz"
UV_RELEASE_SHA256="8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa78821cf85091b4b"
UV_ARCHIVE="$(pwd -P)/.state/uv-release/uv-x86_64-unknown-linux-gnu.tar.gz"
mkdir -p "$(dirname "$UV_ARCHIVE")"
curl --fail --location --proto '=https' --tlsv1.2 \
  "$UV_RELEASE_URL" --output "$UV_ARCHIVE.download"
printf '%s  %s\n' "$UV_RELEASE_SHA256" "$UV_ARCHIVE.download" |
  sha256sum --check --strict
mv -- "$UV_ARCHIVE.download" "$UV_ARCHIVE"
test -f "$UV_ARCHIVE"
test ! -L "$UV_ARCHIVE"
printf '%s  %s\n' "$UV_RELEASE_SHA256" "$UV_ARCHIVE" |
  sha256sum --check --strict

sudo UV_ARCHIVE="$UV_ARCHIVE" ./scripts/flash-ssd.sh \
  --build-id "$BUILD_ID" --profile rpi5-minimal \
  --device "$TARGET_DEVICE" --confirm "$CONFIRMATION"
test -f "artifacts/$BUILD_ID/flash/rpi5-minimal-PASS"
```

A flash PASS means `bmaptool` completed, both partitions appeared, boot files
were inspected read-only, and `/etc/rpi5-build-id` matched on the root
partition.

With Raspberry Pi power removed, fit the physically labeled Camera Module 3
Wide and CSI cable, move the flashed SSD to the Pi, connect wired Ethernet,
then connect a stable 5 V/5 A supply. Leave HDMI disconnected initially.

Continue with [remote Raspberry Pi validation](remote-validation.md).
