#include "algorithms.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define TM_BITAP_MAX   64   
#define TM_MAX_ERRORS   5   

static int bitap_tiermatch(const char *text,    int text_len,
                           const char *pattern, int pat_len,
                           int         max_err,
                           int        *positions, int max_res) {
    
    uint64_t D[256];
    memset(D, 0, sizeof D);
    for (int j = 0; j < pat_len; j++)
        D[(unsigned char)pattern[j]] |= (uint64_t)1 << j;

    const uint64_t match_bit = (uint64_t)1 << (pat_len - 1);

    
    uint64_t R[TM_MAX_ERRORS + 1];
    uint64_t old_R[TM_MAX_ERRORS + 1];
    memset(R, 0, sizeof(uint64_t) * (size_t)(max_err + 1));

    int count = 0;

    for (int i = 0; i < text_len; i++) {
        memcpy(old_R, R, sizeof(uint64_t) * (size_t)(max_err + 1));

        unsigned char t = (unsigned char)text[i];

        
        R[0] = ((R[0] << 1) | 1) & D[t];

        
        for (int d = 1; d <= max_err; d++) {
            R[d] = ((R[d] << 1) | 1) & D[t]   
                 | old_R[d - 1]                
                 | (old_R[d - 1] << 1)         
                 | (R[d - 1] << 1);            
        }

        
        for (int d = 0; d <= max_err; d++) {
            if (R[d] & match_bit) {
                
                int pos = i - pat_len + 1;
                if (pos < 0) pos = 0;
                if (count < max_res)
                    positions[count] = pos;
                count++;

                
                for (int dd = d + 1; dd <= max_err; dd++)
                    R[dd] &= ~match_bit;

                break; 
            }
        }
    }
    return count;
}

static int dp_tiermatch(const char *text,    int text_len,
                        const char *pattern, int pat_len,
                        int         max_err,
                        int        *positions, int max_res) {
    int *dp   = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    int *prev = (int *)malloc((size_t)(pat_len + 1) * sizeof(int));
    if (!dp || !prev) { free(dp); free(prev); return -1; }

    
    for (int j = 0; j <= pat_len; j++) dp[j] = j;

    int count = 0;

    for (int i = 0; i < text_len; i++) {
        memcpy(prev, dp, (size_t)(pat_len + 1) * sizeof(int));
        dp[0] = 0;  

        for (int j = 1; j <= pat_len; j++) {
            int cost = (text[i] == pattern[j - 1]) ? 0 : 1;
            int sub  = prev[j - 1] + cost;
            int del  = prev[j]     + 1;
            int ins  = dp[j - 1]   + 1;
            dp[j] = sub < del ? sub : del;
            if (ins < dp[j]) dp[j] = ins;
        }

        if (dp[pat_len] <= max_err) {
            if (count < max_res)
                positions[count] = i;
            count++;
        }
    }

    free(dp);
    free(prev);
    return count;
}

int tiermatch_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int         max_errors,
                     int        *positions, int max_res) {
    if (pat_len == 0 || text_len == 0) return 0;
    if (max_errors < 0) max_errors = 0;
    if (max_errors > TM_MAX_ERRORS) max_errors = TM_MAX_ERRORS;

    if (pat_len <= TM_BITAP_MAX)
        return bitap_tiermatch(text, text_len, pattern, pat_len,
                               max_errors, positions, max_res);
    else
        return dp_tiermatch(text, text_len, pattern, pat_len,
                            max_errors, positions, max_res);
}
