# Contributing to Schedulo

## Development Setup

```bash
# Clone and enter the directory
git clone <your-repo-url>
cd Schedulo_AI_powered_TimeTable_Generator

# Windows: one command
run_local.bat

# Linux / macOS: one command
bash run_local.sh
```

## Code Style

- **Python**: PEP 8, type hints on all public functions, docstrings on all classes
- **TypeScript**: strict mode, no `any`, named exports only
- **Imports**: absolute imports from `schedulo.*` package

## Branch Strategy

```
main          → stable production-ready code
dev           → integration branch for feature branches
feature/xxx   → individual feature branches
fix/xxx       → bug fix branches
```

## Project Structure

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full package layout.

## Running Tests

```bash
# All tests (recommended before any PR)
pytest tests/ -v

# Portability check first (run on fresh clone)
pytest tests/unit/test_portability.py -v

# Fast tests only (no algorithmic scheduler tests)
make test-fast

# With coverage report
make test
```

## Adding a New API Endpoint

1. Add the route in `schedulo/api_gateway/routes/<feature>.py`
2. Register the router in `schedulo/main.py`
3. Add a test in `tests/integration/test_api.py`
4. Update `docs/ARCHITECTURE.md` if the data flow changes

## Database Migrations

```bash
# Create a new migration after changing models.py
alembic revision --autogenerate -m "describe your change"

# Apply migrations
alembic upgrade head

# Roll back one step
alembic downgrade -1
```

## Environment Variables

Copy `.env.local.example` to `.env` and fill in your values.
See README.md for a full reference table.
