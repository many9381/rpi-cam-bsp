# Kernel residual security follow-up

**Goal:** Reassess the 108 open and 93 inconclusive kernel associations,
apply compatible corrections, and preserve the working Pi 5 camera/Hailo image.

**Approved scope:** The user selected remaining-work item 1 after accepting
image `20261012T172633Z-e664cb9647e7`. This continues the existing source-based
security maintenance workflow; no new architecture or feature removal is planned.

**Approach:** Keep Raspberry Pi Linux 6.18.55 at
`4103a989a46196239b830bd07693277e42b8f992`, its existing local fixes, kernel
configuration, module ABI/version and camera/Hailo integration. Review primary
fixes against the complete affected source paths and actual installed modules.
Unsupported equivalence remains explicitly unresolved.

## Constraints and review focus

- Preserve preexisting work; no staging, commits or additional worktrees.
- Do not modify the operating Pi, reinstall its SSD, run QEMU/minimal builds,
  or perform the excluded long-duration tests.
- No blanket CVE suppression or disabling of functioning features.
- Keep source-level findings distinct from exclusions tied to an omitted
  module in this specific image. `CONFIG_FOO=m` alone proves neither presence
  nor absence in the installed image.
- Review allocation/error unwinding, reference and fence lifetimes, implicit
  synchronization, renamed source paths and optional compilation branches.
- Require focused actual-source regression evidence for applied fixes, patch
  application/reversal, source/configuration binding and integrated compilation.
- Only the coordinator runs BitBake, with four tasks/four compiler workers.
  Check space first and avoid full source copies.

## Tasks

- [x] Freeze the accepted source/configuration and prove the actual WIC module
      inventory; retain the original 403-row assessment unchanged.
- [x] Review V3D CVE-2026-93047 consuming-job synchronization, BO lifetime and
      indirect CPU/CSD error paths; apply a correction only with sufficient proof.
- [x] Review the other 107 open associations and prepare compatible corrections
      with focused regression tests; retain exact next actions otherwise.
- [x] Review source mappings and applicability of all 93 inconclusive records
      using primary sources and actual built/installed paths; retain explicit
      evidence gaps where a conclusive disposition cannot be established.
- [x] Independently review proposed patches and changed assessment conclusions;
      freeze the accepted complete local series before integration.
- [x] Build the integrated Hailo image if source changes are accepted; verify
      kernel/modules, configuration, protected userspace inputs and image contents.
- [x] Reconcile all 403 kernel and 539 original whole-image associations,
      document results and limits in `rpi-cam-hailo/docs/security`, and archive
      selected evidence with checksums. New-image hardware acceptance remains
      separate until the user installs that image.

Investigations use the `dispatching-parallel-agents` procedure: V3D, other
open findings and inconclusive findings have separate private evidence folders
under `.state/kernel-followup-2026-10-13/`. They do not modify the actual BitBake
source or shared layer append; the coordinator reviews and integrates proposals.
