import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, streamMessage } from '../api'
import { App as AntApp, Button, Input, InputNumber, Modal, Popconfirm } from 'antd'
import { DeleteOutlined, EditOutlined } from '@ant-design/icons'
import type {
  ChatHistoryMessage,
  ChatSessionMeta,
  InterviewConfig,
  InterviewerStyle,
  InterviewTurn,
} from '../types'

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

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch {
    return ''
  }
}

export default function ChatPage() {
  const [style, setStyle] = useState<InterviewerStyle>('gentle')
  const [targetCompany, setTargetCompany] = useState('')
  const [targetRole, setTargetRole] = useState('')
  const [jd, setJd] = useState('')
  const [salary, setSalary] = useState('')
  const [rounds, setRounds] = useState<number | null>(null)
  const [setupOpen, setSetupOpen] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([])
  const { message } = AntApp.useApp()
  const [renameTarget, setRenameTarget] = useState<{ id: string; title: string } | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const userStoppedRef = useRef(false)
  const endRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 输入框自动增高
  useEffect(() => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }, [input])

  useEffect(() => {
    loadSessions()
  }, [])

  async function loadSessions() {
    try {
      setSessions(await api.listSessions())
    } catch {
      /* 列表加载失败不阻断对话 */
    }
  }

  function openSetup() {
    setError('')
    setSetupOpen(true)
  }

  async function confirmStart() {
    if (rounds !== null && (rounds < 1 || rounds > 20)) {
      message.warning('面试轮次需在 1-20 之间')
      return
    }
    setSetupOpen(false)
    const cfg: InterviewConfig = {
      interviewer_style: style,
      target_company: targetCompany || null,
      target_role: targetRole || null,
      target_jd: jd || null,
      salary: salary || null,
      rounds: rounds,
    }
    try {
      const r = await api.createSession(cfg)
      setSessionId(r.session_id)
      setMessages([])
      await runStream(r.session_id, '', true)
      await loadSessions()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function openSession(id: string) {
    if (id === sessionId) return
    setError('')
    try {
      const msgs: ChatHistoryMessage[] = await api.getSessionMessages(id)
      const s = sessions.find((x) => x.session_id === id)
      if (s) {
        setStyle(s.interviewer_style)
        setTargetCompany(s.target_company || '')
        setTargetRole(s.target_role || '')
        setJd(s.target_jd || '')
        setSalary(s.salary || '')
        setRounds(s.rounds ?? null)
      }
      setSessionId(id)
      setMessages(msgs.map((m) => ({ role: m.role, text: m.content, turn: m.turn ?? undefined })))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function openRename(id: string, title: string) {
    setRenameTarget({ id, title })
    setRenameValue(title)
  }

  async function confirmRename() {
    if (!renameTarget) return
    const v = renameValue.trim()
    if (!v) {
      message.warning('标题不能为空')
      return
    }
    try {
      await api.renameSession(renameTarget.id, v)
      await loadSessions()
      message.success('已重命名')
      setRenameTarget(null)
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  async function removeSession(id: string) {
    try {
      await api.deleteSession(id)
      if (sessionId === id) {
        setSessionId(null)
        setMessages([])
      }
      await loadSessions()
      message.success('已删除会话')
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  function end() {
    abortRef.current?.abort()
    setSessionId(null)
    setMessages([])
    loadSessions()
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
      <aside className="chat-sidebar">
        <div className="sidebar-head">
          <span className="sidebar-title">训练会话</span>
          {sessions.length > 0 && <span className="sidebar-count">{sessions.length}</span>}
        </div>
        <button className="session-new" onClick={openSetup} disabled={streaming}>
          ＋ 新建会话
        </button>
        <div className="session-list">
          {sessions.length === 0 ? (
            <div className="session-empty">
              还没有历史会话
              <span>点击上方按钮，开始第一次模拟训练</span>
            </div>
          ) : (
            sessions.map((s) => (
              <div
                key={s.session_id}
                className={`session-item ${s.session_id === sessionId ? 'active' : ''}`}
                onClick={() => openSession(s.session_id)}
              >
                <div className="session-title">{s.title}</div>
                <div className="session-meta">
                  <span className="session-style">{STYLE_LABEL[s.interviewer_style]}</span>
                  {s.target_role && <span>{s.target_role}</span>}
                  <span>{s.target_company || '通用'}</span>
                  <span className="session-time">{fmtDate(s.updated_at)}</span>
                </div>
                <div className="session-actions">
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    title="重命名"
                    onClick={(e) => {
                      e.stopPropagation()
                      openRename(s.session_id, s.title)
                    }}
                  />
                  <Popconfirm
                    title="删除会话"
                    description="删除后无法恢复，确认删除？"
                    okText="删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    onConfirm={(e) => {
                      e?.stopPropagation()
                      removeSession(s.session_id)
                    }}
                    onCancel={(e) => e?.stopPropagation()}
                  >
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      title="删除"
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>
                </div>
              </div>
            ))
          )}
        </div>
      </aside>

      <div className="chat-main">
        <header className="chat-head">
          <div className="chat-status">
            <span className={`status-dot ${sessionId ? 'live' : ''}`} />
            <span className="status-text">{sessionId ? '训练进行中' : '等待开始'}</span>
          </div>
          <div className="chat-controls">
            {sessionId ? (
              <button onClick={end} className="danger">
                结束训练
              </button>
            ) : (
              <span className="chat-hint">点击左侧「＋ 新建会话」开始模拟训练</span>
            )}
          </div>
        </header>

        {error && <div className="hint error">{error}</div>}

        <div className="messages">
          <div className="thread">
            {messages.length === 0 && !streaming && (
              <div className="empty-state">
                <div className="orb">🎯</div>
                <h4>准备好接受模拟训练了吗？</h4>
                <p>
                  选择一种教练风格并点击「开始训练」—— Agent 会结合你的知识库与画像提问，
                  每轮回答后即时给出评分与改进建议。
                </p>
                <div className="chips">
                  <span className="chip"><b>STAR</b> 法则作答</span>
                  <span className="chip"><b>先结论</b> 后细节</span>
                  <span className="chip"><b>量化</b> 你的成果</span>
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
                        {m.turn?.evaluation && (
                          <EvaluationCard
                            eval={m.turn.evaluation}
                            originalAnswer={messages[i - 1]?.role === 'user' ? messages[i - 1].text : ''}
                          />
                        )}
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
          </div>
          <div ref={endRef} />
        </div>

        <div className="composer-zone">
          <div className="composer">
            <textarea
              ref={taRef}
              placeholder={
                sessionId
                  ? '输入你的回答…（Enter 发送，Shift + Enter 换行）'
                  : '先在上方开始一个训练会话'
              }
              value={input}
              disabled={!sessionId || streaming}
              rows={1}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            <div className="composer-actions">
              {streaming && (
                <button onClick={stop} className="danger" title="中断当前生成">
                  停止
                </button>
              )}
              <button className="send" onClick={send} disabled={!sessionId || streaming || !input.trim()}>
                {streaming ? '生成中…' : '发送 ↵'}
              </button>
            </div>
          </div>
          <div className="composer-hint">
            <kbd>Enter</kbd> 发送 · <kbd>Shift</kbd> + <kbd>Enter</kbd> 换行 · 建议用 STAR 结构组织回答
          </div>
        </div>
      </div>

      <Modal
        title="重命名会话"
        open={!!renameTarget}
        onOk={confirmRename}
        onCancel={() => setRenameTarget(null)}
        okText="保存"
        cancelText="取消"
        destroyOnClose
        maskClosable={false}
      >
        <Input
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onPressEnter={confirmRename}
          maxLength={30}
          placeholder="请输入会话标题"
          autoFocus
        />
      </Modal>

      <Modal
        title="开始模拟训练"
        open={setupOpen}
        onOk={confirmStart}
        onCancel={() => setSetupOpen(false)}
        okText="开始训练"
        cancelText="取消"
        destroyOnClose
        maskClosable={false}
      >
        <div className="setup-form">
          <label>教练风格</label>
          <div className="seg" role="group" aria-label="教练风格">
            {(['pressure', 'gentle', 'deep'] as InterviewerStyle[]).map((s) => (
              <button
                key={s}
                type="button"
                className={style === s ? 'on' : ''}
                onClick={() => setStyle(s)}
              >
                {STYLE_LABEL[s]}
              </button>
            ))}
          </div>

          <label>目标公司（可选）</label>
          <Input
            value={targetCompany}
            onChange={(e) => setTargetCompany(e.target.value)}
            placeholder="如：字节跳动"
            maxLength={40}
          />

          <label>目标岗位（可选）</label>
          <Input
            value={targetRole}
            onChange={(e) => setTargetRole(e.target.value)}
            placeholder="如：后端开发工程师"
            maxLength={40}
          />

          <label>岗位 JD / 招聘要求（可选）</label>
          <Input.TextArea
            value={jd}
            onChange={(e) => setJd(e.target.value)}
            rows={4}
            maxLength={2000}
            placeholder="粘贴岗位描述或核心要求，面试官会据此设计针对性问题"
          />

          <label>薪资范围（可选）</label>
          <Input
            value={salary}
            onChange={(e) => setSalary(e.target.value)}
            placeholder="如：25-35K"
            maxLength={30}
          />

          <label>第几轮面试（可选）</label>
          <InputNumber
            min={1}
            max={20}
            value={rounds}
            onChange={(v) => setRounds(v ?? null)}
            style={{ width: '100%' }}
            placeholder="如：1"
          />
        </div>
      </Modal>
    </div>
  )
}

function EvaluationCard({ eval: ev, originalAnswer }: { eval: NonNullable<Msg['turn']>['evaluation']; originalAnswer?: string }) {
  if (!ev) return null
  const level = ev.score >= 80 ? 'good' : ev.score >= 60 ? 'mid' : 'low'
  return (
    <div className="eval">
      <div className="eval-head">
        <div className="eval-score">
          <span className={`score-num ${level}`}>{ev.score}</span>
          <small>/ 100</small>
        </div>
        <span className="eval-tag">
          {ev.overall_level ?? (ev.score >= 80 ? '优秀' : ev.score >= 60 ? '良好' : '待改进')}
        </span>
      </div>
      {(ev.covered_points.length > 0 || ev.missing_points.length > 0) && (
        <div className="eval-grid">
          {ev.covered_points.length > 0 && (
            <div className="eval-sec">
              <b className="t-good">✓ 覆盖要点</b>
              <ul>
                {ev.covered_points.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </div>
          )}
          {ev.missing_points.length > 0 && (
            <div className="eval-sec">
              <b className="t-warn">○ 遗漏要点</b>
              <ul>
                {ev.missing_points.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {ev.structure_feedback && (
        <div className="eval-line">
          <b>结构</b>
          <span>{ev.structure_feedback}</span>
        </div>
      )}
      {ev.expression_feedback && (
        <div className="eval-line">
          <b>表达</b>
          <span>{ev.expression_feedback}</span>
        </div>
      )}
      {ev.suggestions.length > 0 && (
        <div className="eval-line">
          <b>建议</b>
          <ul className="suggestions">
            {ev.suggestions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}
      {ev.corrected_answer && (
        <div className="eval-corrected">
          <b className="t-correction">✎ 纠正后回答</b>
          <div className="compare">
            {originalAnswer && (
              <div className="compare-col">
                <span className="compare-label">原回答</span>
                <p className="orig">{originalAnswer}</p>
              </div>
            )}
            <div className="compare-col">
              <span className="compare-label">纠正版</span>
              <p className="fixed">{ev.corrected_answer.corrected_text}</p>
            </div>
          </div>
          {ev.corrected_answer.change_points.length > 0 && (
            <div className="change-points">
              <span className="compare-label">修改点</span>
              <ul>
                {ev.corrected_answer.change_points.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
