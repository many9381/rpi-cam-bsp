# Yocto image completion implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans task by task. Preserve the existing checkout and unrelated changes.

**Goal:** Deliver a verified Hailo camera image including the boot delay fix, usable device acceptance tools, current whole-image vulnerability evidence, and a reproducible record of the local build inputs.

**Architecture:** Keep the existing kas profiles, image, and reusable installer. Extend the camera acceptance procedure to safely release and restore the automatic service around direct sensor tests. Scan the actual image SPDX rather than host or historical Debian packages. Record source contents and input digests without copying credentials.

**Tech stack:** Yocto 6.0 / BitBake 2.18, kas 5.4, Python 3.12 / uv 0.11.31, shell, systemd, libcamera and FFmpeg.

**Spec:** The user's approved Yocto remaining-work list in this conversation: boot delay deployment, device acceptance fixes, final integrated image checks, whole-image CVE assessment, and reproducible source/document alignment. Firmware feature changes and RTSPS behavioral tests are a separate workstream.

## Global constraints

- Work in the existing repository; its README explicitly prohibits moving ongoing work to another worktree without a request.
- Do not build QEMU. Do not erase existing evidence, unrelated changes, or the functioning Pi installation.
- Do not stage, commit or copy private keys, Codex credentials, Wi-Fi credentials, vendor Debian archives, HEFs or camera images into source snapshots.
- Use a new build ID. Record current local inputs; a Git HEAD alone does not describe this dirty checkout.
- Preserve SSH key checks and exact device/build/profile matching. No generic sudo command grants.
- Hardware acceptance and SSD installation may require an operator action after all host-side work is concrete and verified. Do not mark those steps complete before they occur.
- No promise of zero CVEs: record database freshness, coverage gaps and each unresolved finding accurately.

## Review focus

- Failure or interruption during capture restores a service that was initially running, without starting one that was initially stopped.
- Reboot or address change must not silently accept a different SSH host key or image.
- Missing timestamps, malformed video metadata and empty streams must fail validation rather than manufacture a frame rate.
- CVE databases pinned months before the scan date must not be labeled current; vendor components absent from databases remain explicitly unassessed.
- Source/evidence collection must exclude ignored secrets and fail on changing input contents or escaping symlinks.

## Task 1: Service-aware camera acceptance

Files: `scripts/test-camera.sh`, focused helpers under `scripts/lib/`, `tests/host/test_camera_contract.py` and related tests, camera-only support recipe/files, `docs/runbooks/camera-validation.md`.

- [x] Add failing execution tests for an initially active service, restoration on failed capture and interrupted execution, and an initially inactive service.
- [x] Grant only exact camera-service start/stop commands in a camera-only sudo policy, if needed for direct captures. Keep the existing base account policy and app security configuration unchanged.
- [x] Stop an active app before direct camera capture; restore on every exit; handle the post-reboot automatic service consistently and verify restoration.
- [x] Record H.264 in MP4 and validate real codec, dimensions, frame count, duration and frame rate rather than trusting raw H.264 metadata.
- [x] Verify affected tests and shell/sudo policy syntax. Document the brief service interruption and operator prerequisites.

## Task 2: Whole-image security evidence

Files: focused scanner wrapper/configuration and tests, artifact collection integration, `rpi-cam-hailo/docs/security/` record.

- [x] Inspect the pinned OE-Core `sbom-cve-check` integration and official data sources, including snapshot freshness.
- [x] Prepare a bounded reproducible scan using actual image SPDX and current databases; avoid cloning unnecessary historical databases or building other machine profiles.
- [x] Preserve scanner version, data revisions, timestamp, input/output hashes and raw results in ignored build artifacts.
- [x] Assess installed-package findings against versions, backports and enabled paths. Distinguish fixed, unaffected, open and unassessed; do not suppress findings simply to pass.
- [x] Preserve the image SBOM and scan status with collected artifacts. Document any external data limitation and the reproducible retry command.

