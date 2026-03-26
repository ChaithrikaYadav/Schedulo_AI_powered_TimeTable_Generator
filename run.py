"""
run.py — Single-command entry point for the Schedulo prototype.
Usage:
    python run.py                  # Start FastAPI backend on http://localhost:8000
    python run.py --seed           # Seed database then start server
    python run.py --seed-only      # Only seed database, don't start server
    python run.py --with-frontend  # Start backend + Vite frontend together
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).parent
FRONTEND_DIR = ROOT / "frontend"


def run_seed():
    """Run database seeder."""
    print("\n[Seeder] Seeding database...")
    from scripts.seed_from_csvs import main as seed_main
    asyncio.run(seed_main())


def run_server():
    """Start the FastAPI server with uvicorn (blocking)."""
    import uvicorn
    from schedulo.config import get_settings
    settings = get_settings()
    print(f"\n[Backend] Starting Schedulo [{settings.environment.upper()}]")
    print(f"  API docs : http://localhost:8000/docs")
    print(f"  Health   : http://localhost:8000/health\n")
    uvicorn.run(
        "schedulo.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )


def run_server_in_thread() -> threading.Thread:
    """Start FastAPI in a daemon thread so the main thread can manage the frontend."""
    import uvicorn
    from schedulo.config import get_settings
    settings = get_settings()
    print(f"\n[Backend] Starting Schedulo [{settings.environment.upper()}] on port 8000...")

    config = uvicorn.Config(
        "schedulo.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,          # reload=True is incompatible with thread mode
        log_level="info",
    )
    server = uvicorn.Server(config)

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return t


def run_with_frontend():
    """Launch both FastAPI backend (thread) and Vite dev server (subprocess)."""
    print("\n")
    print("  =====================================================")
    print("   Schedulo -- Full Stack Launcher")
    print("  =====================================================")

    # Verify node_modules
    if not (FRONTEND_DIR / "node_modules").exists():
        print("\n[Frontend] node_modules not found — running npm install...")
        subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True, shell=True)

    # Start FastAPI in a background thread
    server_thread = run_server_in_thread()

    # Wait for backend to be ready (max 10s)
    print("[Backend] Waiting for API to be ready...")
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen("http://localhost:8000/health", timeout=1)
            print("[Backend] API is up at http://localhost:8000")
            break
        except Exception:
            time.sleep(0.5)
    else:
        print("[Backend] WARNING: API health check timed out — frontend will start anyway.")

    print("[Frontend] Starting Vite dev server on http://localhost:5173...\n")

    # Start Vite (blocking — keeps the main process alive)
    try:
        vite_proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "--open"],
            cwd=FRONTEND_DIR,
            shell=True,
        )
        print("  Both servers running. Press Ctrl+C to stop.\n")
        vite_proc.wait()
    except KeyboardInterrupt:
        print("\n[Launcher] Shutting down...")
        vite_proc.terminate()
        sys.exit(0)


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--seed-only" in args:
        run_seed()

    elif "--seed" in args:
        run_seed()
        if "--with-frontend" in args:
            run_with_frontend()
        else:
            run_server()

    elif "--with-frontend" in args:
        run_with_frontend()

    else:
        run_server()
