# Remaining image security follow-up implementation plan

> Execute the user-approved security follow-up with independent FFmpeg, kernel and library review tasks, then integrate and verify once. Preserve the existing checkout and evidence.

**Goal:** Assess the remaining installed-image security candidates and apply justified fixes to the Yocto layer while retaining camera/Hailo functionality.

**Architecture:** Start from the 539 raw affected associations of validated image `20261012T031641Z-e664cb9647e7`. Keep raw findings separate from source/configuration assessments. Retain the existing Raspberry Pi kernel and FFmpeg integration; use focused upstream fixes and explicit evidence for exclusions.

**Tech stack:** Yocto/BitBake, Raspberry Pi Linux 6.18, FFmpeg 7.1, C/C++, Python/uv, SPDX/CVE metadata.

**Spec:** The user's approval of remaining-work items 1 and 2 in this conversation: FFmpeg's five unresolved candidates, plus kernel/other installed-package assessment and necessary layer changes. Item 3 (long-duration operation) is explicitly excluded.

## Constraints and review focus

- Work in this checkout. Do not stage, commit, create worktrees or alter the running Pi/SSD.
- No QEMU/minimal image builds or long-duration tests. Build only the integrated Hailo profile as needed to validate changes.
- Preserve previous source/scan/deployment evidence; use `.state/security-followup-2026-10-12/` for new private evidence.
- Do not copy credentials, vendor archives, HEFs, private keys or raw device journals into source or evidence archives.
- Do not classify candidates as unaffected from a package version or disabled-feature guess alone. Record exact source/configuration/installed-file evidence or leave open/unassessed.
- Review backport prerequisites, buffer ownership and size transitions, kernel configuration reachability, shared-library ABI, and scanner/source version correspondence.
- User authorization for these security changes already exists; routine implementation decisions do not require repeating approval.

## Task 1: FFmpeg's five unresolved candidates

Files: `meta-rpi5-cam/recipes-multimedia/rpidistro-ffmpeg/`, private `ffmpeg/` evidence, `rpi-cam-hailo/docs/security/ffmpeg-followup-2026-10-12.md`.

- [x] Verify primary records, current fixing commits and the actual 7.1.5 source/configuration for all five candidates.
- [x] Add narrowly scoped patches with prerequisite analysis and upstream provenance when supported.
- [x] Run meaningful bounded before/after regressions and patch-application checks; preserve unresolved cases explicitly.

## Task 2: Kernel's 403 remaining associations

Files: `meta-rpi5-cam/recipes-kernel/linux/`, private `kernel/` evidence, `rpi-cam-hailo/docs/security/kernel-followup-2026-10-12.md`.

- [x] Produce per-candidate source/configuration assessments with conservative dispositions for all 403 entries.
- [x] Apply supported same-line fixes without changing the validated downstream camera configuration.
- [x] Verify patch prerequisites/application and relevant kernel configuration; provide exact build inputs to integration.

## Task 3: Other libraries' 99 remaining associations

Files: affected `meta-rpi5-cam` recipe appends/patches outside Tasks 1 and 2, private `libraries/` evidence, `rpi-cam-hailo/docs/security/libraries-followup-2026-10-12.md`.

- [x] Assess each remaining non-kernel/non-FFmpeg association against primary sources, actual sources and installed functionality.
- [x] Apply justified focused fixes, prioritizing enabled input-processing and privileged paths.
- [x] Check regressions and dependencies; leave unsupported or unfixed candidates visible.

## Task 4: Integration, review and image evidence

Files: new build artifacts, private integration evidence, security README and completion ledger.

- [x] Independently review changed patches and the assessment evidence; resolve material findings.
- [x] Run relevant package builds and required host checks, then the final Hailo-only image build when source changes are settled.
- [x] Verify actual final image contents, source provenance, package versions and existing camera/Hailo/Codex/service configuration.
- [x] Scan the actual new image SPDX and reconcile raw and assessed results without overwriting baseline evidence.
- [x] Record outcomes, remaining candidates, excluded long-duration work and the boundary between image validation and later SSD deployment.

## Progress

Started 2026-10-12 after the user accepted priorities 1 and 2. FFmpeg, kernel and other-library tasks have separate ownership and evidence directories. Long-duration operation testing is excluded by the user's instruction.

FFmpeg progress: four prerequisite-aware backports prepared, bounded exact-source red/green regressions pass, and independent source review reports no critical/important findings. MOV remains open because the current upstream proposal is unmerged and changes public API/ownership. Kernel is preparing ten same-pin backports; other libraries are validating Expat2.8.5+two fixes, libevent2.1.13 and a glibc resolver fix. Final build/scan and target media checks are pending.

Ruling: short isolated tests using a private unprivileged target directory are permitted as necessary security validation; production packages, configuration, accounts, service state and SSD contents must remain unchanged. This does not include the user-excluded long-duration test.

Integration progress: independent review found an undeclared SUNRPC checksum-length variable in the upstream-context backport; corrected to the existing initialized field and re-reviewed. No unresolved important findings in the reviewed10kernel/fourFFmpeg/sixlibraryinputs. Component build started for rpidistro-ffmpeg, linux-raspberrypi, hailo-pci, expat, libevent and glibc only. Source/config assessments continue; actual exposed paths with safe fixes are not deferred solely because earlier inputs were frozen.

