#include "algorithms.h"
#include <stdint.h>
#include <string.h>

#define BA_MAX_PATTERN 64

extern int flowscan_search(const char *text,    int text_len,
                           const char *pattern, int pat_len,
                           int *positions,      int max_res);

int bitanchor_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    
    if (pat_len > BA_MAX_PATTERN)
        return flowscan_search(text, text_len, pattern, pat_len,
                               positions, max_res);

    
    uint64_t D[256];
    memset(D, 0, sizeof D);
    for (int j = 0; j < pat_len; j++)
        D[(unsigned char)pattern[j]] |= (uint64_t)1 << j;

    const uint64_t match_bit = (uint64_t)1 << (pat_len - 1);
    uint64_t state = 0;
    int      count = 0;
    int      i     = 0;

    while (i < text_len) {
        
        if (state == 0) {
            const char *hit = (const char *)memchr(text + i,
                                                   (unsigned char)pattern[0],
                                                   (size_t)(text_len - i));
            if (!hit) break;
            i = (int)(hit - text);
        }

        state = ((state << 1) | 1) & D[(unsigned char)text[i]];

        if (state & match_bit) {
            if (count < max_res)
                positions[count] = i - pat_len + 1;
            count++;
        }

        i++;
    }

    return count;
}
