import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import TimetableViewer from './pages/TimetableViewer'
import ChronoBot from './pages/ChronoBot'
import GeneratorWizard from './pages/GeneratorWizard'

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-full w-full overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-[var(--bg-primary)]">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/timetable" element={<TimetableViewer />} />
            <Route path="/chatbot" element={<ChronoBot />} />
            <Route path="/generate" element={<GeneratorWizard />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
