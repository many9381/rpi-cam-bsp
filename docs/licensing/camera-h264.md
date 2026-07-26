# Camera H.264 Licensing Gate

The camera profile enables Yocto's `commercial` license flag and configures
FFmpeg with libx264 to prove software H.264 on the selected hardware. This
approval is scoped only to internal development and validation images.
Accepting a Yocto license flag permits the recipe to build; it does not grant
distribution rights.

Official project material states that x264 is offered under the GNU GPL and
also under a separate commercial license. FFmpeg documents that enabling
libx264 changes the applicable FFmpeg build license to GPL. These sources and
the exact built source/license manifests must be reviewed together:

- [FFmpeg license and legal considerations](https://ffmpeg.org/legal.html)
- [FFmpeg external library notes for x264](https://ffmpeg.org/general.html#x264)
- [VideoLAN x264 licensing](https://www.videolan.org/developers/x264.html)
- [Yocto 6.0 license flags](https://docs.yoctoproject.org/6.0/dev-manual/licenses.html)

Any external distribution, product shipment, customer image, hosted download,
or published binary requires a recorded review covering:

1. The exact FFmpeg, x264, and all linked component versions and build flags.
2. GPL source, offer, notice, attribution, modification, and corresponding
   source obligations for the intended delivery model.
3. Product EULA and reverse-engineering terms where applicable.
4. x264 alternative/commercial licensing status.
5. H.264 patent or royalty considerations for every destination jurisdiction.
6. Approval from the organization's qualified legal and release owners.

A missing or incomplete recorded review **blocks external distribution**.
Changing encoder, build flags, delivery model, or jurisdiction invalidates the
previous review and requires a separately reviewed feature and acceptance run.
This runbook is an engineering release gate, not legal advice.
