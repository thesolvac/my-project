# APME – Adaptive Pattern Matching Engine

A full-stack text-search system that dynamically selects the best string-matching
algorithm based on measurable input characteristics. All six algorithms are
implemented in C and called from Python via ctypes.

---

## Architecture

```
my-project/
├── src/
│   ├── c_backend/              C algorithm implementations + shared library
│   │   ├── algorithms.h        Public header (shared interface)
│   │   ├── flowscan.c          DNAScan    — KMP + memchr anchor        O(n/σ₀) best
│   │   ├── skipstride.c        GapJump    — BM + Sunday bonus shift    O(n/(m+1)) best
│   │   ├── twinhash.c          DualRabin  — dual rolling hash          O(n+m) avg
│   │   ├── bitanchor.c         BitMatch   — bit-parallel NFA + skip    O(n) / m≤64
│   │   ├── webscan.c           SweepRun   — Aho-Corasick + bitmap       O(n)
│   │   ├── tiermatch.c         FuzzySearch — k-error Bitap + dedup     O(n·k)
│   │   └── Makefile
│   │
│   ├── python_wrapper/         Python orchestration layer
│   │   ├── heuristics.py       Rule-based algorithm selector
│   │   ├── c_bindings.py       ctypes wrappers for the C library
│   │   └── apme.py             APMEEngine class (search / search_file / compare)
│   │
│   └── web/                    Flask web application
│       ├── app.py              Application factory
│       ├── config.py           Environment-based configuration
│       ├── database.py         MongoDB connection helper
│       ├── models/             UserProxy (Flask-Login)
│       ├── routes/             auth · search · admin blueprints
│       ├── templates/          Jinja2 HTML templates (Bootstrap 5)
│       └── static/             CSS & JS assets
│
├── docs/
│   └── APME_Technical_Justification.md   Heuristic decision rationale
│
├── build.py           Cross-platform C compiler script
├── app.py             Flask development server entry point
├── promote_admin.py   Promote an existing user to admin role
├── kill_port.ps1      PowerShell helper — kills process on port 5005
├── requirements.txt   Python dependencies
├── Makefile           Convenience targets
└── .env.example       Environment variable template
```

---

## Quick Start

### 1. Prerequisites

| Tool | Purpose |
|------|---------|
| Python 3.11+ | Backend runtime |
| GCC / MinGW | Compile C shared library |
| MongoDB | Persistent storage |

### 2. Clone & install

```bash
git clone https://github.com/thesolvac/my-project.git
cd my-project
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY and MONGO_URI at minimum
```

### 4. Compile the C backend

```bash
python build.py
# or: make build
```

> **No GCC?** The app falls back to a pure-Python DNAScan implementation automatically.

### 5. Start MongoDB

```bash
# Windows
"C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe"

# Linux / macOS
mongod --dbpath /data/db
```

### 6. Run

```bash
python app.py
# or: make run
```

Open **http://127.0.0.1:5005** in your browser.

---

## Creating an Admin User

```bash
python promote_admin.py
# or manually via the MongoDB shell / Compass
```

---

## Algorithms

APME ships six proprietary string-matching algorithms, each a tuned variant of a
classic base algorithm with an APME-specific optimisation.

### DNAScan
- Base: Knuth-Morris-Pratt (KMP) with **memchr first-character anchor**
- When no partial match is alive, jumps directly to the next occurrence of
  `pattern[0]` via SIMD-accelerated `memchr` — skipping dead stretches entirely
- Complexity: O(n/σ₀) best · O(n+m) worst · O(m) space
- **Best for:** small alphabets (binary/DNA), repetitive text, short patterns (m ≤ 2)

### GapJump
- Base: Boyer-Moore (Bad Character + Good Suffix) with **Sunday bonus shift**
- After BC and GS, inspects the byte immediately beyond the current window; if
  absent from the pattern, skips the entire window + 1 in one stride
- Complexity: O(n/(m+1)) best · O(n) worst · O(m+σ) space
- **Best for:** natural language, source code, long patterns, large alphabets

### DualRabin
- Base: Rabin-Karp with **dual independent rolling hashes**
- Maintains two parallel polynomial hashes; character verification only when both
  agree simultaneously — false-positive probability ≈ 10⁻¹⁸
- Complexity: O(n+m) average · O(1) space
- **Best for:** short patterns in very large texts, fingerprinting

### BitMatch
- Base: Shift-Or / Bitap (64-bit NFA) with **dead-state memchr skip**
- When NFA state drops to zero (no active threads), jumps to the next `pattern[0]`
  via `memchr` instead of advancing one byte at a time
- Complexity: O(n) for m ≤ 64 · O(σ) space
- **Best for:** short ASCII patterns with a rare leading byte, log scanning

### SweepRun
- Base: Aho-Corasick DFA with **256-bit character presence bitmap**
- Before each DFA transition, tests whether the byte exists in the pattern's
  character set; non-pattern bytes reset to root with no table lookup
- Complexity: O(n) search · O((m+1)·σ) space
- **Best for:** multi-pattern search, keyword spotting in mixed text

### FuzzySearch
- Base: Wu-Manber k-error Bitap with **best-tier deduplication**
- Scans error tiers 0→k; the first tier whose accept bit fires is recorded and
  higher-tier duplicates at the same position are suppressed immediately
- Complexity: O(n·k) Bitap · O(n·m) DP fallback for m > 64
- **Best for:** fuzzy / typo-tolerant search, OCR post-processing

### Auto-selection heuristic

| Priority | Condition | Algorithm |
|----------|-----------|-----------|
| 1 | m ≤ 2 | DNAScan |
| 2 | m ≤ 64 and ASCII-only pattern | BitMatch |
| 3 | Multiple patterns | SweepRun |
| 4 | Alphabet cardinality σ ≤ 4 (binary/DNA) | DNAScan |
| 5 | Text repetitiveness > 70 % | DNAScan |
| 6 | m > 10 and σ > 10 and n > 5 000 | GapJump |
| 7 | m ≤ 10 and n > 100 000 | DualRabin |
| 8 | Default | GapJump |

See [`docs/APME_Technical_Justification.md`](docs/APME_Technical_Justification.md)
for the full mathematical justification.

---

## Features

- **Auto mode** — APME picks the optimal algorithm automatically
- **Manual mode** — user selects the algorithm for direct comparison
- **Compare benchmark** — runs all six algorithms and shows a Chart.js bar chart
- **Statistics dashboard** — per-user charts: algorithm usage, 7-day activity, input method split
- **File streaming** — handles files up to 50 MB without loading them fully into RAM
- **Batch search** — search multiple files or a ZIP archive simultaneously
- **User accounts** — registration, login, per-user search history
- **Admin dashboard** — global analytics, algorithm usage charts, user management
- **MongoDB persistence** — search history, performance logs, user data

---

## MongoDB Collections

| Collection | Purpose |
|------------|---------|
| `users` | Account credentials and roles |
| `search_history` | Per-user search records |
| `performance_log` | Detailed timing data per algorithm |

---

## Dependencies

```
flask>=3.0.0
flask-login>=0.6.3
pymongo>=4.6.0
werkzeug>=3.0.0
python-dotenv>=1.0.0
```
