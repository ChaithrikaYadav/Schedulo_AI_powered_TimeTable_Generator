# Schedulo — AI-Powered University Timetable Generator

An AI-powered timetable generator for universities, built with FastAPI, React, SQLite/PostgreSQL,
and a deterministic 6-phase scheduling engine.

---

## Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Python | **3.11 or 3.12** | [Download](https://www.python.org/downloads/) — must be in PATH |
| Git | Any | For cloning |
| Node.js | 20+ | Optional — only for frontend development |
| Docker Desktop | Latest | Optional — only for PostgreSQL/Redis mode |

---

## Quick Start — Plain Python (SQLite, no Docker)

This is the fastest way. Uses SQLite — no database server required.

### Step 1: Clone
```bash
git clone <your-repo-url>
cd Schedulo_AI_powered_TimeTable_Generator
```

### Step 2: Run the startup script

**Windows** — open Command Prompt in the project folder:
```
start.bat
```

**Linux / macOS:**
```bash
bash start.sh
```

The script automatically:
1. Creates a Python virtual environment (`.venv/`)
2. Installs all dependencies
3. Copies `.env.local.example` → `.env`
4. Creates the SQLite database (`schedulo.db`)
5. Seeds the database from the CSV files
6. Starts the FastAPI backend on port 8000

### Step 3: Open the frontend
```bash
cd frontend
npm install
npm run dev
```

Navigate to **http://localhost:5176** (or the port shown in the terminal).

### Step 4 (Optional): Add your AI keys

Edit `.env` and set your API keys to enable ScheduloBot's full AI capabilities:
```env
GROQ_API_KEY=gsk_xxxxxxxxxxxx     # Free at https://console.groq.com
HF_API_TOKEN=hf_xxxxxxxxxxxx      # Free at https://huggingface.co/settings/tokens
```

Without keys, ScheduloBot still works by querying your live timetable database directly.

---

## Full Stack with Docker (PostgreSQL + Redis + Backend + Frontend)

```bash
# Copy and optionally edit the env file
cp .env.local.example .env

# Start everything (migrations + seeding happen automatically)
docker-compose -f docker-compose.local.yml up --build
```

Services start automatically in this order:
1. **PostgreSQL** + **Redis** (infrastructure, with healthchecks)
2. **`migrate`** container — runs `alembic upgrade head`, then exits
3. **`seed`** container — runs `seed_from_csvs.py`, then exits
4. **Backend** (FastAPI on port 8000) — starts after seeding
5. **Celery worker** — starts after seeding
6. **Frontend** (React on port 5173) — starts after backend is healthy

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

---

## Project Structure

```
schedulo/               Python package (FastAPI app + business logic)
├── main.py             FastAPI app entry point & global exception handlers
├── models.py           Database models (SQLAlchemy ORM)
├── config.py           Settings — reads from .env
├── tasks.py            Celery task definitions
├── ai_agents/          AI agent pipeline (LangGraph)
├── scheduler_core/     6-phase deterministic scheduling engine
├── api_gateway/        FastAPI route handlers
├── chatbot_service/    ScheduloBot LLM client
├── conflict_detector/  Hard constraint violation scanner
├── analytics_dashboard/ Quality metrics
├── data_ingestion/     CSV loading pipeline
└── export_engine/      Excel/PDF export
data/                   CSV datasets (committed to repo)
scripts/                Database setup and migration utilities
frontend/               React + TypeScript UI
alembic/                Database migration scripts
tests/                  Automated test suite (18 tests)
```

---

## Developer Commands

```bash
make help           Show all available commands
make install        Install dependencies + pip install -e .
make run            Start without Docker (SQLite, quickest)
make run-docker     Start with Docker Compose (full stack)
make stop           Stop all Docker containers
make migrate        Run database migrations
make seed           Seed database from CSV files
make test           Run all tests with coverage
make test-fast      Run fast tests only
make lint           Check code style
make clean          Remove build artifacts
make reset          DANGER: Drop DB and re-seed
```

---

## Common Issues

**`ModuleNotFoundError: No module named 'schedulo'`**
```bash
pip install -e .
```

**`alembic: command not found`**
Activate your virtual environment first:
- Linux/macOS: `source .venv/bin/activate`
- Windows: `.venv\Scripts\activate`

**`sqlite3.OperationalError: no such table`**
The database needs to be initialised. This happens automatically in `start.bat`/`start.sh`.
To do it manually: `python run.py` (which auto-creates tables via SQLite).

**`ERROR: Could not find a satisfying requirement for difflib2`**
Pull the latest code — this bug is fixed in `requirements.local.txt`.

**Backend starts but shows no data / empty dashboard**
```bash
python scripts/seed_from_csvs.py
```

**`torch` install takes very long or fails**
The `requirements.local.txt` uses the CPU-only PyTorch build. Make sure you haven't
modified it to remove the `--extra-index-url` line.

---

## Environment Variables Reference

Copy `.env.local.example` to `.env` and edit as needed:

| Variable | Default | Description |
|---|---|---|
| `DB_ENGINE` | `sqlite` | `sqlite` for local, `postgresql` for Docker |
| `DATABASE_URL` | `sqlite+aiosqlite:///./schedulo.db` | Full DB connection URL |
| `CACHE_BACKEND` | `memory` | `memory` for local, `redis` for Docker |
| `CELERY_TASK_ALWAYS_EAGER` | `true` | `true` = run tasks synchronously, no worker needed |
| `GROQ_API_KEY` | *(blank)* | Your Groq key for fast AI responses |
| `HF_API_TOKEN` | *(blank)* | Your HuggingFace token for ScheduloBot |
| `ENVIRONMENT` | `local` | `local` / `server` / `cloud` |
| `DEBUG` | `true` | Set to `false` in production |

---

## Running Tests

```bash
# Run everything (includes portability checks)
pytest tests/ -v

# Run portability tests first (verify setup is correct)
pytest tests/test_portability.py -v

# Run with coverage
pytest tests/ --cov=schedulo --cov-report=html
```
