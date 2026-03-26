import React, { useEffect, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Calendar, RefreshCw, Download, FileSpreadsheet, Archive, Search } from 'lucide-react'
import {
  getTimetables, getTimetableSlots, getTimetableSections,
  downloadTimetable,
  type Timetable, type TimetableSlot, type TimetableSection,
} from '../lib/api'

const DAYS    = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const PERIODS = [
  '9:00–9:55', '9:55–10:50', '10:50–11:45', '11:45–12:40',
  '12:40–1:35', '1:35–2:30',  '2:30–3:25',  '3:25–4:20',   '4:20–5:15',
]

function slotClass(type: string) {
  switch (type.toUpperCase()) {
    case 'THEORY':  return 'theory'
    case 'LAB':     return 'lab'
    case 'LAB_CONT': return 'lab-cont'
    case 'LUNCH':   return 'lunch'
    default:        return 'free'
  }
}

function slotColor(type: string) {
  switch (type.toUpperCase()) {
    case 'THEORY':  return 'var(--teal)'
    case 'LAB':
    case 'LAB_CONT': return 'var(--violet)'
    case 'LUNCH':   return 'var(--amber)'
    default:        return 'var(--text-muted)'
  }
}

type SlotGrid = Record<string, Record<number, TimetableSlot | undefined>>

function buildGrid(slots: TimetableSlot[]): SlotGrid {
  const grid: SlotGrid = {}
  for (const day of DAYS) grid[day] = {}
  for (const s of slots) {
    if (!grid[s.day_name]) grid[s.day_name] = {}
    grid[s.day_name][s.period_number] = s
  }
  return grid
}

/** Shorten a long timetable name for the dropdown */
function shortName(tt: Timetable): string {
  const name = tt.name ?? `TT-${tt.id}`
  // Show full name if short enough
  if (name.length <= 50) return name
  // Otherwise truncate intelligently
  return name.slice(0, 47) + '…'
}

