#include "algorithms.h"
#include <stdlib.h>
#include <string.h>

void skipstride_build_bad_char(const char *pattern, int pat_len,
                               int bc[ALPHABET_SIZE]) {
    for (int i = 0; i < ALPHABET_SIZE; i++) bc[i] = -1;
    for (int i = 0; i < pat_len;      i++) bc[(unsigned char)pattern[i]] = i;
}

void skipstride_build_good_suffix(const char *pattern, int pat_len, int *gs) {
    int *border = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    if (!border) return;

    for (int i = 0; i <= pat_len; i++) gs[i] = 0;

    int i = pat_len;
    int j = pat_len + 1;
    border[i] = j;

    while (i > 0) {
        while (j <= pat_len && pattern[i - 1] != pattern[j - 1]) {
            if (gs[j] == 0) gs[j] = j - i;
            j = border[j];
        }
        border[--i] = --j;
    }

    j = border[0];
    for (i = 0; i <= pat_len; i++) {
        if (gs[i] == 0) gs[i] = j;
        if (i == j)     j = border[j];
    }

    free(border);
}

int skipstride_search(const char *text,    int text_len,
                      const char *pattern, int pat_len,
                      int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    int bc[ALPHABET_SIZE];
    skipstride_build_bad_char(pattern, pat_len, bc);

    int *gs = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    if (!gs) return -1;
    skipstride_build_good_suffix(pattern, pat_len, gs);

    int count = 0;
    int s = 0;

    while (s <= text_len - pat_len) {
        int j = pat_len - 1;

        while (j >= 0 && pattern[j] == text[s + j])
            j--;

        if (j < 0) {
            if (count < max_res)
                positions[count++] = s;
            s += gs[0];
        } else {
            int bc_shift = j - bc[(unsigned char)text[s + j]];
            int gs_shift = gs[j + 1];
            int shift    = (bc_shift > gs_shift) ? bc_shift : gs_shift;
            if (shift < 1) shift = 1;

            
            if (s + pat_len < text_len) {
                unsigned char beyond = (unsigned char)text[s + pat_len];
                int sunday_shift = pat_len - bc[(int)beyond];
                if (sunday_shift < 1) sunday_shift = 1;
                if (sunday_shift > shift) shift = sunday_shift;
            }

            s += shift;
        }
    }

    free(gs);
    return count;
}
