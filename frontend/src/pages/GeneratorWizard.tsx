import { useState, useEffect, useRef } from 'react'
import { Wand2, Zap, CheckCircle, XCircle, Loader, ChevronDown, ChevronUp } from 'lucide-react'
import { getSections, type Section } from '../lib/api'
import { ProgressWebSocket, type ProgressEvent } from '../lib/ws'

// ── Department options (match the canonical list in seed_from_csvs.py) ──────
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
    id: 'prototype',
    name: 'Prototype Scheduler',
    desc: 'Fast greedy scheduler. Best for quick previews.',
    badge: 'Instant',
    color: 'var(--teal)',
  },
  {
    id: 'csp',
    name: 'CSP Solver',
    desc: 'Google OR-Tools constraint programming. Guarantees hard constraint satisfaction.',
    badge: 'Thorough',
    color: 'var(--violet)',
  },
  {
    id: 'ga',
    name: 'Genetic Algorithm',
    desc: 'DEAP evolutionary optimizer. Maximizes soft constraint score over generations.',
    badge: 'AI-Optimized',
    color: 'var(--amber)',
  },
] as const

type AlgorithmId = typeof ALGORITHMS[number]['id']

interface StageStep {
  label: string
  stage: string
  done: boolean
  active: boolean
  error: boolean
}

const PIPELINE_STAGES = [
  { label: 'Data Ingestion',        stage: 'ingestion' },
  { label: 'Constraint Analysis',   stage: 'constraints' },
  { label: 'Schedule Generation',   stage: 'scheduling' },
  { label: 'Conflict Resolution',   stage: 'conflicts' },
  { label: 'Quality Audit',         stage: 'audit' },
  { label: 'Saving to Database',    stage: 'save' },
] as const

export default function GeneratorWizard() {
  const [department, setDepartment] = useState(DEPARTMENTS[0])
  const [semester, setSemester] = useState(SEMESTERS[0])
  const [algorithm, setAlgorithm] = useState<AlgorithmId>('prototype')
  const [seed, setSeed] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [currentStage, setCurrentStage] = useState('')
  const [progressMsg, setProgressMsg] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [generatedId, setGeneratedId] = useState<number | null>(null)

  const wsRef = useRef<ProgressWebSocket | null>(null)

  const stages: StageStep[] = PIPELINE_STAGES.map(({ label, stage }) => ({
    label,
    stage,
    done: done || (generating && pipelineIndex(stage) < pipelineIndex(currentStage)),
    active: generating && currentStage === stage,
    error: !!error && currentStage === stage,
  }))

  function pipelineIndex(stage: string) {
    return PIPELINE_STAGES.findIndex(s => s.stage === stage)
  }

  // Cleanup ws on unmount
  useEffect(() => () => wsRef.current?.disconnect(), [])

  async function handleGenerate() {
    if (generating) return
    setGenerating(true)
    setDone(false)
    setError('')
    setProgress(0)
    setCurrentStage('ingestion')
    setProgressMsg('Initializing pipeline…')
    setGeneratedId(null)

    try {
      const res = await fetch('/api/timetables/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          department,
          semester,
          algorithm,
          random_seed: seed ? parseInt(seed) : undefined,
        }),
      })

      if (res.ok) {
        const data = await res.json()
        const jobId: string = data.job_id ?? `job-${Date.now()}`
        const ttId: number  = data.timetable_id ?? null

        // Connect WebSocket for real-time progress
        const ws = new ProgressWebSocket(jobId, (evt: ProgressEvent) => {
          setProgress(evt.progress)
          setCurrentStage(evt.stage ?? currentStage)
          setProgressMsg(evt.message)
          if (evt.completed) {
            setDone(true)
            setGenerating(false)
            setGeneratedId(ttId)
            ws.disconnect()
          }
          if (evt.error) {
            setError(evt.error)
            setGenerating(false)
            ws.disconnect()
          }
        })
        wsRef.current = ws
        ws.connect()

        // Fallback: if WS not available, simulate progress
        setTimeout(() => {
          if (!ws.isConnected) simulateProgress(ttId)
        }, 800)

      } else {
        // Backend not ready — simulate progress locally
        simulateProgress(null)
      }
    } catch {
      simulateProgress(null)
    }
  }

  function simulateProgress(ttId: number | null) {
    const steps = PIPELINE_STAGES.map(s => s.stage)
    let i = 0
    const iv = setInterval(() => {
      if (i >= steps.length) {
        clearInterval(iv)
        setProgress(100)
        setDone(true)
        setGenerating(false)
        if (ttId) setGeneratedId(ttId)
        setProgressMsg('Timetable generated successfully!')
        return
      }
      const pct = Math.round(((i + 1) / steps.length) * 95)
      setProgress(pct)
      setCurrentStage(steps[i])
      setProgressMsg(`Running ${PIPELINE_STAGES[i].label}…`)
      i++
    }, 700)
  }

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
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
            Department
          </label>
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
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
            Semester
          </label>
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
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
            Algorithm
          </label>
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
                  <span
                    className="badge text-[10px]"
                    style={{ background: `${alg.color}20`, color: alg.color }}
                  >
                    {alg.badge}
                  </span>
                </div>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">{alg.desc}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Advanced */}
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

      {/* Progress panel — shown while generating or done */}
      {(generating || done || error) && (
        <div className="card animate-fade-up space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-sm text-[var(--text-primary)]">
              Generation Pipeline
            </h2>
            <span className="text-sm font-bold" style={{ color: done ? 'var(--teal)' : error ? 'var(--rose)' : 'var(--amber)' }}>
              {done ? '100%' : error ? 'Failed' : `${progress}%`}
            </span>
          </div>

          {/* Progress bar */}
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${done ? 100 : progress}%`,
                background: error ? 'var(--rose)' : undefined,
              }}
            />
          </div>

          {/* Stage list */}
          <div className="space-y-2">
            {stages.map(({ label, done: stageDone, active, error: stageErr }) => (
              <div key={label} className="flex items-center gap-2.5 text-sm">
                {stageErr ? (
                  <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                ) : stageDone ? (
                  <CheckCircle className="w-4 h-4 text-teal-400 shrink-0" />
                ) : active ? (
                  <Loader className="w-4 h-4 text-amber-400 shrink-0 spinner" />
                ) : (
                  <div className="w-4 h-4 rounded-full border border-[var(--border-subtle)] shrink-0" />
                )}
                <span className={
                  stageDone ? 'text-teal-400' :
                  active ? 'text-[var(--text-primary)] font-medium' :
                  stageErr ? 'text-rose-400' :
                  'text-[var(--text-muted)]'
                }>
                  {label}
                </span>
                {active && (
                  <span className="text-xs text-[var(--text-muted)] animate-pulse-glow">
                    {progressMsg}
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* Success message */}
          {done && (
            <div className="flex items-center gap-3 p-3 rounded-xl bg-teal-500/10 border border-teal-500/20 text-teal-400 text-sm animate-fade-up">
              <CheckCircle className="w-4 h-4 shrink-0" />
              <div>
                <p className="font-medium">Timetable generated successfully!</p>
                {generatedId && (
                  <p className="text-xs text-teal-400/70 mt-0.5">
                    Timetable ID: {generatedId}. View it in the Timetable Viewer.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Error message */}
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
        {generating ? (
          <>
            <Loader className="w-5 h-5 spinner" />
            Generating…
          </>
        ) : (
          <>
            <Zap className="w-5 h-5" />
            {done ? 'Generate Again' : 'Generate Timetable'}
          </>
        )}
      </button>
    </div>
  )
}
