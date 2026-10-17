# Private image build input evidence

New image builds through `scripts/build.sh` create
`artifacts/<build-id>/<profile>/provenance/` before invoking kas. This is a
private source snapshot of the local integration inputs, not a public release
or a guarantee that a second build will produce identical bytes. Keep the
ignored artifacts private. Existing historical builds have no retroactive
source or SPDX guarantee.

Start after finalizing image-affecting changes:

```sh
BUILD_ID="$(./scripts/new-build-id.sh)"
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo build
```

The snapshot includes eligible tracked and untracked files from
`meta-rpi5-cam/`, `meta-rpi-cam-hailo/`, `kas/`, and `scripts/`, plus
`pyproject.toml` and `uv.lock`. Layer files use an explicit extension/resource
allowlist in `scripts/lib/build_provenance.py`; kas includes `.yml`, scripts
include `.sh` and `.py`. Known extensionless resources include the administrator
and camera sudo rules and licenses. The optional compiler package group is a
normal versioned input. The former three ignored compiler-validation recipes
have been retired from active layer discovery; they no longer receive an
exception. Ignored source files cause a private-path-free error rather than
being archived or silently omitted. Unknown non-ignored files under the source roots also fail;
a new required resource type must be deliberately added to the allowlist before
building. The layer READMEs are explicitly excluded as documentation.

`provenance/sources.tar` contains regular source files in stable path order
with normalized timestamps and preserved executable status.
`provenance/inputs.json` records the Git HEAD, actual content SHA256/size,
tracked deletions, file status, archive SHA256, and selected input choices.
The firmware source pin and all local firmware patches are source files in the
archive. External layer revisions are recorded separately in
`manifests/layer-revisions.txt`; this snapshot covers the two local integration
layers rather than copying fetched upstream repositories.

The snapshot never copies `keys/`, `.state/`, `artifacts/`, `build/`, generated
local.conf, credentials, the external application checkout, Debian archives,
or model payloads. Public SSH/signing identities receive digests only. Symlinked
source files/directories and selected vendor inputs are rejected. Archive
exclusions never permit BitBake metadata (`.bb`, `.bbappend`, `.bbclass`, `.inc`,
`.conf`) to hide beneath directory names such as `build` or `keys` inside a local
layer: these inputs fail generically without being copied or exposing private
filenames. Ordinary repository root credential/generated trees remain outside
capture. For the Hailo
profile, only the two selected 4.24.0 Hailo Debian archives and
`yolo_model.hef` receive SHA256/size records. Those fixed archive paths match the
current recipes and must be updated alongside a reviewed vendor version change.

`CAMERA_FIRMWARE_MODEL_DIR` can select the model directory. Metadata records
whether the default or environment supplied it and fingerprints the directory;
it does not expose the directory itself. The optional
`CAMERA_FIRMWARE_GIT_URI` transport override is fingerprinted without recording
its URL or embedded credentials. `RPI_CAM_HAILO_DEV_REPO` records its default or
environment origin and effective enabled state (only `0` disables it).
`RPI5_LOCAL_BUILDTOOLS` records the origin and effective target-buildtools
selection: default off, enabled by `1` for Raspberry Pi profiles, always off
for QEMU. Changing this choice requires a fresh build ID. When verifying or
collecting a development build, supply the same environment selection.
Do not publish private environment values in build documentation.

The shared firmware source recipe uses package epoch `1` following the
2026-10-16 Git history privacy cleanup. Rewritten commit hashes are not
monotonic version numbers: the application, web assets and development
checkout must all sort after packages from the previous history. Preserve
this epoch when updating their source pin; do not disable the
`version-going-backwards` QA check or erase build history to bypass it.

Collection verifies the captured sources, deletions, choices, public identities,
vendor digests and archive before replacing incomplete output directories and
again before writing `COMPLETE`. Changed, added or removed eligible files,
executable status changes, or different vendor bytes fail collection. Retrying
an incomplete build verifies its existing provenance instead of overwriting it;
changed inputs require a fresh build ID. Do not edit captured sources during
an active build. A manual verification uses the same selected environment:

```sh
python3 scripts/lib/build_provenance.py verify --repo "$PWD" \
  --out "artifacts/$BUILD_ID/rpi5-camera-hailo/provenance" \
  --profile rpi5-camera-hailo
```

Collection requires the actual deployed
`<image>-<machine>.rootfs.spdx.json` and copies its referent as a regular file
at `manifests/image.spdx.json`. It also preserves the image package manifest,
licenses and camera public key. `manifests/build-metadata.json` records actual
kas, uv and host Python versions. `manifests/resolved-packages.json` records the
installed Codex CLI version from the image package manifest. Codex continues
selecting latest stable each invocation; rebuilding this same snapshot later
can select a newer version, so use the actual package manifest and SPDX to
assess the resulting image.

`checksums/SHA256SUMS` covers all regular files under `images/`, `manifests/`
and `provenance/` in stable path order. Verify it from the profile directory:

```sh
(cd "artifacts/$BUILD_ID/rpi5-camera-hailo" && sha256sum -c checksums/SHA256SUMS)
```

`COMPLETE` confirms artifact collection and unchanged captured inputs. Security
assessment runs separately after the image build and stores its own metadata,
input/output hashes and findings under `security/`; collection does not emit a
security PASS. Mutable scan reports are outside the image checksum manifest.

The current camera layer uses Raspberry Pi libcamera 0.6.0 with its reviewed
Pi patches and matching packaged camera tools. Historical device capture or web
video results remain evidence for their original installed build only. New
images still need the device procedure in
[camera-validation.md](camera-validation.md). The legacy release gate continues
requiring the minimal wired profile; Hailo integration evidence does not expand
that acceptance route.