## Task 3: Reproducible local input evidence

Files: focused provenance helper and tests, build/collection integration, relevant runbooks.

- [x] Capture the actual non-secret recipe/config/script sources, including eligible new files and tracked deletions, with deterministic content hashes and Git state.
- [x] Record application source pin and applied patch hashes, tool/layer revisions, and vendor input hashes only.
- [x] Exclude keys, ignored local configuration, generated trees, credentials, vendor payloads, and external application checkout from source archives.
- [x] Verify unchanged build inputs at collection time; never silently relabel an image with source edits made during its build.
- [x] Update stale runbook statements about libcamera and hardware validation; retain historical evidence as historical.

## Task 4: Integrated build and host validation

- [x] Run focused tests, then the complete host suite and required source/syntax checks.
- [x] Create a new ID and build `rpi5-camera-hailo` once all image-affecting changes are final. Collect images, manifest, licenses, SPDX, provenance and security outputs.
- [x] Verify image checksums, signed public-key correspondence, actual rootfs camera/driver/Wi-Fi/service contents, and final Wic boot configuration.
- [x] Complete a focused review of task changes and resolve important findings before delivery.

## Task 5: Install and device acceptance

- [x] Present the concrete completed artifact and installation/retention implications, then arrange the required SSD/operator action. SSD connection requested; target is currently absent.
- [x] Install only the registered SSD with `scripts/install-ssd.sh`; never write the host disk. Installer recorded success at 2026-10-11 14:27:19 UTC, including separate Codex restore and camera provisioning.
- [ ] Verify the new installed build, service start timing over Wi-Fi, camera acceptance, repeated reboot recovery, and user-visible web/video/Hailo behavior.
- [ ] Record actual results and any remaining operator-dependent work in the security record and task ledger.

2026-10-11 boot acceptance update: Three Wi-Fi reboots passed with app start
5.670/6.438/6.234 seconds from kernel startup, no app restarts, automatic camera
pipeline/web recovery and preserved setup state. User confirmed final video and
Hailo ready/increasing sequence/object results. Evidence is under the build's
`rpi5-camera-hailo/boot-validation/`. Task 5 remains partial: the initial fresh
installation boot had six TLS validity failures before NTP corrected its clock;
this needs a fix and fresh-install validation. Formal JPEG/MP4/AF acceptance is
still pending, and its lsblk UUID lookup needs a target-compatible correction.
No minimal, QEMU or camera acceptance PASS has been created for these checks.

2026-10-11 initial-clock follow-up: Installer now seeds the target timesyncd
clock after TLS creation, preserves newer saved time, and verifies it on
readback. Camera unit starts after time-set.target without waiting for NTP.
Full host suite352 PASS, focused independent review clean after comment
correction. Hailo-only build20261011T155422Z-e664cb9647e7 and actual Wic/rootfs
checks passed; final SPDX scan preserved separately with unchanged installed
findings. Registered SSD is now connected and install-ssd.sh --check selected
this build and passed. No SSD writes performed. Fresh-install first boot and
NTP-delayed/unavailable hardware validation remain pending; warm reboot results
from the earlier image do not close this item.

2026-10-11 fresh-install follow-up: Installation of build
20261011T155422Z-e664cb9647e7 completed at 16:11:34 UTC. The user confirmed the
new Wi-Fi device and its changed SSH key was pinned separately. Its actual
first-boot journal shows RTC 1970 restored to the installer-saved clock before
the app started at 6.374 seconds, with zero TLS identity errors or app restarts.
One controlled reboot passed at 6.294 seconds app start; HTTPS and camera were
active while NTP remained unsynchronized at 10.49 and 31.16 seconds uptime.
No prolonged deliberate NTP blocking was performed. The initial-clock finding
is closed for actual fresh-boot and observed delayed-NTP startup.

