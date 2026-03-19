/**
 * src/lib/ws.ts — WebSocket client with auto-reconnect for progress events.
 *
 * Usage:
 *   const ws = new ProgressWebSocket('job-123', (event) => {
 *     console.log(event.progress, event.message)
 *   })
 *   ws.connect()
 *   // later:
 *   ws.disconnect()
 */

export interface ProgressEvent {
  job_id: string
  stage: string
  progress: number    // 0–100
  message: string
  completed: boolean
  error?: string
}

type ProgressCallback = (event: ProgressEvent) => void

const WS_BASE = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/progress`

export class ProgressWebSocket {
  private _ws: WebSocket | null = null
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _reconnectDelay = 1000
  private _maxReconnects = 5
  private _reconnectCount = 0
  private _connected = false

  constructor(
    private readonly jobId: string,
    private readonly onProgress: ProgressCallback,
    private readonly onClose?: () => void,
  ) {}

  connect(): void {
    if (this._connected) return
    try {
      this._ws = new WebSocket(`${WS_BASE}/${this.jobId}`)

      this._ws.onopen = () => {
        this._connected = true
        this._reconnectCount = 0
        this._reconnectDelay = 1000
      }

      this._ws.onmessage = (evt) => {
        try {
          const data: ProgressEvent = JSON.parse(evt.data as string)
          this.onProgress(data)
          if (data.completed || data.error) {
            this.disconnect()
          }
        } catch {
          // ignore malformed events
        }
      }

      this._ws.onclose = () => {
        this._connected = false
        this._ws = null
        this.onClose?.()
        if (this._reconnectCount < this._maxReconnects) {
          this._scheduleReconnect()
        }
      }

      this._ws.onerror = () => {
        this._ws?.close()
      }
    } catch {
      // WebSocket not available (e.g. SSR)
    }
  }

  disconnect(): void {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer)
      this._reconnectTimer = null
    }
    this._ws?.close()
    this._ws = null
    this._connected = false
  }

  private _scheduleReconnect(): void {
    this._reconnectCount++
    this._reconnectTimer = setTimeout(() => {
      this._reconnectDelay = Math.min(this._reconnectDelay * 2, 10000)
      this.connect()
    }, this._reconnectDelay)
  }

  get isConnected(): boolean {
    return this._connected
  }
}
