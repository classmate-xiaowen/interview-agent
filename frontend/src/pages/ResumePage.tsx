import { useEffect, useMemo, useState } from 'react'
import { App as AntApp, Button, Input, Radio, Tag, Upload } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { api } from '../api'
import type { PiiItem, PiiCategory, MaskSelection, UserProfile } from '../types'

const CAT_LABEL: Record<PiiCategory, string> = {
  name: '姓名', phone: '手机号', email: '邮箱', id_card: '身份证',
  company: '公司', address: '住址', social: '社交账号',
}

export default function ResumePage() {
  const { message } = AntApp.useApp()
  const [original, setOriginal] = useState('')
  const [items, setItems] = useState<PiiItem[]>([])
  const [actions, setActions] = useState<Record<number, MaskSelection['action']>>({})
  const [masked, setMasked] = useState('')
  const [busy, setBusy] = useState(false)

  const selections = useMemo<MaskSelection[]>(
    () => items.map((it, i) => ({
      start: it.start, end: it.end, category: it.category,
      action: actions[i] ?? 'placeholder',
    })),
    [items, actions],
  )

  // 高亮预览：按 items 切片 original
  const segments = useMemo(() => {
    if (!items.length) return [{ text: original, pii: null as PiiItem | null }]
    const segs: { text: string; pii: PiiItem | null }[] = []
    let cursor = 0
    for (const it of items) {
      if (it.start > cursor) segs.push({ text: original.slice(cursor, it.start), pii: null })
      segs.push({ text: original.slice(it.start, it.end), pii: it })
      cursor = it.end
    }
    if (cursor < original.length) segs.push({ text: original.slice(cursor), pii: null })
    return segs
  }, [original, items])

  async function detect() {
    if (!original.trim()) { message.warning('请先粘贴简历原文'); return }
    setBusy(true); setMasked('')
    try {
      const r = await api.detectPII(original)
      setItems(r.items)
      message.success(`检测到 ${r.items.length} 处疑似敏感信息`)
    } catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }

  async function generate() {
    if (!original.trim()) { message.warning('请先粘贴简历原文'); return }
    setBusy(true)
    try {
      const r = await api.maskResume(original, selections)
      setMasked(r.masked_text)
      message.success('已生成脱敏版，可手动微调后保存')
    } catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }

  async function save() {
    if (!masked.trim()) { message.warning('请先生成脱敏版'); return }
    try {
      const p: UserProfile = await api.getProfile()
      await api.updateProfile({ ...p, resume_text: masked })
      message.success('已保存到画像，面试 Agent 将参考该背景')
    } catch (e) { message.error((e as Error).message) }
  }

  // 进入页面时同步一次画像中的脱敏版（若有）
  useEffect(() => {
    api.getProfile().then((p) => { if (p.resume_text) setMasked(p.resume_text) }).catch(() => {})
  }, [])

  // 本地解析上传的 .txt / .md 文件（原文不离开本机），填入文本框走原流程
  async function handleFile(file: File) {
    const name = file.name.toLowerCase()
    if (!name.endsWith('.txt') && !name.endsWith('.md') && !name.endsWith('.text')) {
      message.warning('当前仅支持 .txt / .md 文本文件，PDF/Word 暂不支持')
      return false
    }
    try {
      const text = await file.text()
      setOriginal(text)
      setItems([])
      setMasked('')
      message.success(`已读取 ${file.name}（${text.length} 字）`)
    } catch {
      message.error('文件读取失败')
    }
    return false
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="kicker">Resume Desensitization</div>
          <h2>简历脱敏导入</h2>
        </div>
      </div>

      <section className="card">
        <label className="block-label">① 粘贴简历原文，或上传 .txt / .md 文件（仅本地解析，不会上传原文）</label>
        <Upload accept=".txt,.md,.text" beforeUpload={handleFile} showUploadList={false} maxCount={1}>
          <Button icon={<UploadOutlined />} style={{ marginBottom: 10 }}>上传简历文件</Button>
        </Upload>
        <Input.TextArea rows={8} value={original} onChange={(e) => setOriginal(e.target.value)}
          placeholder="支持文本 / Markdown / 纯文本。粘贴或上传后点击「自动检测」。" />
        <div className="actions">
          <Button type="primary" onClick={detect} loading={busy} disabled={!original.trim()}>自动检测</Button>
        </div>
      </section>

      {items.length > 0 && (
        <section className="card">
          <label className="block-label">② 检测预览（高亮为疑似 PII，逐条选择处置方式）</label>
          <div className="resume-preview">
            {segments.map((s, i) => s.pii ? (
              <span key={i} className="pii-hl" data-cat={s.pii.category}>
                {s.text}<sup>{CAT_LABEL[s.pii.category]}</sup>
              </span>
            ) : <span key={i}>{s.text}</span>)}
          </div>
          <div className="pii-list">
            {items.map((it, i) => (
              <div key={i} className="pii-row">
                <Tag color="warning">{CAT_LABEL[it.category]}</Tag>
                <code className="pii-text">{it.text}</code>
                <Radio.Group
                  size="small"
                  value={actions[i] ?? 'placeholder'}
                  onChange={(e) => setActions((a) => ({ ...a, [i]: e.target.value }))}
                  optionType="button"
                  options={[
                    { label: '占位符', value: 'placeholder' },
                    { label: '打码', value: 'mask' },
                    { label: '忽略', value: 'ignore' },
                  ]}
                />
              </div>
            ))}
          </div>
          <div className="actions">
            <Button type="primary" onClick={generate} loading={busy}>生成脱敏版</Button>
          </div>
        </section>
      )}

      {masked && (
        <section className="card">
          <label className="block-label">③ 脱敏版（可手动微调，弥补漏检）</label>
          <Input.TextArea rows={8} value={masked} onChange={(e) => setMasked(e.target.value)} />
          <div className="actions">
            <Button type="primary" onClick={save}>保存到画像</Button>
          </div>
        </section>
      )}
    </div>
  )
}
