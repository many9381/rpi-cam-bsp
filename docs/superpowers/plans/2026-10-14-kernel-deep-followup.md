# Kernel deep follow-up implementation plan

**Goal:** Complete the next reviewed correction pass on the nine remaining
kernel associations after acceptance of `20261014T064455Z-e664cb9647e7`.

**Architecture:** Continue the established source-reviewed backport workflow.
Retain Linux 6.18.55 at `4103a989a46196239b830bd07693277e42b8f992`, all 60
accepted patches and the accepted configuration. Independently prepare small
source candidates; only the coordinator integrates the layer and builds.

**Spec:** The user's selected item 1 and the Remaining conditions in
`rpi-cam-hailo/docs/security/kernel-followup-2026-10-14.md`. The preceding
deployment report establishes the current accepted image, not a future image.

**Tech stack:** Raspberry Pi ARM64 kernel, Yocto/BitBake, C source regressions,
actual ARM64 translation-unit compilation, Python evidence checks.

## Constraints

- Existing maintenance scope and execution method remain authorized. Work in
  the current checkout, preserving existing changes; no commits or worktree.
- Build only the Hailo image, at most four build workers and two private ARM64
  compiler workers. No QEMU/minimal image, SSD write, device configuration
  change, crash/exploit or long-duration test.
- Never substitute feature disabling, blanket CVE overrides or partial bounds
  checks for complete compatible corrections. Unproved candidates stay open.
- Keep secrets and working evidence Git-excluded. Preserve accepted artifacts.
- Reconcile the original 403 kernel / 539 total associations without changing
  unrelated conclusions. Source corrections and hardware/policy exclusions
  are separate; retained scanner snapshot date must remain explicit.

## Work and gates

- [x] Freeze current source/config, 60 patches, export commands, module/import
      inventory, actual-image/library baselines and accepted deployment.
- [ ] BPF arena (`CVE-2026-74354`): establish detachment, MM/VMA and page
      ownership across fault/free/unmap/exit, aliases and OOM paths. Preserve
      failing-before and valid controls; keep unsafe experiments private.
- [x] io_uring (`CVE-2026-43174`): complete per-ifq lifetime on the retained
      provider API, including delayed pool destruction and every registration
      failure. Assert exactly-once netdev/area/rbuf/device cleanup.
- [x] Direct I/O (`CVE-2026-89584`): propagate memory alignment through all
      actual callers, reject first/later invalid vectors, correctly handle
      registered BVEC and roll back duplicate/folio pins without short success.
- [x] Tracing (`CVE-2026-98032`): implement destination-owned capacity across
      allocator/reuse/read/splice, preserving partial reads and error ownership.
      Exercise shrink/grow, mismatch copy, wait/failure and splice references
      with 16 KiB pages; cover headers and benchmark callers.
- [x] NVMe FDP (`CVE-2026-98153`): construct immutable placement data before
      shared-head publication, adapt explicit unpublished-head APIs and all
      failure cleanup. Cover discovery/reuse, absent/disabled FDP and faults.
- [ ] Retain or refine the other four records only with evidence: ICMP timestamp,
      IPv6 L2 multicast, coredump policy and unavailable Sun/Brocade record.
      No implicit authorization to change network or coredump policy.
- [x] Independently review complete candidate/caller/error paths. Compile all
      affected configured ARM64 C units using actual saved compiler commands;
      label optional-configuration controls. Run existing/new source regressions.
- [x] Register approved patches under
      `meta-rpi5-cam/recipes-kernel/linux/files/` and the 6.18 bbappend, run the
      project host suite, then build and collect only `rpi5-camera-hailo`.
- [x] Bind final source/config, all shipped module CRCs and every export change
      to the compiled kernel. Verify actual WIC, protected userspace/libraries,
      boot/camera/Wi-Fi configuration, privileged metadata and secret exclusion.
- [x] Reconcile assessments and publish the result under
      `rpi-cam-hailo/docs/security/`, with independently reviewed, checksummed
      evidence. Report new-image hardware acceptance as pending installation.

Private work: `.state/kernel-deep-followup-2026-10-14/`.
Each candidate provides `assessment.json`, `patch-manifest.json`, source/caller
hashes, bounded red/green regressions and a compile-unit list. Tests extract
actual changed source; modeled facilities never replace compiler API checks.

Pre-build status: four source corrections are approved. The BPF arena and policy/
equivalence checkboxes remain open because those security outcomes are unresolved.
No arena experiment is integrated. The first image build stopped before collection;
the final ZCRX revision adds final-publication spinlock and live-context admission.

Final delivery: image `20261014T092945Z-e664cb9647e7` passed the host suite,
ARM64 compilation, full source/module/library and actual WIC verification.
The independent final review approved delivery, and the 5,983-file evidence
archive passed its checksum manifest verification. Four corrections are in the
layer. BPF arena and the four policy/equivalence records remain unresolved;
the additional NVMe response-count finding is documented separately.
SSD installation and new-image Pi hardware acceptance remain pending.
