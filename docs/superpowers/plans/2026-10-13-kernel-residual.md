# Kernel residual security follow-up

**Goal:** Continue the approved kernel security work on the 45 open and 18
inconclusive associations after acceptance of image
`20261013T124642Z-e664cb9647e7`.

**Design:** Continue the existing source-reviewed backport workflow. Keep
Raspberry Pi Linux 6.18.55 at
`4103a989a46196239b830bd07693277e42b8f992`, all 26 existing patches, kernel
configuration and camera/Hailo integration. Independently investigate BPF,
other active kernel paths and historical applicability gaps, then review their
combined result before integrating only substantiated corrections.

The user selected this remaining-work item after the previous deployment
passed. This is maintenance of the existing implementation, not a new
architecture or permission to change the operating device.

## Constraints

- Preserve preexisting changes, historical assessments and accepted artifacts.
  No staging, commits, worktrees or changes to the operating Pi/SSD.
- No QEMU/minimal builds, long-duration tests, exploit tests on the Pi,
  blanket CVE suppression or disabling working features.
- Keep source findings distinct from exact-image exclusions. Module absence,
  CPU/DT capability and configuration claims require concrete evidence.
- Freeze source/configuration/layer inputs. Use small source subsets and limit
  compilation to four BitBake tasks and four compiler workers.
- Complete correction means prerequisites, all relevant callers and ownership,
  error handling and synchronization are mapped to the current implementation.
  Missing proof remains an explicit open or inconclusive record.

## Work and verification

- [x] Freeze accepted image evidence, current configuration and 179 existing
      layer inputs; partition all 63 records without overlap.
- [x] Investigate 15 BPF records in the private `bpf/` folder. Reproduce selected
      defects on actual source with valid controls before adapting corrections.
- [x] Investigate 31 other open records in `other/`, including filesystem,
      storage, network, display and device lifetimes.
- [x] Investigate 17 historical inconclusive records in `unassessed/`, retaining
      precise source equivalence or exposure gaps when unresolved.
- [x] Independently review proposed changes and assessment transitions. Freeze
      the full accepted patch series and combined changed-source hashes.
- [x] Register accepted patches only in
      `meta-rpi5-cam/recipes-kernel/linux/linux-raspberrypi_6.18.bbappend` and its
      `files/` directory. Verify zero-fuzz application/reversal and regressions.
- [x] Run the project host suite and build only the integrated Hailo image.
      Check actual compiled source, kernel configuration/symbol compatibility,
      all image modules, preserved userspace and provisioning inputs.
- [x] Reconcile all 403 kernel and 539 original whole-image records, preserving
      non-kernel conclusions. Record source fixes and exclusions separately.
- [x] Publish results and remaining limits in `rpi-cam-hailo/docs/security/`,
      with checksummed evidence beside the new image. Hardware acceptance stays
      pending until the user installs it and requests verification.

Working evidence: `.state/kernel-residual-2026-10-13/` (Git-excluded).
The coordinator alone modifies shared layer inputs and runs BitBake.
