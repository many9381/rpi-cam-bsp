# USB SSD Build and Flash

This is **Hands-on SSD session 1 of 2**. Disconnect unrelated removable drives
first. Never infer the target from `/dev/sdX` ordering, never invoke the `dd`
command, and stop on any identity mismatch.

The flashing tool independently rejects the host root/swap disks, partitions,
mounted targets, non-USB transport, undersized media, mismatched checksums,
missing gates, and an inexact confirmation string.

## Automatic development installation

After an image build, connect the registered SSD to the build PC and run:

```bash
./scripts/install-ssd.sh
```

This replaces the registered SSD's existing contents with the latest completed
`rpi5-camera-hailo` image. The command stays the same after every build; there
is no per-build launcher to edit. Run it as the normal build user, without
`sudo`; it requests administrator authentication only for disk installation.

The installer selects the newest build ID with that profile's `COMPLETE`
marker and verifies its metadata, image and bmap checksums. It does not use a
potentially stale `.state/active-build-id`. An incomplete build is ignored;
a broken completed build fails instead of silently selecting an older one.
Use `--build-id ID` to select a specific completed build or `--profile
rpi5-camera` / `--profile rpi5-minimal` to select another Raspberry Pi image.

The target is registered once in Git-ignored `keys/ssd-target.json`, containing
the `vendor`, `model`, `serial` strings and integer `size_bytes` reported by:

```bash
lsblk --bytes --paths -d -o PATH,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL
```

The installer matches the registration against connected USB disks, so a
change from `/dev/sdb` to `/dev/sdc` is handled automatically. Missing or
ambiguous matches, a read-only disk, and a target backing a protected host
filesystem stop installation. The exact device fingerprint is passed to the
writer and checked again immediately before writing. To use a different SSD,
update the registration deliberately; do not register a host system disk.

