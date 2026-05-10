/**
 * Aho-Corasick Automaton — Single-Pattern Adapter
 * =================================================
 *
 * Builds a complete DFA from a single pattern using the classic
 * Aho-Corasick construction (trie + BFS failure links), then searches
 * the text in a single left-to-right pass with no backtracking.
 *
 * Construction (O(m · σ)):
 *   1. Build a trie for the pattern (m+1 nodes).
 *   2. Compute failure links via BFS: fail[v] is the longest proper
 *      suffix of the string represented by v that is also a prefix of
 *      some pattern (here, the pattern itself).
 *   3. Fill in "goto" for missing edges so every state has a transition
 *      for every byte value — producing a complete DFA with no failure
 *      links needed at query time.
 *
 * Search (O(n)):
 *   Follow DFA transitions for each text byte.  Emit a match whenever
 *   the current state is the accepting state.
 *
 * Complexity
 *   Preprocessing  O(m · σ)  where σ = 256 (byte alphabet)
 *   Search         O(n)
 *   Space          O((m + 1) · σ)  ≈ 1 KB per pattern character
 *
 * When APME prefers Aho-Corasick
 *   - Simultaneous search for tens to thousands of patterns (the
 *     multi-pattern API is the primary use case)
 *   - The single-pattern adapter here demonstrates the automaton
 *     correctly and shares the same function signature as the other
 *     algorithms, making it directly comparable in benchmark mode
 *
 * Reference: Aho & Corasick, "Efficient String Matching: An Aid to
 *            Bibliographic Search", CACM 18(6), 1975.
 */

#include "algorithms.h"
#include <stdlib.h>
#include <string.h>

/* One DFA node: a full transition table + failure link + output flag */
typedef struct {
    int child[ALPHABET_SIZE];  /* child[c] = next state on byte c */
    int fail;                  /* failure link (longest proper border) */
    int output;                /* 1 = this state is an accepting state */
} AcNode;


static AcNode *build_dfa(const char *pattern, int m) {
    /* Allocate m+1 nodes (root = 0, pattern prefixes = 1..m) */
    AcNode *nodes = (AcNode *)malloc((size_t)(m + 1) * sizeof(AcNode));
    if (!nodes) return NULL;

    /* Initialise every node: no children, fail → root, not accepting */
    for (int i = 0; i <= m; i++) {
        for (int c = 0; c < ALPHABET_SIZE; c++) nodes[i].child[c] = -1;
        nodes[i].fail   = 0;
        nodes[i].output = 0;
    }

    /* Build the single-path trie 0 → 1 → 2 → … → m */
    for (int j = 0; j < m; j++)
        nodes[j].child[(unsigned char)pattern[j]] = j + 1;
    nodes[m].output = 1;

    /* BFS to compute failure links and complete all transitions */
    int *queue = (int *)malloc((size_t)(m + 1) * sizeof(int));
    if (!queue) { free(nodes); return NULL; }
    int head = 0, tail = 0;

    /* Root's direct children: failure = root; others redirect to root */
    for (int c = 0; c < ALPHABET_SIZE; c++) {
        int ch = nodes[0].child[c];
        if (ch != -1) {
            nodes[ch].fail = 0;
            queue[tail++]  = ch;
        } else {
            nodes[0].child[c] = 0;  /* missing → stay at root */
        }
    }

    while (head < tail) {
        int u = queue[head++];
        for (int c = 0; c < ALPHABET_SIZE; c++) {
            int v = nodes[u].child[c];
            if (v != -1) {
                /* Failure link of v = transition from u's failure on c */
                nodes[v].fail = nodes[nodes[u].fail].child[c];
                /* Propagate output (for overlapping matches) */
                nodes[v].output |= nodes[nodes[v].fail].output;
                queue[tail++] = v;
            } else {
                /* Complete the DFA: missing edge → follow failure */
                nodes[u].child[c] = nodes[nodes[u].fail].child[c];
            }
        }
    }

    free(queue);
    return nodes;
}


int ac_search(const char *text,    int text_len,
              const char *pattern, int pat_len,
              int *positions,      int max_res) {
    if (pat_len == 0 || text_len == 0 || pat_len > text_len) return 0;

    AcNode *dfa = build_dfa(pattern, pat_len);
    if (!dfa) return -1;  /* malloc failure */

    int state = 0;
    int count = 0;

    for (int i = 0; i < text_len; i++) {
        state = dfa[state].child[(unsigned char)text[i]];
        if (dfa[state].output) {
            /* Match: ends at text[i], starts at i - pat_len + 1 */
            if (count < max_res)
                positions[count] = i - pat_len + 1;
            count++;
        }
    }

    free(dfa);
    return count;
}
