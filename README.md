# Schedulo — AI-Powered University Timetable Generator

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ChaithrikaYadav/Schedulo_AI_powered_TimeTable_Generator)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ChaithrikaYadav/Schedulo_AI_powered_TimeTable_Generator)

An AI-powered timetable generator for universities — FastAPI backend, React frontend, deterministic 6-phase scheduling engine, and ScheduloBot AI chatbot.

---

## ⚡ Quickest Start — GitHub Codespaces (Zero Install)

Click **"Open in Codespaces"** above. A full dev environment in your browser is ready in ~2 minutes — no Python, no Node.js, no installation needed on your machine.

Once the Codespace loads:
```bash
# Start the backend (in one terminal)
python run.py --seed

# Start the frontend (in a second terminal)
cd frontend && npm run dev
```
Ports 8000 and 5173 are auto-forwarded. Click the link in the Ports tab to open the app.

---

## 💻 Local Quick Start

> **Requirements:** Python 3.11+, Git. Node.js 18+ optional (frontend only).

```bash
# 1. Clone
git clone https://github.com/ChaithrikaYadav/Schedulo_AI_powered_TimeTable_Generator.git
cd Schedulo_AI_powered_TimeTable_Generator

# 2. One command (Windows)
run_local.bat

# 2. One command (Linux / macOS)
bash run_local.sh
```

The script automatically:
1. Creates a Python virtual environment (`.venv/`)
2. Installs all dependencies from `requirements.local.txt`
3. Copies `.env.local.example` → `.env`
4. Seeds the SQLite database from CSV files
5. Starts the FastAPI backend at **http://localhost:8000**

Then in a second terminal:
```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### Optional: AI Keys
Edit `.env` to enable ScheduloBot's full AI:
```env
GROQ_API_KEY=gsk_xxxx     # Free: https://console.groq.com
HF_API_TOKEN=hf_xxxx      # Free: https://huggingface.co/settings/tokens
```
Without keys, ScheduloBot works by querying the live timetable database.

---

## ☁️ Cloud Hosting — Render.com (Free Tier)

1. Fork this repo to your GitHub account
2. Go to **https://dashboard.render.com** → **New → Blueprint**
3. Connect your GitHub repo — Render reads `render.yaml` automatically
4. Set `GROQ_API_KEY` and `HF_API_TOKEN` in the Render dashboard env vars
5. Click **Apply** — backend + frontend deploy automatically

| Service | URL (after deploy) |
|---------|-------------------|
| Frontend | `https://schedulo-ui.onrender.com` |
| Backend API | `https://schedulo-api.onrender.com` |
| API Docs | `https://schedulo-api.onrender.com/docs` |

> **Note:** Free tier spins down after 15 minutes of inactivity. First request may take ~30s to warm up.

---

## 🐳 Docker (Full Stack — PostgreSQL + Redis)

```bash
cp .env.local.example .env
docker-compose -f docker-compose.local.yml up --build
```

Services start in order: PostgreSQL → Redis → migrate → seed → backend → Celery → frontend.

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

---

## 📁 Project Structure

```
schedulo/           Core Python package (FastAPI + business logic)
├── main.py         App entry point + global exception handlers
├── models.py       SQLAlchemy ORM models
├── config.py       Pydantic settings (reads from .env)
├── ai_agents/      LangGraph multi-agent pipeline
├── scheduler_core/ 6-phase deterministic scheduling engine
├── api_gateway/    FastAPI route handlers
└── chatbot_service/ ScheduloBot LLM client (Groq/HF/DB fallback)

frontend/           React 18 + TypeScript UI (Vite)
├── src/types/      Shared TypeScript interfaces
├── src/hooks/      Custom React hooks
├── src/pages/      Dashboard, Generator, TimetableViewer, ScheduloBot
└── src/lib/        API client + WebSocket client

data/               CSV datasets (committed to repo)
scripts/            DB setup, seeding, ML training utilities
docs/               ARCHITECTURE.md + CONTRIBUTING.md
tests/unit/         101 unit tests (run: pytest tests/ -v)
tests/integration/  API integration tests
```

---

## 🛠️ Developer Commands

```bash
make help           Show all commands
make install        Install deps + pip install -e .
make run            Start backend (SQLite, no Docker)
make seed           Seed DB from CSV files
make test           Run all tests with coverage
make test-fast      Fast tests only
make lint           Check code style (ruff)
make clean          Remove build artifacts
```

---

## ⚠️ Common Issues

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: No module named 'schedulo'` | `pip install -e .` |
| `sqlite3.OperationalError: no such table` | `python scripts/seed_from_csvs.py` |
| Backend starts but dashboard is empty | `python scripts/seed_from_csvs.py` |
| `torch` install is slow | Uses CPU-only build — don't remove the `--extra-index-url` line |
| `.venv` errors after `git clone` | Don't commit `.venv/` — delete it and run `run_local.bat` / `bash run_local.sh` |
| `node_modules` errors after `git clone` | Run `cd frontend && npm install` |

---

## 🔑 Environment Variables

Copy `.env.local.example` → `.env` and fill in values:

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `local` | `local` / `server` / `cloud` |
| `DEBUG` | `true` | Set to `false` in production |
| `DB_ENGINE` | `sqlite` | `sqlite` or `postgresql` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./schedulo.db` | Full DB connection string |
| `CELERY_TASK_ALWAYS_EAGER` | `true` | `true` = synchronous tasks (no worker needed) |
| `GROQ_API_KEY` | *(blank)* | Groq key for fast AI ([get one free](https://console.groq.com)) |
| `HF_API_TOKEN` | *(blank)* | HuggingFace token ([get one free](https://huggingface.co/settings/tokens)) |

---

## 🧪 Tests

```bash
pytest tests/ -v                          # All 101 tests
pytest tests/unit/test_portability.py -v  # Portability check (run first on new machines)
pytest tests/ --cov=schedulo              # With coverage
```
