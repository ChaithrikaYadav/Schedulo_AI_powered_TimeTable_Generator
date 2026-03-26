import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Users, BookOpen, DoorOpen, LayoutGrid, TrendingUp,
  AlertTriangle, Clock, Sparkles,
} from 'lucide-react'
import { getTimetables, getSections, getFaculty, getSubjects, getRooms, type Timetable } from '../lib/api'

interface StatCardProps {
  icon: React.ReactNode
  iconBg: string
  label: string
  value: string | number
  sub?: string
}

function StatCard({ icon, iconBg, label, value, sub }: StatCardProps) {
  return (
    <div className="stat-card animate-fade-up">
      <div className={`stat-icon ${iconBg}`}>{icon}</div>
      <div>
        <div className="text-2xl font-bold text-[var(--text-primary)]">{value}</div>
        <div className="text-sm font-medium text-[var(--text-secondary)]">{label}</div>
        {sub && <div className="text-xs text-[var(--text-muted)] mt-0.5">{sub}</div>}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    COMPLETED: 'badge-teal',
    GENERATING: 'badge-amber',
    DRAFT: 'badge-gray',
    FAILED: 'badge-rose',
  }
  return <span className={`badge ${map[status] ?? 'badge-gray'}`}>{status}</span>
}

export default function Dashboard() {
  const nav = useNavigate()
  const [timetables, setTimetables] = useState<Timetable[]>([])
  const [stats, setStats] = useState({ sections: 0, faculty: 0, subjects: 0, rooms: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [tts, secs, fac, subs, rooms] = await Promise.allSettled([
          getTimetables(),
          getSections(),
          getFaculty(),
          getSubjects(),
          getRooms(),
        ])
        if (cancelled) return
        setTimetables(tts.status === 'fulfilled' ? tts.value : [])
        setStats({
          sections: secs.status === 'fulfilled' ? secs.value.length : 0,
          faculty:  fac.status === 'fulfilled'  ? fac.value.length  : 0,
          subjects: subs.status === 'fulfilled' ? subs.value.length : 0,
          rooms:    rooms.status === 'fulfilled' ? rooms.value.length : 0,
        })
      } catch (e) {
        if (!cancelled) setError('Could not connect to API. Is the backend running?')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[var(--text-primary)]">
            Dashboard <span className="gradient-text">Overview</span>
          </h1>
          <p className="text-[var(--text-muted)] mt-1 text-sm">
            Schedulo — AI-powered university timetable generation
          </p>
        </div>
        <button
          id="btn-generate-from-dashboard"
          onClick={() => nav('/generate')}
          className="btn btn-primary"
        >
          <Sparkles className="w-4 h-4" />
          Generate Timetable
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<LayoutGrid className="w-5 h-5 text-teal-400" />}
          iconBg="bg-teal-500/10"
          label="Sections"
          value={loading ? '—' : stats.sections}
          sub="Student groups"
        />
        <StatCard
          icon={<Users className="w-5 h-5 text-violet-400" />}
          iconBg="bg-violet-500/10"
          label="Faculty"
          value={loading ? '—' : stats.faculty}
          sub="Teaching staff"
        />
        <StatCard
          icon={<BookOpen className="w-5 h-5 text-amber-400" />}
          iconBg="bg-amber-500/10"
          label="Subjects"
          value={loading ? '—' : stats.subjects}
          sub="Course catalogue"
        />
        <StatCard
          icon={<DoorOpen className="w-5 h-5 text-rose-400" />}
          iconBg="bg-rose-500/10"
          label="Rooms"
          value={loading ? '—' : stats.rooms}
          sub="Classrooms & Labs"
        />
      </div>

      {/* Recent timetables */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-[var(--text-primary)]">Recent Timetables</h2>
          <button
            id="btn-view-all-timetables"
            onClick={() => nav('/timetable')}
            className="btn btn-ghost text-xs"
          >
            View all →
          </button>
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1,2,3].map(i => (
              <div key={i} className="h-12 rounded-lg bg-[var(--bg-hover)] animate-pulse" />
            ))}
          </div>
        ) : timetables.length === 0 ? (
          <div className="text-center py-12">
            <DoorOpen className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-3" />
            <p className="text-[var(--text-secondary)] text-sm">No timetables yet.</p>
            <button
              onClick={() => nav('/generate')}
              className="btn btn-secondary mt-3 text-xs"
            >
              Generate your first timetable
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  {['Name', 'Department', 'Semester', 'Status', 'Conflicts', 'Time', ''].map(h => (
                    <th key={h} className="text-left text-[10px] uppercase tracking-wide text-[var(--text-muted)] pb-2 pr-4 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {timetables.slice(0, 8).map((tt) => (
                  <tr
                    key={tt.id}
                    className="border-b border-[var(--border)] hover:bg-[var(--bg-hover)] transition-colors"
                  >
                    <td className="py-3 pr-4 font-medium text-[var(--text-primary)]">
                      {tt.name || `TT-${tt.id}`}
                    </td>
                    <td className="py-3 pr-4 text-[var(--text-secondary)] text-xs">
                      {tt.department || '—'}
                    </td>
                    <td className="py-3 pr-4 text-[var(--text-secondary)] text-xs">
                      {tt.semester || '—'}
                    </td>
                    <td className="py-3 pr-4"><StatusBadge status={tt.status} /></td>
                    <td className="py-3 pr-4">
                      {tt.conflict_count > 0 ? (
                        <span className="flex items-center gap-1 text-rose-400 text-xs">
                          <AlertTriangle className="w-3 h-3" /> {tt.conflict_count}
                        </span>
                      ) : (
                        <span className="text-teal-400 text-xs">✓ Clean</span>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-[var(--text-muted)] text-xs">
                      {tt.generation_time_ms ? `${(tt.generation_time_ms / 1000).toFixed(1)}s` : '—'}
                    </td>
                    <td className="py-3">
                      <button
                        onClick={() => nav(`/timetable?ttId=${tt.id}`)}
                        className="btn btn-ghost text-xs px-2 py-1"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'View Timetables', icon: '📅', to: '/timetable', color: 'var(--teal)' },
          { label: 'Ask ScheduloBot',   icon: '🤖', to: '/chatbot',   color: 'var(--violet)' },
          { label: 'New Generation',  icon: '⚡', to: '/generate',  color: 'var(--amber)' },
        ].map(({ label, icon, to, color }) => (
          <button
            key={to}
            onClick={() => nav(to)}
            className="card cursor-pointer text-left hover:translate-y-[-2px] transition-transform duration-200"
            style={{ borderColor: `${color}22` }}
          >
            <div className="text-2xl mb-2">{icon}</div>
            <div className="font-medium text-sm" style={{ color }}>{label}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
