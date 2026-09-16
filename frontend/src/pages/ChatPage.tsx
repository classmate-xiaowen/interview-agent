import { useEffect, useRef, useState } from 'react'
import { api, streamMessage } from '../api'
import type { InterviewConfig, InterviewerStyle, InterviewTurn } from '../types'

interface Msg {
  role: 'assistant' | 'user'
  text: string
  turn?: InterviewTurn
}

const STYLE_LABEL: Record<InterviewerStyle, string> = {
  pressure: '高压型',
  gentle: '温和型',
  deep: '深挖型',
}

export default function ChatPage() {
  const [style, setStyle] = useState<InterviewerStyle>('gentle')
  const [targetCompany, setTargetCompany] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const draftRef = useRef('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function start() {
    setError('')
    const cfg: InterviewConfig = {
      interviewer_style: style,
      target_company: targetCompany || null,
    }
    try {
      const r = await api.createSession(cfg)
      setSessionId(r.session_id)
      setMessages([{ role: 'assistant', text: r.question, turn: r }])
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function end() {
    setSessionId(null)
    setMessages([])
    draftRef.current = ''
  }

  async function send() {
    if (!sessionId || !input.trim() || streaming) return
    const userText = input.trim()
    setInput('')
    setError('')
    setMessages((m) => [...m, { role: 'user', text: userText }])
    draftRef.current = ''
    setStreaming(true)
    try {
      await streamMessage(
        sessionId,
        userText,
        (t) => {
          draftRef.current += t
          setMessages((m) => {
            const c = [...m]
            const last = c[c.length - 1]
            if (last?.role === 'assistant') last.text = draftRef.current
            else c.push({ role: 'assistant', text: draftRef.current })
            return [...c]
          })
        },
        (turn) => {
          setMessages((m) => {
            const c = [...m]
            let i = -1
            for (let k = c.length - 1; k >= 0; k--) {
              if (c[k].role === 'assistant') {
                i = k
                break
              }
            }
            const text = i >= 0 ? c[i].text : turn.question
            if (i >= 0) c[i] = { role: 'assistant', text, turn }
            else c.push({ role: 'assistant', text, turn })
            return [...c]
          })
        },
      )
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setStreaming(false)
    }
  }

  const lastIdx = messages.length - 1
  return (
    <div className="page chat">
      <div className="chat-head">
        <div className="row">
          <label>Coach style:</label>
          <select value={style} onChange={(e) => setStyle(e.target.value as InterviewerStyle)}>
            {(['pressure', 'gentle', 'deep'] as InterviewerStyle[]).map((s) => (
              <option key={s} value={s}>
                {STYLE_LABEL[s]}
              </option>
            ))}
          </select>
          <input
            placeholder="目标公司（可选）"
            value={targetCompany}
            onChange={(e) => setTargetCompany(e.target.value)}
          />
          {!sessionId ? (
            <button onClick={start} disabled={streaming}>
              Start
            </button>
          ) : (
            <button onClick={end} className="danger">
              End
            </button>
          )}
        </div>
        {!sessionId && (
          <p className="muted">Pick a style and start — the agent draws on your knowledge base and profile to ask questions.</p>
        )}
      </div>

      {error && <div className="hint error">{error}</div>}

      <div className="messages">
        {messages.map((m, i) => {
          const isStreamingLast = streaming && i === lastIdx && m.role === 'assistant'
          return (
            <div key={i} className={`msg ${m.role}`}>
              <div className="avatar">{m.role === 'assistant' ? '🎯' : '🧑'}</div>
              <div className={`bubble ${m.role}`}>
                <div className="text">
                  {m.text}
                  {isStreamingLast && <span className="caret" />}
                </div>
                {m.turn?.evaluation && <EvaluationCard eval={m.turn.evaluation} />}
                {m.turn?.references?.length ? (
                  <div className="refs">
                    <span className="refs-label">引用来源：</span>
                    {m.turn.references.map((r) => (
                      <span key={r.record_id} className="ref">
                        📎 {r.snippet}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          )
        })}
        <div ref={endRef} />
      </div>

      <div className="composer">
        <textarea
          placeholder={sessionId ? 'Type your answer… (Enter to send, Shift+Enter for newline)' : 'Start a session first'}
          value={input}
          disabled={!sessionId || streaming}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
        />
        <button onClick={send} disabled={!sessionId || streaming || !input.trim()}>
          {streaming ? '生成中…' : '发送'}
        </button>
      </div>
    </div>
  )
}

function EvaluationCard({ eval: ev }: { eval: NonNullable<Msg['turn']>['evaluation'] }) {
  if (!ev) return null
  return (
    <div className="eval">
      <div className="eval-score">评分：{ev.score}/100</div>
      {ev.covered_points.length > 0 && (
        <div>
          <b>覆盖要点：</b>
          <ul>
            {ev.covered_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {ev.missing_points.length > 0 && (
        <div>
          <b>遗漏要点：</b>
          <ul>
            {ev.missing_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {ev.structure_feedback && (
        <div>
          <b>结构：</b>
          {ev.structure_feedback}
        </div>
      )}
      {ev.expression_feedback && (
        <div>
          <b>表达：</b>
          {ev.expression_feedback}
        </div>
      )}
      {ev.suggestions.length > 0 && (
        <div>
          <b>建议：</b>
          <ul>
            {ev.suggestions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
