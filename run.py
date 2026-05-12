"""
APME – Application Entry Point
================================
Run the Flask development server.

Usage:
    python run.py               # starts on http://127.0.0.1:5000
    python run.py --port 8080   # custom port

For production use a proper WSGI server:
    gunicorn "src.web.app:create_app()" --bind 0.0.0.0:5000
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path for "src.*" imports
sys.path.insert(0, str(Path(__file__).parent))

from src.web.app import create_app

app = create_app()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the APME Flask server")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print(f"\n  APME – Adaptive Pattern Matching Engine")
    print(f"  Server: http://{args.host}:{args.port}")
    print(f"  Press CTRL+C to quit\n")

    app.run(port=5005, debug=True, host=args.host)
