import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
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
  const abortRef = useRef<AbortController | null>(null)
  const userStoppedRef = useRef(false)
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
      setMessages([])
      await runStream(r.session_id, '', true)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function end() {
    abortRef.current?.abort()
    setSessionId(null)
    setMessages([])
  }

  function stop() {
    userStoppedRef.current = true
    abortRef.current?.abort()
  }

  async function runStream(sessionId: string, message: string, kickoff: boolean) {
    setStreaming(true)
    setError('')
    userStoppedRef.current = false
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamMessage(
        sessionId,
        message,
        {
          signal: controller.signal,
          onToken: (t) => {
            setMessages((m) => {
              const c = [...m]
              const last = c[c.length - 1]
              if (last && last.role === 'assistant') c[c.length - 1] = { ...last, text: last.text + t }
              else c.push({ role: 'assistant', text: t })
              return c
            })
          },
          onTurn: (turn) => {
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
              if (i >= 0) c[i] = { ...c[i], turn }
              else c.push({ role: 'assistant', text, turn })
              return c
            })
          },
          onError: (msg) => setError(msg),
        },
        kickoff,
      )
    } catch (e) {
      const err = e as Error
      // 用户主动「停止」不提示；其余（含后端无响应超时）给出明确错误信息。
      if (err.name !== 'AbortError' || !userStoppedRef.current) setError(err.message)
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  async function send() {
    if (!sessionId || !input.trim() || streaming) return
    const userText = input.trim()
    setInput('')
    setMessages((m) => [...m, { role: 'user', text: userText }])
    await runStream(sessionId, userText, false)
  }

  const lastIdx = messages.length - 1
  return (
    <div className="page chat">
      <div className="chat-head">
        <div className="row">
          <label>教练风格</label>
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
              开始训练
            </button>
          ) : (
            <button onClick={end} className="danger">
              结束训练
            </button>
          )}
        </div>
        {!sessionId && (
          <p className="muted">Pick a style and start — the agent draws on your knowledge base and profile to ask questions.</p>
        )}
      </div>

      {error && <div className="hint error">{error}</div>}

      <div className="messages">
        {messages.length === 0 && !streaming && (
          <div className="empty-state">
            <div className="orb">🎯</div>
            <h4>准备好接受模拟训练了吗？</h4>
            <p>
              选择一种教练风格并点击「开始训练」—— Agent 会结合你的知识库与画像进行提问，
              每轮回答后即时给出评分与改进建议。
            </p>
            <div className="chips">
              <span className="chip">STAR 法则作答</span>
              <span className="chip">先结论后细节</span>
              <span className="chip">量化你的成果</span>
            </div>
          </div>
        )}
        {messages.map((m, i) => {
          const isStreamingLast = streaming && i === lastIdx && m.role === 'assistant'
          return (
            <div key={i} className={`msg ${m.role}`}>
              <div className="avatar">{m.role === 'assistant' ? '🎯' : '🧑'}</div>
              <div className={`bubble ${m.role}`}>
                {m.role === 'assistant' ? (
                  <>
                    <div className="md">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          a: ({ node, ...props }) => (
                            <a {...props} target="_blank" rel="noreferrer" />
                          ),
                        }}
                      >
                        {m.text}
                      </ReactMarkdown>
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
                  </>
                ) : (
                  <div className="text">
                    {m.text}
                    {isStreamingLast && <span className="caret" />}
                  </div>
                )}
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
        {streaming && (
          <button onClick={stop} className="danger" title="中断当前生成">
            停止
          </button>
        )}
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
      <div className="eval-head">
        <div className="eval-score">
          {ev.score}
          <small> / 100</small>
        </div>
        <span className="eval-tag">
          {ev.score >= 80 ? '优秀' : ev.score >= 60 ? '良好' : '待改进'}
        </span>
      </div>
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
