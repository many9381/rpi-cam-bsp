# Kernel remaining findings follow-up

**Goal:** Continue the approved kernel security work on all 27 open and 11
inconclusive associations after hardware acceptance of
`20261013T204349Z-e664cb9647e7`.

**Design:** Retain Raspberry Pi Linux 6.18.55 at
`4103a989a46196239b830bd07693277e42b8f992`, its 40 existing patches and the
accepted configuration. Extend the established source-reviewed backport
workflow, with independent BPF, other-path and historical-proof investigations.
Only the coordinator changes shared layer inputs and runs BitBake.

The user selected this existing maintenance item after the preceding image
passed deployment checks. The governing scope is the prior residual plan and
the user's instruction to proceed; no new product architecture is introduced.

## Constraints and review focus

- Preserve existing work, accepted images and historical evidence. No staging,
  commits, worktrees, operating-device changes or SSD writes.
- Build only `rpi5-camera-hailo`; no QEMU/minimal image or endurance/exploit test.
- Do not disable working features or suppress source CVEs by blanket metadata.
- Complete corrections include prerequisites, callers, lifetime/locking,
  allocation and every error path. Keep inconclusive claims explicit.
- Use bounded actual-source regressions with failing pre-fix controls and valid
  operation controls; host adapters must not invent missing kernel APIs.
- Compile complete changed C translation units with real ARM64 headers before
  integration. Record optional-configuration controls separately.
- Bind all shipped module hashes and required symbol CRCs to the final kernel.
  Explain export changes; do not infer internal ABI compatibility from release
  strings or successful linking alone.
- Retain unchanged camera/Hailo userspace, IPA signatures, boot configuration,
  board DTB, credential-exclusion rules and provisioning behavior.
- Limit integrated BitBake and compiler concurrency to four. Keep private
  snapshots small and reserve sufficient space for final WIC extraction.

## Tasks

- [x] Freeze the accepted build, assessment and 40 existing layer patches.
      Partition all 38 records once: seven BPF/classifier, nineteen other
      active source paths, eleven inconclusive plus one ICMP policy record.
- [x] Investigate each partition in its own private directory; preserve
      primary evidence, source hashes, proposed patches, regressions and a
      disposition with precise remaining work for every selected record.
- [x] Review combined patches and assessment changes independently. Reconstruct
      the candidate with zero-fuzz patches, compile its real ARM64 translation
      units, and replay existing plus new regressions against combined source.
- [x] Register approved patches in
      `meta-rpi5-cam/recipes-kernel/linux/linux-raspberrypi_6.18.bbappend`.
      Run the project host suite and build the integrated Hailo image only.
- [x] Verify compiled source/configuration, module imports and export changes;
      compare final WIC modules, protected userspace, libraries, privileged
      metadata, camera/Wi-Fi configuration and secret exclusion.
- [x] Reconcile all 403 kernel and 539 original whole-image associations without
      altering non-kernel conclusions. Distinguish retained scanner snapshot
      results from current primary-source review.
- [x] Publish the result in `rpi-cam-hailo/docs/security/` with checksummed,
      secret-free evidence. New-image hardware acceptance requires a later
      user installation and verification; prior acceptance is not transferred.

Working evidence and progress ledger:
`.state/kernel-followup-2026-10-14/` (Git-excluded).