Installation uses the completed Pi image directly and does not build or run
QEMU. QEMU validation is optional and is invoked separately through
`build.sh ... qemu build` and `test-qemu.sh`. The checksum-pinned uv archive
is downloaded if absent. The
existing `flash-ssd.sh` then unmounts target partitions, writes with bmaptool,
mounts the new boot/root filesystems to verify them, restores and verifies
Codex credentials for camera images, provisions and verifies the camera app,
flushes writes and unmounts everything. The camera signing identity and public
address are kept in Git-ignored `keys/camera-firmware/`; camera builds prepare
them automatically. The installer checks the selected image's public key
against that identity before erasing the SSD. See
[camera provisioning](camera-firmware.md#device-provisioning) for the first-boot
web setup and certificate trust. Older images without an exported public key
need rebuilding for automatic app provisioning.

Camera provisioning also seeds `/var/lib/systemd/timesync/clock` on the SSD
after generating its HTTPS certificate. The saved timestamp is the install
PC's current UTC time, at least one second after the certificate's validity
start; a newer saved timestamp is preserved. Ownership uses the image's
`systemd-timesync` account. The installer verifies the timestamp and file
permissions again after remounting the SSD read-only.

The camera service starts after `time-set.target`, when systemd-timesyncd has
restored this local time floor. It does not wait for an Internet/NTP response.
TLS validity checks remain enabled, and normal NTP synchronization continues
when connectivity is available. This floor is not proof of accurate current
time: keep the install PC's clock correct, and do not treat it as a substitute
for NTP or a working RTC after long storage. The service ordering change
requires the rebuilt image; updating only the installer does not update an
already running Pi.

Wait for `PASS flash ... safe to disconnect` before moving the SSD to the Pi.
Personal credentials are written only onto the SSD, with Git and the image
remaining free of them. Installation evidence is readable by the invoking
user under `artifacts/<build-id>/flash/`.

To fix only camera port selection on an already installed camera SSD, use:

```bash
./scripts/install-ssd.sh --repair-camera-boot --check
./scripts/install-ssd.sh --repair-camera-boot
```

This mode uses the same registered-SSD identity and protected-host-disk checks.
It does not select an image, reflash, restore credentials, or mount the root
partition. It mounts partition 1, verifies the project's Pi 5 USB boot files,
backs up `config.txt` as `config.txt.before-camera-autodetect`, removes the
forced IMX708 overlay, and enables `camera_auto_detect=1`. Other boot settings
are preserved. It checks the result read-only and unmounts before reporting
`PASS camera boot repair ... safe to disconnect`. Repeating it is harmless.
Custom conditional/include configurations and custom IMX708 parameters are
rejected for manual review. `--check` validates disk selection without mounting;
the boot contents are checked during the actual repair. Run as the normal user;
sudo is requested for mounting and writing only the boot configuration.

For an installed libcamera 0.6 image whose IMX708 sensor probes but whose
userspace cannot acquire the downstream CFE, use the validated runtime repair:

```bash
./scripts/install-ssd.sh --repair-camera-runtime --check
./scripts/install-ssd.sh --repair-camera-runtime
```

This includes the boot repair above and replaces only libcamera libraries,
IPA modules, proxies and tuning data from the local, Git-ignored
`.state/camera-runtime-repair` payload. The payload is prepared from the
Raspberry Pi `0.6.0+rpt20251202` package tested on the Pi. Missing or altered
payloads fail closed; this mode never falls back to flashing an image.
`readelf` (host `binutils`) checks AArch64 and the 0.6 SONAME in both installed
libraries and replacements. Existing SONAME links and the camera image
profile must match before writes. `--check` verifies payload and device
selection without mounting; installed-file checks happen during repair.

The root partition is inspected read-only, mounted for the limited update,
and remounted read-only for verification. Original files and their hashes
are backed up under `/var/backups/rpi5-camera-runtime/` on the SSD. Writes
are atomic per file; a write error or SIGINT/SIGTERM restores originals by
rename, including when replacement fails for lack of space. Any incomplete
rollback reports the affected paths and retained backup for recovery.
This is not a power-loss-atomic filesystem transaction. Failed unmounts
preserve the mount tree instead of deleting its contents.

Accounts, TLS, signed app configuration, the app binary and Codex credentials
are outside the update paths. Wait for `PASS camera runtime repair ... safe
to disconnect`, move the SSD back to the Pi, and check normal camera
enumeration and the web runtime after boot. This targeted repair keeps the
installed image build ID and RPM database unchanged; it records the update
in its backup manifest. Future complete image installations include the
fixed library through the layer recipe and report its package version.

This is the development workflow: missing phase-1 hardware acceptance is
recorded as bypassed. QEMU evidence is not a prerequisite. An existing
successful installation record for the selected build/profile stops a repeat
write. It does not erase that evidence or claim hardware acceptance.

For a read-only preflight without builds, downloads, mounts or SSD writes:

```bash
./scripts/install-ssd.sh --check
```

The lower-level commands below remain available for explicit manual control.

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

For a development camera image without phase-1 hardware evidence, explicitly
add `--allow-unvalidated-hardware` to the flash command and select
`rpi5-camera` or `rpi5-camera-hailo`. The selected image's COMPLETE remains
required; QEMU validation is optional. This exception is recorded as `hardware_gate_bypassed: true`
in the flash JSON; it does not create hardware acceptance evidence. Run the
command with `sudo` in your own terminal if administrator authentication is
required.

Camera installations also restore the sudo caller's current Codex login onto
the SSD automatically. The host's `~/.codex/auth.json` must be a private
`0600` file owned by that user; it is checked before erasing the SSD. After
writing and verifying the image, the installer adds the credentials only to
the SSD, then remounts read-only to verify them before flash PASS. The image,
build caches and Git remain free of Codex credentials. The flash JSON records
`codex_auth_restored: true` without any token values.

For a custom host credential path, add
`--codex-auth-file /absolute/path/auth.json`. To install a camera SSD without
personal credentials, explicitly use `--skip-codex-auth`. Minimal images do
not read or restore Codex credentials. See [Codex authentication](codex.md)
for details and the SSH restore method for an already running Pi.

With Raspberry Pi power removed, fit the physically labeled Camera Module 3
Wide and CSI cable, move the flashed SSD to the Pi, connect wired Ethernet,
then connect a stable 5 V/5 A supply. Leave HDMI disconnected initially.

Continue with [remote Raspberry Pi validation](remote-validation.md).

## Raspberry Pi 5 fan control

All Raspberry Pi image variants explicitly install `kernel-module-pwm-fan`
for a fan connected to the board's 4-pin FAN connector. The pinned kernel
builds `CONFIG_SENSORS_PWM_FAN=m` and `CONFIG_PWM_RP1=y`. The firmware enables
the detected fan in the device tree; udev loads the matching module, and the
kernel thermal governor controls its speed. No separate fan daemon or fixed
PWM setting is needed for this connection.

The pinned Pi 5 device tree uses active trip points of 50, 60, 67.5 and 75°C,
each with 5°C hysteresis. See the [Raspberry Pi cooling documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#cooling-raspberry-pi-5).
Fans powered directly from GPIO 5V/GND need their own control hardware;
this module controls the board's PWM fan connection.

Earlier images omitted this module even though the kernel built it. They use
`packagegroup-core-boot`, which does not consume the BSP's
`MACHINE_EXTRA_RRECOMMENDS` through `packagegroup-machine-base`. A detected
fan could therefore keep running without any registered cooling device.
Installing `kernel-module-pwm-fan` explicitly avoids pulling in every kernel
module and applies to minimal, camera and Hailo camera images, but not QEMU.

After booting the updated image, check as `rpiadmin`:

```sh
cat /sys/class/thermal/thermal_zone0/temp
readlink /sys/bus/platform/devices/cooling_fan/driver
for device in /sys/class/thermal/cooling_device*; do
    [ -f "$device/type" ] || continue
    cat "$device/type" "$device/cur_state" "$device/max_state"
done
for monitor in /sys/class/hwmon/hwmon*; do
    [ "$(cat "$monitor/name")" = "pwmfan" ] || continue
    cat "$monitor/pwm1" "$monitor/fan1_input"
done
```

The fan driver link should resolve to `pwm-fan`, with a `pwm-fan` cooling
device and a `pwmfan` hardware monitor. A cold, idle Pi may have zero PWM and
RPM; the temperature governor should increase cooling as the trip points
are crossed. If the fan device exists but the driver link does not, use
`modprobe -n -v pwm-fan` to check module availability without loading it.

## USB SSD boot mount

The Raspberry Pi profiles use `usb-ssd-raspberrypi.wks` from
`meta-rpi5-cam/files/wic/`. Its `--ondisk sda` settings make Wic generate
`/dev/sda1 /boot vfat` in the final image, matching the kernel command line's
`root=/dev/sda2`. `BOOT_MEDIA = "usb"` alone does not change Wic's fstab output.
The flash verification checks the final root filesystem's `/boot` entry.

An older image using `sdimage-raspberrypi.wks` can mount its USB root filesystem
but wait for `/dev/mmcblk0p1` at `/boot`, then enter emergency mode after about
90 seconds. Wired DHCP can work in that state while SSH remains unavailable.
Check the persistent journal and the **final Wic image's** `/etc/fstab`;
the recipe's pre-Wic rootfs does not contain the added mount entry.
