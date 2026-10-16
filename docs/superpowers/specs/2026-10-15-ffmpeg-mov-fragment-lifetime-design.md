# MOV fragment growth: allocation lifetime design

Status: **deferred; excluded from current required firmware work**, as agreed
with the user on 2026-10-15. This is a retained design investigation, not an
active implementation or pending approval request. No production allocator or
layer change has been made. The accepted camera image remains
`20261015T185424Z-e664cb9647e7`.

## Decision and conditions for reconsideration

Keep the verified cleanup and incremental-append patches. Do not implement the
common-allocator redesign for the current camera workflow. Retain the residual
CVE-2026-107678 assessment as partially mitigated/open and preserve the existing
reproducer; this scope decision does not establish a complete fix or image-wide
non-applicability.

Reassess if the product adds external MOV/MP4 upload, playback, conversion or
thumbnail processing, if operational ffmpeg/ffprobe use accepts untrusted media,
or if new evidence establishes a reachable input path. A compatible upstream
fix may also justify a focused review. Such a review does not automatically
restart this allocator proposal or require a new image build.

Future work prioritization must establish the actual input path and impact on
the camera product before promoting a residual advisory to required work. The
earlier priority recommendation was made before that exposure check.

## Intent and compatibility requirements

Remove repeated PSSH buffer growth caused by separate MOV fragment parsing
passes, without discarding records, changing their serialized bytes/order,
altering public structure layouts, or making caller-owned copies unsafe.
Preserve the current camera/Hailo image and existing security fixes.

The initial MOV residual follow-up was authorized. Investigation shows that a
MOV-only cache change cannot meet these requirements: parameter copying and
public side-data replacement may free a buffer and reuse its address with a
smaller allocation. Root invalidation currently prevents stale-capacity writes.
The proposed correction therefore crosses into FFmpeg's common allocator.

## Current firmware exposure and change impact

The accepted camera executable's hash matches the WIC. It links libswscale,
which uses libavutil, but not libavformat. Product sources have no
`avformat_open_input`, `avformat_find_stream_info` or `av_read_frame` calls.
The camera encodes frames and sends them through GStreamer streaming pipelines;
it does not implement an external MOV/MP4 file ingestion API. This is evidence
against a direct trigger in the current camera application, not a blanket
exclusion for the image: installed ffmpeg/ffprobe tools do link libavformat.

The proposed libavutil allocator change has a wider impact than the exposed
MOV reader. Video downscaling and CPU AI preprocessing use libswscale/libavutil.
An implementation defect or excessive bookkeeping overhead could affect those
paths. No speed or image-quality improvement for ordinary camera/Hailo operation
is expected from correcting the MOV parser.

Accordingly, the agreed action is to retain the accepted safe patch and track
the residual issue without implementing this redesign. The source/dependency
check narrows the immediate application exposure. The approach and acceptance
gates below are retained for reference only if the scope is reconsidered.

## Measured problem

The fixture contains one PSSH record and one ordinary PCM packet per fragment,
with monotonic fragment sequence numbers and decode timestamps. All media
packets and expected PSSH bytes are verified through the real MOV demuxer.

| Fragments | PSSH growth requests | Sum of requested PSSH bytes | Logical prefix bytes relocated on this host |
|---:|---:|---:|---:|
| 1,024 | 1,024 | 19,411,461 | 280,109 |
| 2,048 | 2,048 | 77,620,230 | 526,069 |
| 4,096 | 4,096 | 310,429,696 | 950,385 |

Request volume is quadratic. It is not a measurement of actual allocator
copying or a demonstrated target CPU denial of service. The current glibc host
often extends allocations in place. A moving-allocation test must establish
the worst-case copying bound separately.

## Deferred approach (reference only)

Add opt-in allocation-capacity tracking inside libavutil for encryption-init
serialization buffers only. Track the live allocation, not a MOV pointer cache.

1. An internal helper reserves tracking metadata before a fallible buffer growth.
   The table stores pointer and requested allocation capacity, never media bytes.
   Unknown copies have unknown capacity and must undergo a real allocation before
   their spare capacity can be used.
2. Successful `av_realloc()` updates a tracked allocation's identity/capacity;
   failed reallocation preserves its old valid record. `av_free()` invalidates
   the record before its address can be reused. Audit all allocator backends and
   wrappers in the pinned FFmpeg source; direct backend frees must not bypass it.
3. Use synchronized, bounded-load lookup with a fast empty-table path. Metadata
   uses the raw backend to avoid recursive registry operations. Reserve space
   before mutation so allocation failure cannot corrupt an existing public
   pointer, size or byte sequence. Remove all per-buffer metadata on free.
4. The appender obtains trusted capacity from this internal mechanism. Retain its
   public signature and documented failure behavior. Remove redundant MOV cached
   pointer/capacity state only after same-address replacement tests pass.
5. Preserve PSSH collected during stream discovery transactionally when generic
   codec-parameter replacement would restore an older decoder snapshot. Prepare
   replacement parameters/side-data slot before transferring live ownership.
   Demonstrate that path with a failing regression before changing it.

No public structure layout or existing exported function signature changes.
No input record cap, padded public serialization, dropped data, direct allocator
size introspection, or assumption that pointer equality proves lifetime is used.

## Alternatives rejected

- Removing root invalidation or using a private MOV/FFStream generation alone
  cannot see all public buffer replacement paths and can cause invalid writes.
- A private accumulator copied to public side data every packet still copies all
  accumulated prefixes; it does not remove the repeated-fragment cost.
- Publicly exposing reserved capacity as extra side-data bytes changes the
  serialized representation. Undocumented allocator spare space is not a usable
  ownership contract.
- A new record/size cap changes accepted input semantics and only bounds work;
  it is a different policy choice, not the proposed compatible correction.

## Acceptance gates if reconsidered

Before a layer change: reproduce old failure; test continuous and many-fragment
inputs; preserve exact serialized bytes, record count/order, stream assignment,
media packet count and discovery behavior. Test parameter copy-back, public
side-data replacement/free, forced same-address reuse, realloc shrink/grow,
allocation failures at every ownership transition, and final cleanup.

Run normal and ASan/UBSan/leak checks; add concurrent independent contexts and
an allocator overhead control, because common allocation/free paths change.
Review the complete patch independently before packaging. Reject the approach
if it causes material allocator overhead or cannot meet failure/lifetime gates.

Then build only `rpi5-camera-hailo`, verify actual WIC/library/source binding,
public ABI/export stability, preserved camera files and the security ledger.
No QEMU, long-duration device test, SSD installation or live device mutation is
part of this change. New-image hardware acceptance remains a later deployment.

## Scope limits

The target is amortized append storage across parsing passes while the caller
has not explicitly replaced the public data. A caller repeatedly copying the
entire public list necessarily requests its own cumulative copying. Repeated
bitstream-triggered codec-context updates also require assessment; do not claim
universal linear demuxing or close CVE-2026-107678 solely from the append test.
Retain the advisory's partial status until the actual remaining paths have
adequate evidence. Existing unrelated assessments remain unchanged.

Evidence: `.state/ffmpeg-mov-fragments-2026-10-15/`. The official PR/CVE and
discussion were fetched again on October 15; the PR head remains
`df40e69194187f8ab0db3558bf2a154d32fd0040`, open and unmerged.
