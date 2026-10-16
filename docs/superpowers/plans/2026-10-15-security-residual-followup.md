# Residual image security follow-up plan

> Use systematic-debugging and verification-before-completion. Independent
> source investigations use dispatching-parallel-agents; integration is owned
> by the primary agent in the existing user-authorized checkout.

**Goal:** Follow up all 15 remaining image/advisory associations, implement
supported compatible corrections where established, and record exact residual
conditions for accepted image `20261014T170636Z-e664cb9647e7`.

**Architecture:** Preserve the existing 546-association assessment and its
separate resolved BusyBox cp follow-up. Compare fresh official records with
actual built sources and known reproduction evidence. Candidate corrections
must pass failing-before/passing-after tests and compatibility controls before
layer integration. Hardware acceptance remains separate from build proof.

**Tech stack:** Yocto, C/C++, native bounded regression fixtures, Python, JSON.

**Spec:** User selected remaining-work item 1: residual image security follow-up
(12 open, two partially mitigated, one unassessed), with prior authorization to
apply security corrections to layers and record them in firmware docs/security.

## Constraints and review focus

- Preserve unrelated changes and previous evidence; no commits or worktrees.
- No QEMU, long-duration soak test, SSD write, or device reboot for this audit.
- Never read or archive credentials, private keys, cookies or signed settings.
- No broad CVE overrides, feature removal, arbitrary limits or API breakage to
  force closure. Public-fix absence alone is not a no-impact conclusion.
- Source-open findings with tested runtime policy mitigation stay distinct.
- Preserve valid schema/entity values, MOV side-data ownership, binary URL
  decoding, legitimate long-lived clients, and procfd/ACL callers.
- Reuse existing source/build evidence; available disk space is approximately
  27 GiB. Any required image build is only the Hailo profile, after space checks.

## Task 1: Freeze baseline and refresh primary evidence

Files: `.state/security-residual-followup-2026-10-15/baseline.json`, `primary/`,
`xml-media/`, `library-boundaries/`, `busybox-binutils/`, `kernel/`.

- [x] Preserve baseline ledger/source/layer identities and enumerate all 15 IDs.
- [x] Retrieve current CNA records and exact official issue/commit discussions.
- [x] Compare actual built code and earlier reproductions; distinguish changed
  upstream evidence from conditions already investigated.

## Task 2: Resolve actionable candidates

Files: isolated candidate source/tests in the corresponding ignored directories;
applicable `meta-rpi5-cam/recipes-*/<component>/` patches and appends only if justified.

- [x] For each actionable candidate, reproduce the reported defect with bounded
  input, test the exact correction, and run valid-input/ownership controls.
- [x] Integrate verified compatible corrections; run relevant target compilation,
  package/ABI checks and Hailo image validation if product inputs changed.
- [x] If no compatible correction is established, retain the accurate disposition
  and state the concrete prerequisite for further action; do not rebuild unchanged inputs.

## Task 3: Reconcile and publish

Files: `rpi-cam-hailo/docs/security/security-residual-followup-2026-10-15.md`,
security README, ignored `assessment.json`, `integrated-assessment.json`, archive.

- [x] Cover all 15 selected associations; preserve all unrelated dispositions.
- [x] Independently review candidate changes, test sensitivity and conclusions.
- [x] Publish results with primary links, explicit limitations and checked hashes.
- [x] Report concrete changes, validation and remaining blockers without claiming
  whole-image security clearance or unperformed hardware acceptance.
