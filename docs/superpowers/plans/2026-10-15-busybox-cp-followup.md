# BusyBox cp applicability verification plan

> Execute the authorized investigation inline using the systematic-debugging,
> executing-plans and verification-before-completion workflows. Preserve the
> existing checkout and all earlier evidence.

**Goal:** Resolve the separate CVE-2007-4998 BusyBox `cp` applicability question
for accepted Hailo image `20261014T170636Z-e664cb9647e7`.

**Architecture:** Bind the actual installed binary to WIC/build evidence and
test the official same-basename, preserved-symlink scenario in a private
unprivileged directory. Compile the same source natively with the relevant
copy configuration and with only its protection disabled to validate test
sensitivity. Correct product code only if the investigation establishes a gap.

**Tech stack:** BusyBox 1.37.0, Yocto metadata, C, POSIX shell, Python, pinned SSH.

**Spec:** User approval of remaining-work item 1: inspect BusyBox `cp`, then
fix, regression-test and integrate into the layer if necessary.

## Constraints and review focus

- Keep the existing checkout; no commits, resets, worktrees or unrelated fixes.
- No QEMU, SSD flash or full image rebuild unless an actual correction requires it.
- Device tests use only disposable fixtures owned by `rpiadmin`; no root,
  service interruption, configuration changes, credentials or real victim files.
- Distinguish this exact multi-source destination-link scenario from arbitrary
  ancestor-directory replacement races and all other BusyBox advisories.
- Check existing and missing targets, relative and absolute links, preservation
  options, recursive duplicate directories, and safe ordinary copy behavior.
- Preserve earlier assessment counts and historical evidence; record the separate
  BusyBox conclusion without rewriting the original kernel association or scan.

## Task 1: Source and artifact identity

- [x] Read the official report and upstream safe-copy configuration history.
- [x] Inspect actual `coreutils/cp.c`, `libbb/copy_file.c`, final config and
  generated autoconf; identify `FEATURE_NON_POSIX_CP=y` in the upstream layer.
- [x] Record source/config/recipe hashes and verified WIC/installed binary identity.

## Task 2: Bounded behavioral proof

Files: `tests/integration/check-busybox-cp-symlinks.sh` and ignored
`.state/busybox-cp-followup-2026-10-15/`.

- [x] Implement a self-cleaning non-root fixture suite; content/type assertions
  must detect a copied symlink redirecting later same-name source data.
- [x] Build same-source native safe and unsafe-control cp configurations;
  show the unsafe control fails the intended protection cases.
- [x] Show the safe native build and actual installed applet/`cp` entry pass;
  preserve exit codes and exact case results, and verify fixture cleanup.
- [x] Check ordinary file copy, overwrite, recursive copy, preserved source
  links, explicit source dereference, no-clobber and interactive refusal.

## Task 3: Assessment and review

Files: `rpi-cam-hailo/docs/security/busybox-cp-followup-2026-10-15.md`, security
README, and a separate same-build ignored evidence archive.

- [x] Review source-to-binary binding, test sensitivity and applicability limits.
- [x] If existing protection is sufficient, record configuration-specific
  not-affected status; do not introduce an unnecessary patch or rebuild.
- Conditional correction branch: not required; existing protection verified.
- [x] Publish the new assessment, test evidence and checked archive hashes;
  link it from the security index and preserve original build-stage records.

Outcome: configuration-specific **not affected**. Independent review and
archive checksum verification passed. Existing layer protection is sufficient;
no product patch, image rebuild or device installation was needed.
