import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Wand2, Zap, CheckCircle, XCircle, Loader, Eye,
  ChevronDown, ChevronUp, Plus, Trash2, BookOpen, FlaskConical,
} from 'lucide-react'
import { generateTimetable, type CustomSubject } from '../lib/api'
import { ProgressWebSocket, type ProgressEvent } from '../lib/ws'

// ── Constants ─────────────────────────────────────────────────────────────────

const DEPARTMENTS = [
  'School of Computer Science & Engineering',
  'School of Management',
  'IILM Law School',
  'School of Hospitality & Services Management',
  'School of Design',
  'School of Psychology',
  'School of Journalism & Communication',
  'School of Liberal Arts & Social Sciences',
  'School of Biotechnology',
]

const SEMESTERS = ['Sem 1', 'Sem 2', 'Sem 3', 'Sem 4', 'Sem 5', 'Sem 6', 'Sem 7', 'Sem 8']

const ALGORITHMS = [
  {
    id: 'fcfs' as const,
    name: 'FCFS — First Come First Served',
    desc: 'Subjects scheduled in dataset order. Slots filled Monday → Saturday, Period 1 → 9. Deterministic, fair, zero-randomness.',
    badge: 'Deterministic',
    color: 'var(--teal)',
  },
  {
    id: 'priority' as const,
    name: 'Priority-Based',
    desc: 'High-credit / high-priority subjects placed first in morning slots. Core courses won\'t get pushed to evenings.',
    badge: 'Optimised',
    color: 'var(--amber)',
  },
  {
    id: 'round_robin' as const,
    name: 'Round-Robin',
    desc: 'Each subject gets one slot per turn, cycling evenly. Maximally balanced distribution across the entire week.',
    badge: 'Balanced',
    color: 'var(--violet)',
  },
  {
    id: 'prototype' as const,
    name: 'Prototype (Greedy)',
    desc: 'Original greedy scheduler with constraint enforcement. Best for quick previews.',
    badge: 'Fast',
    color: 'var(--rose)',
  },
] as const

type AlgorithmId = typeof ALGORITHMS[number]['id']

const PIPELINE_STAGES = [
  { label: 'Data Ingestion',      stage: 'ingestion' },
  { label: 'Constraint Analysis', stage: 'constraints' },
  { label: 'Schedule Generation', stage: 'scheduling' },
  { label: 'Conflict Resolution', stage: 'conflicts' },
  { label: 'Quality Audit',       stage: 'audit' },
  { label: 'Saving to Database',  stage: 'save' },
] as const

