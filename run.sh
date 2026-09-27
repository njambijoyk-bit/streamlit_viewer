#!/usr/bin/env bash
# ── TISL Backup Viewer — macOS / Linux launcher ──────────────────────────────
# Run with:  ./run.sh   (first run sets everything up)
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
  echo "Setting up for first use..."
  "$PY" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "Starting TISL Backup Viewer..."
streamlit run app.py
