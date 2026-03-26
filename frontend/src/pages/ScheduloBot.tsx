import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Bot, User, RefreshCw, Trash2, Zap, Key, ChevronDown, ChevronUp, Eye, EyeOff } from 'lucide-react'
import { getTimetables, type Timetable } from '../lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  source?: string   // "ai:groq" | "ai:hf" | "db" | "fallback"
}

// Persistent session for the browser tab
const SESSION_ID = `schedulo-${Date.now()}-${Math.random().toString(36).slice(2)}`

const EXAMPLE_PROMPTS = [
  'Show me all CSE sections for Monday',
  'Who teaches Computer Networks?',
  'Are there any conflicts in this timetable?',
  'Give me an overview / summary',
  'What sections are in this timetable?',
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
        <span className="text-xs text-[var(--text-muted)]">ScheduloBot is thinking…</span>
      </div>
    </div>
  )
}

/** Render markdown: **bold**, `code`, newlines */
function renderContent(text: string) {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  const html = escaped
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="bg-[var(--bg-secondary)] px-1 py-0.5 rounded text-teal-400 text-xs font-mono">$1</code>')
  return html
    .split('\n')
    .map((line, i) => (
      <p
        key={i}
        dangerouslySetInnerHTML={{ __html: line || '&nbsp;' }}
        className="leading-relaxed"
      />
    ))
}

/** Tiny badge showing where the response came from */
function SourceBadge({ source }: { source?: string }) {
  if (!source || source === 'fallback') return null
  const label =
    source === 'ai:groq' ? '⚡ Groq AI' :
    source === 'ai:hf'   ? '🤗 HF AI'  :
    source === 'db'      ? '🗄️ Live DB' : null
  if (!label) return null
  return (
    <span className="text-[9px] opacity-50 font-medium mt-0.5 block">
      {label}
    </span>
  )
}

