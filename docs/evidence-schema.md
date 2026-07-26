# Evidence Schema

Raw evidence lives under ignored `artifacts/BUILD_ID/` directories. It can
contain console logs, an IP address, a MAC address, a device serial, SSH host
keys, sample media, a user name, retrieved captures, and a raw journal, so it
is never committed. A private key or public key is never copied into evidence.

Only `artifacts/releases/BUILD_ID.json` may be committed. Schema version 1 has
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