export default function TimetableViewer() {
  const [searchParams] = useSearchParams()
  const [timetables,       setTimetables]       = useState<Timetable[]>([])
  const [filter,           setFilter]           = useState('')
  const [selectedId,       setSelectedId]       = useState<number | null>(null)
  const [slots,            setSlots]            = useState<TimetableSlot[]>([])
  const [sections,         setSections]         = useState<TimetableSection[]>([])
  const [selectedSection,  setSelectedSection]  = useState<number | null>(null)
  const [loading,          setLoading]          = useState(false)
  const [loadingTTs,       setLoadingTTs]       = useState(true)
  const [downloading,      setDownloading]      = useState<'xlsx' | 'zip' | null>(null)

  // Filtered list for dropdown
  const filteredTTs = timetables.filter(tt =>
    !filter || (tt.name ?? '').toLowerCase().includes(filter.toLowerCase())
  )

  // ── Load timetable list (respect ?ttId= from URL) ─────────────────────────
  useEffect(() => {
    getTimetables()
      .then(tts => {
        setTimetables(tts)
        // If URL has ?ttId=, select that specific timetable
        const urlId = searchParams.get('ttId')
        if (urlId && tts.find(t => t.id === Number(urlId))) {
          setSelectedId(Number(urlId))
        } else if (tts.length > 0) {
          setSelectedId(tts[0].id)
        }
      })
      .catch(() => {})
      .finally(() => setLoadingTTs(false))
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load slots & sections when timetable changes ──────────────────────────
  const loadSlots = useCallback(async (ttId: number, secId: number | null) => {
    setLoading(true)
    try {
      // Load slots
      const data = await getTimetableSlots(ttId, secId ?? undefined)
      setSlots(data)

      // Load section labels (only when switching timetable, not section)
      if (secId === null) {
        try {
          const secData = await getTimetableSections(ttId)
          const secs = secData.sections ?? []
          setSections(secs)
          if (secs.length > 0) setSelectedSection(secs[0].id)
        } catch {
          // Fall back to extracting from slots
          const ids = [...new Set(data.map(s => s.section_id).filter(Boolean) as number[])]
          setSections(ids.map(id => ({ id, label: `Section ${id}` })))
          if (ids.length > 0) setSelectedSection(ids[0])
        }
      }
    } catch {
      setSlots([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedId) {
      setSelectedSection(null)
      setSections([])
      loadSlots(selectedId, null)
    }
  }, [selectedId, loadSlots])

  useEffect(() => {
    if (selectedId && selectedSection !== null) {
      loadSlots(selectedId, selectedSection)
    }
  }, [selectedSection, selectedId, loadSlots])

  // ── Export handler ────────────────────────────────────────────────────────
  async function handleDownload(fmt: 'xlsx' | 'zip') {
    if (!selectedId || downloading) return
    setDownloading(fmt)
    try {
      downloadTimetable(selectedId, fmt)
    } finally {
      setTimeout(() => setDownloading(null), 1500)
    }
  }

  const grid = buildGrid(
    slots.filter(s => selectedSection == null || s.section_id === selectedSection)
  )

  const selectedTT = timetables.find(t => t.id === selectedId)

  return (
    <div className="p-8 space-y-6 max-w-full">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            <Calendar className="inline w-6 h-6 mb-1 mr-2 text-teal-400" />
            Timetable <span className="gradient-text">Viewer</span>
          </h1>
          <p className="text-[var(--text-muted)] text-sm mt-1">
            {selectedTT?.name
              ? <span title={selectedTT.name} className="text-[var(--text-secondary)]">{selectedTT.name}</span>
              : '6-day × 9-period weekly schedule'}
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Search + Timetable picker */}
          {loadingTTs ? (
            <div className="h-9 w-52 rounded-lg bg-[var(--bg-hover)] animate-pulse" />
          ) : (
            <div className="flex flex-col gap-1">
              {/* Search input */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-muted)]" />
                <input
                  id="filter-timetable"
                  type="text"
                  placeholder="Search timetables…"
                  className="input text-xs pl-7 h-8"
                  style={{ minWidth: '200px' }}
                  value={filter}
                  onChange={e => setFilter(e.target.value)}
                />
              </div>
              {/* Dropdown */}
              <select
                id="select-timetable"
                className="select"
                style={{ maxWidth: '300px' }}
                value={selectedId ?? ''}
                onChange={e => {
                  setSelectedId(Number(e.target.value))
                  setSelectedSection(null)
                  setSections([])
                  setSlots([])
                }}
              >
                <option value="" disabled>Select timetable…</option>
                {filteredTTs.map((tt, idx) => (
                  <option key={tt.id} value={tt.id} title={tt.name ?? ''}>
                    {idx === 0 ? '★ ' : ''}{shortName(tt)}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Section picker — shows actual section_id labels */}
          {sections.length > 0 && (
            <select
              id="select-section"
              className="select"
              style={{ minWidth: '140px' }}
              value={selectedSection ?? ''}
              onChange={e => setSelectedSection(Number(e.target.value))}
            >
              <option value="" disabled>Section…</option>
              {sections.map(sec => (
                <option key={sec.id} value={sec.id}>{sec.label}</option>
              ))}
            </select>
          )}

          {/* Refresh */}
          <button
            id="btn-refresh-timetable"
            className="btn btn-secondary"
            onClick={() => selectedId && loadSlots(selectedId, selectedSection)}
            disabled={loading}
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'spinner' : ''}`} />
          </button>

          {/* ── Export buttons ── */}
          {selectedId && (
            <>
              <button
                id="btn-download-xlsx"
                className="btn btn-secondary"
                onClick={() => handleDownload('xlsx')}
                disabled={!!downloading}
                title="Download as Excel (.xlsx)"
              >
                {downloading === 'xlsx'
                  ? <RefreshCw className="w-4 h-4 spinner" />
                  : <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                }
                <span className="text-xs">Excel</span>
              </button>

              <button
                id="btn-download-zip"
                className="btn btn-secondary"
                onClick={() => handleDownload('zip')}
                disabled={!!downloading}
                title="Download CSV bundle (.zip)"
              >
                {downloading === 'zip'
                  ? <RefreshCw className="w-4 h-4 spinner" />
                  : <Archive className="w-4 h-4 text-violet-400" />
                }
                <span className="text-xs">CSV</span>
              </button>
            </>
          )}
        </div>
      </div>

      {/* ── Legend ── */}
      <div className="flex items-center gap-4 text-xs">
        {[
          { label: 'Theory', color: 'var(--teal)' },
          { label: 'Lab',    color: 'var(--violet)' },
          { label: 'Lunch',  color: 'var(--amber)' },
          { label: 'Free',   color: 'var(--text-muted)' },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm" style={{ background: `${color}40`, border: `1px solid ${color}` }} />
            <span className="text-[var(--text-muted)]">{label}</span>
          </div>
        ))}
      </div>

      {/* ── No timetable state ── */}
      {!selectedId && !loadingTTs && (
        <div className="card text-center py-16">
          <Calendar className="w-12 h-12 mx-auto mb-4 text-[var(--text-muted)]" />
          <p className="text-[var(--text-secondary)]">No timetables found.</p>
          <p className="text-[var(--text-muted)] text-sm mt-1">Generate a timetable first.</p>
        </div>
      )}

      {/* ── Grid ── */}
      {selectedId && (
        <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
          {loading ? (
            <div className="flex items-center justify-center py-24">
              <RefreshCw className="w-6 h-6 text-teal-400 spinner" />
              <span className="ml-3 text-[var(--text-muted)]">Loading timetable…</span>
            </div>
          ) : (
            <div
              className="tt-grid"
              style={{ gridTemplateColumns: `80px repeat(${PERIODS.length}, minmax(100px, 1fr))` }}
            >
              {/* Column headers */}
              <div className="tt-header-cell">Day / Period</div>
              {PERIODS.map((p, i) => (
                <div key={p} className="tt-header-cell text-[10px]">
                  <span className="text-[var(--teal)] font-bold">{i + 1}</span>
                  <br />{p}
                </div>
              ))}

              {/* Rows */}
              {DAYS.map(day => (
                <React.Fragment key={day}>
                  <div className="tt-day-cell">{day.slice(0, 3).toUpperCase()}</div>
                  {PERIODS.map((_, pi) => {
                    const slot = grid[day]?.[pi + 1]
                    const type = slot?.slot_type ?? 'FREE'
                    return (
                      <div
                        key={`${day}-${pi}`}
                        className={`tt-slot ${slotClass(type)}`}
                      >
                        {slot && type === 'LUNCH' ? (
                          <div className="text-amber-400 font-medium text-xs text-center w-full mt-1">
                            LUNCH
                          </div>
                        ) : slot && type !== 'FREE' ? (
                          <>
                            {slot.cell_display_line1 && (
                              <div className="font-semibold leading-tight text-[11px]" style={{ color: slotColor(type) }}>
                                {slot.cell_display_line1}
                              </div>
                            )}
                            {slot.cell_display_line2 && (
                              <div className="text-[var(--text-muted)] leading-tight text-[10px]">
                                {slot.cell_display_line2}
                              </div>
                            )}
                            {slot.cell_display_line3 && (
                              <div className="text-[10px] text-[var(--text-muted)] leading-tight">
                                📍 {slot.cell_display_line3}
                              </div>
                            )}
                          </>
                        ) : null}
                      </div>
                    )
                  })}
                </React.Fragment>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
