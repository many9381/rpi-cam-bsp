/* Bounded source regression: recursive cleanup must not exhaust the stack;
 * every node and child allocation must be released, and serialization kept. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libavutil/encryption_info.h"
#include "libavutil/intreadwrite.h"
#include "libavutil/mem.h"

static AVEncryptionInitInfo *chain(unsigned count)
{
    AVEncryptionInitInfo *head = NULL, **tail = &head;
    for (unsigned i = 0; i < count; i++) {
        AVEncryptionInitInfo *n = av_encryption_init_info_alloc(1, 2, 1, 1);
        if (!n) exit(3);
        n->system_id[0] = 0x10 + (i & 15);
        n->key_ids[0][0] = 0x20;
        n->key_ids[1][0] = 0x30;
        n->data[0] = 0x40;
        *tail = n;
        tail = &n->next;
    }
    return head;
}

int main(int argc, char **argv)
{
    AVEncryptionInitInfo *info, *parsed;
    uint8_t *data;
    size_t size = 0;
    unsigned count;
    if (argc != 2) return 2;
    if (!strcmp(argv[1], "null")) {
        av_encryption_init_info_free(NULL);
        puts("null cleanup passed");
        return 0;
    }
    if (!strcmp(argv[1], "empty")) {
        info = av_encryption_init_info_alloc(0, 0, 0, 0);
        if (!info) return 3;
        av_encryption_init_info_free(info);
        puts("empty node cleanup passed");
        return 0;
    }
    count = !strcmp(argv[1], "small") ? 2 : 20000;
    info = chain(count);
    if (!strcmp(argv[1], "long-free")) {
        av_encryption_init_info_free(info);
        puts("20000 fully populated nodes released");
        return 0;
    }
    data = av_encryption_init_info_add_side_data(info, &size);
    if (!data || size != 4 + 20 * count || AV_RB32(data) != count) return 4;
    if (count == 2) {
        static const uint8_t expected[] = {
            0,0,0,2,
            0,0,0,1, 0,0,0,2, 0,0,0,1, 0,0,0,1, 0x10,0x20,0x30,0x40,
            0,0,0,1, 0,0,0,2, 0,0,0,1, 0,0,0,1, 0x11,0x20,0x30,0x40
        };
        if (sizeof(expected) != size || memcmp(data, expected, size)) return 5;
    }
    if (!strcmp(argv[1], "truncated-long")) {
        /* Decoder must release 19999 complete nodes on a truncated final one. */
        parsed = av_encryption_init_info_get_side_data(data, size - 1);
        if (parsed) return 6;
    } else {
        unsigned found = 0;
        parsed = av_encryption_init_info_get_side_data(data, size);
        if (!parsed) return 7;
        for (AVEncryptionInitInfo *p = parsed; p; p = p->next, found++) {
            if (p->system_id_size != 1 || p->num_key_ids != 2 || p->key_id_size != 1 ||
                p->data_size != 1 || p->system_id[0] != 0x10 + (found & 15) ||
                p->key_ids[0][0] != 0x20 || p->key_ids[1][0] != 0x30 || p->data[0] != 0x40)
                return 8;
        }
        if (found != count) return 9;
        av_encryption_init_info_free(parsed);
    }
    av_free(data);
    av_encryption_init_info_free(info);
    printf("%s serialization/cleanup passed (%u nodes)\n", argv[1], count);
    return 0;
}
