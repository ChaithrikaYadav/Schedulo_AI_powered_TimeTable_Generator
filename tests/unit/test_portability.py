"""
tests/test_portability.py
Portability verification tests — run these first on any new machine.

These tests verify the project structure is correct and all imports work.
They do NOT require a database, Redis, or any external service.
Run: pytest tests/test_portability.py -v
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent  # tests/unit/ -> tests/ -> project root


# ── Test 1: Python version ─────────────────────────────────────────────────────
def test_python_version_is_311_or_higher():
    """Python 3.11+ is required for asyncio.run() and match/case syntax."""
    assert sys.version_info >= (3, 11), (
        f"Python 3.11+ required. Current: {sys.version_info.major}.{sys.version_info.minor}\n"
        "Download from https://www.python.org/downloads/"
    )


# ── Test 2: All critical files exist ──────────────────────────────────────────
@pytest.mark.parametrize("filepath", [
    # Package markers
    "schedulo/__init__.py",
    "schedulo/main.py",
    "schedulo/models.py",
    "schedulo/config.py",
    "schedulo/tasks.py",
    "schedulo/database.py",
    # Agent package
    "schedulo/ai_agents/__init__.py",
    # Core scheduler
    "schedulo/scheduler_core/__init__.py",
    "schedulo/scheduler_core/prototype_scheduler.py",
    # Sub-packages
    "schedulo/data_ingestion/__init__.py",
    "schedulo/conflict_detector/__init__.py",
    "schedulo/analytics_dashboard/__init__.py",
    # Infrastructure
    "alembic/env.py",
    "alembic/versions",
    "scripts/seed_from_csvs.py",
    # CSV datasets
    "data/Room_Dataset.csv",
    "data/Student_Sections_DATASET.csv",
    "data/Subjects_Dataset.csv",
    "data/Teachers_Dataset.csv",
    # Config and startup
    ".env.local.example",
    "requirements.local.txt",
    "requirements.dev.txt",
    "pyproject.toml",
    "docker-compose.local.yml",
    "Dockerfile.local",
    "Dockerfile.frontend.local",
    "README.md",
])
def test_critical_file_exists(filepath):
    """Every file in this list must exist in the repository."""
    full_path = PROJECT_ROOT / filepath
    assert full_path.exists(), (
        f"Missing critical file: {filepath}\n"
        "This file must exist for the application to work on a fresh clone.\n"
        "See README.md → Common Issues for resolution steps."
    )


# ── Test 3: Core modules import without error ─────────────────────────────────
@pytest.mark.parametrize("module_path", [
    "schedulo",
    "schedulo.config",
    "schedulo.models",
    "schedulo.database",
    "schedulo.tasks",
    "schedulo.scheduler_core",
    "schedulo.scheduler_core.prototype_scheduler",
    "schedulo.data_ingestion",
    "schedulo.conflict_detector",
    "schedulo.analytics_dashboard",
])
def test_module_imports_without_error(module_path):
    """Every core module must be importable without error on a fresh install."""
    try:
        importlib.import_module(module_path)
    except ImportError as e:
        pytest.fail(
            f"ImportError on '{module_path}': {e}\n"
            "Run 'pip install -e .' and verify all files exist."
        )


# ── Test 4: requirements.local.txt has no phantom packages ───────────────────
def test_requirements_no_phantom_packages():
    """Check for known bad packages in requirements.local.txt (non-comment lines only)."""
    KNOWN_BAD = {
        "difflib2": "difflib is Python standard library — no install needed",
    }
    content = (PROJECT_ROOT / "requirements.local.txt").read_text()
    # Only scan actual package lines, not comments
    package_lines = [
        line.strip() for line in content.split("\n")
        if line.strip() and not line.strip().startswith(("#", "-", "http", "--"))
    ]
    package_text = "\n".join(package_lines)
    for pkg, reason in KNOWN_BAD.items():
        assert pkg not in package_text, (
            f"requirements.local.txt installs '{pkg}': {reason}"
        )


# ── Test 5: requirements.local.txt has no duplicate packages ─────────────────
def test_requirements_no_duplicates():
    """Each package should appear only once in requirements.local.txt."""
    content = (PROJECT_ROOT / "requirements.local.txt").read_text()
    pkg_names: list[str] = []
    for line in content.split("\n"):
        line = line.strip()
        # Skip blank lines, comments, pip options (-- flags), and URL lines
        if not line or line.startswith(("#", "-", "http", "--")):
            continue
        # Extract package name before version specifier or inline comment
        name_part = line.split("#")[0].strip()  # strip inline comments first
        name = re.split(r"[>=<!;\[\s]", name_part)[0].strip().lower()
        if name:
            pkg_names.append(name)
    duplicates = [p for p in set(pkg_names) if pkg_names.count(p) > 1]
    assert not duplicates, (
        f"Duplicate packages in requirements.local.txt: {duplicates}\n"
        "Remove the duplicate entry to avoid pip warnings."
    )


# ── Test 6: .env.local.example has all required variables ────────────────────
def test_env_example_has_required_variables():
    """The .env template must contain all required environment variables."""
    REQUIRED_VARS = [
        "ENVIRONMENT",
        "DEBUG",
        "DB_ENGINE",
        "DATABASE_URL",
        "ALLOWED_ORIGINS",
    ]
    content = (PROJECT_ROOT / ".env.local.example").read_text()
    missing = [v for v in REQUIRED_VARS if v not in content]
    assert not missing, (
        f"Variables missing from .env.local.example: {missing}\n"
        "New developers will not know these need to be set."
    )


# ── Test 7: .gitignore covers sensitive files ─────────────────────────────────
def test_gitignore_covers_sensitive_files():
    """Sensitive and generated files must be gitignored."""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text()
    required = [
        "*.db",
        ".env",
        "outputs/",
        "ml_models/",
        "__pycache__/",
    ]
    missing = [p for p in required if p not in gitignore]
    assert not missing, (
        f"Patterns missing from .gitignore: {missing}\n"
        "Add these patterns to prevent committing sensitive or generated files."
    )


# ── Test 8: CSV data files exist and are non-empty ────────────────────────────
@pytest.mark.parametrize("csv_file", [
    "data/Room_Dataset.csv",
    "data/Student_Sections_DATASET.csv",
    "data/Subjects_Dataset.csv",
    "data/Teachers_Dataset.csv",
])
def test_csv_data_files_exist_and_nonempty(csv_file):
    path = PROJECT_ROOT / csv_file
    assert path.exists(), (
        f"CSV file missing: {csv_file}\n"
        "Run: python scripts/seed_from_csvs.py"
    )
    assert path.stat().st_size > 100, (
        f"CSV file appears empty: {csv_file}"
    )


# ── Test 9: docker-compose references existing Dockerfiles ───────────────────
def test_docker_compose_references_valid_dockerfiles():
    """Every dockerfile: reference in docker-compose.local.yml must exist."""
    compose_content = (PROJECT_ROOT / "docker-compose.local.yml").read_text()
    referenced = re.findall(r"dockerfile:\s*(\S+)", compose_content)
    for dockerfile in referenced:
        # Resolve relative to project root (docker-compose context is root)
        path = PROJECT_ROOT / dockerfile
        assert path.exists(), (
            f"docker-compose.local.yml references '{dockerfile}' which does not exist.\n"
            "Create this file or fix the reference."
        )


# ── Test 10: pyproject.toml declares schedulo package ────────────────────────
def test_pyproject_declares_schedulo_package():
    """pyproject.toml must exist and declare the 'schedulo' package."""
    toml_path = PROJECT_ROOT / "pyproject.toml"
    assert toml_path.exists(), "pyproject.toml is missing — cannot run 'pip install -e .'"
    content = toml_path.read_text()
    assert "schedulo" in content, (
        "pyproject.toml doesn't reference the 'schedulo' package.\n"
        "Ensure [tool.setuptools.packages.find] includes 'schedulo*'."
    )
