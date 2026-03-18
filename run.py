"""
run.py — Single-command entry point for the ChronoAI prototype.
Usage:
    python run.py              # Start FastAPI backend on http://localhost:8000
    python run.py --seed       # Seed database then start server
    python run.py --seed-only  # Only seed database, don't start server
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

# Ensure we can import chronoai from the project root
sys.path.insert(0, str(Path(__file__).parent))


def run_seed():
    """Run database seeder."""
    print("\n🌱 Seeding database...")
    import asyncio
    from scripts.seed_from_csvs import main as seed_main
    asyncio.run(seed_main())


def run_server():
    """Start the FastAPI server with uvicorn."""
    import uvicorn
    from chronoai.config import get_settings
    settings = get_settings()
    print(f"\n🚀 Starting ChronoAI [{settings.environment.upper()}]")
    print(f"   API docs: http://localhost:8000/docs")
    print(f"   Frontend: http://localhost:5173 (start separately with: cd frontend && npm run dev)\n")
    uvicorn.run(
        "chronoai.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--seed-only" in args:
        run_seed()
    elif "--seed" in args:
        run_seed()
        run_server()
    else:
        run_server()
