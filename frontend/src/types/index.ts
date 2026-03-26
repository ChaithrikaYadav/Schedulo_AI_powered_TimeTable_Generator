// Shared TypeScript type definitions for Schedulo frontend
// Import from "@/types" in your components

export interface Timetable {
  id: number;
  name: string;
  department_id: number;
  academic_year: string;
  semester: string;
  status: "DRAFT" | "GENERATING" | "COMPLETED" | "FAILED";
  created_at: string;
  updated_at: string;
}

export interface TimetableSlot {
  id: number;
  timetable_id: number;
  section_id: string;
  day_of_week: number;
  day_name: string;
  period_number: number;
  period_label: string;
  slot_type: "THEORY" | "LAB" | "LUNCH" | "FREE";
  cell_display_line1?: string;
  cell_display_line2?: string;
  cell_display_line3?: string;
}

export interface Department {
  id: number;
  name: string;
  short_code: string;
}

export interface Faculty {
  id: number;
  name: string;
  department_id: number;
  main_subject: string;
  max_classes_per_week: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface GenerationProgress {
  status: "idle" | "running" | "done" | "error";
  phase: string;
  percent: number;
  message: string;
}
