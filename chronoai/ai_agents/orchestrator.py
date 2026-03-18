"""
chronoai/ai_agents/orchestrator.py
ChronoOrchestrator — LangGraph StateGraph DAG that wires all 6 ChronoAI
agents into a production-ready pipeline.

Pipeline flow:
    START
      ↓
   [ingest_data]          DataIngestionAgent
      ↓
   [generate_timetable]   SchedulerAgent
      ↓
   [analyse_constraints]  ConstraintAnalysisAgent
      ↓ (branching)
   [resolve_conflicts]    ConflictResolutionAgent  ← if violations found
      ↓
   [audit_quality]        QualityAuditAgent
      ↓
    END

WebSocket progress events are emitted at each node transition.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

# ── Shared state schema (TypedDict for LangGraph) ─────────────────
State = dict[str, Any]

# ── Node transition events ────────────────────────────────────────
PIPELINE_STEPS = [
    "ingest_data",
    "generate_timetable",
    "analyse_constraints",
    "resolve_conflicts",
    "audit_quality",
]


class ChronoOrchestrator:
    """
    LangGraph-based pipeline orchestrator for ChronoAI.

    Usage (async):
        orch = ChronoOrchestrator(db=db)
        result = await orch.run(department="...", academic_year="2024-25")

    Usage (with WebSocket progress):
        async for event in orch.stream(state):
            await ws.send_json(event)
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Build LangGraph StateGraph. Falls back to sequential execution if langgraph unavailable."""
        try:
            from langgraph.graph import StateGraph, END
            from chronoai.ai_agents.data_ingestion_agent import DataIngestionAgent
            from chronoai.ai_agents.scheduler_agent import SchedulerAgent
            from chronoai.ai_agents.constraint_analysis_agent import ConstraintAnalysisAgent
            from chronoai.ai_agents.conflict_resolution_agent import ConflictResolutionAgent
            from chronoai.ai_agents.quality_audit_agent import QualityAuditAgent

            builder = StateGraph(dict)

            builder.add_node("ingest_data",          DataIngestionAgent(self._db).run)
            builder.add_node("generate_timetable",   SchedulerAgent(self._db).run)
            builder.add_node("analyse_constraints",  ConstraintAnalysisAgent(self._db).run)
            builder.add_node("resolve_conflicts",    ConflictResolutionAgent(self._db).run)
            builder.add_node("audit_quality",        QualityAuditAgent(self._db).run)

            # Linear edges
            builder.set_entry_point("ingest_data")
            builder.add_edge("ingest_data", "generate_timetable")
            builder.add_edge("generate_timetable", "analyse_constraints")

            # Conditional: skip resolution if no violations
            def _should_resolve(state: State) -> str:
                return "resolve_conflicts" if state.get("analysis_critical", 0) > 0 else "audit_quality"

            builder.add_conditional_edges(
                "analyse_constraints",
                _should_resolve,
                {"resolve_conflicts": "resolve_conflicts", "audit_quality": "audit_quality"},
            )
            builder.add_edge("resolve_conflicts", "audit_quality")
            builder.add_edge("audit_quality", END)

            return builder.compile()

        except ImportError:
            logger.warning("langgraph not installed — using sequential fallback pipeline")
            return None

    async def run(
        self,
        department: str,
        academic_year: str = "2024-25",
        random_seed: int | None = None,
        force_reingest: bool = False,
    ) -> State:
        """
        Execute the full pipeline synchronously and return the final state.

        Returns:
            Final state dict containing all agent outputs (timetable_id,
            quality_score, analysis_violations, etc.)
        """
        initial_state: State = {
            "department": department,
            "academic_year": academic_year,
            "random_seed": random_seed,
            "force_reingest": force_reingest,
        }

        if self._graph:
            # LangGraph compiled graph
            return await self._graph.ainvoke(initial_state)
        else:
            # Sequential fallback
            return await self._run_sequential(initial_state)

    async def stream(self, initial_state: State) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream pipeline progress events suitable for WebSocket / SSE.

        Yields dicts:
            {"step": str, "status": "started"|"completed", "data": dict}
        """
        from chronoai.ai_agents.data_ingestion_agent import DataIngestionAgent
        from chronoai.ai_agents.scheduler_agent import SchedulerAgent
        from chronoai.ai_agents.constraint_analysis_agent import ConstraintAnalysisAgent
        from chronoai.ai_agents.conflict_resolution_agent import ConflictResolutionAgent
        from chronoai.ai_agents.quality_audit_agent import QualityAuditAgent

        state = dict(initial_state)

        agents: list[tuple[str, Any]] = [
            ("ingest_data", DataIngestionAgent(self._db)),
            ("generate_timetable", SchedulerAgent(self._db)),
            ("analyse_constraints", ConstraintAnalysisAgent(self._db)),
        ]

        for step_name, agent in agents:
            yield {"step": step_name, "status": "started", "data": {}}
            state = await agent.run(state)
            yield {
                "step": step_name,
                "status": "completed",
                "data": {k: v for k, v in state.items() if isinstance(v, (str, int, float, bool))},
            }
            await asyncio.sleep(0)

        # Conditional resolve
        if state.get("analysis_critical", 0) > 0:
            yield {"step": "resolve_conflicts", "status": "started", "data": {}}
            state = await ConflictResolutionAgent(self._db).run(state)
            yield {"step": "resolve_conflicts", "status": "completed", "data": {}}
            await asyncio.sleep(0)

        yield {"step": "audit_quality", "status": "started", "data": {}}
        state = await QualityAuditAgent(self._db).run(state)
        yield {
            "step": "audit_quality",
            "status": "completed",
            "data": {
                "timetable_id": state.get("timetable_id"),
                "quality_score": state.get("quality_score"),
            },
        }

        yield {"step": "pipeline_complete", "status": "completed", "data": state}

    async def _run_sequential(self, state: State) -> State:
        """Fallback: run all agents sequentially without LangGraph."""
        from chronoai.ai_agents.data_ingestion_agent import DataIngestionAgent
        from chronoai.ai_agents.scheduler_agent import SchedulerAgent
        from chronoai.ai_agents.constraint_analysis_agent import ConstraintAnalysisAgent
        from chronoai.ai_agents.conflict_resolution_agent import ConflictResolutionAgent
        from chronoai.ai_agents.quality_audit_agent import QualityAuditAgent

        state = await DataIngestionAgent(self._db).run(state)
        state = await SchedulerAgent(self._db).run(state)
        state = await ConstraintAnalysisAgent(self._db).run(state)

        if state.get("analysis_critical", 0) > 0:
            state = await ConflictResolutionAgent(self._db).run(state)

        state = await QualityAuditAgent(self._db).run(state)
        return state
