# Remaining library security remediation

**Goal:** Complete the user-selected library follow-up with supported layer fixes, reproducible regressions and explicit residual findings.

**Architecture:** Preserve the validated camera image's kernel, application and library ABI. Review actual enabled source paths, apply focused compatible fixes, then build the Hailo image once inputs are settled.

**Spec:** The user's approval of remaining-work item 1: finish Avahi/libevent partial mitigations and assess/remediate remaining installed-library candidates, including glibc, libxml2 and Expat. The existing 2026-10-12 assessment is the baseline; its evidence remains immutable.

**Execution:** Independent component investigation under dispatching-parallel-agents, followed by integrated source/image verification and a fresh review. This is continued authorized security maintenance in the existing checkout; no additional design approval, worktree, staging or commits are required.

## Constraints

- Preserve existing dirty changes, earlier images and evidence.
- No QEMU/minimal builds, long-duration tests or SSD writes. Do not change production Pi packages/accounts/configuration.
- Use `.state/library-residual-2026-10-12/` for private work. Do not archive credentials, vendor payloads, copied binaries or full sources.
- Raw CVE matches are not exploit counts. Keep partial, upstream-unfixed and unsupported assessments visible.
- No broad CVE_STATUS suppression, feature removal or public-API change to make a scan pass.
- A final build uses bounded parallelism to avoid repeating the previous host OOM.

## Review focus

- Avahi listener backoff must recover after allocation/descriptor failure and must not indefinitely starve ordinary clients or evict legitimate long-running queries.
- Libevent percent decoding must preserve documented binary decoding APIs and reject ambiguous URI use at the appropriate boundary.
- Loader and privileged-code applicability must use actual image metadata, not host pseudo permission bits.
- Backport prerequisites, ownership and error cleanup must match the exact pinned sources; patch application alone is insufficient.
- XML hardening must preserve legitimate documents and retain bounded resource behavior without claiming all DoS is eliminated.

## Tasks

- [x] 1. Avahi/libevent: inspect primary advisories and source; reproduce residual behaviors; implement compatible source fixes or justified configuration mitigation; verify normal/recovery cases.
- [x] 2. glibc: assess all thirteen residual candidates against exact source and actual privileged image paths; apply supported fixes with meaningful regressions.
- [x] 3. libxml2/Expat: inspect remaining schema/entity and DoS conditions; fix supported cases, retaining explicit upstream-unfixed limitations.
- [x] 4. Other library candidates: review remaining installed API paths and upstream fixes; apply only supported compatible changes and record specific unresolved prerequisites.
- [x] 5. Review all changed layer inputs and regressions. Run relevant host checks and actual BitBake builds; verify final WIC package/module/service contents and scan evidence as appropriate.
- [x] 6. Record applied changes, exact validation boundaries and remaining findings in `rpi-cam-hailo/docs/security`; link the new report from the security index.

## Progress

Started 2026-10-12. Deployed baseline is `20261012T080118Z-e664cb9647e7`; installed-file and three-reboot acceptance already completed. Library baseline is 40 fixed, 17 excluded, 40 open and two partial among 99 original associations. Existing checksums and assessment files will not be overwritten.

Source review completed: 24 candidate associations have supported maintenance
backports (glibc10, GLib5, X11 four, ALSA two, GnuTLS two, PNG one); two BFD
XCOFF candidates have configuration exclusions pending final-image equivalence.
Avahi and libevent remain partial despite additional tested mitigations.
Fourteen candidates remain open, including libxml2's rejected normal-input
regression and Expat's upstream-unfixed condition. Ordinary API tests and
source review do not substitute for complete security regression coverage.

Independent read-only reviews found no scoped source blockers. Host suite:
365 passed. Baseline Pi normal libc checks passed without changing its boot,
camera process or restart count. Build `20261012T135745Z-e664cb9647e7` started
with 38 frozen layer inputs and four-task/four-job limits. Only the Hailo image
is selected. Build, image, source, symbol compatibility and deployment status
remain separate; the new image has not been installed.

First integrated build stopped on a missing private GIO authentication class
prerequisite. The official four-file companion patch was added; five full
authentication translation units now compile with the exact native options,
and independent source review passed. Build `20261012T140609Z-e664cb9647e7`
replaces the failed attempt with 39 frozen layer inputs. Original failure,
source snapshot and earlier per-component evidence are retained.

Final Hailo build completed at 15:13 UTC: all 7,786 tasks succeeded (4,459
reused). Actual sources verify 34 local patches across eight changed recipes;
182 SONAME/export comparisons passed, with 13 changed library files. Actual
WIC selected-file checks, seven kernel modules, platform/service configuration,
two IPA signatures and credential-path absence checks passed. The new libc
and loader passed normal unprivileged API checks on the Pi; all temporary
files were removed and its boot, camera PID and restart count were preserved.

Unresolved raw matching with the unchanged 2026-10-11 scanner databases fell from 483 to
459, with no new candidate associations. The reviewed 42 findings are 24
source-corrected in the built image, two excluded by actual BFD configuration,
14 open and two partial. Among the original 99 libraries the totals are
64 fixed, 19 excluded, 14 open and two partial. This completes the supported
maintenance/assessment pass, not all library security work. New-image
installation and full hardware acceptance remain pending. See
`rpi-cam-hailo/docs/security/library-residual-remediation-2026-10-12.md`.
