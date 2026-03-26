import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import TimetableViewer from './pages/TimetableViewer'
import ScheduloBot from './pages/ScheduloBot'
import GeneratorWizard from './pages/GeneratorWizard'
import { ErrorBoundary } from './components/ErrorBoundary'

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <div className="flex h-full w-full overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-y-auto bg-[var(--bg-primary)]">
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/timetable" element={<TimetableViewer />} />
                <Route path="/chatbot" element={<ScheduloBot />} />
                <Route path="/generate" element={<GeneratorWizard />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </ErrorBoundary>
          </main>
        </div>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