The camera acceptance UUID lookup now falls back to the unique udev link for
the actual root device when unprivileged lsblk cannot read UUID. Malformed or
ambiguous identities fail, and existing device, phase-1 and service-restoration
guards remain. Final helper passed on the target, the full host suite passed
361 tests, and independent re-review found no remaining scoped findings.
This host-only script correction requires no new image build or SSD install.
Evidence is in the new build's separate boot-validation directory. Formal
JPEG/MP4/AF acceptance remains pending; no minimal or camera PASS was generated.

2026-10-11 camera functional acceptance follow-up: User confirmed Camera Module
3 Wide. Installed Hailo image passed full-resolution JPEG and Focused AF metadata
before and after one controlled reboot. Real MP4 measured 1920x1080 H.264,
291 decoded frames, 9.696820 seconds and 30.009823 average fps; target/local probe
results and sample hashes match, and full decode has no errors. App state was
restored after both capture intervals; latest PID camera/RTSPS logs, HTTPS and
20-second stability checks passed with no unexpected restarts. Highest sampled
SoC temperature59.5C. No build, SSD write or firmware change required.

Ruling: This closes the installed development image's JPEG/MP4/AF functional
checks. The README explicitly separates that development workflow from the
minimal-image release route. Existing phase-1 gate was preserved, no minimal or
camera release PASS was emitted, and no QEMU/minimal build was launched. The
separate release chain remains NOT_RUN, as do authenticated web media/AI and
RTSPS security regression checks. Evidence is under this build's camera-validation/.

2026-10-11 separate RTSPS workstream: Device regression was executed against
the installed build. TLS/authentication rejection, valid SHA-256 Digest, actual
nonce expiry, authenticated KeyMgmt edge cases, SRTP/SRTCP reception and complete
1080p H.264 decoding passed within their recorded scope. Overall result is FAIL:
an unauthenticated second connection using a known active Session can disrupt
the first connection's media when it closes, through both PLAY and public OPTIONS.
Controls without that request or with a nonexistent Session preserve playback.
GStreamer registers the session before URL authentication; public OPTIONS also
needs consideration in a fix. Current app remains active with no restarts.

This newly reproduced session-isolation defect is the next security correction;
it is not fixed by the existing 1.28.8 layer update. No product source, image or
SSD was changed during these tests. The temporary HA1 file was removed. See
rpi-cam-hailo/docs/security/rtsp-device-regression-2026-10-11.md and this build's
separate rtsp-validation/ evidence. No release PASS is emitted.

2026-10-11 RTSPS remediation follow-up: The approved session-isolation fix now
authenticates requests before global session access, requires authentication for
OPTIONS carrying either selector header, and restricts responses to sessions
already owned by that connection. The response bypass was independently
reproduced before fixing it. Both GStreamer and application patches are included
in the runtime image, with the application patch also in the optional devrepo.

Real Pi isolated-process tests passed 126 RTSP unit and 44 integration/config/CLI
cases; 361 host tests passed. Mixed-version controls failed as expected and show
both fixes are necessary. Final scoped review has no blocking findings. Hailo
build 20261011T180648Z-e664cb9647e7 completed; checksums, provenance and actual WIC
contents passed, including the tested GStreamer ELF identity and identical
patched firmware/devrepo sources. Evidence and deployment boundary are recorded
in rpi-cam-hailo/docs/security/rtsp-session-isolation-remediation-2026-10-11.md.

Deployment remains pending. The operating Pi still runs build
20261011T155422Z-e664cb9647e7, with unchanged PID 1169, zero restarts and healthy
HTTPS after temporary test-file removal. No SSD write, QEMU/minimal build or
hardware/release PASS for the new image was performed. Existing historical
RTSPS FAIL evidence is preserved; passing isolated tests do not relabel it.

2026-10-11 corrected-image deployment follow-up: The installer completed at
18:25:05 UTC. User confirmed the new Wi-Fi device before pinning its changed
SSH key, then completed initial setup and confirmed web video. Installed image
ID, firmware/library hashes and three devrepo source/test files match the WIC.
The app started at 6.130249 seconds; PID 554 and zero restarts persisted.

