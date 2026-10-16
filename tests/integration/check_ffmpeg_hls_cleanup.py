#!/usr/bin/env python3
"""Exercise production HLS detach/reject/cleanup blocks with owned allocations.

Takes patched libavformat/hls.c. The adapter models parser control flow and
external interfaces, while executing the exact production ownership blocks.
This is a cleanup regression, not a complete HLS parser or network test.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def function(source, name):
    match = re.search(r"static (?:void|int) " + name + r"\(.*?\n}\n", source, re.S)
    if not match:
        raise ValueError(f"Production function not found: {name}")
    return match.group()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.read_text()
    parse = function(source, "parse_playlist")
    detach_start = parse.index("    if (pls) {\n        prev_start_seq_no")
    detach_end = parse.index("    while (!avio_feof(in))", detach_start)
    detach = parse[detach_start:detach_end]
    tail = parse[parse.index("    if (prev_segments) {"):]
    guards = []
    for tag in ("#EXT-X-STREAM-INF:", "#EXT-X-MEDIA:"):
        start = parse.index("            if (pls) {", parse.index('"' + tag + '"'))
        end = parse.index("\n            }", start) + len("\n            }")
        guards.append(parse[start:end])
    adapter = r'''
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define AV_NOPTS_VALUE INT64_MIN
#define AVFMTCTX_UNSEEKABLE 1
#define AVERROR_INVALIDDATA (-123)
#define PLS_TYPE_UNSPECIFIED 0
#define PLS_TYPE_EVENT 1
#define av_log(...) ((void)0)
static int live;
static void *owned(size_t n) {
    void *p = calloc(1, n);
    if (!p) abort();
    ++live;
    return p;
}
static void av_free(void *p) { if (p) { --live; free(p); } }
static void av_freep(void *p) { void **v = p; av_free(*v); *v = NULL; }
struct segment { char *key, *url; int64_t duration; };
struct playlist {
    struct segment **segments;
    int n_segments, finished, type;
    int64_t start_seq_no, last_load_time;
};
struct variant { int n_playlists; struct playlist **playlists; };
typedef struct { unsigned ctx_flags; } AVFormatContext;
typedef struct {
    AVFormatContext *ctx;
    int64_t first_timestamp;
    int n_variants;
    struct variant **variants;
} HLSContext;
static int64_t av_gettime_relative(void) { return 1; }
static void ff_format_io_close(AVFormatContext *c, void *p) { (void)c; (void)p; abort(); }
'''
    entry = r'''
static int scenario(int mode, struct playlist *pls) {
    AVFormatContext format = {0};
    HLSContext context = {.ctx = &format, .first_timestamp = AV_NOPTS_VALUE};
    HLSContext *c = &context;
    struct segment **prev_segments = NULL;
    int prev_n_segments = 0, close_in = 0, ret = 0;
    int64_t prev_start_seq_no = -1;
    void *in = NULL;
    char *new_url = NULL;
    if (mode == 3) { ret = AVERROR_INVALIDDATA; goto fail; }
'''
    tests = r'''
int main(void) {
    for (int mode = 0; mode < 5; mode++) {
        struct playlist pls = {0};
        if (mode != 4) {
            pls.n_segments = 2;
            pls.segments = owned(2 * sizeof(*pls.segments));
            for (int i = 0; i < 2; i++) {
                pls.segments[i] = owned(sizeof(**pls.segments));
                pls.segments[i]->key = owned(4);
                pls.segments[i]->url = owned(8);
            }
        }
        int ret = scenario(mode, &pls);
        int rejected = mode >= 1 && mode <= 3;
        if (ret != (rejected ? AVERROR_INVALIDDATA : 0)) return 2;
        if (mode == 3 && (pls.n_segments != 2 || live != 7)) return 2;
        free_segment_list(&pls);
        if (live != 0) {
            fprintf(stderr, "FAIL: scenario=%d leaves %d owned allocations\n", mode, live);
            return 1;
        }
    }
    puts("PASS: normal reload, both rejected tags, early failure and empty reload release ownership correctly");
    return 0;
}
'''
    code = adapter + function(source, "free_segment_dynarray") + function(source, "free_segment_list")
    code += entry + detach
    for mode, guard in enumerate(guards, 1):
        code += f"    if (mode == {mode}) {{\n" + guard + "\n    }\n"
    code += tail + tests
    with tempfile.TemporaryDirectory(prefix="ffmpeg-hls-cleanup-") as directory:
        path = Path(directory) / "test.c"
        binary = Path(directory) / "test"
        path.write_text(code)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Wno-unused-variable",
                        str(path), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
