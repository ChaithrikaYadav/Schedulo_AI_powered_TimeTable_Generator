/**
 * ErrorBoundary.tsx — Global React error boundary.
 * Catches uncaught render errors and shows a recovery UI instead of a blank page.
 */
import { Component, type ReactNode, type ErrorInfo } from 'react'

interface Props { children: ReactNode }
interface State { hasError: boolean; error: string }

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: '' }
  }

  static getDerivedStateFromError(err: Error): State {
    return { hasError: true, error: err.message ?? 'An unexpected error occurred.' }
  }

  componentDidCatch(err: Error, info: ErrorInfo) {
    console.error('[Schedulo ErrorBoundary]', err, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center">
        <div className="card max-w-md w-full space-y-4 p-8">
          <div className="text-4xl">⚠️</div>
          <h2 className="text-xl font-bold text-[var(--text-primary)]">Something went wrong</h2>
          <p className="text-sm text-[var(--text-muted)]">
            The page encountered an unexpected error. This has been noted.
          </p>
          {this.state.error && (
            <pre className="text-xs bg-[var(--bg-secondary)] rounded p-3 text-left overflow-auto text-rose-400 max-h-32">
              {this.state.error}
            </pre>
          )}
          <div className="flex gap-3 justify-center">
            <button
              className="btn btn-primary"
              onClick={() => this.setState({ hasError: false, error: '' })}
            >
              Try again
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => window.location.replace('/')}
            >
              Go to Dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }
}
