import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  CalendarDays,
  MessageSquareText,
  Wand2,
  Brain,
  ExternalLink,
} from 'lucide-react'

const NAV_ITEMS = [
  { to: '/',          icon: LayoutDashboard,    label: 'Dashboard'  },
  { to: '/timetable', icon: CalendarDays,       label: 'Timetables' },
  { to: '/generate',  icon: Wand2,              label: 'Generate'   },
  { to: '/chatbot',   icon: MessageSquareText,  label: 'ScheduloBot'  },
] as const

export default function Sidebar() {
  return (
    <aside className="flex flex-col w-56 h-full shrink-0 border-r border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden">

      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-5 border-b border-[var(--border)]">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center bg-gradient-to-br from-teal-500 to-violet-500 shadow-lg shadow-teal-500/20">
          <Brain className="w-4 h-4 text-white" />
        </div>
        <div>
          <div className="font-bold text-sm leading-tight gradient-text">Schedulo</div>
          <div className="text-[10px] text-[var(--text-muted)] leading-tight">Smart Scheduler</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)] px-2 py-2 mb-1">
          Main Menu
        </p>
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `sidebar-link ${isActive ? 'active' : ''}`
            }
          >
            <Icon className="w-4 h-4 shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-[var(--border)] space-y-2">
        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="sidebar-link text-[12px]"
        >
          <ExternalLink className="w-3.5 h-3.5 shrink-0" />
          <span>API Docs</span>
        </a>
        <div className="px-2 py-1">
          <span className="badge badge-teal">v1.0.0</span>
        </div>
      </div>
    </aside>
  )
}
