# Schedulo — Developer Makefile
# Usage: make <target>
# Requires: make (Linux/macOS built-in; Windows: install via Chocolatey `choco install make` or use WSL)

.PHONY: help install run run-docker stop migrate seed test test-fast lint clean reset

help:
	@echo "Schedulo Developer Commands:"
	@echo "  make install      Install all Python dependencies"
	@echo "  make run          Start app without Docker (SQLite mode)"
	@echo "  make run-docker   Start full stack with Docker Compose"
	@echo "  make stop         Stop all Docker containers"
	@echo "  make migrate      Run Alembic database migrations"
	@echo "  make seed         Seed database from CSV files"
	@echo "  make test         Run all tests with coverage"
	@echo "  make test-fast    Run tests without slow algorithmic tests"
	@echo "  make lint         Check code style with ruff"
	@echo "  make clean        Remove __pycache__, .pytest_cache, build artifacts"
	@echo "  make reset        DANGER: Drop DB and re-seed from scratch"

install:
	pip install --upgrade pip
	pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.local.txt
	pip install -e .

run:
	@cp -n .env.local.example .env 2>/dev/null || true
	@python run.py

run-docker:
	docker-compose -f docker-compose.local.yml up --build

stop:
	docker-compose -f docker-compose.local.yml down

migrate:
	alembic upgrade head

seed:
	python scripts/seed_from_csvs.py

test:
	pytest tests/ -v --cov=schedulo --cov-report=term-missing --cov-report=html

test-fast:
	pytest tests/unit/test_bug_fixes.py tests/unit/test_portability.py -v

lint:
	ruff check schedulo/ tests/ 2>/dev/null || echo "ruff not installed: pip install ruff"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage dist/ build/ *.egg-info/ 2>/dev/null || true
	@echo "Clean complete"

reset:
	@echo "WARNING: This will DELETE all timetable data and re-seed from CSV."
	@read -p "Are you sure? (yes/no): " confirm && [ "$$confirm" = "yes" ]
	rm -f schedulo.db
	alembic upgrade head
	python scripts/seed_from_csvs.py
	@echo "Database reset complete."