All 126 RTSP unit and 44 integration/config/CLI tests passed using the installed
system library. The actual operating RTSPS service passed 16 unauthenticated/TLS,
5 selector-policy, 12 authenticated and 7 session-isolation cases. Existing
streams survived rejected requests and unsolicited responses; authenticated
controls remained 200. The actual camera stream yielded 9,298 SRTP / 3 SRTCP
packets and 711 fully decoded 1080p frames without decoder errors. Empty raw
headers are dropped by the upstream parser; this is documented separately from
in-memory header-presence unit tests, not treated as an authentication bypass.

Deployment and operating-service revalidation of RTSP-SESSION-ISOLATION-01 are
complete. Temporary HA1 and target test files were deleted; production account
and configuration were not changed. Evidence is under the new build's
security/rtsp-deployment/ and the app's docs/security/rtsp-deployment-validation-
2026-10-11.md. Historical failure evidence and distinct release acceptance gates
remain intact. No further image build, SSD write or reboot was performed.

2026-10-11 OpenSSH security follow-up: Upgraded the pinned OE-Core integration
from 10.3p1 to official portable 10.6p1, retaining the key-only login policy and
package/service layout. Three narrowly scoped Red Hat-only CVE annotations are
supported by CNA and source evidence. Independent review found the changed
sshd -T directive casing; both acceptance scripts now compare directive names
case-insensitively while retaining exact values and strict AuthenticationMethods
handling. Actual awk-filter regression tests failed before and passed after.

Final Hailo image 20261011T190155Z-e664cb9647e7 completed all 7786 tasks; 365 host
tests passed. On the Pi, packaged binaries passed 13 upstream fast-mode unit
suites and seven upstream functional suites in an isolated directory. UTF-8
required a test-only locale; the first connect run required upstream helper
links. Those initial harness failures are retained in evidence. Final WIC
binaries match tested package hashes; camera/Wi-Fi/clock/RTSP configuration,
checksums and provenance passed. No QEMU/minimal image was built.

The final SPDX scan has zero raw unresolved OpenSSH candidates, down from 25.
The scoped assessment is 20 fixed by version and five not affected. Two platform
cases labelled fixed by the scanner are separately assessed using Linux seccomp
and fd-passing configuration, without editing raw reports. Whole-image raw
unresolved associations remain 4825 (190 non-kernel); this is not a whole-image
security PASS. Kernel/FFmpeg/curl follow-up remains necessary.

The operating Pi remains on image 20261011T180648Z-e664cb9647e7/OpenSSH 10.3p1.
Test processes, listener, keys and directory were removed; production boot/app
PID stayed unchanged, restart count zero and HTTPS healthy. SSD installation and
new-image boot/SSH/camera/Hailo acceptance are pending. Login-protected Hailo
dashboard confirmation for the currently installed RTSP image is also pending.
See rpi-cam-hailo/docs/security/openssh-remediation-2026-10-11.md and the final
image's security/openssh-remediation/ evidence. No hardware/release PASS emitted.

2026-10-12 OpenSSH image deployment follow-up: User booted final image
20261011T190155Z-e664cb9647e7. Installer evidence from 2026-10-11T19:22:34Z
matches the compressed-image SHA256. The reinstalled host key was pinned in a
new evidence directory; image/profile, board identity, USB root and new UUID
were verified. Twelve installed binary/development-source files match the WIC.
Actual OpenSSH 10.6p1 socket activation, key-only policy, denied root/non-key
logins, rejected shell-metacharacter username and a 128 KiB SFTP round trip pass.
Both acceptance parsers pass ten checks using the actual mixed-case sshd dump.

