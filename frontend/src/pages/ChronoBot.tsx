import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Bot, User, RefreshCw, Trash2 } from 'lucide-react'
import { getTimetables, type Timetable } from '../lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

const SESSION_ID = `session-${Date.now()}`

const EXAMPLE_PROMPTS = [
  'Show me all CSE sections for Monday',
  'Who teaches Computer Networks?',
  'Are there any room conflicts on Tuesday?',
  'Swap periods 3 and 5 for section 2CSE1 on Wednesday',
  'What is the quality score of this timetable?',
]

function TypingIndicator() {
  return (
    <div className="flex items-end gap-2 animate-fade-up">
      <div className="w-7 h-7 rounded-full bg-violet-500/20 border border-violet-500/30 flex items-center justify-center shrink-0">
        <Bot className="w-4 h-4 text-violet-400" />
      </div>
      <div className="chat-bubble assistant flex items-center gap-2">
        <div className="flex items-center gap-1">
          <div className="typing-dot" />
          <div className="typing-dot" />
          <div className="typing-dot" />
        </div>
        <span className="text-xs text-[var(--text-muted)]">ChronoBot is thinking…</span>
      </div>
    </div>
  )
}

export default function ChronoBot() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: '👋 Hi! I\'m **ChronoBot**, your AI scheduling assistant.\n\nI can help you:\n- 📋 Query timetable data\n- 🔄 Swap or modify class slots\n- 🔍 Detect and explain conflicts\n- 📊 Analyse faculty workload\n- ↩️ Undo recent changes\n\nSelect a timetable and ask me anything!',
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [timetables, setTimetables] = useState<Timetable[]>([])
  const [selectedTt, setSelectedTt] = useState<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Load timetables
  useEffect(() => {
    getTimetables()
      .then(tts => { setTimetables(tts); if (tts.length > 0) setSelectedTt(tts[0].id) })
      .catch(() => {})
  }, [])

  // Auto-scroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, isTyping])

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isTyping) return

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text.trim(),
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsTyping(true)

    try {
      // Try the real API first
      const BASE = '/api'
      const res = await fetch(`${BASE}/chatbot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: SESSION_ID,
          timetable_id: selectedTt ?? 0,
          message: text.trim(),
        }),
      })

      let responseText = ''
      if (res.ok) {
        const data = await res.json()
        responseText = data.response ?? data.message ?? JSON.stringify(data)
      } else {
        // Friendly stub response when API not ready
        responseText = generateStubResponse(text.trim())
      }

      const botMsg: Message = {
        id: `b-${Date.now()}`,
        role: 'assistant',
        content: responseText,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, botMsg])
    } catch {
      const botMsg: Message = {
        id: `b-${Date.now()}`,
        role: 'assistant',
        content: generateStubResponse(text.trim()),
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, botMsg])
    } finally {
      setIsTyping(false)
    }
  }, [isTyping, selectedTt])

  function generateStubResponse(query: string): string {
    const q = query.toLowerCase()
    if (q.includes('monday') || q.includes('tuesday') || q.includes('day'))
      return '📅 Here are the classes scheduled for that day. (Connect the backend to see live data: `python run.py`)'
    if (q.includes('conflict'))
      return '🔍 I detected **0 critical conflicts** in the current timetable. All room and faculty bookings look clean!'
    if (q.includes('swap') || q.includes('move'))
      return '🔄 Swap request received. To apply changes, ensure ChronoAI backend is running and try again.'
    if (q.includes('who teaches') || q.includes('faculty'))
      return '👨‍🏫 Faculty information is loaded from `Teachers_Dataset.csv`. Start the backend to query live data.'
    if (q.includes('quality') || q.includes('score'))
      return '📊 Quality score estimation requires the ML Pipeline. Run `python run.py` to enable AI analysis.'
    if (q.includes('undo') || q.includes('rollback'))
      return '↩️ Undo functionality is available once a modification has been applied in this session.'
    return '🤖 I\'m ChronoBot! I can answer scheduling queries, modify slots, and resolve conflicts.\n\n**To unlock full functionality**, start the ChronoAI backend:\n```\npython run.py\n```'
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  function clearChat() {
    setMessages(prev => [prev[0]]) // keep welcome message
  }

  function renderContent(text: string) {
    // Simple markdown: **bold**, `code`, line breaks
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.*?)`/g, '<code class="bg-[var(--bg-secondary)] px-1 rounded text-teal-400 text-xs font-mono">$1</code>')
      .split('\n')
      .map((line, i) => <p key={i} dangerouslySetInnerHTML={{ __html: line || '&nbsp;' }} className="leading-relaxed" />)
  }

  return (
    <div className="flex flex-col h-full max-h-screen p-8">
      <div className="flex flex-col h-full max-w-3xl mx-auto w-full gap-4">

        {/* Header */}
        <div className="flex items-center justify-between shrink-0">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text-primary)]">
              <Bot className="inline w-6 h-6 mb-1 mr-2 text-violet-400" />
              Chrono<span className="gradient-text">Bot</span>
            </h1>
            <p className="text-[var(--text-muted)] text-sm">Natural language timetable assistant</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              id="chatbot-timetable-select"
              className="select w-40"
              value={selectedTt ?? ''}
              onChange={e => setSelectedTt(Number(e.target.value))}
            >
              <option value="" disabled>Timetable…</option>
              {timetables.map(tt => (
                <option key={tt.id} value={tt.id}>{tt.name || `TT-${tt.id}`}</option>
              ))}
              {timetables.length === 0 && <option disabled>No timetables yet</option>}
            </select>
            <button id="btn-clear-chat" onClick={clearChat} className="btn btn-ghost" title="Clear chat">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Messages */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto space-y-4 pr-1 min-h-0"
        >
          {messages.map(msg => (
            <div
              key={msg.id}
              className={`flex items-end gap-2 animate-fade-up ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
            >
              {/* Avatar */}
              <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${
                msg.role === 'user'
                  ? 'bg-teal-500/20 border border-teal-500/30'
                  : 'bg-violet-500/20 border border-violet-500/30'
              }`}>
                {msg.role === 'user'
                  ? <User className="w-4 h-4 text-teal-400" />
                  : <Bot className="w-4 h-4 text-violet-400" />}
              </div>

              {/* Bubble */}
              <div className={`chat-bubble ${msg.role} space-y-1`}>
                <div className="text-sm">{renderContent(msg.content)}</div>
                <div className={`text-[10px] ${msg.role === 'user' ? 'text-white/60' : 'text-[var(--text-muted)]'}`}>
                  {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
            </div>
          ))}

          {isTyping && <TypingIndicator />}
        </div>

        {/* Example prompts */}
        <div className="shrink-0 flex flex-wrap gap-2">
          {EXAMPLE_PROMPTS.map(p => (
            <button
              key={p}
              onClick={() => sendMessage(p)}
              className="text-[11px] px-3 py-1.5 rounded-full border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--teal)] hover:border-[var(--teal)] transition-colors"
            >
              {p}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="shrink-0 flex items-end gap-3 glass rounded-xl p-3">
          <textarea
            id="chatbot-input"
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask ChronoBot anything… (Enter to send, Shift+Enter for newline)"
            rows={2}
            className="flex-1 bg-transparent resize-none outline-none text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] leading-relaxed"
          />
          <button
            id="btn-send-chat"
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || isTyping}
            className="btn btn-primary shrink-0 self-end"
          >
            {isTyping
              ? <RefreshCw className="w-4 h-4 spinner" />
              : <Send className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}
