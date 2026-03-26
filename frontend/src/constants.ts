// Schedulo — shared frontend constants
// Import: import { API_BASE, WS_BASE } from "@/constants";

/** Base URL for the FastAPI backend REST API. */
export const API_BASE =
  import.meta.env.VITE_API_URL
    ? `${import.meta.env.VITE_API_URL}/api`
    : "http://localhost:8000/api";

/** WebSocket base URL (replaces http(s) with ws(s)). */
export const WS_BASE = API_BASE.replace(/^http/, "ws").replace("/api", "");

/** Max chat history messages displayed in ScheduloBot. */
export const MAX_CHAT_HISTORY = 100;

/** Polling interval (ms) for generation status updates in GeneratorWizard. */
export const GENERATION_POLL_MS = 2000;

/** Days of the week in Schedulo timetable order (Mon–Sat). */
export const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] as const;

/** Period time labels in order. */
export const PERIOD_LABELS = [
  "9:00–9:55",
  "9:55–10:50",
  "10:50–11:45",
  "11:45–12:40",
  "12:40–1:35",
  "1:35–2:30",
  "2:30–3:25",
  "3:25–4:20",
  "4:20–5:15",
] as const;
