/* ===========================================================================
 * tiermatch.c  —  FuzzySearch approximate (k-difference) matching
 * ---------------------------------------------------------------------------
 * Project-book design (SWOT 8.6, bibliography): Wu-Manber bitap for m<=64 and
 * Myers bit-parallel dynamic programming (G. Myers, JACM 1999) for m>64,
 * replacing the O(n*m) naive DP. The Myers path encodes the column's
 * vertical deltas in VP/VN bit-vectors and, for m>64, uses the multi-word
 * block formulation with K = ceil(m/64) words and horizontal-carry
 * propagation between words, giving O(n * ceil(m/64)).
 *
 * Both paths share one reporting convention — for each text end position i
 * whose best edit distance is <= max_errors, the match start max(0, i-m+1) is
 * reported once. (The legacy DP reported the end index i, which the display
 * layer then discarded near end-of-text; Myers is made consistent with the
 * bitap path here.) max_errors stays capped at 5; the signature is unchanged.
 * =========================================================================== */
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

/* Myers bit-parallel DP (JACM 1999), multi-word block version for m > 64.
 * VP/VN hold the column's vertical deltas; horizontal carries (hin/hout in
 * {-1,0,+1}) propagate between the K = ceil(m/64) words. The running `score`
 * tracks D[m][i] (bottom-right cell) via the bottom-row horizontal delta,
 * which lives in the last word at bit (m-1) mod 64. */
static int myers_tiermatch(const char *text,    int text_len,
                           const char *pattern, int pat_len,
                           int         max_err,
                           int        *positions, int max_res) {
    int K = (pat_len + 63) / 64;

    uint64_t *Peq = (uint64_t *)calloc((size_t)256 * K, sizeof(uint64_t));
    uint64_t *VP  = (uint64_t *)malloc((size_t)K * sizeof(uint64_t));
    uint64_t *VN  = (uint64_t *)malloc((size_t)K * sizeof(uint64_t));
    if (!Peq || !VP || !VN) { free(Peq); free(VP); free(VN); return -1; }

    for (int j = 0; j < pat_len; j++)
        Peq[(size_t)(unsigned char)pattern[j] * K + (j >> 6)]
            |= (uint64_t)1 << (j & 63);

    for (int b = 0; b < K; b++) { VP[b] = ~(uint64_t)0; VN[b] = 0; }

    const int      lb          = K - 1;                         /* last word */
    const uint64_t bottom_mask = (uint64_t)1 << ((pat_len - 1) & 63);
    const uint64_t TOP_BIT     = (uint64_t)1 << 63;

    int score = pat_len;        /* D[m][-1] = m */
    int count = 0;

    for (int i = 0; i < text_len; i++) {
        const uint64_t *Prow = Peq + (size_t)(unsigned char)text[i] * K;
        int hin = 0;            /* free-start search: 0 horizontal carry into word 0 */

        for (int b = 0; b < K; b++) {
            uint64_t Eq  = Prow[b];
            uint64_t Pvb = VP[b], Mvb = VN[b];
            uint64_t Xv  = Eq | Mvb;
            if (hin < 0) Eq |= (uint64_t)1;

            uint64_t Xh = (((Eq & Pvb) + Pvb) ^ Pvb) | Eq;
            uint64_t Ph = Mvb | ~(Xh | Pvb);
            uint64_t Mh = Pvb & Xh;

            int hout;
            if (b == lb) {                       /* bottom row → update score */
                if      (Ph & bottom_mask) score += 1;
                else if (Mh & bottom_mask) score -= 1;
                hout = 0;
            } else {                             /* inter-word horizontal carry */
                hout = (Ph & TOP_BIT) ? 1 : ((Mh & TOP_BIT) ? -1 : 0);
            }

            Ph <<= 1;
            Mh <<= 1;
            if      (hin < 0) Mh |= (uint64_t)1;
            else if (hin > 0) Ph |= (uint64_t)1;

            VP[b] = Mh | ~(Xv | Ph);
            VN[b] = Ph & Xv;
            hin   = hout;
        }

        if (score <= max_err) {
            int pos = i - pat_len + 1;
            if (pos < 0) pos = 0;
            if (count < max_res) positions[count] = pos;
            count++;
        }
    }

    free(Peq);
    free(VP);
    free(VN);
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
        return myers_tiermatch(text, text_len, pattern, pat_len,
                               max_errors, positions, max_res);
}
