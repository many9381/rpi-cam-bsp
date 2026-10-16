/* Exercise real encryption-info allocation/cleanup with deterministic failures.
 * Link encryption_info.c with --wrap=av_mallocz,--wrap=av_calloc,--wrap=av_free.
 * A missing NULL key-array guard fails fail-3 and zero-key-size; leaking any
 * owned allocation fails the live-allocation check, independently of sanitizers.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libavutil/encryption_info.h"

void *__real_av_mallocz(size_t size);
void *__real_av_calloc(size_t count, size_t size);
void __real_av_free(void *ptr);

static void *live[64];
static unsigned calls, fail_at, live_count;

static void *remember(void *ptr)
{
    if (ptr) {
        if (live_count == sizeof(live) / sizeof(live[0])) exit(20);
        live[live_count++] = ptr;
    }
    return ptr;
}

void *__wrap_av_mallocz(size_t size)
{
    if (++calls == fail_at) return NULL;
    return remember(__real_av_mallocz(size));
}

void *__wrap_av_calloc(size_t count, size_t size)
{
    if (++calls == fail_at) return NULL;
    return remember(__real_av_calloc(count, size));
}

void __wrap_av_free(void *ptr)
{
    if (ptr) {
        unsigned i;
        for (i = 0; i < live_count && live[i] != ptr; i++) {}
        if (i == live_count) exit(21);
        live[i] = live[--live_count];
    }
    __real_av_free(ptr);
}

int main(int argc, char **argv)
{
    AVEncryptionInitInfo *info;
    unsigned keys = 2, key_size = 1;
    if (argc != 2) return 2;
    if (strlen(argv[1]) == 6 && !strncmp(argv[1], "fail-", 5) &&
        argv[1][5] >= '1' && argv[1][5] <= '6') {
        fail_at = (unsigned)(argv[1][5] - '0');
    } else if (!strcmp(argv[1], "zero-key-size")) {
        key_size = 0;
    } else if (!strcmp(argv[1], "zero-key-count")) {
        keys = 0;
    } else if (strcmp(argv[1], "normal")) {
        return 2;
    }
    info = av_encryption_init_info_alloc(1, keys, key_size, 1);
    if (fail_at) {
        if (calls < fail_at || info) return 3;
    } else {
        if (!info || info->num_key_ids != keys || info->key_id_size != key_size ||
            !info->system_id || !info->data) return 4;
        if (keys && key_size && (!info->key_ids || !info->key_ids[0] || !info->key_ids[1])) return 5;
        if (!key_size && info->key_ids) return 6;
        av_encryption_init_info_free(info);
    }
    if (live_count) return 7;
    printf("%s: no owned allocations remain\n", argv[1]);
    return 0;
}
