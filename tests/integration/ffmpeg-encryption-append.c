/* Bounded contract checks for the production encryption-init appender. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "libavutil/encryption_info.h"
#include "libavutil/error.h"
#include "libavutil/intreadwrite.h"
#include "libavutil/mem.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)

int main(void)
{
    uint8_t sid[] = {0xaa, 0xbb}, key[] = {0x11, 0x22}, payload[] = {0xee};
    uint8_t *keys[] = {key};
    AVEncryptionInitInfo info = {.system_id=sid, .system_id_size=2,
        .key_ids=keys, .num_key_ids=1, .key_id_size=2, .data=payload, .data_size=1};
    /* Two identical records, encoded independently of the library serializer. */
    const uint8_t expected[] = {
        0,0,0,2,
        0,0,0,2, 0,0,0,1, 0,0,0,2, 0,0,0,1, 0xaa,0xbb,0x11,0x22,0xee,
        0,0,0,2, 0,0,0,1, 0,0,0,2, 0,0,0,1, 0xaa,0xbb,0x11,0x22,0xee
    };
    uint8_t *data = NULL, *old;
    size_t size = 123, old_size;
    unsigned capacity = 0;
    CHECK(av_encryption_init_info_append_side_data(&data,&size,&capacity,NULL) == 0);
    CHECK(size == 4 && AV_RB32(data) == 0);
    CHECK(av_encryption_init_info_append_side_data(&data,&size,&capacity,&info) == 0);
    CHECK(size == 25 && AV_RB32(data) == 1);
    /* Real allocation failure, with unknown capacity as after a copied buffer. */
    old = data; old_size = size; capacity = 0;
    av_max_alloc(16);
    int ret = av_encryption_init_info_append_side_data(&data,&size,&capacity,&info);
    av_max_alloc(SIZE_MAX);
    CHECK(ret == AVERROR(ENOMEM) && data == old && size == old_size && capacity == 0);
    CHECK(AV_RB32(data) == 1 && !memcmp(data+4,expected+4,size-4));
    CHECK(av_encryption_init_info_append_side_data(&data,&size,&capacity,&info) == 0);
    CHECK(size == sizeof(expected) && !memcmp(data,expected,size));
    CHECK(av_encryption_init_info_append_side_data(&data,&size,&capacity,NULL) == 0);
    CHECK(size == sizeof(expected) && !memcmp(data,expected,size));
    old=data; data=av_memdup(data,size); av_free(old); capacity=0;
    CHECK(data && av_encryption_init_info_append_side_data(&data,&size,&capacity,&info) == 0);
    CHECK(size == 67 && AV_RB32(data) == 3 && !memcmp(data+46,expected+4,21));
    old=data; old_size=size;
    AVEncryptionInitInfo huge = info;
    huge.system_id_size = UINT32_MAX;
    CHECK(av_encryption_init_info_append_side_data(&data,&size,&capacity,&huge) == AVERROR(EINVAL));
    CHECK(data == old && size == old_size && AV_RB32(data) == 3);
    for (unsigned i=3; i<20000; i++)
        CHECK(av_encryption_init_info_append_side_data(&data,&size,&capacity,&info) == 0);
    CHECK(size == 420004 && AV_RB32(data) == 20000);
    for (unsigned i=0; i<20000; i++) CHECK(!memcmp(data+4+21*i,expected+4,21));
    av_free(data);
    puts("PASS: empty, exact bytes, failure preservation/retry, writable copy, overflow preflight, 20000 appends");
    return 0;
}
