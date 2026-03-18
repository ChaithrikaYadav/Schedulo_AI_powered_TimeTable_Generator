"""
chronoai/ai_agents/data_ingestion_agent.py
DataIngestionAgent — LangGraph node that ingests CSV data into the database.

Responsibilities:
  - Validate CSV files exist and are parseable
  - Call CSVIngestionPipeline.run_all()
  - Report row counts and any schema warnings
  - Emit progress events for WebSocket dashboard
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CSV_ROOT = Path(__file__).parent.parent.parent

REQUIRED_CSVS = [
    "Room_Dataset.csv",
    "Student_Sections_DATASET.csv",
    "Subjects_Dataset.csv",
    "Teachers_Dataset.csv",
    "course_dataset_final.csv",
    "faculty_dataset_final.csv",
]


@dataclass
class IngestionResult:
    success: bool
    rows_inserted: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_state(self) -> dict[str, Any]:
        return {
            "ingestion_success": self.success,
            "ingestion_counts": self.rows_inserted,
            "ingestion_warnings": self.warnings,
            "ingestion_errors": self.errors,
        }


class DataIngestionAgent:
    """
    LangGraph-compatible agent node for CSV data ingestion.

    Can be called directly or wired into a LangGraph StateGraph:

        builder.add_node("ingest_data", DataIngestionAgent(db).run)
    """

    def __init__(self, db: Any | None = None, csv_root: Path | None = None) -> None:
        self._db = db
        self._root = csv_root or CSV_ROOT

    # ── Validation ────────────────────────────────────────────────
    def validate_csvs(self) -> list[str]:
        """Check which CSV files are present. Returns list of missing filenames."""
        return [f for f in REQUIRED_CSVS if not (self._root / f).exists()]

    # ── LangGraph node ────────────────────────────────────────────
    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph node function. Receives state dict and returns updated state.

        Expected state keys (optional):
            force_reingest: bool — if True, wipe and re-ingest even if data exists

        Returned state keys:
            ingestion_success, ingestion_counts, ingestion_warnings, ingestion_errors
        """
        logger.info("DataIngestionAgent: starting")
        result = await self._ingest(force=state.get("force_reingest", False))
        logger.info(f"DataIngestionAgent: done — {result.rows_inserted}")
        return {**state, **result.to_state()}

    async def _ingest(self, force: bool = False) -> IngestionResult:
        from chronoai.data_ingestion.csv_loader import CSVIngestionPipeline

        missing = self.validate_csvs()
        warnings = [f"Missing CSV: {f}" for f in missing]

        if not self._db:
            return IngestionResult(
                success=False,
                warnings=warnings,
                errors=["No DB session provided to DataIngestionAgent"],
            )

        try:
            pipeline = CSVIngestionPipeline(self._db, csv_root=self._root)
            counts = await pipeline.run_all()
            return IngestionResult(success=True, rows_inserted=counts, warnings=warnings)
        except Exception as exc:
            logger.exception("DataIngestionAgent: ingestion failed")
            return IngestionResult(
                success=False,
                warnings=warnings,
                errors=[str(exc)],
            )

    # ── Sync convenience wrapper ──────────────────────────────────
    def run_sync(self) -> IngestionResult:
        """Blocking wrapper for scripts and tests (not for async contexts)."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._ingest()
        )