Three Wi-Fi reboots passed: SSH/HTTPS recovery 51.523, 29.882 and 51.091 seconds;
app startup 6.206, 6.378 and 6.406 seconds, zero restarts and 20-second stability
per cycle. SSH/TLS pins, setup state and media UUID persisted. Each boot started
the IMX708 1080p pipeline automatically and logged zero TLS identity errors.
Operating RTSPS passed 16 TLS/unauthenticated and five OPTIONS policy checks
before and after reboots; authenticated media/session-isolation testing from
the earlier image was not relabelled as a new run.

User confirmed normal video, hailo / ready, increasing frames and object labels
with confidence after the final reboot. Final device checks also confirm HAILO8
firmware 4.24.0, pwm-fan control and Codex 0.162.1 ChatGPT login persistence.
Temporary SFTP files were removed; production accounts/config were untouched.
See rpi-cam-hailo/docs/security/openssh-deployment-validation-2026-10-12.md and
the image's security/openssh-deployment-2026-10-12/ evidence. No build, SSD write,
QEMU/minimal run or separate wired/minimal release PASS occurred in this task.
Kernel/FFmpeg/curl security follow-up and long-duration/web acceptance remain
separate pending work; this closes the new image's deployment/boot acceptance.

2026-10-12 platform security follow-up: Updated curl8.19.0 to the signature-
verified8.22.0 release; corrected Raspberry Pi FFmpeg's erroneous7.1.13 package
label (actual7.1.3 source) to epoch1/7.1.5, retaining Pi29 codec support and adding
21 exact upstream CVE backports. Independent review found DRM double-close and
HLS reload cleanup defects; both have separate fixes and failing-before/passing-
after regressions. Updated Pi kernel6.18.33 to pinned6.18.55 plus one stable IPv4
RCU lifetime backport; this is not the complete6.18.56 release.

Isolated Pi tests passed curl Secure-cookie/TLS controls; FFmpeg VobSub stream
reuse, HLS rejection after two requests, H.264/MP4/JPEG roundtrips and actual DRM
API failure cleanup. All nine shared libraries retain existing exported symbols.
The final WIC matches the tested libraries/FFmpeg tools, new kernel and seven
camera/fan/Wi-Fi/Hailo modules. Hailo vermagic is6.18.55-v8-16k. Camera/Wi-Fi/
clock configuration, development checkout, credential exclusion, previous
OpenSSH/RTSP identity, checksums and source provenance passed. No device reboot,
SSD write or QEMU/minimal image build/guest run occurred.

The first image attempt20261012T023656Z-e664cb9647e7 failed Codex file-rdeps QA:
its bundled glibc-linked rg lacked explicit glibc/libgcc runtime dependencies.
The recipe now declares them; actual QA passes without suppression. Final
image20261012T031641Z-e664cb9647e7 completed all7786 tasks with7236 reused results.
Final host suite365/365 passed. An intermediate five-second fake-launcher timing
test exceeded the limit under build load; unchanged standalone retry and final
full suite pass. libcamera cached-version warning recovered through the real
task; installed version and two libraries match the previous validated Pi.

Using the same2026-10-11 CVE database snapshots, final installed raw unresolved
associations fell4825→539 (kernel4635→403, non-kernel190→136, curl33→0,
FFmpeg58→37). Source/configuration review reconciles FFmpeg's37 remaining raw
rows to32 fixed/absent/disabled/uninstalled cases and five unresolved candidates.
Do not equate those raw associations with confirmed exploits or whole-image
security PASS. Kernel's remaining403 and other recipes still need review.

The running Pi remains on20261011T190155Z-e664cb9647e7; test files were removed,
boot/appPID/restart count unchanged and pinned HTTPS/setup healthy. New-image
SSD installation and boot/camera/Hailo/fan/Wi-Fi/Codex acceptance remain pending,
along with the five FFmpeg follow-ups and long-duration/web acceptance. See
rpi-cam-hailo/docs/security/platform-security-remediation-2026-10-12.md and
the final image's security/platform-security-2026-10-12/ curated evidence.

