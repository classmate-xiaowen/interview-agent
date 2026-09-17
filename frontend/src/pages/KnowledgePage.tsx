import { useEffect, useState } from 'react'
import { api } from '../api'
import type {
  InterviewRecordCreate, InterviewRecordRead, ParsedQuestion, RecordResult,
} from '../types'

/** 心态标签词表：固定选项避免自由填写导致检索稀疏（呼应需求文档 FR-10）。 */
const MINDSET_OPTIONS = ['压力型', '温和引导型', '技术深挖型', '业务导向型'] as const

type GlobalMeta = {
  company: string
  department: string
  mindset: string[]
  difficulty: string // '' 或 '1'..'5'
  result: '' | RecordResult
}

type PreviewRow = ParsedQuestion & {
  key: number
  include: boolean
  company: string
  department: string
  mindset: string[]
  difficulty: string
  result: '' | RecordResult
  dup: boolean
}

const EMPTY_META: GlobalMeta = {
  company: '', department: '', mindset: [], difficulty: '', result: '',
}

function normalize(s: string) {
  return (s || '').trim().toLowerCase().replace(/\s+/g, '')
}

function MindsetChips({ value, onToggle }: { value: string[]; onToggle: (m: string) => void }) {
  return (
    <div className="chips-row">
      {MINDSET_OPTIONS.map((m) => (
        <span
          key={m}
          className={`chip-toggle ${value.includes(m) ? 'on' : ''}`}
          onClick={() => onToggle(m)}
        >
          {m}
        </span>
      ))}
    </div>
  )
}

