# Dedicated camera firmware layer

The user approved extracting the existing firmware/web recipes into a visible
root `meta-rpi-cam-hailo` layer and including the local vendor model on
2026-09-15. This extends the 2026-09-13 integration design: model deployment
is now image packaging, while device secrets remain operator-provisioned.

## Boundaries

Work in the project root on `feature/root-firmware-layers`, never a hidden
worktree. Preserve unrelated dirty files, historical builds and evidence.
Move the existing application recipe directory and application packagegroup
from `meta-rpi5-cam` to `meta-rpi-cam-hailo`, retaining package names, pinned
sources, CMake patch, web lock, licenses, installation paths and service.
Keep images, Wi-Fi, Codex, HailoRT, PCIe and chip firmware in `meta-rpi5-cam`.
Only camera kas profiles enable the new layer. Minimal/QEMU stay independent.

Build C++ firmware with the Yocto AArch64 toolchain, not a copied host binary.
Static web assets and HEF data are CPU-independent packages. Firmware sources
remain pinned at `ba503a1fbc4ed68c1fd29aace7214a5c330d7021`, with the existing
optional local Git transport. Do not edit or commit `rpi-cam-hailo`.

## Model and configuration

Add `camera-firmware-models` selected only by the firmware's Hailo option.
Its local input defaults to `rpi-cam-hailo/vendor/models/yolo_model.hef` relative
to the project root, overridable through `CAMERA_FIRMWARE_MODEL_DIR`.
Pin SHA-256 `eebaf6e491f8c182c095d2a2fd38d8fc6efbc55d595be1bbec75338f55751917`;
fail on missing or different input, never substitute another model silently.
Install it at `/usr/share/camera-firmware/models/yolo_model.hef`. Treat its
unverified redistribution license as CLOSED; no inferred license grant.
Do not commit the HEF or other generated binaries. There is no pose HEF.

Install a Hailo-specific secure example as `app.yaml.example` when Hailo is
enabled; preserve the non-Hailo example otherwise. Use the upstream single
model schema (objects, object_detection, 640x640 rgb8, letterbox, threshold
0.40, coco80) and the installed absolute HEF path. Do not install an active
`app.yaml`. Keep TLS, authentication and integrity checks enabled; no private
keys, fixed SRTP secrets or upstream insecure development configuration.
Packaging does not claim HEF chip compatibility or working inference.

## Verification and non-goals

Exercise actual recipe install/validation functions against good, missing and
changed model fixtures. Verify installed secure configuration and paths. Check
the new layer/profile dependency metadata using the pinned BitBake parser,
including standard camera and Hailo separation and AArch64 targeting. Run the
whole existing host suite and an independent read-only review.

This change configures recipes; no complete image build, SSD writes, hardware
acceptance, release merge or push. Keep the three local compiler recipes,
private inputs and reference checkout Git-excluded. No task commit is made
while this checkout also contains unrelated uncommitted changes.
