# Dedicated Firmware Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the existing AArch64 firmware packaging into a visible root layer and include the local HEF in Hailo images.

**Architecture:** Keep platform/image recipes in `meta-rpi5-cam`; move firmware, web and their packagegroup into `meta-rpi-cam-hailo`. A separate local-input model recipe and secure Hailo example complete the optional Hailo runtime bundle.

**Tech Stack:** Yocto wrynose, BitBake 2.18, kas 5.4, CMake, Python unittest.

**Spec:** `docs/superpowers/specs/2026-09-15-firmware-layer-design.md`

## Global Constraints

- Work in the project root on `feature/root-firmware-layers`, never a hidden worktree.
- Preserve unrelated dirty changes and historical artifacts; no image build or SSD write.
- Do not edit or commit `rpi-cam-hailo`, model binaries, secrets or local compiler overrides.
- Application revision remains `ba503a1fbc4ed68c1fd29aace7214a5c330d7021`.
- Model SHA-256 is `eebaf6e491f8c182c095d2a2fd38d8fc6efbc55d595be1bbec75338f55751917`.
- No automatic active app.yaml or security bypasses; no claim of hardware validation.
- Use apply_patch for edits. Do not stage, commit, switch branches or create worktrees.

## Task 1: Extract and complete the firmware runtime layer

**Files:**
- Move: `meta-rpi5-cam/recipes-camera/camera-firmware/*` to the same relative subtree in `meta-rpi-cam-hailo/`.
- Move: `meta-rpi5-cam/recipes-core/packagegroups/packagegroup-camera-firmware.bb` to the same relative subtree in `meta-rpi-cam-hailo/`.
- Create: `meta-rpi-cam-hailo/conf/layer.conf`, `meta-rpi-cam-hailo/README.md`.
- Create: `meta-rpi-cam-hailo/recipes-camera/camera-firmware-models/camera-firmware-models_1.0.bb`.
- Create: `meta-rpi-cam-hailo/recipes-camera/camera-firmware/files/app-hailo.yaml.example`.
- Modify: `kas/rpi5-camera.yml`, `README.md`, `docs/runbooks/camera-firmware.md`.
- Modify: `tests/host/test_firmware_packaging.py`; create `tests/host/test_firmware_models.py`.

**Interfaces:**
- Consumes existing recipe names/pins and source schema `rpi-cam-hailo/config/app-rpi5-ai-dev.yaml`.
- Produces new layer collection `rpicamhailo`, runtime package `camera-firmware-models`, optional `CAMERA_FIRMWARE_MODEL_DIR`, and installed model path `/usr/share/camera-firmware/models/yolo_model.hef`.
- Parent will independently exercise real BitBake metadata in the four profiles and run full host tests after implementation.

- [x] **Step 1: Test the changed runtime package boundary before implementation.**
  Change the existing web install test's recipe root to the new layer and use
  an explicit existence assertion so the missing layer yields a clear failure.
  Write model behavior tests that execute the real recipe validation/install
  body (fixture files, no BitBake worker required). Assert correct bytes and
  mode 0644 at the installed absolute path, checksum failure on changed bytes,
  failure on absent source, and no output model on failure. Use a literal
  fixture digest, independently calculated once, not a copied runtime result.
  Verify installed config parses as YAML, references the installed HEF, keeps
  TLS/security/client auth enabled and does not create an active app.yaml.
  Run `uv run --locked python -m unittest discover -s tests/host -p 'test_firmware*.py' -q`
  and record the expected failures before implementation.

- [x] **Step 2: Relocate the existing recipe bodies without unrelated changes.**
  Move files via apply_patch (preserve content), update the test path. Add:

  ```bitbake
  BBPATH .= ":${LAYERDIR}"
  RPI_CAM_HAILO_LAYERDIR := "${LAYERDIR}"
  BBFILES += "${LAYERDIR}/recipes-*/*/*.bb ${LAYERDIR}/recipes-*/*/*.bbappend"
  BBFILE_COLLECTIONS += "rpicamhailo"
  BBFILE_PATTERN_rpicamhailo = "^${LAYERDIR}/"
  BBFILE_PRIORITY_rpicamhailo = "9"
  LAYERDEPENDS_rpicamhailo = "core rpi5cam openembedded-layer multimedia-layer"
  LAYERSERIES_COMPAT_rpicamhailo = "wrynose"
  ```

  Add `meta-rpi-cam-hailo:` to `repos.meta-rpi5-cam.layers` in the camera kas
  profile only. Restrict the C++ recipe to `COMPATIBLE_HOST = "aarch64.*-linux"`.
  Retain all source pins and compile/install behavior.

