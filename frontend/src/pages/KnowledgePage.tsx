import { useEffect, useState } from 'react'
import { api } from '../api'
import type { InterviewRecordCreate, InterviewRecordRead, RecordResult } from '../types'

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
          <h3>批量导入</h3>
          <p className="muted">用空行分隔多道题目，将按当前筛选公司归类</p>
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
    </div>
  )
}
