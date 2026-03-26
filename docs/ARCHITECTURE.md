# Schedulo Architecture Overview

## Package Layout

```
Schedulo_AI_powered_TimeTable_Generator/
│
├── schedulo/                   ← Core Python package (FastAPI + business logic)
│   ├── main.py                 ← FastAPI app entry point, global exception handlers
│   ├── models.py               ← SQLAlchemy ORM models (all DB tables)
│   ├── database.py             ← Async engine + session factory
│   ├── config.py               ← Pydantic settings (3-tier: local/server/cloud)
│   ├── tasks.py                ← Celery task definitions
│   │
│   ├── api_gateway/            ← FastAPI route handlers
│   │   └── routes/
│   │       ├── timetable.py    ← Timetable CRUD + generation trigger
│   │       ├── chatbot.py      ← ScheduloBot WebSocket + REST endpoints
│   │       ├── faculty.py      ← Faculty list endpoint
│   │       └── placeholder_routes.py ← Stub routers for future endpoints
│   │
│   ├── scheduler_core/         ← 6-phase deterministic scheduling engine
│   │   ├── prototype_scheduler.py ← Main scheduler class (reads CSVs from data/)
│   │   ├── engine.py           ← Pipeline orchestrator
│   │   ├── phase1_demand.py    ← Demand calculation
│   │   ├── phase2_priority.py  ← Priority queue
│   │   ├── phase3_faculty.py   ← Faculty matching
│   │   ├── phase4_slots.py     ← Interval scheduling
│   │   ├── phase5_rooms.py     ← Bin packing (room assignment)
│   │   └── phase6_balance.py   ← Load balancing
│   │
│   ├── constraint_engine/      ← Hard + soft constraint definitions
│   │   ├── base.py             ← BaseConstraint + ConstraintViolation
│   │   ├── hard_constraints.py ← HC-01 through HC-08
│   │   └── soft_constraints.py ← SC-01 through SC-05
│   │
│   ├── ai_agents/              ← LangGraph multi-agent pipeline
│   │   ├── orchestrator.py     ← Agent graph builder
│   │   ├── scheduler_agent.py  ← Core scheduling agent
│   │   ├── conflict_resolution_agent.py
│   │   ├── quality_audit_agent.py
│   │   ├── constraint_analysis_agent.py
│   │   ├── chatbot_modification_agent.py
│   │   └── data_ingestion_agent.py
│   │
│   ├── chatbot_service/        ← ScheduloBot LLM client (Groq/HF/DB fallback)
│   │   └── llm_client.py
│   │
│   ├── conflict_detector/      ← Constraint violation scanner
│   │   └── detector.py
│   │
│   ├── data_ingestion/         ← CSV loading pipeline
│   │   └── csv_loader.py
│   │
│   ├── analytics_dashboard/    ← Quality metrics + reporting
│   │   └── metrics.py
│   │
│   └── export_engine/          ← Excel/PDF/DOCX export
│       ├── xlsx_renderer.py
│       ├── pdf_renderer.py
│       └── docx_renderer.py
│
├── frontend/                   ← React 18 + TypeScript UI (Vite)
│   └── src/
│       ├── pages/              ← Route-level page components
│       ├── components/         ← Reusable UI components
│       └── lib/                ← API client + WebSocket client
│
├── data/                       ← Source CSV datasets (committed to repo)
│   ├── Room_Dataset.csv
│   ├── Student_Sections_DATASET.csv
│   ├── Subjects_Dataset.csv
│   └── Teachers_Dataset.csv
│
├── scripts/                    ← Utility and maintenance scripts
│   ├── seed_from_csvs.py       ← DB seeder from CSV files
│   ├── generate_timetable.py   ← CLI timetable generator
│   ├── clean_subjects_table.py ← DB cleanup utility
│   ├── migrate_room_ids.py     ← Room ID migration helper
│   └── ml_training/            ← ML model training scripts
│       ├── train_quality_predictor.py
│       ├── train_anomaly_detector.py
│       └── model_registry.py
│
├── ml_models/                  ← Trained ML model files (.pkl)
│   ├── quality_predictor.pkl   ← XGBoost quality scoring model
│   └── anomaly_detector.pkl    ← Isolation Forest anomaly model
│
├── tests/                      ← Automated test suite
│   ├── conftest.py             ← Shared fixtures (async DB sessions)
│   ├── unit/                   ← Unit tests (no DB/network required)
│   └── integration/            ← Integration tests (live DB)
│
├── alembic/                    ← Database migration scripts
│   ├── env.py                  ← Async migration runner
│   └── versions/               ← Migration revision files
│
├── outputs/                    ← Generated timetable files (gitignored)
├── logs/                       ← Application logs (gitignored)
└── docs/                       ← Developer documentation
```

## Data Flow

```
CSV Files (data/) ──► seed_from_csvs.py ──► SQLite/PostgreSQL DB
                                                    │
Frontend Request ──► FastAPI (main.py) ──► SchedulerAgent
                                                    │
                              PrototypeScheduler (6-phase engine)
                                                    │
                              TimetableSlot rows saved to DB
                                                    │
                  ◄── JSON response ◄── API Gateway ◄──
```

## AI Chatbot Flow

```
User message ──► ScheduloBot (frontend) ──► WebSocket /api/ws
                                                    │
                              LLM Client (llm_client.py)
                              1. Groq API (primary, fastest)
                              2. HuggingFace API (secondary)
                              3. DB Query Fallback (always works)
                                                    │
                              ◄── Streamed response ◄──
```

## Environment Tiers

| Tier | DB | Cache | Task Queue |
|------|----|-------|------------|
| Local (`ENVIRONMENT=local`) | SQLite | Memory | Inline (sync) |
| Server (`ENVIRONMENT=server`) | PostgreSQL | Redis | Celery |
| Cloud (`ENVIRONMENT=cloud`) | PostgreSQL | Redis | Celery + S3 |
