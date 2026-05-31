#ifndef ALGORITHMS_H
#define ALGORITHMS_H

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

#define MAX_RESULTS   1000000

#define ALPHABET_SIZE 256

void dnascan_build_lps(const char *pattern, int pat_len, int *lps);

int dnascan_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res);

void gapjump_build_bad_char(const char *pattern, int pat_len, int bc[ALPHABET_SIZE]);
void gapjump_build_good_suffix(const char *pattern, int pat_len, int *gs);

int gapjump_search(const char *text,    int text_len,
                      const char *pattern, int pat_len,
                      int *positions,      int max_res);

int dualrabin_search(const char *text,    int text_len,
                    const char *pattern, int pat_len,
                    int *positions,      int max_res);

int bitmatch_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int *positions,      int max_res);

int sweeprun_search(const char *text,    int text_len,
                   const char *pattern, int pat_len,
                   int *positions,      int max_res);

/* True multi-pattern Aho-Corasick. Reports (position, pattern_id) pairs in
 * positions[]/pattern_ids[] (pattern_ids may be NULL to ignore ids). Returns
 * the match count, or a negative value on allocation failure. */
int sweeprun_search_multi(const char *text, int text_len,
                         const char **patterns, const int *pat_lens,
                         int n_patterns,
                         int *positions, int *pattern_ids, int max_res);

int fuzzysearch_search(const char *text,    int text_len,
                     const char *pattern, int pat_len,
                     int         max_errors,
                     int        *positions, int max_res);

#endif 
