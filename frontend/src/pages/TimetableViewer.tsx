import { useEffect, useState, useCallback } from 'react'
import { Calendar, RefreshCw } from 'lucide-react'
import { getTimetables, getTimetableSlots, type Timetable, type TimetableSlot } from '../lib/api'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const PERIODS = [
  '9:00–9:55', '9:55–10:50', '10:50–11:45', '11:45–12:40',
  '12:40–1:35', '1:35–2:30', '2:30–3:25', '3:25–4:20', '4:20–5:15',
]

function slotClass(type: string) {
  switch (type.toUpperCase()) {
    case 'THEORY':  return 'theory'
    case 'LAB':     return 'lab'
    case 'LAB_CONT':
    case 'PROJECT': return 'lab-cont'
    case 'LUNCH':   return 'lunch'
    default:        return 'free'
  }
}

function slotColor(type: string) {
  switch (type.toUpperCase()) {
    case 'THEORY':  return 'var(--teal)'
    case 'LAB':     return 'var(--violet)'
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

export default function TimetableViewer() {
  const [timetables, setTimetables] = useState<Timetable[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [slots, setSlots] = useState<TimetableSlot[]>([])
  const [sectionIds, setSectionIds] = useState<number[]>([])
  const [selectedSection, setSelectedSection] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingTTs, setLoadingTTs] = useState(true)

  // Load timetable list
  useEffect(() => {
    getTimetables()
      .then(tts => { setTimetables(tts); if (tts.length > 0) setSelectedId(tts[0].id) })
      .catch(() => {})
      .finally(() => setLoadingTTs(false))
  }, [])

  // Load slots when timetable selected
  const loadSlots = useCallback(async (ttId: number, secId: number | null) => {
    setLoading(true)
    try {
      const data = await getTimetableSlots(ttId, secId ?? undefined)
      setSlots(data)
      // Extract unique section IDs
      const secs = [...new Set(data.map(s => s.section_id).filter(Boolean) as number[])]
      setSectionIds(secs)
      if (!secId && secs.length > 0) setSelectedSection(secs[0])
    } catch {
      setSlots([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedId) loadSlots(selectedId, selectedSection)
  }, [selectedId, selectedSection, loadSlots])

  const grid = buildGrid(slots.filter(s =>
    selectedSection == null || s.section_id === selectedSection
  ))

  return (
    <div className="p-8 space-y-6 max-w-full">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            <Calendar className="inline w-6 h-6 mb-1 mr-2 text-teal-400" />
            Timetable <span className="gradient-text">Viewer</span>
          </h1>
          <p className="text-[var(--text-muted)] text-sm mt-1">6-day × 9-period weekly schedule</p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {/* Timetable picker */}
          {loadingTTs ? (
            <div className="h-9 w-40 rounded-lg bg-[var(--bg-hover)] animate-pulse" />
          ) : (
            <select
              id="select-timetable"
              className="select w-44"
              value={selectedId ?? ''}
              onChange={e => { setSelectedId(Number(e.target.value)); setSelectedSection(null) }}
            >
              <option value="" disabled>Select timetable…</option>
              {timetables.map(tt => (
                <option key={tt.id} value={tt.id}>{tt.name || `TT-${tt.id}`}</option>
              ))}
            </select>
          )}

          {/* Section picker */}
          {sectionIds.length > 0 && (
            <select
              id="select-section"
              className="select w-36"
              value={selectedSection ?? ''}
              onChange={e => setSelectedSection(Number(e.target.value))}
            >
              <option value="" disabled>Section…</option>
              {sectionIds.map(id => (
                <option key={id} value={id}>Section {id}</option>
              ))}
            </select>
          )}

          <button
            id="btn-refresh-timetable"
            className="btn btn-secondary"
            onClick={() => selectedId && loadSlots(selectedId, selectedSection)}
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'spinner' : ''}`} />
          </button>
        </div>
      </div>

      {/* Legend */}
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

      {/* Empty / no timetable state */}
      {!selectedId && !loadingTTs && (
        <div className="card text-center py-16">
          <Calendar className="w-12 h-12 mx-auto mb-4 text-[var(--text-muted)]" />
          <p className="text-[var(--text-secondary)]">No timetables found.</p>
          <p className="text-[var(--text-muted)] text-sm mt-1">Generate a timetable first.</p>
        </div>
      )}

      {/* Grid */}
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
              style={{ gridTemplateColumns: `64px repeat(${PERIODS.length}, minmax(90px, 1fr))` }}
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
                <>
                  <div key={`${day}-label`} className="tt-day-cell">{day.slice(0, 3)}</div>
                  {PERIODS.map((_, pi) => {
                    const slot = grid[day]?.[pi + 1]
                    const type = slot?.slot_type ?? 'FREE'
                    return (
                      <div
                        key={`${day}-${pi}`}
                        className={`tt-slot ${slotClass(type)}`}
                      >
                        {slot && type !== 'FREE' ? (
                          <>
                            {slot.cell_display_line1 && (
                              <div className="font-semibold leading-tight" style={{ color: slotColor(type) }}>
                                {slot.cell_display_line1}
                              </div>
                            )}
                            {slot.cell_display_line2 && (
                              <div className="text-[var(--text-muted)] leading-tight">
                                {slot.cell_display_line2}
                              </div>
                            )}
                            {slot.cell_display_line3 && (
                              <div className="text-[10px] text-[var(--text-muted)] leading-tight">
                                📍 {slot.cell_display_line3}
                              </div>
                            )}
                            {type === 'LUNCH' && (
                              <div className="text-amber-400 font-medium">🍴 LUNCH</div>
                            )}
                          </>
                        ) : type === 'LUNCH' ? (
                          <div className="text-amber-400 font-medium text-xs">🍴 LUNCH</div>
                        ) : null}
                      </div>
                    )
                  })}
                </>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
