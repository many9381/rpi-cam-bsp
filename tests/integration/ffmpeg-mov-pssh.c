/* Exercise the real MOV demuxer through public libavformat APIs.
 * The independent Python fixture builder supplies exact expected wire bytes.
 * Link static production libraries with --wrap for the four allocators below.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libavformat/avformat.h"
#include "libavcodec/codec_par.h"
#include "libavutil/intreadwrite.h"
#include "libavutil/mem.h"

static uint64_t calls, requested, growths, growth_bytes;
static int fail_insertion;
#ifdef TRACE_PSSH_GROWTH
#include "libavutil/encryption_info.h"
static int appending_pssh;
static uint64_t pssh_growths, pssh_growth_bytes, pssh_moved_prefix_bytes;
int __real_av_encryption_init_info_append_side_data(uint8_t **data, size_t *size,
    unsigned *capacity, const AVEncryptionInitInfo *info);
int __wrap_av_encryption_init_info_append_side_data(uint8_t **data, size_t *size,
    unsigned *capacity, const AVEncryptionInitInfo *info)
{
    uintptr_t before = (uintptr_t)*data;
    size_t old_size = *data ? *size : 0;
    appending_pssh = 1;
    int result = __real_av_encryption_init_info_append_side_data(data, size, capacity, info);
    appending_pssh = 0;
    if (result >= 0 && before && before != (uintptr_t)*data)
        pssh_moved_prefix_bytes += old_size;
    return result;
}
#endif
void *__real_av_malloc(size_t n);
void *__real_av_mallocz(size_t n);
void *__real_av_calloc(size_t n, size_t s);
void *__real_av_realloc(void *p, size_t n);
void *__real_av_fast_realloc(void *p, unsigned *capacity, size_t n);
AVPacketSideData *__real_av_packet_side_data_add(AVPacketSideData **sd, int *nb,
    enum AVPacketSideDataType type, void *data, size_t size, int flags);
AVPacketSideData *__wrap_av_packet_side_data_add(AVPacketSideData **sd, int *nb,
    enum AVPacketSideDataType type, void *data, size_t size, int flags)
{
    if (fail_insertion && type == AV_PKT_DATA_ENCRYPTION_INIT_INFO) {
        fail_insertion = 0;
        return NULL;
    }
    return __real_av_packet_side_data_add(sd, nb, type, data, size, flags);
}
void *__wrap_av_malloc(size_t n) { calls++; requested += n; return __real_av_malloc(n); }
void *__wrap_av_mallocz(size_t n) { calls++; requested += n; return __real_av_mallocz(n); }
void *__wrap_av_calloc(size_t n, size_t s) { calls++; requested += n*s; return __real_av_calloc(n,s); }
void *__wrap_av_realloc(void *p, size_t n) { calls++; requested += n; return __real_av_realloc(p,n); }
void *__wrap_av_fast_realloc(void *p, unsigned *capacity, size_t n)
{
    if (n > *capacity) { growths++; growth_bytes += n; }
#ifdef TRACE_PSSH_GROWTH
    if (appending_pssh && n > *capacity) { pssh_growths++; pssh_growth_bytes += n; }
#endif
    return __real_av_fast_realloc(p, capacity, n);
}

static int check(AVFormatContext *ctx, const char *prefix, int final)
{
    char missing[4096];
    if (!ctx->nb_streams) return 1;
    snprintf(missing, sizeof(missing), "%s.%u.bin", prefix, ctx->nb_streams);
    FILE *extra = fopen(missing, "rb");
    if (extra) { fclose(extra); fputs("FAIL missing expected stream\n", stderr); return 1; }
    for (unsigned i = 0; i < ctx->nb_streams; i++) {
        char name[4096];
        snprintf(name, sizeof(name), "%s.%u.bin", prefix, i);
        FILE *f = fopen(name, "rb");
        if (!f) return 1;
        fseek(f, 0, SEEK_END);
        long size = ftell(f);
        rewind(f);
        uint8_t *expected = malloc(size ? size : 1);
        if (!expected || fread(expected, 1, size, f) != (size_t)size) return 1;
        fclose(f);
        const AVPacketSideData *sd = av_packet_side_data_get(
            ctx->streams[i]->codecpar->coded_side_data,
            ctx->streams[i]->codecpar->nb_coded_side_data, AV_PKT_DATA_ENCRYPTION_INIT_INFO);
        int bad = !size ? sd != NULL : !sd || sd->size < 4 || sd->size > (size_t)size ||
            (final && sd->size != (size_t)size) ||
            (sd && AV_RB32(sd->data) > AV_RB32(expected)) ||
            (sd && memcmp(sd->data + 4, expected + 4, sd->size - 4)) ||
            (final && sd && AV_RB32(sd->data) != AV_RB32(expected));
        free(expected);
        if (bad) { fprintf(stderr, "FAIL side data stream %u final %d\n", i, final); return 1; }
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 5) return 2;
    unsigned n = strtoul(argv[4], NULL, 10);
    int discover = !strcmp(argv[3], "discover");
    int copy = !strcmp(argv[3], "copy") || discover, bounded = !strcmp(argv[3], "bounded");
    AVFormatContext *ctx = avformat_alloc_context();
    if (!ctx) return 2;
    ctx->flags |= AVFMT_FLAG_IGNIDX;
    ctx->max_analyze_duration = 1;
    fail_insertion = !strcmp(argv[3], "insertion-failure");
    av_log_set_level(AV_LOG_ERROR);
    int ret = avformat_open_input(&ctx, argv[1], NULL, NULL);
    if (!strcmp(argv[3], "insertion-failure")) {
        int ok = ret == AVERROR(ENOMEM) && !ctx && !fail_insertion;
        avformat_close_input(&ctx);
        puts(ok ? "PASS: insertion ENOMEM propagated and context released" : "FAIL: insertion ENOMEM lost");
        return !ok;
    }
    if (ret < 0) { fprintf(stderr, "FAIL open %d\n", ret); return 1; }
    if (check(ctx, argv[2], 0)) return 1;
    if (discover) {
        if (avformat_find_stream_info(ctx, NULL) < 0 || check(ctx, argv[2], 0)) return 1;
        const AVPacketSideData *sd = av_packet_side_data_get(ctx->streams[0]->codecpar->coded_side_data,
            ctx->streams[0]->codecpar->nb_coded_side_data, AV_PKT_DATA_ENCRYPTION_INIT_INFO);
        if (!sd || AV_RB32(sd->data) >= n) return 1;
        printf("records_after_discovery=%u final_expected=%u\n", AV_RB32(sd->data), n);
    }
    AVPacket *pkt = av_packet_alloc();
    unsigned packets = 0, copies = 0;
    while (1) {
        if (copy) {
            for (unsigned i = 0; i < ctx->nb_streams; i++) {
                AVCodecParameters *tmp = avcodec_parameters_alloc();
                if (!tmp || avcodec_parameters_copy(tmp, ctx->streams[i]->codecpar) < 0 ||
                    avcodec_parameters_copy(ctx->streams[i]->codecpar, tmp) < 0) return 1;
                avcodec_parameters_free(&tmp);
                copies++;
            }
        }
        ret = av_read_frame(ctx, pkt);
        if (ret < 0) break;
        if (check(ctx, argv[2], 0)) return 1;
        packets++;
        av_packet_unref(pkt);
    }
    if (ret != AVERROR_EOF || !packets || check(ctx, argv[2], 1)) return 1;
    av_packet_free(&pkt);
    avformat_close_input(&ctx);
    printf("packets=%u copies=%u allocations=%llu requested_bytes=%llu growths=%llu growth_bytes=%llu records=%u\n",
           packets, copies, (unsigned long long)calls, (unsigned long long)requested,
           (unsigned long long)growths, (unsigned long long)growth_bytes, n);
#ifdef TRACE_PSSH_GROWTH
    printf("pssh_growths=%llu pssh_growth_bytes=%llu relocated_logical_prefix_bytes=%llu\n",
           (unsigned long long)pssh_growths, (unsigned long long)pssh_growth_bytes,
           (unsigned long long)pssh_moved_prefix_bytes);
#endif
    /* Detect repeated reconstruction of old records; allow ample demux overhead. */
    if (bounded && calls > 64ULL*n + 10000) {
        fputs("FAIL superlinear allocation work\n", stderr);
        return 1;
    }
    if (bounded && growth_bytes > 2048ULL*n + 65536) {
        fputs("FAIL superlinear growth requests\n", stderr);
        return 1;
    }
    puts("PASS");
    return 0;
}