- [x] **Step 3: Implement the local HEF package and its Hailo selection.**
  The model recipe is LICENSE CLOSED, inherits allarch, has no configure or
  compile task, reads `file://yolo_model.hef` via FILESEXTRAPATHS from:

  ```bitbake
  CAMERA_FIRMWARE_MODEL_DIR ?= "${RPI_CAM_HAILO_LAYERDIR}/../rpi-cam-hailo/vendor/models"
  CF_MODEL_SHA256 = "eebaf6e491f8c182c095d2a2fd38d8fc6efbc55d595be1bbec75338f55751917"
  ```

  Explicitly check SHA-256 of the unpacked file before installing; do not
  assume local file URI checksum flags enforce an immutable pin. Fail clearly
  on wrong/missing input before producing a model. Install 0644 under
  `${datadir}/camera-firmware/models` and include it in FILES:${PN}.
  Add `camera-firmware-models` as the fourth field (runtime dependency) of
  PACKAGECONFIG[hailo] in the firmware recipe. Forward the model-dir override
  in camera kas env (inherited by Hailo); normal camera never selects it.

- [x] **Step 4: Install a secure Hailo example with target paths.**
  Derive the Hailo example from existing secure app.yaml.example, changing
  camera.ai to enabled/model_ids [objects] and top-level ai to enabled/backend
  hailo and the upstream single object_detection model schema. Reference
  `@DATADIR@/camera-firmware/models/yolo_model.hef`; keep all secure sections.
  Choose the input example with bb.utils.contains('PACKAGECONFIG', 'hailo',
  'app-hailo.yaml.example', 'app.yaml.example', d); install it under the same
  example name and existing permissions. Never install active app.yaml.

- [x] **Step 5: Document the visible layout and private-input workflow.**
  Explain layer roles, AArch64 source builds, optional local Git URI and model
  directory, checksum update procedure, model/package paths and licensing.
  Replace current operational recipe paths and obsolete “HEF not bundled”
  wording; preserve historical design/plan evidence. Explain no pose model,
  model hardware compatibility not yet verified, and remaining per-device
  TLS/SRTP/integrity provisioning. Preserve root-workspace preference.

- [x] **Step 6: Verify and hand off for independent review.**
  Run the firmware host tests again and `git diff --check`. Report the exact
  before/after results and changed files. No commit. Parent runs full host
  tests, real BitBake checks and independent read-only review; fixes return
  to the same implementer with a focused test rerun.

## Verification evidence (2026-09-15)

- RED: firmware host suite ran 18 tests with 10 expected failures before the
  new layer/model recipe existed. GREEN: all 18 passed after implementation.
- Full host suite: `uv run --locked python -m unittest discover -s tests/host -q`
  passed 207 tests. `git diff --check` passed.
- Real pinned Tinfoil configuration and individual-recipe parsing passed for
  QEMU, Pi minimal, standard camera and Hailo. The checks verified real root
  layer paths, AArch64, source pin/transport, native web build, optional model
  RDEPENDS, example selection and image/profile package routing.
- Actual local HEF fetch-path resolution and SHA-256 passed. Parsed model
  validation/install bodies installed the real HEF into temporary directories
  with expected digest/path/mode 0644; corrupt/missing input was rejected.
- Both camera profiles parsed with an intentionally absent model directory:
  only the model provider was skipped with a missing-input reason. The Hailo
  app still requires the model; normal camera does not.
- Task review: spec and quality PASS, no Critical/Important/Minor findings.
- Final whole-change review: ready for recipe-configuration handoff, no
  Critical/Important/Minor findings. This is not release/image acceptance.
- Ordinary `bitbake -p` is blocked by host user-namespace/AppArmor policy:
  the existing scoped exception attaches only to the historical worktree's
  executable, not the new root path. No host policy or sanity bypass was made.
  Config/individual-recipe checks do not prove the complete provider graph,
  target compilation, package QA or image assembly.
- No SSD writes, device tests, HEF inference/compatibility claims, commits,
  staging, merges or pushes. Historical acceptance markers were not reused.
