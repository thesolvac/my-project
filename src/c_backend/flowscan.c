#include "algorithms.h"
#include <stdlib.h>
#include <string.h>

void flowscan_build_lps(const char *pattern, int pat_len, int *lps) {
    int len = 0;
    lps[0]  = 0;
    int i   = 1;

    while (i < pat_len) {
        if (pattern[i] == pattern[len]) {
            lps[i] = ++len;
            i++;
        } else if (len != 0) {
            len = lps[len - 1];
        } else {
            lps[i] = 0;
            i++;
        }
    }
}

int flowscan_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    int *lps = (int *)malloc((size_t)pat_len * sizeof(int));
    if (!lps) return -1;

    flowscan_build_lps(pattern, pat_len, lps);

    int count = 0;
    int i = 0;   
    int j = 0;   

    while (i < text_len) {
        
        if (j == 0) {
            const char *hit = (const char *)memchr(text + i,
                                                   (unsigned char)pattern[0],
                                                   (size_t)(text_len - i));
            if (!hit) break;          
            i = (int)(hit - text);
        }

        if (pattern[j] == text[i]) {
            i++;
            j++;
        }

        if (j == pat_len) {
            if (count < max_res)
                positions[count++] = i - pat_len;
            j = lps[j - 1];
        } else if (i < text_len && pattern[j] != text[i]) {
            if (j != 0)
                j = lps[j - 1];
            else
                i++;
        }
    }

    free(lps);
    return count;
}
