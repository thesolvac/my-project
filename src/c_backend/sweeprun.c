/* ===========================================================================
 * sweeprun.c  —  SweepRun multi-pattern matching
 * ---------------------------------------------------------------------------
 * Project-book design (SWOT 8.5, §21.3.4): a true multi-pattern Aho-Corasick
 * automaton, replacing the single-pattern "AC in disguise".
 *
 *   sweeprun_search_multi() builds a trie over ALL patterns, computes failure
 *   links by BFS, propagates dictionary-suffix (output) links so that every
 *   pattern that is a suffix of the current path is reported, densifies the
 *   goto table into a full DFA for O(1) transitions, and uses a 256-bit
 *   presence bitmap to bypass the DFA for bytes absent from every pattern.
 *   It returns (position, pattern_id) pairs.
 *
 *   sweeprun_search() is preserved unchanged in signature: it is now a thin
 *   wrapper that runs the multi-pattern engine over a single pattern (with a
 *   NULL pattern_ids buffer), so all existing callers keep working.
 * =========================================================================== */
#include "algorithms.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    int child[ALPHABET_SIZE];   /* densified goto: always valid after BFS    */
    int fail;                   /* failure link                              */
    int out_link;               /* nearest terminal proper fail-ancestor, -1 */
    int term_head;              /* head of pattern-id list ending here, or -1 */
} AcNode;

int sweeprun_search_multi(const char *text, int text_len,
                         const char **patterns, const int *pat_lens,
                         int n_patterns,
                         int *positions, int *pattern_ids, int max_res) {
    if (text_len == 0 || n_patterns <= 0) return 0;

    /* upper bound on node count: one root + total pattern length */
    long total = 1;
    for (int p = 0; p < n_patterns; p++)
        if (pat_lens[p] > 0) total += pat_lens[p];

    AcNode *nodes = (AcNode *)malloc((size_t)total * sizeof(AcNode));
    int    *id_next = (int *)malloc((size_t)n_patterns * sizeof(int));
    int    *queue   = (int *)malloc((size_t)total * sizeof(int));
    if (!nodes || !id_next || !queue) {
        free(nodes); free(id_next); free(queue);
        return -1;
    }

    /* root */
    for (int c = 0; c < ALPHABET_SIZE; c++) nodes[0].child[c] = -1;
    nodes[0].fail = 0; nodes[0].out_link = -1; nodes[0].term_head = -1;
    int node_count = 1;

    /* 256-bit presence bitmap over all pattern bytes */
    uint64_t presence[4];
    memset(presence, 0, sizeof presence);

    /* insert every (non-empty) pattern into the trie */
    for (int p = 0; p < n_patterns; p++) {
        int m = pat_lens[p];
        if (m <= 0) { id_next[p] = -1; continue; }
        int cur = 0;
        for (int k = 0; k < m; k++) {
            unsigned char c = (unsigned char)patterns[p][k];
            presence[c >> 6] |= (uint64_t)1 << (c & 63);
            if (nodes[cur].child[c] == -1) {
                int nc = node_count++;
                for (int x = 0; x < ALPHABET_SIZE; x++) nodes[nc].child[x] = -1;
                nodes[nc].fail = 0; nodes[nc].out_link = -1;
                nodes[nc].term_head = -1;
                nodes[cur].child[c] = nc;
                cur = nc;
            } else {
                cur = nodes[cur].child[c];
            }
        }
        id_next[p]          = nodes[cur].term_head;   /* chain duplicates */
        nodes[cur].term_head = p;
    }

    /* BFS: failure links, output links, and goto densification */
    int head = 0, tail = 0;
    for (int c = 0; c < ALPHABET_SIZE; c++) {
        int ch = nodes[0].child[c];
        if (ch != -1) {
            nodes[ch].fail     = 0;
            nodes[ch].out_link = -1;          /* root is never terminal */
            queue[tail++]      = ch;
        } else {
            nodes[0].child[c] = 0;
        }
    }
    while (head < tail) {
        int u = queue[head++];
        for (int c = 0; c < ALPHABET_SIZE; c++) {
            int v = nodes[u].child[c];
            if (v == -1) {
                nodes[u].child[c] = nodes[nodes[u].fail].child[c];
            } else {
                int f = nodes[nodes[u].fail].child[c];
                nodes[v].fail     = f;
                nodes[v].out_link = (nodes[f].term_head != -1)
                                  ? f : nodes[f].out_link;
                queue[tail++]     = v;
            }
        }
    }

    int count = 0;
    int state = 0;
    for (int i = 0; i < text_len; i++) {
        unsigned char c = (unsigned char)text[i];

        /* bytes absent from every pattern send the DFA back to the root */
        if (!(presence[c >> 6] & ((uint64_t)1 << (c & 63)))) {
            state = 0;
            continue;
        }

        state = nodes[state].child[c];

        /* report this node's terminals, then walk the output-link chain */
        for (int w = state; w != -1; w = nodes[w].out_link) {
            for (int p = nodes[w].term_head; p != -1; p = id_next[p]) {
                int pos = i - pat_lens[p] + 1;
                if (count < max_res) {
                    positions[count] = pos;
                    if (pattern_ids) pattern_ids[count] = p;
                }
                count++;
            }
        }
    }

    free(nodes); free(id_next); free(queue);
    return count;
}

int sweeprun_search(const char *text,    int text_len,
                   const char *pattern, int pat_len,
                   int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    const char *patterns[1] = { pattern };
    int         pat_lens[1] = { pat_len };
    /* single-pattern callers don't supply an id buffer → pass NULL */
    return sweeprun_search_multi(text, text_len, patterns, pat_lens, 1,
                                positions, NULL, max_res);
}
