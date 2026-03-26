/**
 * src/lib/api.ts — Typed API client for Schedulo backend.
 * All functions return typed Promises; errors are re-thrown as Error instances.
 */

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText)
    throw new Error(`API ${res.status}: ${msg}`)
  }
  return res.json() as Promise<T>
}

// ── Types ─────────────────────────────────────────────────────────────────

export interface Room {
  id: number
  room_id: string
  building: string
  type: string
  capacity: number
}

export interface Subject {
  id: number
  name: string
  type: string
  credits: number
  weekly_periods: number
}

export interface Section {
  id: number
  section_id: string
  semester: string | null
  strength: number | null
  program: string | null
}

export interface Faculty {
  id: number
  teacher_id: string | null
  name: string
  department: string | null
  main_subject: string | null
}

export interface Timetable {
  id: number
  name: string | null
  department: string | null
  academic_year: string | null
  semester: string | null
  status: string
  ga_fitness_score: number | null
  conflict_count: number
  generation_time_ms: number | null
  created_at: string
}

export interface TimetableSlot {
  id: number
  day_name: string
  period_number: number
  period_label: string
  slot_type: string
  cell_display_line1: string | null
  cell_display_line2: string | null
  cell_display_line3: string | null
  is_lab_continuation: boolean
  section_id: number | null
}

export interface ConflictItem {
  id: number
  type: string
  severity: string
  description: string
  resolved: boolean
}

export interface AnalyticsSummary {
  timetable_id: number
  total_slots: number
  slot_type_distribution: Record<string, number>
  total_conflicts: number
  unresolved_conflicts: number
}

export interface CustomSubject {
  name: string
  subject_type: 'THEORY' | 'LAB'
  duration: number          // periods per session
  days_per_week: number     // periods per week
  priority: number          // 1=low 2=medium 3=high
}

export interface GenerateRequest {
  department: string
  semester?: string
  algorithm?: 'prototype' | 'fcfs' | 'priority' | 'round_robin' | 'ga'
  random_seed?: number
  custom_subjects?: CustomSubject[]
}

export interface GenerateResponse {
  timetable_id: number
  job_id?: string
  status: string
  message: string
}

export interface ChatRequest {
  session_id: string
  timetable_id: number
  message: string
}

// ── API Functions ─────────────────────────────────────────────────────────

// Rooms
export const getRooms = ()                  => request<Room[]>('/rooms/')
export const getAvailableRooms = (day: string, period: number, ttId: number) =>
  request<Room[]>(`/rooms/available?day=${day}&period=${period}&timetable_id=${ttId}`)

// Subjects
export const getSubjects = ()               => request<Subject[]>('/subjects/')

// Sections
export const getSections = ()               => request<Section[]>('/sections/')

// Faculty
export const getFaculty = ()                => request<Faculty[]>('/faculty/')

// Timetables
export const getTimetables = ()             => request<Timetable[]>('/timetables/')
export const getTimetable = (id: number)    => request<Timetable>(`/timetables/${id}`)
export const deleteTimetable = (id: number) =>
  request<void>(`/timetables/${id}`, { method: 'DELETE' })

export const generateTimetable = (body: GenerateRequest) =>
  request<GenerateResponse>('/timetables/generate', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const getTimetableSlots = (ttId: number, sectionId?: number) => {
  const q = sectionId ? `?section_id=${sectionId}` : ''
  return request<TimetableSlot[]>(`/timetables/${ttId}/slots${q}`)
}

// Conflicts
export const getConflicts = (ttId: number)  => request<ConflictItem[]>(`/conflicts/?timetable_id=${ttId}`)

// Analytics
export const getAnalytics = (ttId: number)  => request<AnalyticsSummary>(`/analytics/summary/${ttId}`)

// Auth
export const login = (username: string, password: string) => {
  const body = new URLSearchParams({ username, password })
  return fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  }).then(r => r.json())
}

// Chatbot
export const sendChatMessage = (body: ChatRequest) =>
  request<{ response: string; session_id: string }>('/chatbot/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  })

// Sections within a timetable
export interface TimetableSection {
  id: number
  label: string
}

export const getTimetableSections = (ttId: number) =>
  request<{ timetable_id: number; sections: TimetableSection[] }>(`/timetables/${ttId}/sections`)

// Download timetable file (triggers browser download)
export function downloadTimetable(ttId: number, format: 'xlsx' | 'zip'): void {
  const url = `/api/timetables/${ttId}/download/${format}`
  const a = document.createElement('a')
  a.href = url
  a.download = `timetable-${ttId}.${format}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