2026-10-12 platform image deployment follow-up: User booted image
20261012T031641Z-e664cb9647e7 and confirmed the Pi at Wi-Fi 198.51.100.60.
Installer evidence dated 2026-10-12T06:16:37Z matches the actual compressed WIC
SHA256. A separate SSH pin and the authenticated TLS certificate were retained
through all checks. Board identity, USB root and the new filesystem UUID match.
Thirty-four installed binary/module/configuration/development-source files
match the validated image/source. The running kernel is 6.18.55-v8-16k with
16 KiB pages; all seven camera/fan/Wi-Fi/Hailo modules are loaded with matching
vermagic. Initial/final targeted kernel fault-pattern counts are zero.

Three Wi-Fi reboots passed: SSH/HTTPS recovery 41.900, 40.898 and 40.884 seconds;
app startup 6.290245, 6.330304 and 6.270393 seconds, zero restarts and 20-second
stability per cycle. Each boot automatically started the IMX708 1080p pipeline.
Setup state and SSH/TLS pins persisted; whole-boot TLS identity errors are zero.
Initial/final NTP synchronization passed, with normal pending synchronization
in early post-reboot snapshots; application startup did not wait for it.

Installed system FFmpeg 7.1.5 passed bounded VobSub stream reuse and synthetic
H.264/MP4/JPEG encoding/decoding. Actual OpenSSH 10.6p1 policy, root/non-key login
denials and 128 KiB SFTP roundtrip passed. Operating RTSPS passed 16 TLS/auth
rejection and five OPTIONS selector-policy checks before and after reboots.
These are separate from the earlier authenticated RTSP media/isolation tests.

After the third reboot the user confirmed normal video, hailo / ready,
increasing frames and object labels/confidence. Final hardware checks confirm
HAILO8 firmware 4.24.0, pwm-fan 2/4 at 5026 RPM, Codex 0.162.1 ChatGPT login
persistence and bundled rg 15.2.0 execution. Highest recorded temperature
snapshot is 61.70 C, not a continuous-load maximum. Temporary transfer/media
files were removed; operating accounts, packages and configuration were
unchanged. No new build, SSD write or QEMU/minimal build/guest execution occurred.

See rpi-cam-hailo/docs/security/platform-deployment-validation-2026-10-12.md
and the image's security/platform-deployment-2026-10-12/ curated evidence.
This completes the new platform image's deployment/automatic-start acceptance.
The existing 539 raw CVE associations, five scoped unresolved FFmpeg candidates,
long-duration testing and separate formal wired/minimal acceptance are not
closed by this result; no new CVE scan or formal release PASS was generated.

2026-10-12 remaining security follow-up: User approved FFmpeg and kernel/other
library work and excluded long-duration operation. Final Hailo image
20261012T080118Z-e664cb9647e7 completed all 7,786 tasks (7,757 reused) and
artifact collection. Initial LLVM/Node host OOM failures and a later intentional
Node parallelism restart are preserved separately; final continuation exited 0.
No frozen layer input changed during recovery.

Applied four FFmpeg patches, twelve same-pin kernel backports, Expat 2.8.5 plus
two fixes, libevent 2.1.13, glibc resolver, eight libxml2 patches, util-linux
failed-mount cleanup and partial Avahi availability mitigation. The 37 layer
inputs match provenance. Host tests passed 365/365; 29 actual patches, unchanged
kernel configuration, 182 shared-library SONAME/export comparisons and actual
WIC binaries/modules/configuration passed. Twelve libraries changed; camera
binary differences were fully explained and both IPA signatures verified.
Isolated Pi FFmpeg media and non-capture camera-library/IPA enumeration passed,
with production service identity preserved and temporary files removed.

Final actual-image SPDX raw affected associations are 483, down from 539 using
the same 2026-10-11 database snapshots, with no new candidates. Per-source/config
assessment covers all 539 baseline rows: 87 fixed (50 newly remediated),
208 excluded, 149 open, two partial and 93 inconclusive. MOV CVE-2026-107678,
V3D CVE-2026-93047 and the other explicit residual findings remain open;
raw version matches are not confirmed exploit counts. A separate BusyBox cp
follow-up is retained. No whole-image security or hardware release PASS.