export default function ScheduloBot() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        '👋 Hi! I\'m **ScheduloBot**, your AI scheduling assistant.\n\nI can help you:\n- 📋 Query timetable slots for any day or section\n- 👨‍🏫 Find who teaches a subject\n- 🔍 Detect and explain conflicts\n- 📊 Summarise timetable statistics\n- 🔄 Swap or modify class slots\n\nSelect a **timetable from the dropdown** above and ask me anything!',
      timestamp: new Date(),
    },
  ])
  const [input, setInput]         = useState('')
  const [isTyping, setIsTyping]   = useState(false)
  const [timetables, setTimetables] = useState<Timetable[]>([])
  const [selectedTt, setSelectedTt] = useState<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)

  // ── AI key state (persisted to localStorage) ──────────────────────────────
  const [showKeyPanel, setShowKeyPanel] = useState(false)
  const [groqKey, setGroqKey]           = useState(() => localStorage.getItem('chrono_groq_key') ?? '')
  const [hfToken, setHfToken]           = useState(() => localStorage.getItem('chrono_hf_token') ?? '')
  const [showGroq, setShowGroq]         = useState(false)
  const [showHf, setShowHf]             = useState(false)

  // Save keys to localStorage whenever they change
  useEffect(() => { localStorage.setItem('chrono_groq_key', groqKey)  }, [groqKey])
  useEffect(() => { localStorage.setItem('chrono_hf_token', hfToken)  }, [hfToken])

  const activeAI = groqKey.length > 10 ? '⚡ Groq' : hfToken.startsWith('hf_') ? '🤗 HF' : null

  // Load timetables list on mount
  useEffect(() => {
    getTimetables()
      .then(tts => {
        setTimetables(tts)
        if (tts.length > 0) setSelectedTt(tts[0].id)
      })
      .catch(() => {})
  }, [])

  // Auto-scroll to bottom on new messages
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
      const res = await fetch('/api/chatbot/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: SESSION_ID,
          timetable_id: selectedTt ?? null,
          message: text.trim(),
          // Include keys from localStorage if present
          groq_api_key: groqKey || undefined,
          hf_api_token: hfToken || undefined,
        }),
      })

      let responseText = ''
      let source: string | undefined

      if (res.ok) {
        const data = await res.json()
        responseText = data.response ?? data.message ?? JSON.stringify(data)
        source = data.source
      } else {
        // Non-200 — show the actual error from the API
        const errData = await res.json().catch(() => null)
        responseText =
          errData?.detail
            ? `⚠️ Server error: ${errData.detail}`
            : `⚠️ Server returned HTTP ${res.status}. Check that the backend is running.`
      }

      setMessages(prev => [
        ...prev,
        {
          id: `b-${Date.now()}`,
          role: 'assistant',
          content: responseText,
          timestamp: new Date(),
          source,
        },
      ])
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          id: `b-${Date.now()}`,
          role: 'assistant',
          content:
            '⚠️ **Cannot reach the backend.**\n\nMake sure the Schedulo server is running:\n```\npython run.py\n```',
          timestamp: new Date(),
        },
      ])
    } finally {
      setIsTyping(false)
    }
  }, [isTyping, selectedTt, groqKey, hfToken])

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  function clearChat() {
    setMessages(prev => [prev[0]])   // keep welcome message
    // Also clear on server
    fetch(`/api/chatbot/history/${SESSION_ID}`, { method: 'DELETE' }).catch(() => {})
  }

  return (
    <div className="flex flex-col h-full max-h-screen p-8">
      <div className="flex flex-col h-full max-w-3xl mx-auto w-full gap-4">

        {/* Header */}
        <div className="flex items-center justify-between shrink-0">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text-primary)]">
              <Bot className="inline w-6 h-6 mb-1 mr-2 text-violet-400" />
              Schedulo<span className="gradient-text">Bot</span>
            </h1>
            <p className="text-[var(--text-muted)] text-sm">Natural language timetable assistant</p>
          </div>
          <div className="flex items-center gap-2">

            {/* AI status badge */}
            {activeAI && (
              <span className="badge text-[10px] px-2 py-0.5" style={{ background: 'var(--teal)20', color: 'var(--teal)' }}>
                {activeAI} Active
              </span>
            )}

            {/* AI Keys toggle */}
            <button
              id="btn-ai-keys"
              onClick={() => setShowKeyPanel(p => !p)}
              className="btn btn-ghost text-xs"
              title="Configure AI keys"
            >
              <Key className="w-3.5 h-3.5" />
              AI Keys
              {showKeyPanel ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>

            {/* Timetable picker */}
            <select
              id="chatbot-timetable-select"
              className="select w-48"
              value={selectedTt ?? ''}
              onChange={e => setSelectedTt(Number(e.target.value))}
            >
              <option value="" disabled>Select timetable…</option>
              {timetables.map(tt => (
                <option key={tt.id} value={tt.id}>
                  {(tt.name && tt.name.length > 40
                    ? tt.name.slice(0, 37) + '…'
                    : tt.name) || `TT-${tt.id}`}
                </option>
              ))}
              {timetables.length === 0 && <option disabled>No timetables yet</option>}
            </select>

            {/* Clear chat */}
            <button
              id="btn-clear-chat"
              onClick={clearChat}
              className="btn btn-ghost"
              title="Clear chat history"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* AI Keys panel */}
        {showKeyPanel && (
          <div className="shrink-0 card animate-fade-up space-y-3 p-4">
            <p className="text-xs font-semibold text-[var(--text-secondary)] flex items-center gap-1.5">
              <Key className="w-3.5 h-3.5 text-teal-400" />
              AI Keys — stored in your browser only, never sent to any server except Schedulo
            </p>

            {/* Groq key */}
            <div>
              <label className="block text-[11px] text-[var(--text-muted)] mb-1">
                ⚡ Groq API Key
                <a href="https://console.groq.com" target="_blank" rel="noopener noreferrer"
                   className="ml-2 text-teal-400 hover:underline">Get free key →</a>
              </label>
              <div className="relative">
                <input
                  id="input-groq-key"
                  type={showGroq ? 'text' : 'password'}
                  className="input text-xs pr-8 font-mono"
                  placeholder="gsk_…"
                  value={groqKey}
                  onChange={e => setGroqKey(e.target.value)}
                />
                <button
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  onClick={() => setShowGroq(p => !p)}
                  type="button"
                >
                  {showGroq ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
              {groqKey.length > 10 && <p className="text-[10px] text-teal-400 mt-0.5">✓ Groq key set — AI responses enabled</p>}
            </div>

            {/* HuggingFace token */}
            <div>
              <label className="block text-[11px] text-[var(--text-muted)] mb-1">
                🤗 HuggingFace Token
                <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noopener noreferrer"
                   className="ml-2 text-teal-400 hover:underline">Get free token →</a>
              </label>
              <div className="relative">
                <input
                  id="input-hf-token"
                  type={showHf ? 'text' : 'password'}
                  className="input text-xs pr-8 font-mono"
                  placeholder="hf_…"
                  value={hfToken}
                  onChange={e => setHfToken(e.target.value)}
                />
                <button
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  onClick={() => setShowHf(p => !p)}
                  type="button"
                >
                  {showHf ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
              {hfToken.startsWith('hf_') && !groqKey && <p className="text-[10px] text-teal-400 mt-0.5">✓ HF token set — AI responses enabled</p>}
            </div>

            <p className="text-[10px] text-[var(--text-muted)]">
              Without keys, ScheduloBot queries your live timetable database directly.
              Priority: Groq &gt; HuggingFace &gt; DB fallback.
            </p>
          </div>
        )}

        {/* No timetable warning */}
        {!selectedTt && timetables.length > 0 && (
          <div className="shrink-0 flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
            <Zap className="w-3.5 h-3.5 shrink-0" />
            Select a timetable above so ScheduloBot can query your live schedule data.
          </div>
        )}

        {/* Message thread */}
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
                  : <Bot  className="w-4 h-4 text-violet-400" />}
              </div>

              {/* Bubble */}
              <div className={`chat-bubble ${msg.role} space-y-1 max-w-[80%]`}>
                <div className="text-sm">{renderContent(msg.content)}</div>
                <div className={`text-[10px] flex items-center justify-between gap-2 ${msg.role === 'user' ? 'text-white/60' : 'text-[var(--text-muted)]'}`}>
                  <span>{msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  <SourceBadge source={msg.source} />
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
              disabled={isTyping}
              className="text-[11px] px-3 py-1.5 rounded-full border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--teal)] hover:border-[var(--teal)] transition-colors disabled:opacity-40"
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
            placeholder="Ask ScheduloBot anything… (Enter to send, Shift+Enter for newline)"
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