// ── Empty subject factory ──────────────────────────────────────────────────────
function emptySubject(): CustomSubject & { id: number } {
  return {
    id: Date.now() + Math.random(),
    name: '',
    subject_type: 'THEORY',
    duration: 1,
    days_per_week: 3,
    priority: 2,
  }
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function GeneratorWizard() {
  const navigate = useNavigate()
  const [department, setDepartment]     = useState(DEPARTMENTS[0])
  const [semester, setSemester]         = useState(SEMESTERS[0])
  const [algorithm, setAlgorithm]       = useState<AlgorithmId>('prototype')
  const [seed, setSeed]                 = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [useCustom, setUseCustom]       = useState(false)

  type SubjectRow = CustomSubject & { id: number }
  const [subjects, setSubjects] = useState<SubjectRow[]>([emptySubject()])

  const [generating, setGenerating] = useState(false)
  const [progress, setProgress]     = useState(0)
  const [currentStage, setCurrentStage] = useState('')
  const [progressMsg, setProgressMsg]   = useState('')
  const [done, setDone]         = useState(false)
  const [error, setError]       = useState('')
  const [generatedId, setGeneratedId] = useState<number | null>(null)

  const wsRef = useRef<ProgressWebSocket | null>(null)
  useEffect(() => () => wsRef.current?.disconnect(), [])

  // ── Subject helpers ────────────────────────────────────────────────────────
  function addSubject() {
    setSubjects(prev => [...prev, emptySubject()])
  }

  function removeSubject(id: number) {
    setSubjects(prev => prev.length === 1 ? prev : prev.filter(s => s.id !== id))
  }

  function updateSubject(id: number, key: keyof CustomSubject, value: string | number) {
    setSubjects(prev => prev.map(s => s.id === id ? { ...s, [key]: value } : s))
  }

  // ── Stage helpers ──────────────────────────────────────────────────────────
  function pipelineIndex(stage: string) {
    return PIPELINE_STAGES.findIndex(s => s.stage === stage)
  }

  const stages = PIPELINE_STAGES.map(({ label, stage }) => ({
    label,
    stage,
    done: done || (generating && pipelineIndex(stage) < pipelineIndex(currentStage)),
    active: generating && currentStage === stage,
    error: !!error && currentStage === stage,
  }))

  // ── Generate ───────────────────────────────────────────────────────────────
  async function handleGenerate() {
    if (generating) return

    // Validate custom subjects
    if (useCustom) {
      const invalid = subjects.some(s => !s.name.trim())
      if (invalid) { setError('All subjects must have a name.'); return }
    }

    setGenerating(true)
    setDone(false)
    setError('')
    setProgress(0)
    setCurrentStage('ingestion')
    setProgressMsg('Initializing pipeline…')
    setGeneratedId(null)

    try {
      const body: Parameters<typeof generateTimetable>[0] = {
        department,
        semester,
        algorithm,
        random_seed: seed ? parseInt(seed) : undefined,
        custom_subjects: useCustom
          ? subjects
              .filter(s => s.name.trim())
              .map(({ id: _id, ...rest }) => rest)
          : undefined,
      }

      const data = await generateTimetable(body)
      const ttId = data.timetable_id

      // Connect WebSocket for real-time progress
      const ws = new ProgressWebSocket(data.job_id ?? `job-${Date.now()}`, (evt: ProgressEvent) => {
        setProgress(evt.progress)
        setCurrentStage(evt.stage ?? currentStage)
        setProgressMsg(evt.message)
        if (evt.completed) {
          setDone(true); setGenerating(false); setGeneratedId(ttId); ws.disconnect()
        }
        if (evt.error) {
          setError(evt.error); setGenerating(false); ws.disconnect()
        }
      })
      wsRef.current = ws
      ws.connect()
      setTimeout(() => { if (!ws.isConnected) simulateProgress(ttId) }, 800)

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      // API returned an error — still simulate pipeline visually then show error
      setError(msg)
      setGenerating(false)
    }
  }

  function simulateProgress(ttId: number | null) {
    const steps = PIPELINE_STAGES.map(s => s.stage)
    let i = 0
    const iv = setInterval(() => {
      if (i >= steps.length) {
        clearInterval(iv)
        setProgress(100); setDone(true); setGenerating(false)
        if (ttId) setGeneratedId(ttId)
        setProgressMsg('Timetable generated successfully!')
        return
      }
      setProgress(Math.round(((i + 1) / steps.length) * 95))
      setCurrentStage(steps[i])
      setProgressMsg(`Running ${PIPELINE_STAGES[i].label}…`)
      i++
    }, 700)
  }

  // ── UI ─────────────────────────────────────────────────────────────────────
  return (
    <div className="p-8 max-w-2xl mx-auto space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          <Wand2 className="inline w-6 h-6 mb-1 mr-2 text-amber-400" />
          Generator <span className="gradient-text">Wizard</span>
        </h1>
        <p className="text-[var(--text-muted)] text-sm mt-1">
          Configure and launch an AI-powered timetable generation run
        </p>
      </div>

      {/* Form card */}
      <div className="card space-y-5">

        {/* Department */}
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">Department</label>
          <select
            id="gen-department"
            className="select"
            value={department}
            onChange={e => setDepartment(e.target.value)}
            disabled={generating}
          >
            {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        {/* Semester */}
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">Semester</label>
          <div className="flex flex-wrap gap-2">
            {SEMESTERS.map(s => (
              <button
                key={s}
                onClick={() => setSemester(s)}
                disabled={generating}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
                  semester === s
                    ? 'border-teal-500 bg-teal-500/10 text-teal-400'
                    : 'border-[var(--border-subtle)] text-[var(--text-muted)] hover:border-[var(--border-subtle)] hover:text-[var(--text-primary)]'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Algorithm */}
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">Algorithm</label>
          <div className="space-y-2">
            {ALGORITHMS.map(alg => (
              <button
                key={alg.id}
                id={`algo-${alg.id}`}
                onClick={() => setAlgorithm(alg.id)}
                disabled={generating}
                className={`w-full text-left p-3 rounded-xl border transition-all ${
                  algorithm === alg.id
                    ? 'border-[var(--teal)] bg-teal-500/5'
                    : 'border-[var(--border)] hover:border-[var(--border-subtle)]'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm text-[var(--text-primary)]">{alg.name}</span>
                  <span className="badge text-[10px]" style={{ background: `${alg.color}20`, color: alg.color }}>
                    {alg.badge}
                  </span>
                </div>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">{alg.desc}</p>
              </button>
            ))}
          </div>
        </div>

        {/* ── Custom Subjects ── */}
        <div className="border-t border-[var(--border)] pt-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-sm font-medium text-[var(--text-secondary)]">Custom Subjects</p>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                Define specific subjects with duration, priority & days/week
              </p>
            </div>
            <button
              id="toggle-custom-subjects"
              onClick={() => setUseCustom(p => !p)}
              disabled={generating}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                useCustom ? 'bg-teal-500' : 'bg-[var(--border)]'
              }`}
            >
              <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                useCustom ? 'translate-x-4' : 'translate-x-1'
              }`} />
            </button>
          </div>

          {useCustom && (
            <div className="space-y-3 animate-fade-up">
              {subjects.map((subj, idx) => (
                <div
                  key={subj.id}
                  className="rounded-xl border border-[var(--border)] p-3 space-y-3 bg-[var(--bg-secondary)]"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-[var(--text-muted)]">Subject {idx + 1}</span>
                    <button
                      onClick={() => removeSubject(subj.id)}
                      disabled={generating || subjects.length === 1}
                      className="text-[var(--text-muted)] hover:text-rose-400 transition-colors disabled:opacity-30"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Subject name */}
                  <input
                    type="text"
                    className="input"
                    placeholder="Subject name (e.g. Data Structures)"
                    value={subj.name}
                    onChange={e => updateSubject(subj.id, 'name', e.target.value)}
                    disabled={generating}
                  />

                  <div className="grid grid-cols-2 gap-3">
                    {/* Type */}
                    <div>
                      <label className="block text-[10px] text-[var(--text-muted)] mb-1">Type</label>
                      <div className="flex gap-2">
                        {(['THEORY', 'LAB'] as const).map(t => (
                          <button
                            key={t}
                            onClick={() => updateSubject(subj.id, 'subject_type', t)}
                            disabled={generating}
                            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs border transition-all ${
                              subj.subject_type === t
                                ? t === 'LAB'
                                  ? 'border-violet-500 bg-violet-500/10 text-violet-400'
                                  : 'border-teal-500 bg-teal-500/10 text-teal-400'
                                : 'border-[var(--border)] text-[var(--text-muted)]'
                            }`}
                          >
                            {t === 'LAB'
                              ? <FlaskConical className="w-3 h-3" />
                              : <BookOpen className="w-3 h-3" />
                            }
                            {t}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Duration */}
                    <div>
                      <label className="block text-[10px] text-[var(--text-muted)] mb-1">
                        Duration (periods/session)
                      </label>
                      <select
                        className="select text-sm py-1.5"
                        value={subj.duration}
                        onChange={e => updateSubject(subj.id, 'duration', parseInt(e.target.value))}
                        disabled={generating}
                      >
                        <option value={1}>1 period</option>
                        <option value={2}>2 periods (lab pair)</option>
                        <option value={3}>3 periods</option>
                      </select>
                    </div>

                    {/* Days/week */}
                    <div>
                      <label className="block text-[10px] text-[var(--text-muted)] mb-1">
                        Days per week
                      </label>
                      <select
                        className="select text-sm py-1.5"
                        value={subj.days_per_week}
                        onChange={e => updateSubject(subj.id, 'days_per_week', parseInt(e.target.value))}
                        disabled={generating}
                      >
                        {[1, 2, 3, 4, 5, 6].map(n => (
                          <option key={n} value={n}>{n}×/week</option>
                        ))}
                      </select>
                    </div>

                    {/* Priority */}
                    <div>
                      <label className="block text-[10px] text-[var(--text-muted)] mb-1">Priority</label>
                      <div className="flex gap-1.5">
                        {[
                          { v: 1, label: 'Low',  color: 'text-[var(--text-muted)] border-[var(--border)]' },
                          { v: 2, label: 'Med',  color: 'text-amber-400 border-amber-500/50 bg-amber-500/5' },
                          { v: 3, label: 'High', color: 'text-rose-400 border-rose-500/50 bg-rose-500/5' },
                        ].map(({ v, label, color }) => (
                          <button
                            key={v}
                            onClick={() => updateSubject(subj.id, 'priority', v)}
                            disabled={generating}
                            className={`flex-1 py-1.5 rounded-lg text-[10px] font-medium border transition-all ${
                              subj.priority === v ? color : 'border-[var(--border)] text-[var(--text-muted)]'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))}

              <button
                id="btn-add-subject"
                onClick={addSubject}
                disabled={generating}
                className="btn btn-secondary w-full justify-center text-sm py-2 border-dashed"
              >
                <Plus className="w-4 h-4" />
                Add Another Subject
              </button>
            </div>
          )}
        </div>

        {/* Advanced Options */}
        <div>
          <button
            className="btn btn-ghost text-xs"
            onClick={() => setShowAdvanced(p => !p)}
          >
            {showAdvanced ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            Advanced Options
          </button>
          {showAdvanced && (
            <div className="mt-3 animate-fade-up">
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
                Random Seed <span className="text-[var(--text-muted)] font-normal">(optional — for reproducibility)</span>
              </label>
              <input
                id="gen-seed"
                type="number"
                className="input w-40"
                placeholder="e.g. 42"
                value={seed}
                onChange={e => setSeed(e.target.value)}
                disabled={generating}
              />
            </div>
          )}
        </div>
      </div>

      {/* Progress panel */}
      {(generating || done || error) && (
        <div className="card animate-fade-up space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-sm text-[var(--text-primary)]">Generation Pipeline</h2>
            <span className="text-sm font-bold" style={{ color: done ? 'var(--teal)' : error ? 'var(--rose)' : 'var(--amber)' }}>
              {done ? '100%' : error ? 'Failed' : `${progress}%`}
            </span>
          </div>

          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${done ? 100 : progress}%`, background: error ? 'var(--rose)' : undefined }}
            />
          </div>

          <div className="space-y-2">
            {stages.map(({ label, done: stageDone, active, error: stageErr }) => (
              <div key={label} className="flex items-center gap-2.5 text-sm">
                {stageErr    ? <XCircle    className="w-4 h-4 text-rose-400 shrink-0" />
                : stageDone  ? <CheckCircle className="w-4 h-4 text-teal-400 shrink-0" />
                : active     ? <Loader      className="w-4 h-4 text-amber-400 shrink-0 spinner" />
                              : <div className="w-4 h-4 rounded-full border border-[var(--border-subtle)] shrink-0" />}
                <span className={
                  stageDone ? 'text-teal-400' :
                  active    ? 'text-[var(--text-primary)] font-medium' :
                  stageErr  ? 'text-rose-400' :
                              'text-[var(--text-muted)]'
                }>{label}</span>
                {active && <span className="text-xs text-[var(--text-muted)] animate-pulse-glow">{progressMsg}</span>}
              </div>
            ))}
          </div>

          {done && (
            <div className="flex flex-col gap-2 p-3 rounded-xl bg-teal-500/10 border border-teal-500/20 text-teal-400 text-sm animate-fade-up">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 shrink-0" />
                <div>
                  <p className="font-medium">Timetable generated successfully!</p>
                  {generatedId && (
                    <p className="text-xs text-teal-400/70 mt-0.5">
                      Timetable ID: {generatedId} • Algorithm: <span className="capitalize">{algorithm.replace('_', ' ')}</span>
                    </p>
                  )}
                </div>
              </div>
              {generatedId && (
                <button
                  id="btn-view-timetable"
                  className="btn btn-primary w-full justify-center text-sm py-2"
                  onClick={() => navigate(`/timetable?ttId=${generatedId}`)}
                >
                  <Eye className="w-4 h-4" />
                  View My Timetable
                </button>
              )}
            </div>
          )}

          {error && (
            <div className="flex items-center gap-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
              <XCircle className="w-4 h-4 shrink-0" />
              {error}
            </div>
          )}
        </div>
      )}

      {/* Generate button */}
      <button
        id="btn-generate"
        onClick={handleGenerate}
        disabled={generating}
        className="btn btn-primary w-full justify-center py-3 text-base"
      >
        {generating
          ? <><Loader className="w-5 h-5 spinner" /> Generating…</>
          : <><Zap className="w-5 h-5" /> {done ? 'Generate Again' : 'Generate Timetable'}</>
        }
      </button>
    </div>
  )
}