Reports: rpi-cam-hailo/docs/security/security-followup-2026-10-12.md and its
three linked component records. Curated checksummed evidence is beside the
new image under security/security-followup-2026-10-12/. The Pi remains on
20261012T031641Z-e664cb9647e7; new-image SSD installation and boot/camera/Hailo
acceptance remain pending. No SSD write, reboot, QEMU/minimal image or
long-duration test was performed in this follow-up.

2026-10-12 security follow-up deployment: User installed image
20261012T080118Z-e664cb9647e7 and confirmed the new Pi at Wi-Fi 198.51.100.60.
Installer timestamp 12:55:09Z and compressed WIC SHA256 match the running
build. The confirmed new SSH key and SSH-authenticated loopback TLS certificate
were pinned separately; old pins/evidence were preserved. Board, USB root and
new filesystem UUID stayed fixed. All 47 checked installed binary/module/
configuration/signature/development-source files match validated image inputs.

Three Wi-Fi reboots passed: recovery 66.326/50.052/64.307 seconds; camera app
start 6.314244/5.726360/6.302262 seconds, zero restarts and 20-second stability
per cycle. The IMX708 1080p pipeline started automatically each time. HTTPS,
setup state and SSH/TLS pins persisted; whole-boot TLS identity errors are zero.
Initial and final NTP synchronization passed, with pending synchronization in
early reboot snapshots. The app did not wait for NTP or networkd-wait-online.

Installed system FFmpeg passed bounded VobSub, H.264/MP4/JPEG and four changing
32x24/64x48 frames through floodfill/hqdn3d. Actual OpenSSH policy/login denials
and 128 KiB SFTP roundtrip passed. Operating RTSPS passed 16 rejection/TLS and
five selector-policy checks before and after reboots. Initial/final seven
loaded kernel modules match 6.18.55-v8-16k; targeted kernel fault counts are zero.
HAILO8 firmware4.24.0, fan control, Codex0.162.1 ChatGPT login persistence and
bundled rg15.2.0 all passed. Final fan2/4,5108RPM; temperature57.85C snapshot.

After the third reboot the user confirmed normal video, hailo/ready, increasing
frames and object labels/confidence. Temporary device files were removed;
operating accounts/packages/configuration were not changed. No new build,
SSD write, QEMU/minimal run or long-duration operation test was performed.

See rpi-cam-hailo/docs/security/security-deployment-validation-2026-10-12.md
and the image's security/security-deployment-2026-10-12/ archive. This completes
new-image installation/automatic-start acceptance over Wi-Fi. Prior raw483
security associations and per-source open/partial/inconclusive findings remain;
no new CVE scan or formal wired/minimal release PASS was generated.

2026-10-12 later library follow-up: Hailo image
`20261012T140609Z-e664cb9647e7` built successfully (7,786 tasks; 4,459 reused).
Thirty-four ordered local patches across eight changed recipes, 182 installed
SONAME/export comparisons and 34 selected actual WIC files were verified.
Twenty-four additional library associations have supported source corrections;
two BFD/XCOFF associations are excluded by the actual compiled configuration.
Avahi/libevent have additional mitigations but remain partial; fourteen library
candidates remain open. Unresolved raw associations with the same 2026-10-11 database fell
483 to 459; the original 539-association ledger now has 111 fixed, 210 excluded,
123 open, two partial and 93 unassessed. The new image is not installed.
An isolated normal-API check used its WIC-matched libc/loader on the existing Pi
without changing the boot, camera process or restart count. Full-image boot,
video and Hailo acceptance remains pending. No QEMU/minimal image, SSD write or
long-duration acceptance run was performed. Details are in
`rpi-cam-hailo/docs/security/library-residual-remediation-2026-10-12.md`.
