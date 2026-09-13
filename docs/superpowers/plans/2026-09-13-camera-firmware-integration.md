# Camera Firmware Integration Implementation Plan

> Implement the independent recipe domains in this session; use
> superpowers:dispatching-parallel-agents for the Hailo and C++ recipe tasks.

**Goal:** Package the existing camera application in the Yocto camera image.

**Architecture:** Pinned external application source, layer-owned build patches,
offline native web compilation, target application packages, optional Hailo.

**Tech Stack:** Yocto wrynose, BitBake 2.18, kas 5.4, CMake, Node.js, Python unittest.

**Spec:** `docs/superpowers/specs/2026-09-13-camera-firmware-integration-design.md`

## Global Constraints

- Never stage or modify the separate `rpi-cam-hailo` checkout.
- Application SRCREV: `ba503a1fbc4ed68c1fd29aace7214a5c330d7021`.
- Drogon SRCREV: `f215cb15a0f53abd0ca7ee8b95ed8c9c3b40d262`.
- Trantor SRCREV: `79e1ffc59aa1b9c8226c2988fe2e1185e97cd795`.
- HailoRT and PCIe driver: 4.24.0; no configure/compile network access.
- Keep QEMU/minimal profiles usable without multimedia or Hailo layers.
- Commit only explicit project paths after verification.

## Task 1: C++ firmware recipe and target installation

- [x] Add `recipes-camera/camera-firmware/camera-firmware-source.inc` with
  `CAMERA_FIRMWARE_GIT_URI`, `CAMERA_FIRMWARE_SRCREV`, named `firmware` source,
  `S = "${UNPACKDIR}/git"`; both app and web recipes consume this include.
- [x] Add `camera-firmware_git.bb`, CMake integration patch, service and
  example configuration under the same recipe directory. The app depends on
  `camera-firmware-web` at runtime, not on a target Node.js package.
- [x] Support `PACKAGECONFIG[hailo]` consuming recipe `hailort`.
- [x] Disable upstream web build through a patch option; install all binaries
  and the SRTP plugin with target paths. Retain upstream dependency validation.
- [x] Inspect the required libcamera APIs. Retain the pinned PiSP-enabled 0.6.0
  baseline; no missing API was found by inspection. Target compilation remains
  a separate required check below.
- [x] Validate patch application against a clean archive of the pinned source.

## Task 2: Hailo-8 dependencies

- [x] Add recipes under `recipes-hailo/` and `recipes-kernel/hailo-pci/` for
  `hailort`, `hailo-firmware`, and `hailo-pci` version 4.24.0.
- [x] HailoRT SRCREV `63adffec12da88f1e7cfdc07f2e07681671e83e8` and driver
  SRCREV `2789e0ff8b75ffdbaf8f7235f55aef3c06a2ed24`.
- [x] Fetch all build dependencies before configure and use native protoc
  explicitly. Install headers and shared libraries for the C++ recipe.
- [x] Build the PCIe module through the Yocto kernel interface and install the
  chip firmware under the firmware directory expected by that driver.
- [x] Verify licenses, checksums and patches; report external requirements.

## Task 3: Offline web build

- [x] Add behavior tests in `tests/host/test_firmware_npm_lock.py` that exercise
  valid scoped/nested dependencies, duplicate archives, invalid URLs/checksums,
  lock changes and deterministic generation using temporary lock fixtures.
- [x] Run the test to observe the missing generator failure.
- [x] Implement `scripts/firmware_npm_lock.py` with stdout output and check mode.
  Require registry.npmjs.org HTTPS archives, SHA-512 SRI, lockfile v3 and no
  external links. Generate URI metadata, checksum flags, archive paths and
  the source lock SHA-256 into `camera-firmware-npm.inc`.
- [x] Add `camera-firmware-web_git.bb`: native Node dependency, offline npm
  cache seeding and npm ci, explicit build, install only dist assets.
- [x] Regenerate the include from the pinned reference and run behavior tests.
- [x] Install checksum-pinned third-party web license notices; test the actual
  recipe install body and its missing-notice failure before/after the fix.

## Task 4: Image/profile integration and verification

- [x] Ignore `/rpi-cam-hailo/`, add camera package group and image dependency.
- [x] Add Hailo kas overlay; extend build/collection profile routing while
  preserving the same QEMU and hardware prerequisite checks.
- [x] Document source transport override, dependency pins, build commands,
  provisioning and manual runtime validation in a firmware integration runbook.
- [x] Run `.venv/bin/python -m unittest discover -s tests/host -v`.
- [x] Parse individual layer recipes through real Tinfoil metadata APIs under
  both camera profiles and minimal/QEMU; assert image/profile separation.
- [x] Review all changes, fix runtime plugin dependencies and symmetric
  profile validation, and verify the reference checkout remains untouched.
- [ ] Run normal BitBake parsing, dependency graph generation and target
  userspace/image builds on a host that permits BitBake user namespaces.

## Verification results (2026-09-13)

- Final host suite: 182 tests passed, including lock generation, real web
  install commands, runtime-plugin declarations, profile routing and evidence.
- Real Tinfoil config/individual-recipe parsing passed for ten local recipes
  in four kas profiles. Camera assertions also executed the image profile
  writer, checked the source-URI environment override and inspected the actual
  GStreamer SRTP build option. This is not full provider/task-graph validation.
- Real BitBake HTTPS fetching verified all 174 npm archives. The parsed web
  configure/compile/install bodies ran successfully using official Node 22.23.1
  outside BitBake workers: offline npm installed 144 applicable packages and
  the three web assets plus third-party notices were installed.
- All app integration and upstream hardening patches applied to clean pinned
  sources. Hailo patches and source/license checksums were checked.
- Standalone builds succeeded for protobuf 21.12 native protoc and HailoRT/CLI
  4.24.0 using CMake 4.3.1 with disconnected dependencies. A separate installed
  HailoRT CMake consumer compiled and ran. These are host builds, not target
  userspace BitBake builds.
- The PCIe module compiled with the existing Raspberry Pi target toolchain and
  kernel artifacts: AArch64, driver 4.24.0, vermagic `6.18.33-v8-16k`.
- Normal `bitbake -p` stops before recipe processing with `User namespaces are
  not usable by BitBake, possibly due to AppArmor.` No host security policy or
  BitBake isolation/sanity check was changed to bypass it.
- Target application compilation, package QA, complete image assembly, boot,
  provisioned HTTPS/live video/RTSPS/SRTCP and Hailo inference remain unverified.
  No hardware acceptance evidence was generated by these host checks.

Commit only explicit project paths with an English Conventional Commit. Keep
the implementation branch/worktree available; do not merge or push implicitly.
