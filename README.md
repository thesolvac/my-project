# APME – Adaptive Pattern Matching Engine

A full-stack text-search system that dynamically selects the best string-matching
algorithm (KMP, Boyer-Moore, or Rabin-Karp) based on measurable input
characteristics. Algorithms are implemented in C and called from Python via ctypes.

---

## Architecture

```
my-project/
├── src/
│   ├── c_backend/          C algorithm implementations + shared library
│   │   ├── algorithms.h    Public header (shared interface)
│   │   ├── kmp.c           Knuth-Morris-Pratt  O(n+m)
│   │   ├── boyer_moore.c   Boyer-Moore BC+GS   O(n/m) best
│   │   ├── rabin_karp.c    Rabin-Karp RH        O(n+m) avg
│   │   └── Makefile
│   │
│   ├── engine/             Python orchestration layer
│   │   ├── heuristics.py   Rule-based algorithm selector
│   │   ├── c_bindings.py   ctypes wrappers for the C library
│   │   └── apme.py         APMEEngine class (search / search_file / compare)
│   │
│   └── web/                Flask web application
│       ├── app.py          Application factory
│       ├── config.py       Environment-based configuration
│       ├── database.py     MongoDB connection helper
│       ├── models/         UserProxy (Flask-Login)
│       ├── routes/         auth · search · admin blueprints
│       ├── templates/      Jinja2 HTML templates (Bootstrap 5)
│       └── static/         CSS & JS assets
│
├── docs/
│   └── APME_Technical_Justification.md   Heuristic decision rationale
│
├── build.py          Cross-platform C compiler script
├── run.py            Flask development server entry point
├── requirements.txt  Python dependencies
├── Makefile          Convenience targets
└── .env.example      Environment variable template
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
git clone <repo-url>
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

> **No GCC?** The app falls back to a pure-Python KMP implementation automatically.

### 5. Start MongoDB

```bash
# Windows
"C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe"

# Linux / macOS
mongod --dbpath /data/db
```

### 6. Run

```bash
python run.py
# or: make run
```

Open **http://127.0.0.1:5000** in your browser.

---

## Creating an Admin User

```bash
make seed-admin
# or manually:
python -c "
from src.web.app import create_app
from src.web.database import get_db
from werkzeug.security import generate_password_hash
from datetime import datetime
app = create_app()
with app.app_context():
    get_db().users.insert_one({
        'username': 'admin', 'email': 'admin@example.com',
        'password': generate_password_hash('yourpassword'),
        'role': 'admin', 'created_at': datetime.utcnow(), 'search_count': 0,
    })
"
```

---

## Algorithms

### KMP – Knuth-Morris-Pratt
- Pre-builds an LPS (Longest Proper Prefix = Suffix) table in O(m)
- Never re-examines a character in the text → guaranteed O(n + m)
- **Best for:** small alphabets, repetitive text, short patterns

### Boyer-Moore (Bad Character + Good Suffix)
- Scans the pattern right-to-left; on mismatch, takes the larger of two shifts
- Average skip ≈ m·(1 − 1/σ) characters → **sub-linear O(n/m)**
- **Best for:** natural language, long patterns, large alphabets

### Rabin-Karp (Rolling Hash)
- Computes a polynomial hash; sliding window update is O(1)
- Verification only on hash collision → O(n + m) average
- **Best for:** multiple patterns, short patterns in large texts

### APME Heuristic Selector
See [`docs/APME_Technical_Justification.md`](docs/APME_Technical_Justification.md)
for the full decision table and mathematical justification.

---

## Features

- **Auto mode** — APME picks the optimal algorithm automatically
- **Manual mode** — user selects the algorithm for comparison
- **Compare benchmark** — runs all three algorithms and shows a Chart.js bar chart
- **File streaming** — handles files up to 50 MB without loading them fully into RAM
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