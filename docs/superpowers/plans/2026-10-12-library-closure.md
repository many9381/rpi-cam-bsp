# Common-library security follow-up

The user selected remaining-work item 1 after accepting the latest image's
initial setup, video, Hailo and three-reboot checks. Review the remaining 14
open and two partially mitigated library associations, apply compatible
corrections, document evidence, and build the integrated Hailo image.

The accepted baseline is `20261012T162756Z-e664cb9647e7`. Prior evidence is
immutable. This is continued authorized security maintenance in the current
checkout, with no additional design approval, worktree, staging or commits.

## Boundaries

- Preserve existing dirty changes, public library ABI and working features.
- No QEMU/minimal image, long-duration test, SSD write or production Pi change.
- Do not hide unresolved conditions with broad scanner overrides.
- Use current primary sources and actual-source regressions. Distinguish
  upstream fixes, locally adapted candidates, exclusions and unresolved work.
- Keep private evidence in `.state/library-closure-2026-10-12/`; publish a
  sanitized report in `rpi-cam-hailo/docs/security/`.
- Only the coordinator runs BitBake, with four tasks and four compiler jobs.

## Tasks

- [x] Review GnuTLS DTLS reassembly, libxml2 schema entities and Expat DoS.
- [x] Review BusyBox ash/awk, ALSA configuration indices and binutils readelf.
- [x] Review glibc's three residual findings and ACL pathname operations.
- [x] Recheck Avahi/libevent mitigations, contracts and installed consumers.
- [x] Independently review final patches and regression evidence.
- [x] Build the Hailo image; verify applied sources, image contents and shared
      library compatibility against the accepted baseline.
- [x] Reconcile findings, archive selected evidence and record limitations.

The component investigations run independently under the
`dispatching-parallel-agents` procedure. The integration review must validate
the exact patch set used by the final build; an agent's PASS alone is not
completion evidence. Hardware acceptance belongs to the newly built image
and is not inherited from the deployed baseline.

## Progress

Source review and bounded regressions support four additional corrections and
two precise glibc exclusions; eight findings remain open and two partial.
Libevent also receives a tested local duplicate Content-Length correction.
Independent review found no blocking issue. The host suite passed 365 tests;
preexisting upstream ash failures and GnuTLS timeout/skip limits are recorded
separately. Four recipes' 14 local inputs are frozen. Hailo image
`20261012T172633Z-e664cb9647e7` is building with four-task/four-job limits;
actual-image verification and archival remain pending.

The build completed at 17:51 UTC: 7,786 tasks succeeded, 6,796 reused. Final
source verification covers ten local patches; 182 SONAME/export comparisons
passed with five changed libraries. WIC verification checked 58 files, seven
modules, sixteen privileged-file metadata entries and two IPA signatures.
The application and setup assets match the accepted baseline. The final raw
scanner count is 455 (previously 459), with no new associations against the
unchanged 2026-10-11 database. Library totals: 68 corrected, 21 excluded, eight
open and two partial. Documentation is updated; curated archive checksums are
the last completion step. No installation or new-image hardware acceptance
has been performed.

The curated evidence archive was created and its checksums verified. All
authorized source/build/documentation tasks are complete; residual findings
and new-image deployment remain explicitly separate follow-up work.
