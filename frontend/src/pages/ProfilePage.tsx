import { useEffect, useState } from 'react'
import { api } from '../api'
import type { UserProfile } from '../types'

export default function ProfilePage() {
  const [p, setP] = useState<UserProfile>({
    skills: '',
    years: 0,
    target_role: '',
    target_companies: [],
    weaknesses: '',
    market_context: '',
  })
  const [companiesStr, setCompaniesStr] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api
      .getProfile()
      .then((d) => {
        setP(d)
        setCompaniesStr(d.target_companies.join(', '))
      })
      .catch((e) => setMsg(e.message))
  }, [])

  async function save() {
    const data: UserProfile = {
      ...p,
      target_companies: companiesStr
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    }
    await api.updateProfile(data)
    setMsg('已保存')
  }

  return (
    <div className="page">
      <div className="page-head">
        <h2>我的画像</h2>
      </div>
      {msg && <div className="hint">{msg}</div>}

      <section className="card">
        <div className="form">
          <div className="field">
            <label>技能栈</label>
            <input value={p.skills} onChange={(e) => setP({ ...p, skills: e.target.value })} />
          </div>
          <div className="field">
            <label>工作年限</label>
            <input
              type="number"
              value={p.years}
              onChange={(e) => setP({ ...p, years: Number(e.target.value) })}
            />
          </div>
          <div className="field full">
            <label>目标岗位</label>
            <input
              value={p.target_role}
              placeholder="如 高级前端工程师"
              onChange={(e) => setP({ ...p, target_role: e.target.value })}
            />
          </div>
          <div className="field full">
            <label>目标公司（逗号分隔）</label>
            <input
              value={companiesStr}
              placeholder="如 字节跳动, 腾讯, 阿里"
              onChange={(e) => setCompaniesStr(e.target.value)}
            />
          </div>
          <div className="field full">
            <label>薄弱环节</label>
            <textarea
              value={p.weaknesses}
              placeholder="技术短板、表达紧张、算法弱…"
              onChange={(e) => setP({ ...p, weaknesses: e.target.value })}
              rows={2}
            />
          </div>
          <div className="field full">
            <label>市场环境摘要</label>
            <textarea
              value={p.market_context}
              placeholder="目标行业/岗位的最新趋势、招聘热度…"
              onChange={(e) => setP({ ...p, market_context: e.target.value })}
              rows={3}
            />
          </div>
          <div className="actions">
            <button onClick={save}>保存画像</button>
          </div>
        </div>
      </section>
    </div>
  )
}