export default function KnowledgePage() {
  const [records, setRecords] = useState<InterviewRecordRead[]>([])
  const [company, setCompany] = useState('')
  const [msg, setMsg] = useState('')

  const [question, setQuestion] = useState('')
  const [myAnswer, setMyAnswer] = useState('')
  const [referenceAnswer, setReferenceAnswer] = useState('')
  const [formCompany, setFormCompany] = useState('')
  const [department, setDepartment] = useState('')
  const [mindsetStr, setMindsetStr] = useState('')
  const [difficultyStr, setDifficultyStr] = useState('')
  const [result, setResult] = useState<'' | RecordResult>('')
  const [note, setNote] = useState('')

  const [importText, setImportText] = useState('')

  // --- AI 智能导入状态 ---
  const [rawText, setRawText] = useState('')
  const [parsing, setParsing] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [modalStep, setModalStep] = useState<'meta' | 'preview'>('meta')
  const [globalMeta, setGlobalMeta] = useState<GlobalMeta>(EMPTY_META)
  const [parsed, setParsed] = useState<ParsedQuestion[]>([])
  const [preview, setPreview] = useState<PreviewRow[]>([])

  async function load() {
    const list = await api.listRecords(company || undefined)
    setRecords(list)
  }
  useEffect(() => {
    load()
  }, [])

  async function handleCreate() {
    if (!question.trim()) {
      setMsg('问题不能为空')
      return
    }
    const data: InterviewRecordCreate = {
      question: question.trim(),
      my_answer: myAnswer || null,
      reference_answer: referenceAnswer || null,
      company: formCompany || null,
      department: department || null,
      interviewer_mindset: mindsetStr
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      difficulty: difficultyStr ? Number(difficultyStr) : null,
      result: result || null,
      note: note || null,
    }
    await api.createRecord(data)
    setMsg('已保存')
    setQuestion('')
    setMyAnswer('')
    setReferenceAnswer('')
    setFormCompany('')
    setDepartment('')
    setMindsetStr('')
    setDifficultyStr('')
    setResult('')
    setNote('')
    load()
  }

  async function handleDelete(id: string) {
    await api.deleteRecord(id)
    load()
  }

  async function handleImport() {
    const items: InterviewRecordCreate[] = importText
      .split(/\n\s*\n/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map((q) => ({ question: q, company: company || null }))
    if (!items.length) {
      setMsg('批量内容为空')
      return
    }
    const r = await api.importRecords(items)
    setMsg(`已导入 ${r.imported} 条`)
    setImportText('')
    load()
  }

  // --- AI 解析流程 ---
  async function handleAiParse(initial?: string) {
    const text = (initial ?? rawText).trim()
    if (!text) {
      setMsg('请先粘贴内容，或点击/拖入文件、从剪贴板导入')
      return
    }
    setRawText(text)
    setParsing(true)
    setMsg('')
    try {
      const bank = await api.parseBank(text)
      if (!bank.questions.length) {
        setMsg('AI 未能从内容中拆出任何题目，请检查文本或换种表述')
        setParsing(false)
        return
      }
      setParsed(bank.questions)
      setGlobalMeta({ ...EMPTY_META, company: company || '' })
      setModalStep('meta')
      setShowModal(true)
    } catch (e) {
      setMsg(`解析失败：${(e as Error).message}`)
    } finally {
      setParsing(false)
    }
  }

  async function importFromFile(file: File) {
    try {
      const text = await file.text()
      if (!text.trim()) {
        setMsg('文件内容为空')
        return
      }
      await handleAiParse(text)
    } catch {
      setMsg('读取文件失败')
    }
  }

  async function importFromClipboard() {
    try {
      const text = await navigator.clipboard.readText()
      if (!text.trim()) {
        setMsg('剪贴板为空')
        return
      }
      await handleAiParse(text)
    } catch {
      setMsg('无法读取剪贴板（浏览器可能未授权）')
    }
  }

  function applyMeta() {
    const seen = new Set(
      records.map((r) => normalize(r.question) + ' ' + normalize(r.company || '')),
    )
    const rows: PreviewRow[] = parsed.map((p, i) => {
      const dup = seen.has(normalize(p.question) + ' ' + normalize(globalMeta.company))
      return {
        ...p,
        key: i,
        include: !dup,
        company: globalMeta.company,
        department: globalMeta.department,
        mindset: [...globalMeta.mindset],
        difficulty: globalMeta.difficulty,
        result: globalMeta.result,
        dup,
      }
    })
    setPreview(rows)
    setModalStep('preview')
  }

  function updateRow(key: number, patch: Partial<PreviewRow>) {
    setPreview((rows) => rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  }

  function toggleMindset(key: number, m: string) {
    setPreview((rows) =>
      rows.map((r) => {
        if (r.key !== key) return r
        const has = r.mindset.includes(m)
        return { ...r, mindset: has ? r.mindset.filter((x) => x !== m) : [...r.mindset, m] }
      }),
    )
  }

  function toggleGlobalMindset(m: string) {
    setGlobalMeta((g) => {
      const has = g.mindset.includes(m)
      return { ...g, mindset: has ? g.mindset.filter((x) => x !== m) : [...g.mindset, m] }
    })
  }

  async function confirmImport() {
    const items: InterviewRecordCreate[] = preview
      .filter((r) => r.include)
      .map((r) => ({
        question: r.question,
        my_answer: r.my_answer || null,
        reference_answer: r.reference_answer || null,
        company: r.company || null,
        department: r.department || null,
        interviewer_mindset: r.mindset,
        difficulty: r.difficulty ? Number(r.difficulty) : null,
        result: r.result || null,
        note: r.note || null,
      }))
    if (!items.length) {
      setMsg('没有选中任何题目')
      return
    }
    const res = await api.importRecords(items)
    setMsg(`已导入 ${res.imported} 条`)
    setShowModal(false)
    setParsed([])
    setPreview([])
    setRawText('')
    load()
  }

  const selectedCount = preview.filter((r) => r.include).length

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="kicker">Knowledge Base</div>
          <h2>知识库</h2>
        </div>
        <div className="filter">
          <input
            placeholder="按公司筛选"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
          <button onClick={load}>筛选</button>
        </div>
      </div>

      {msg && <div className="hint">{msg}</div>}

      <div className="grid">
        <section className="card">
          <h3>添加记录</h3>
          <div className="form">
            <div className="field full">
              <label>问题 *</label>
              <textarea
                placeholder="例：讲一下你做过的最有挑战的项目"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={3}
              />
            </div>
            <div className="field full">
              <label>我的回答</label>
              <textarea
                placeholder="你当时的回答（用于复盘对比）"
                value={myAnswer}
                onChange={(e) => setMyAnswer(e.target.value)}
                rows={2}
              />
            </div>
            <div className="field full">
              <label>参考答案</label>
              <textarea
                placeholder="理想的回答要点"
                value={referenceAnswer}
                onChange={(e) => setReferenceAnswer(e.target.value)}
                rows={2}
              />
            </div>
            <div className="field">
              <label>公司</label>
              <input
                placeholder="如 字节跳动"
                value={formCompany}
                onChange={(e) => setFormCompany(e.target.value)}
              />
            </div>
            <div className="field">
              <label>部门</label>
              <input
                placeholder="如 基础架构"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
              />
            </div>
            <div className="field">
              <label>心态标签（逗号分隔）</label>
              <input
                placeholder="如 紧张, 求稳"
                value={mindsetStr}
                onChange={(e) => setMindsetStr(e.target.value)}
              />
            </div>
            <div className="field">
              <label>难度（1-5）</label>
              <input
                placeholder="3"
                value={difficultyStr}
                onChange={(e) => setDifficultyStr(e.target.value)}
              />
            </div>
            <div className="field">
              <label>结果</label>
              <select value={result} onChange={(e) => setResult(e.target.value as '' | RecordResult)}>
                <option value="">不选</option>
                <option value="passed">通过</option>
                <option value="failed">未通过</option>
                <option value="pending">待定</option>
              </select>
            </div>
            <div className="field">
              <label>&nbsp;</label>
              <button onClick={handleCreate}>保存记录</button>
            </div>
            <div className="field full">
              <label>备注</label>
              <textarea
                placeholder="复盘心得、改进点…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
              />
            </div>
          </div>
        </section>

        <section className="card">
          <h3>AI 智能导入</h3>
          <p className="muted">一键导入：拖入 / 选择文件，或从剪贴板读取；AI 自动拆题、纠偏并整理你的回答。也支持手动粘贴后点「AI 解析」。</p>
          <label
            className="dropzone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              const f = e.dataTransfer.files?.[0]
              if (f) importFromFile(f)
            }}
          >
            <input
              type="file"
              accept=".md,.markdown,.txt,.text"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) importFromFile(f)
              }}
            />
            <span className="dz-icon">⤓</span>
            <span>点击选择文件，或将 .md / .txt 文件拖到这里</span>
          </label>
          <div className="row" style={{ gap: 8 }}>
            <button className="ghost" onClick={importFromClipboard}>从剪贴板导入</button>
          </div>
          <textarea
            placeholder={'例如：\n教练问了我项目里最难的一个 bug 怎么排查的，我当时说了看日志和监控…\n还有一道是让我讲讲 TCP 三次握手'}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            rows={8}
          />
          <div className="actions">
            <button onClick={() => handleAiParse()} disabled={parsing || !rawText.trim()}>
              {parsing ? 'AI 解析中…' : 'AI 解析'}
            </button>
          </div>
        </section>

        <section className="card">
          <h3>快速文本导入</h3>
          <p className="muted">无 AI 时的轻量兜底：用空行分隔多道题目，仅按当前筛选公司归类（不含答案/标签）。</p>
          <textarea
            placeholder={'讲一下你做过最有挑战的项目\n\n你如何排查线上故障'}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            rows={8}
          />
          <div className="actions">
            <button onClick={handleImport}>导入题目</button>
          </div>
        </section>
      </div>

      <section className="card">
        <h3>记录列表（{records.length}）</h3>
        <ul className="list">
          {records.map((r) => (
            <li key={r.id} className="item">
              <div className="item-main">
                <div className="q">{r.question}</div>
                <div className="meta">
                  {r.company && <span>🏢 {r.company}</span>}
                  {r.department && <span>📁 {r.department}</span>}
                  {(r.interviewer_mindset ?? []).map((m) => (
                    <span key={m} className="tag">
                      {m}
                    </span>
                  ))}
                  {r.result && (
                    <span className={`tag ${r.result}`}>
                      {r.result === 'passed' ? '通过' : r.result === 'failed' ? '未通过' : '待定'}
                    </span>
                  )}
                </div>
              </div>
              <button className="danger" onClick={() => handleDelete(r.id)}>
                删除
              </button>
            </li>
          ))}
          {records.length === 0 && <li className="empty muted">暂无记录，先在上方添加或批量导入吧</li>}
        </ul>
      </section>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            {modalStep === 'meta' ? (
              <>
                <div className="modal-head">
                  <h3>设置全局元数据（应用到全部 {parsed.length} 题）</h3>
                  <button className="ghost" onClick={() => setShowModal(false)}>✕</button>
                </div>
                <div className="form">
                  <div className="field">
                    <label>公司</label>
                    <input
                      placeholder="如 字节跳动"
                      value={globalMeta.company}
                      onChange={(e) => setGlobalMeta({ ...globalMeta, company: e.target.value })}
                    />
                  </div>
                  <div className="field">
                    <label>部门</label>
                    <input
                      placeholder="如 基础架构"
                      value={globalMeta.department}
                      onChange={(e) => setGlobalMeta({ ...globalMeta, department: e.target.value })}
                    />
                  </div>
                  <div className="field full">
                    <label>心态标签（多选）</label>
                    <MindsetChips value={globalMeta.mindset} onToggle={toggleGlobalMindset} />
                  </div>
                  <div className="field">
                    <label>难度（1-5）</label>
                    <select
                      value={globalMeta.difficulty}
                      onChange={(e) => setGlobalMeta({ ...globalMeta, difficulty: e.target.value })}
                    >
                      <option value="">不填</option>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <option key={n} value={n}>{n}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label>结果</label>
                    <select
                      value={globalMeta.result}
                      onChange={(e) => setGlobalMeta({ ...globalMeta, result: e.target.value as '' | RecordResult })}
                    >
                      <option value="">不填</option>
                      <option value="passed">通过</option>
                      <option value="failed">未通过</option>
                      <option value="pending">待定</option>
                    </select>
                  </div>
                </div>
                <div className="modal-actions">
                  <button className="ghost" onClick={() => setShowModal(false)}>取消</button>
                  <button onClick={applyMeta}>应用到全部并预览</button>
                </div>
              </>
            ) : (
              <>
                <div className="modal-head">
                  <h3>导入预览（{preview.length} 题，已选 {selectedCount}）</h3>
                  <button className="ghost" onClick={() => setShowModal(false)}>✕</button>
                </div>
                <div className="preview-wrap">
                  <table className="preview-table">
                    <thead>
                      <tr>
                        <th>导入</th>
                        <th>问题 / 内容</th>
                        <th>公司</th>
                        <th>部门</th>
                        <th>心态</th>
                        <th>难度</th>
                        <th>结果</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.map((r) => (
                        <tr key={r.key} className={r.dup ? 'dup' : ''}>
                          <td>
                            <input
                              type="checkbox"
                              checked={r.include}
                              onChange={() => updateRow(r.key, { include: !r.include })}
                            />
                            {r.dup && <div className="tag warn">疑似重复</div>}
                          </td>
                          <td className="preview-q">
                            <div>{r.question}</div>
                            <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                              {r.my_answer ? '我的回答 ✔ ' : ''}
                              {r.reference_answer ? '参考答案 ✔' : ''}
                              {r.note ? ' 备注 ✔' : ''}
                              {!r.my_answer && !r.reference_answer && !r.note ? '（仅题干）' : ''}
                            </div>
                          </td>
                          <td>
                            <input
                              value={r.company}
                              onChange={(e) => updateRow(r.key, { company: e.target.value })}
                            />
                          </td>
                          <td>
                            <input
                              value={r.department}
                              onChange={(e) => updateRow(r.key, { department: e.target.value })}
                            />
                          </td>
                          <td>
                            <MindsetChips
                              value={r.mindset}
                              onToggle={(m) => toggleMindset(r.key, m)}
                            />
                          </td>
                          <td>
                            <select
                              value={r.difficulty}
                              onChange={(e) => updateRow(r.key, { difficulty: e.target.value })}
                            >
                              <option value="">不填</option>
                              {[1, 2, 3, 4, 5].map((n) => (
                                <option key={n} value={n}>{n}</option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <select
                              value={r.result}
                              onChange={(e) => updateRow(r.key, { result: e.target.value as '' | RecordResult })}
                            >
                              <option value="">不填</option>
                              <option value="passed">通过</option>
                              <option value="failed">未通过</option>
                              <option value="pending">待定</option>
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="modal-actions">
                  <button className="ghost" onClick={() => setModalStep('meta')}>上一步</button>
                  <button className="ghost" onClick={() => setShowModal(false)}>取消</button>
                  <button onClick={confirmImport} disabled={selectedCount === 0}>
                    确认导入 {selectedCount} 条
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
