# ChronoAI — Task Checklist

## Phase 1: Project Scaffold & Database (Weeks 1–2)
- [/] Create project directory structure under `chronoai/`
- [ ] Write `config.py` with 3-tier settings (Local/Server/Cloud)
- [ ] Write SQLAlchemy models matching DB schema (Section 2.3)
- [ ] Write Alembic migration config
- [ ] Write `scripts/seed_from_csvs.py` with all 6 CSV loaders + DEPT_CODE_MAP
- [ ] Write `requirements.local.txt`
- [ ] Write `.env.local.example`
- [ ] Write `docker-compose.local.yml`
- [ ] Write FastAPI skeleton (`main.py`, `api_gateway/`)
- [ ] Write `run.py` (entry point)
- [ ] Fix [app.py](file:///c:/Users/Aryan%20Singh/OneDrive/Music/Antigravity%20Projects/Schedulo_AI_powered_TimeTable_Generator/app.py) openpyxl `writer.save()` bug (keep Streamlit app runnable)

## Phase 2: Constraint Engine & Core Scheduler
- [ ] Implement `BaseConstraint` ABC
- [ ] Implement HC-01 through HC-08 hard constraint classes
- [ ] Implement SC-01 through SC-08 soft constraint classes
- [ ] Port [build_timetable()](file:///c:/Users/Aryan%20Singh/OneDrive/Music/Antigravity%20Projects/Schedulo_AI_powered_TimeTable_Generator/timetable_generator.py#74-162) to `PrototypeScheduler` class
- [ ] Replace random subject/weekly count with credits-based from [course_dataset_final.csv](file:///c:/Users/Aryan%20Singh/OneDrive/Music/Antigravity%20Projects/Schedulo_AI_powered_TimeTable_Generator/course_dataset_final.csv)
- [ ] Add Saturday as Day 6
- [ ] Implement OR-Tools CSP solver (Stage 2)
- [ ] Implement DEAP Genetic Algorithm (Stage 3)

## Phase 3: ML Pipeline
- [ ] Feature engineering pipeline (scikit-learn)
- [ ] XGBoost quality predictor (Stage 4)
- [ ] PPO RL fine-tuner with Gymnasium (Stage 5)
- [ ] Isolation Forest anomaly detector (Stage 6)

## Phase 4: AI Agents (LangGraph)
- [ ] DataIngestionAgent
- [ ] ConstraintAnalysisAgent
- [ ] SchedulerAgent (Core)
- [ ] ConflictResolutionAgent
- [ ] IllustrationAgent
- [ ] QualityAuditAgent
- [ ] ChatbotModificationAgent
- [ ] LangGraph DAG orchestration
- [ ] WebSocket progress reporting

## Phase 5: Export Engine
- [ ] ReportLab PDF renderer (pixel-perfect aSc match)
- [ ] python-docx DOCX renderer
- [ ] openpyxl XLSX renderer
- [ ] Async Celery export jobs
- [ ] Download API endpoints

## Phase 6: ChronoBot (Chatbot)
- [ ] `ChronoBotLLMClient` (HuggingFace Inference API wrapper)
- [ ] Streaming SSE `/api/chatbot/stream` endpoint
- [ ] All 8 chatbot tool implementations (F1–F8)
- [ ] Conversation history persistence
- [ ] Undo/rollback mechanism

## Phase 7: React Frontend
- [ ] Vite + TypeScript + Shadcn/UI + Tailwind scaffold
- [ ] CSS variables (`globals.css`) with full design token set
- [ ] Sidebar component (persistent navigation)
- [ ] Screen 1: Dashboard Overview
- [ ] Screen 2: Timetable Viewer (TimetableGrid component)
- [ ] Screen 3: ChronoBot Interface
- [ ] Screen 4: Generator Wizard
- [ ] Real-time WebSocket progress dashboard

## Phase 8: Testing & Documentation
- [ ] Unit tests (pytest, 90% coverage goal)
- [ ] Integration tests
- [ ] Property-based tests (Hypothesis)
- [ ] E2E tests (Playwright)
- [ ] README.md
- [ ] ARCHITECTURE.md
- [ ] DEPLOYMENT.md
- [ ] API_REFERENCE.md
