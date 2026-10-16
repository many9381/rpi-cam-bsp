# Kernel boundary follow-up — 2026-10-14

The user selected finishing current-image validation (item 4), then the two
kernel follow-ups (item 1). Retain the established reviewed-backport workflow,
source pin, accepted feature configuration and current checkout. No commits,
worktree, QEMU/minimal image, endurance test or further Pi changes are needed.

Baseline: `20261014T092945Z-e664cb9647e7`, Linux 6.18.55-v8-16k,
64 existing patches. Its automated deployment checks passed; its explicit
post-reboot web-video/Hailo confirmation must precede final acceptance.

Private evidence: `.state/kernel-boundary-followup-2026-10-14/`.
Public outcome: `rpi-cam-hailo/docs/security/`.

## Sequence and gates

- [x] Finish the current deployment report after actual user UI confirmation.
      Preserve three-reboot and installed-image evidence; checksum the archive.
- [x] Freeze accepted source, configuration, layer inputs, module/export and
      actual-image baselines. Prepare separate arena/NVMe candidate directories.
- [x] BPF arena: trace every VM/MM alias, fault/free/close and allocation error
      path against the complete relevant upstream implementation. Establish a
      compatible ownership and locking correction before proposing integration.
      Retain old rejected inputs as negative evidence only. Do not transplant a
      lock call under the wrong lock order or disable existing mapping features.
- [x] NVMe FDP: establish partial-transfer/count semantics from the complete
      official specification. Bound reads to transferred RUHS descriptor bytes;
      audit configuration-log header/descriptor walking and all cleanup. Preserve
      valid placement registration and the accepted publication-lifetime fix.
- [x] Add bounded actual-source regression checks before candidate changes;
      verify old-input failures, corrected input and ordinary/error controls.
      No device crash, malformed hardware response or exploitation test.
- [x] Independently review final source, callers, cleanup and evidence. Compile
      complete affected ARM64 units with saved real commands (one worker per
      investigation; at most two total). Resolve findings before layer changes.
- [x] Integrate only reviewed corrections in `linux-raspberrypi_6.18.bbappend`,
      preserve all 64 accepted patches and run the project host suite.
- [x] Build only the Hailo image with at most four workers. Bind complete applied
      source/configuration, module CRCs, export deltas and actual WIC files to
      the final image. Preserve camera/Wi-Fi/Hailo/app/Codex compatibility.
- [x] Record precise dispositions and limits, independent review and checksummed
      evidence. New-image installation/acceptance is a separate later action.

## Review focus

Arena controls must cover legal fork aliases and parent close, pending fault
page installation, dying MM, map destruction, OOM and whole-call free/alloc/
reserve serialization. A model alone cannot prove kernel concurrency safety.
NVMe controls must cover zero/126/127/65535 returned counts with bounded transfer
storage, valid subset semantics, short or changing log sizes, descriptor header
and length boundaries, supported granularity and allocation/command failures.
Prior resolved findings remain unchanged. The NVMe response-bound finding is
separate from the original CVE ledger; do not manufacture an advisory assignment.
