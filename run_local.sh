#!/usr/bin/env bash
# ============================================================
#  Schedulo — One-command local startup for Linux / macOS
#  Usage: bash run_local.sh
#  Prerequisites: Python 3.11+
# ============================================================
set -e

echo ""
echo " ============================================"
echo "  Schedulo - AI-Powered Timetable Generator"
echo " ============================================"
echo ""

# Step 1: Check Python version
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found. Install from https://www.python.org/downloads/"
    exit 1
fi
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"; then
    VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo "[ERROR] Python 3.11+ required. Found: $VER"
    exit 1
fi
echo "[OK] Python $(python3 -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")') detected"

# Step 2: Create virtual environment if missing
if [ ! -d ".venv" ]; then
    echo "[Setup] Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate
echo "[OK] Virtual environment active"

# Step 3: Install dependencies
echo "[Setup] Checking dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.local.txt
echo "[OK] Dependencies ready"

# Step 4: Copy .env if missing
if [ ! -f ".env" ]; then
    echo "[Setup] Creating .env from template..."
    cp .env.local.example .env
    echo "        Set GROQ_API_KEY or HF_API_TOKEN in .env for AI features."
fi

# Step 5: Create required directories
mkdir -p outputs ml_models logs data/postgres data/redis
echo "[OK] Directories ready"

# Step 6: Launch backend (auto-seeds DB on first run)
echo ""
echo " ============================================"
echo "  Backend  : http://localhost:8000"
echo "  API Docs : http://localhost:8000/docs"
echo "  Ctrl+C to stop"
echo " ============================================"
echo ""
python run.py --seed
