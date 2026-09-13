# Raspberry Pi 5 Camera Firmware

This repository cross-builds a pinned Yocto 6.0 (`wrynose`) firmware on an
x86_64 Ubuntu 24.04 host. The supported target is a Raspberry Pi 5 booting
from a USB SSD with Camera Module 3 Wide (IMX708), headless autofocus still
capture, and software H.264 encoding.

The camera image also packages the separately maintained `rpi-cam-hailo`
C++20 application, its React web assets and secure streaming dependencies.
`kas/rpi5-camera-hailo.yml` adds Hailo-8 support. The source checkout is ignored
by Git; recipes fetch an immutable application revision. See the
[firmware integration runbook](docs/runbooks/camera-firmware.md) for source
access, offline web builds and device provisioning before service startup.

## Supported route

Use one unchanged Git revision and build ID for the complete acceptance run:

1. Prepare the host and pass the QEMU build/runtime gate.
2. Build and safely flash the minimal Raspberry Pi image.
3. Pass USB-boot, network, SSH, and three-reboot acceptance.
4. Build and safely flash the camera image.
5. Pass IMX708, JPEG, H.264, thermal, transfer, and reboot acceptance.

The route has exactly two planned hands-on SSD sessions: the initial minimal
image flash/assembly and the later camera image reflash. Physical camera
validation remains deferred until the final integrated acceptance run.

Follow these documents in order:

1. [Build and QEMU gate](docs/runbooks/build-qemu.md)
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
