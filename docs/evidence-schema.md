# Evidence Schema

Raw evidence lives under ignored `artifacts/BUILD_ID/` directories. It can
contain console logs, an IP address, a MAC address, a device serial, SSH host
keys, sample media, a user name, retrieved captures, and a raw journal, so it
is never committed. A private key or public key is never copied into evidence.

The default profile may commit `artifacts/releases/BUILD_ID.json`. Schema version 1 has
this logical structure:

```json
{
  "schema_version": 1,
  "build_id": "YYYYMMDDThhmmssZ-0123456789ab",
  "project_revision": "40-character Git SHA",
  "source_revisions": {
    "repository": "40-character Git SHA"
  },
  "images": {
    "rpi5_minimal": {
      "filename": "minimal Wic filename",
      "sha256": "64 lowercase hexadecimal characters"
    },
    "rpi5_camera": {
      "filename": "camera Wic filename",
      "sha256": "64 lowercase hexadecimal characters"
    }
  },
  "validation": {
    "qemu": "PASS",
    "rpi5": "PASS",
    "reboots": 3,
    "camera": "PASS",
    "sensor": "imx708",
    "lens_variant": "wide-operator-verified",
    "h264": "libx264-1920x1080-30fps"
  },
  "validation_completed_at": "UTC RFC 3339 timestamp"
}
```

The release record must not contain a private key, public key, IP address, MAC
address, device serial, SSH host key, user name, sample media, console log, raw
journal, filesystem path to raw evidence, or free-form operator notes.

Generate the record only after every required COMPLETE/PASS marker for the same
build ID exists and both image metadata records match the current full project
revision. Exact external source revisions must match the kas lock and collected
layer revisions. Image checksum files and raw evidence remain in controlled
external storage under the [artifact retention policy](../artifacts/README.md).

QEMU validation is optional. `validation.qemu` is `PASS` only when both the
QEMU build and runtime PASS markers exist as regular files for the build ID.
When no runtime PASS is recorded it is `NOT_RUN`; this does not block a Pi
release. A runtime PASS without its build marker is rejected as inconsistent
evidence. Raspberry Pi and camera acceptance remain required.

## Optional Hailo image

`release_summary.py --profile rpi5-camera-hailo` writes
`artifacts/releases/BUILD_ID-rpi5-camera-hailo.json` using schema version 2.
It preserves the same sanitized fields and `images.rpi5_camera` checksum slot,
and adds `camera_profile: "rpi5-camera-hailo"` plus
`validation.hailo_inference: "NOT_TESTED"`. Camera capture acceptance does not
certify AI inference. The selected variant must have its own image/flash
markers and `camera-hailo-test/` results; `camera-test/PASS` is never reused.
The Hailo capture result must identify its profile explicitly.

Only these two sanitized release filename forms may be committed. All raw
Hailo diagnostics, model inputs, device identifiers and source/build logs obey
the same private evidence policy as the default profile.
