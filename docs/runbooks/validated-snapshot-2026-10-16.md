# Validated development snapshot — 2026-10-16

The local annotated tag `validated-20261016T111625Z` in both repositories
preserves the reviewed source and integration work associated with accepted
image `20261016T111625Z-e664cb9647e7` (`rpi5-camera-hailo`). The repositories
remain separate: this workspace uses `feature/root-firmware-layers`, and
`rpi-cam-hailo` uses `master`. No remote publication is part of this task.

## Image and source relationship

The accepted image was built **before** these snapshot commits. Its original
integration HEAD was `e664cb9647e724ee99b8f6024e8a7c0f571fa100`, plus the local
inputs captured in its private `provenance/` directory. Do not substitute the
new commit IDs into historical build or deployment records.

- Compressed image: `images/rpi5-camera-image-raspberrypi5.rootfs.wic.bz2`.
- SHA-256: `49417cfdc898f1cb0ab9aae7a2f78de92d19f45666a0e4c0a5f2d4276f7a9c12`.
- Firmware recipe pin: `ba503a1fbc4ed68c1fd29aace7214a5c330d7021`, with the
  existing recipe patch chains through `0010`. The snapshot does not change
  this pin; selecting the new firmware commit while retaining these patches
  would apply integrated changes twice.
- Firmware snapshot commit: `f1675ff7ea4bf5e2d243b89f681e930bbf9d32da`, also
  available as `validated-20261016T111625Z^{commit}` in the separate firmware
  repository and recorded in this repository's annotated tag message.

Before committing, all **296** captured integration inputs matched their
recorded content hashes and executable modes. The source archive and complete
image checksum list also passed. All **431** firmware quality-review inputs
matched the October 16 source record; **170** production files additionally
matched both the compiled recipe source and packaged development checkout.
Only documentation and ignore-rule hygiene were added for this snapshot.
The non-patch staged diff passes whitespace checks. Diagnostics within
upstream/backport patch payloads were retained with the verified patch bytes;
this preservation task does not reformat those build inputs.

The firmware [snapshot record](../../rpi-cam-hailo/docs/security/version-preservation-2026-10-16.md)
separates newly run checks from existing target/device evidence. The
[deployment record](../../rpi-cam-hailo/docs/security/static-warning-deployment-validation-2026-10-16.md)
continues to cover the installed image. This is a development checkpoint,
not a certification, a zero-vulnerability release or a guarantee of identical
future image bytes. Existing security classifications and agreed work
exclusions remain unchanged.

## Private prerequisites and future builds

The image, build caches, credentials, SSH/signing keys, Codex login sessions,
Hailo Debian archives, model payloads and diagnostic boot photo stay outside
Git. Three local compiler-validation recipes remain explicitly ignored in
`.git/info/exclude`; their bytes are preserved only in the private build
provenance. A checkout of the tag alone does not supply these private/local
inputs or the fetched upstream repositories.

Committing changes both Git HEAD and tracked/untracked status. The provenance
guard intentionally rejects reuse of the old build ID even when captured
source bytes still match. Preserve the old artifact/provenance unchanged and
use a **fresh build ID** for any later build:

```sh
BUILD_ID="$(./scripts/new-build-id.sh)"
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo build
```

Keep any required local Git transport override and private provisioning inputs
configured as described in [camera-firmware.md](camera-firmware.md) and
[build-provenance.md](build-provenance.md). The Codex latest-stable resolver
still runs on later builds; the accepted image's package manifest records
version `0.163.0`. The installed image and its completed installation record
remain valid; this snapshot itself requires no rebuild or SSD reinstallation.
`scripts/install-ssd.sh` retains its existing checks, including rejecting a
build/profile that already has a completed installation record.
