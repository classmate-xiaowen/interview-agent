import type {
  ChatHistoryMessage,
  ChatSessionMeta,
  CostStats,
  DetectResponse,
  InterviewConfig,
  InterviewRecordCreate,
  InterviewRecordRead,
  InterviewTurn,
  MaskResponse,
  MaskSelection,
  ParsedQuestionBank,
  UserProfile,
} from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`请求失败 ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  listRecords(company?: string, mindset?: string) {
    const qs = new URLSearchParams()
    if (company) qs.set('company', company)
    if (mindset) qs.set('mindset', mindset)
    return fetch(`${BASE}/api/knowledge/records?${qs.toString()}`).then((r) =>
      json<InterviewRecordRead[]>(r),
    )
  },
  createRecord(data: InterviewRecordCreate) {
    return fetch(`${BASE}/api/knowledge/records`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then((r) => json<InterviewRecordRead>(r))
  },
  deleteRecord(id: string) {
    return fetch(`${BASE}/api/knowledge/records/${id}`, { method: 'DELETE' }).then((r) =>
      json<{ deleted: boolean }>(r),
    )
  },
  importRecords(items: InterviewRecordCreate[]) {
    return fetch(`${BASE}/api/knowledge/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(items),
    }).then((r) => json<{ imported: number }>(r))
  },
  parseBank(text: string) {
    return fetch(`${BASE}/api/knowledge/parse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }).then((r) => json<ParsedQuestionBank>(r))
  },
  getProfile() {
    return fetch(`${BASE}/api/profile`).then((r) => json<UserProfile>(r))
  },
  detectPII(text: string) {
    return fetch(`${BASE}/api/resume/detect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }).then((r) => json<DetectResponse>(r))
  },
  maskResume(text: string, selections: MaskSelection[]) {
    return fetch(`${BASE}/api/resume/mask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, selections }),
    }).then((r) => json<MaskResponse>(r))
  },
  updateProfile(data: UserProfile) {
    return fetch(`${BASE}/api/profile`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then((r) => json<UserProfile>(r))
  },
  createSession(config: InterviewConfig) {
    return fetch(`${BASE}/api/chat/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }).then((r) => json<{ session_id: string }>(r))
  },
  listSessions() {
    return fetch(`${BASE}/api/chat/sessions`).then((r) => json<ChatSessionMeta[]>(r))
  },
  getSessionMessages(id: string) {
    return fetch(`${BASE}/api/chat/sessions/${id}/messages`).then((r) =>
      json<ChatHistoryMessage[]>(r),
    )
  },
  renameSession(id: string, title: string) {
    return fetch(`${BASE}/api/chat/sessions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }).then((r) => json<{ ok: boolean }>(r))
  },
  deleteSession(id: string) {
    return fetch(`${BASE}/api/chat/sessions/${id}`, { method: 'DELETE' }).then((r) =>
      json<{ deleted: boolean }>(r),
    )
  },
  getCostStats() {
    return fetch(`${BASE}/api/chat/cost`).then((r) => json<CostStats>(r))
  },
}

export interface StreamHandlers {
  onToken: (text: string) => void
  onTurn: (turn: InterviewTurn) => void
  onError?: (message: string) => void
  onDone?: () => void
  signal?: AbortSignal
}

/**
 * 消费 /api/chat/message 的 SSE 流（text/event-stream）。
 *
 * 后端协议（每帧以 `\n\n` 分隔）：
 *   data: {"type":"token","text":...}              逐段问题正文
 *   data: {"type":"turn","turn":{...InterviewTurn}} 完整结构化结果（评分/引用）
 *   data: {"type":"done"}                           正常结束
 *   event: error\n data: {"type":"error","message"}  异常中断
 *
 * 采用 fetch + ReadableStream（而非 EventSource），因为需要 POST 请求体。
 * 支持 AbortSignal：调用方中断时直接抛出 AbortError。
 *
 * 超时保护：SSE 长连接本身没有超时，若后端 worker 崩溃 / 无响应，连接会「半死不活」
 * 地一直挂起（reader.read 永远阻塞）。因此内部再套一层 AbortController，超时即中止。
 */
const STREAM_TIMEOUT_MS = 60_000

export async function streamMessage(
  sessionId: string,
  message: string,
  handlers: StreamHandlers,
  kickoff = false,
): Promise<void> {
  // 内部控制器：合并「用户主动中断」与「超时保护」，避免后端无响应时前端永久挂起。
  const controller = new AbortController()
  const timer = setTimeout(
    () => controller.abort(new Error(`连接超时：后端未在 ${STREAM_TIMEOUT_MS / 1000}s 内返回数据，请检查服务是否可用`)),
    STREAM_TIMEOUT_MS,
  )
  const onExternalAbort = () => controller.abort(handlers.signal?.reason as Error | undefined)
  if (handlers.signal) {
    if (handlers.signal.aborted) controller.abort(handlers.signal.reason as Error | undefined)
    else handlers.signal.addEventListener('abort', onExternalAbort, { once: true })
  }

  try {
    const res = await fetch(`${BASE}/api/chat/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message, kickoff }),
      signal: controller.signal,
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`请求失败 ${res.status}: ${text}`)
    }
    if (!res.body) throw new Error('无响应流')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const dispatch = (frame: string) => {
    let event = ''
    const dataLines: string[] = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
    }
    if (dataLines.length === 0) return
    const data = dataLines.join('\n')
    let obj: any
    try {
      obj = JSON.parse(data)
    } catch {
      return
    }
    if (event === 'error' || obj?.type === 'error') {
      handlers.onError?.(obj?.message || 'stream error')
      return
    }
    if (obj.type === 'token') handlers.onToken(String(obj.text ?? ''))
    else if (obj.type === 'turn') handlers.onTurn(obj.turn as InterviewTurn)
    else if (obj.type === 'done') handlers.onDone?.()
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      if (frame.trim()) dispatch(frame)
    }
  }
  // 连接关闭后冲刷剩余缓冲
  if (buffer.trim()) dispatch(buffer)
  } finally {
    clearTimeout(timer)
    if (handlers.signal) handlers.signal.removeEventListener('abort', onExternalAbort)
  }
}
