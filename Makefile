# =============================================================================
# APME – Root Makefile
# =============================================================================
# Targets:
#   make install   – install Python dependencies
#   make build     – compile the C shared library
#   make run       – start the Flask development server
#   make all       – install + build + run
#   make clean     – remove compiled C artifacts
#   make seed-admin – create the first admin user (interactive)
# =============================================================================

PYTHON = py -3
PIP    = py -3 -m pip

.PHONY: all install build run clean seed-admin

all: install build run

install:
	$(PIP) install -r requirements.txt

build:
	$(PYTHON) build.py

run:
	$(PYTHON) run.py

clean:
	$(PYTHON) build.py --clean
	find . -name "*.pyc"       -delete 2>/dev/null || true
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

seed-admin:
	$(PYTHON) -c "
from src.web.app import create_app
from src.web.database import get_db
from werkzeug.security import generate_password_hash
from datetime import datetime

app = create_app()
with app.app_context():
    db = get_db()
    username = input('Admin username: ')
    email    = input('Admin email: ')
    password = input('Admin password (min 6 chars): ')
    doc = {
        'username': username, 'email': email.lower(),
        'password': generate_password_hash(password),
        'role': 'admin', 'created_at': datetime.utcnow(), 'search_count': 0,
    }
    db.users.insert_one(doc)
    print(f'Admin user \"{username}\" created.')
"
