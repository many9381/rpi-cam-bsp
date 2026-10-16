# meta-rpi-cam-hailo

This Yocto layer packages the pinned `rpi-cam-hailo` camera application,
its static web interface, secure configuration examples and optional local
Hailo model. Platform images, device configuration, HailoRT, the PCIe driver
and chip firmware remain in `meta-rpi5-cam`.

`camera-firmware` is built for AArch64 with the Yocto toolchain. The web and
model packages inherit `allarch`. Application source remains pinned even when
`CAMERA_FIRMWARE_GIT_URI` selects a local Git transport.

The application, web UI and development checkout share the reviewed
`0005-dhcp-setup-and-optional-management-ip-policy.patch`. Direct HTTPS setup
uses the Pi's current socket address, and new setup leaves management IP
restrictions optional. Existing security databases retain their restrictions
when migrated. Device provisioning can use `public_host: null`; see the runbook
for the bootstrap certificate's trust and name-validation limits.

The optional `rpi-cam-hailo-devrepo` package installs an independent, editable
Git checkout at `/home/rpiadmin/rpi-cam-hailo`, owned by `rpiadmin`. Camera kas
profiles enable it for development; set `RPI_CAM_HAILO_DEV_REPO=0` to omit it.
The package reuses the application commit pin without copying host Git
configuration, credentials, ignored files or cache references. It is not a
dependency of the runtime application and can be removed independently.
Its `CF_DEV_SECURITY_PATCHES` list currently applies patches `0004`–`0010`:
web/SBOM fixes, DHCP and optional IP policy, RTSP session isolation, setup
session recovery, capture health, the source-quality/bootstrap-peer fix and
selected intermediate-copy reductions with rollback-error regressions.
They remain visible in the device checkout's `git diff`; arbitrary host source
or documentation edits are not copied by the recipe.
Patch `0010` is included in image `20261016T111625Z-e664cb9647e7`; its
[image verification](../rpi-cam-hailo/docs/security/static-warning-image-2026-10-16.md)
and [installation/device acceptance](../rpi-cam-hailo/docs/security/static-warning-deployment-validation-2026-10-16.md)
both passed on October 16.

The Hailo profile expects the private input
`../rpi-cam-hailo/vendor/models/yolo_model.hef` by default. Override its
directory with `CAMERA_FIRMWARE_MODEL_DIR`; the recipe verifies the reviewed
SHA-256 before installing the CLOSED model as
`/usr/share/camera-firmware/models/yolo_model.hef`. The model is not stored in
this layer and its redistribution rights are not inferred. Image
`20261016T111625Z-e664cb9647e7` passed video/Hailo device acceptance on
2026-10-16; another image/model combination requires its own validation.
No pose model is packaged.

See the [firmware runbook](../docs/runbooks/camera-firmware.md) for source,
checksum-update, build and per-device provisioning, including current image
SPDX/package-manifest paths and the distinction from historical Debian SBOMs.
