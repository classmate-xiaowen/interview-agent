import type {
  InterviewConfig,
  InterviewRecordCreate,
  InterviewRecordRead,
  InterviewTurn,
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
  getProfile() {
    return fetch(`${BASE}/api/profile`).then((r) => json<UserProfile>(r))
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
    }).then((r) => json<{ session_id: string } & InterviewTurn>(r))
  },
}

/**
 * 消费 /api/chat/message 的 SSE 流。
 * 后端逐个推送 `data: {"type":"token","text":...}`，末尾推送 `event: turn\ndata: <InterviewTurn JSON>`。
 */
export async function streamMessage(
  sessionId: string,
  message: string,
  onToken: (text: string) => void,
  onTurn: (turn: InterviewTurn) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/api/chat/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })
  if (!res.body) throw new Error('无响应流')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const raw of lines) {
      const line = raw.trim()
      if (!line || line.startsWith('event:')) continue
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      try {
        const obj = JSON.parse(payload)
        if (obj && obj.type === 'token') onToken(String(obj.text))
        else onTurn(obj as InterviewTurn)
      } catch {
        /* 忽略非 JSON 行 */
      }
    }
  }
}
