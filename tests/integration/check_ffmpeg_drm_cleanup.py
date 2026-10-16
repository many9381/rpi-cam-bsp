#!/usr/bin/env python3
"""Exercise the exact patched FFmpeg DRM create/free bodies with real FDs.

Usage: check_ffmpeg_drm_cleanup.py /path/to/patched/libavutil/hwcontext_drm.c
The small adapter supplies FFmpeg interfaces and an ioctl failure; it does not
replace the resource ownership code under test. No DRM hardware is required.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.read_text()
    bodies = []
    for name in ("drm_device_free", "drm_device_create"):
        match = re.search(r"static (?:void|int) " + name + r"\(.*?\n}\n", source, re.S)
        if not match:
            raise SystemExit(f"Cannot locate production function {name}")
        bodies.append(match.group())
    adapter = r'''
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
typedef struct AVDictionary AVDictionary;
typedef struct { int fd; } AVDRMDeviceContext;
typedef struct AVHWDeviceContext {
    void *hwctx;
    void (*free)(struct AVHWDeviceContext *);
} AVHWDeviceContext;
typedef struct {
    AVDRMDeviceContext ctx;
    AVDictionary *opts;
    uint32_t *fmts;
} drm_dev_ctx;
typedef struct { char *name; int version_major, version_minor, version_patchlevel; } *drmVersionPtr;
#define AVERROR(e) (-(e))
#define AV_LOG_ERROR 1
#define AV_LOG_VERBOSE 2
#define av_log(...) ((void)0)
static int closes, canary = -1;
static int checked_close(int fd) {
    int rc = close(fd);
    ++closes;
    if (closes == 1) {
        canary = open("/dev/null", O_RDONLY);
        if (canary != fd) { fprintf(stderr, "FD reuse setup failed\n"); exit(2); }
    }
    return rc;
}
#define close checked_close
static void av_dict_free(AVDictionary **p) { (void)p; }
static void av_freep(void *p) { (void)p; }
static int av_dict_copy(AVDictionary **d, const AVDictionary *s, int f) {
    (void)d; (void)s; (void)f; abort();
}
static uint32_t *mk_fmt_list(AVHWDeviceContext *c, AVDictionary *d) {
    (void)c; (void)d; abort();
}
static drmVersionPtr drmGetVersion(int fd) {
    if (fcntl(fd, F_GETFD) < 0) abort();
    errno = ENOTTY;
    return NULL;
}
static void drmFreeVersion(drmVersionPtr p) { (void)p; abort(); }
'''
    harness = r'''
#undef close
int main(void) {
    drm_dev_ctx ctx = {0};
    AVHWDeviceContext hwdev = {.hwctx = &ctx};
    int rc = drm_device_create(&hwdev, "/dev/null", NULL, 0);
    if (rc != AVERROR(EINVAL) || !hwdev.free) return 2;
    /* av_hwdevice_ctx_create unreferences its context on create failure. */
    hwdev.free(&hwdev);
    int alive = fcntl(canary, F_GETFD) >= 0;
    if (alive) close(canary);
    if (closes != 1 || !alive) {
        fprintf(stderr, "FAIL: cleanup closes=%d, reused descriptor intact=%d\n", closes, alive);
        return 1;
    }
    puts("PASS: DRM failure closes once and preserves the reused descriptor");
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="ffmpeg-drm-cleanup-") as directory:
        test = Path(directory) / "test.c"
        binary = Path(directory) / "test"
        test.write_text(adapter + "\n".join(bodies) + harness)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Wno-unused-parameter",
                        str(test), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