Final source freeze:37layer inputs (four FFmpeg patches, twelve kernel patches,
thirteen library patches and their appends) match image provenance for
20261012T080118Z-e664cb9647e7. Independent final assessment review corrected
optional EROFS on-demand/THP/legacy-xtables reachability and retained all93
inconclusive kernel records. The final kernel ledger is26fixed/176excluded/
108open/93inconclusive. Library ledger has34new source fixes,6existing fixes,
17exclusions and42open/partial associations.

The component build was stopped gracefully after3193attempted tasks succeeded
to include the final reviewed inputs in the image build. Exit1 reflects the
intentional stop, not a successful completed build. Final Hailo-only image build
started2026-10-12T08:01Z and is in progress; no second BitBake runs concurrently.

Source-integration validation handles overlapping libxml2 prerequisite context
by reversing the registered series on private file copies and reapplying it,
requiring exact original hashes. An initial per-patch reverse check failed on
that overlap, and an early full check ran before kernel shared configuration
was available. Both logs are retained; neither is a layer build failure.

Integration continuation: the host suite passed all 365 tests in 376.326 s.
Final verification-helper review fixed GNU patch direction guessing, required
media PASS/current build identity, and invalidated stale verification results.
The source checker reverses/reapplies library series only on private copies.

The first final-image attempt ended at 2026-10-12T09:21:15Z: 6,619 tasks
attempted, 4,635 reused, with two host OOM failures (LLVM-native and Node.js-native).
Kernel main/module compilation and target GCC completed successfully. Host
kernel OOM logs and both compiler failure logs are retained. No layer input
changed. `.state/security-followup-2026-10-12/resume-build.py` resumed the same
image ID using a private post-read configuration (four tasks, four compile
workers). LLVM, FFmpeg, camera-firmware compilation, kernel deployment and
libcamera QA subsequently passed. Node.js remains compiling at this checkpoint.

After resource-limited build/collection completes, run actual source integration,
library ABI comparison, final library exclusions, bounded isolated target media
checks, final WIC verification and actual-image SPDX scan. Reconcile all 539
baseline associations and any new raw findings; then finalize the four security
reports, curated evidence checksums and this ledger. The final integration
helpers are under `.state/security-followup-2026-10-12/`. No SSD deployment or
long-duration operation test belongs to this task.

Final outcome (2026-10-12): image 20261012T080118Z-e664cb9647e7 completed at
11:02 UTC, all 7,786 tasks succeeded with 7,757 reused; collector exited 0.
The private continuation used four tasks/four compile workers, with eight
workers for Node.js only after other large toolchains completed. The frozen
37 layer inputs stayed unchanged through recovery.

Final source checks passed all 29 patches, 16 FFmpeg flags and unchanged
kernel configuration. SONAME/export comparison passed for 182 libraries;
12 changed libraries matched actual WIC contents. Isolated new FFmpeg passed
H.264/MP4/JPEG and alternating-dimension floodfill/hqdn3d tests on Pi.
The old libcamera byte-identity assumption correctly failed; exact ELF review
explained generated timestamps, IPA public key and libpisp version-constructor
differences. Both actual IPA signatures and altered-signature rejection passed.
A minimal non-capture CameraManager probe loaded the private new PiSP IPA,
validated its signature and enumerated IMX708 Wide. Existing capture caused
sensor-busy/static-property diagnostics, so this is not capture acceptance.
Independent review found no material verification issue. Temporary device files
were removed, app/boot identity stayed unchanged and HTTPS/setup remained healthy.

Actual WIC checks and image SPDX scan passed. With the same 2026-10-11 database
snapshots, raw affected associations fell 539→483 with no new candidates.
All 539 baseline records reconcile to 87 fixed (50 from this work), 208 specific
exclusions, 149 open, two partial and 93 inconclusive. BusyBox cp remains a
separate follow-up; no whole-image security PASS is asserted. Reports are in
rpi-cam-hailo/docs/security/*followup-2026-10-12.md; curated hashes/evidence are
under the new image's security/security-followup-2026-10-12/. New-image SSD
installation and full hardware acceptance remain separate. User-excluded
long-duration tests, QEMU/minimal builds, SSD writes and reboots were not run.

Subsequent user-authorized deployment validation completed 2026-10-12:
the user installed and booted 20261012T080118Z-e664cb9647e7. Installer/WIC/build
identity,47installed files, system FFmpeg regressions, SSH/SFTP and operating
RTSPS policy passed. Three Wi-Fi reboots recovered in66.326/50.052/64.307s with
camera startup6.314244/5.726360/6.302262s and zero restarts. Final video/Hailo
readiness, increasing frames and detection labels/confidence were confirmed by
the user. Kernel/modules, fan, Codex login and NTP final checks passed.
Report: rpi-cam-hailo/docs/security/security-deployment-validation-2026-10-12.md.
The original build-only evidence is retained; deployment has a separate archive.
This closes the subsequent SSD/boot/camera/Hailo validation boundary, without
closing unresolved security findings or running excluded long-duration work.
