import { useEffect, useState } from 'react'
import { Alert, Card, Col, Row, Spin, Statistic, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { api } from '../api'
import type { CostBreakdownRow, CostStats } from '../types'

const { Title, Text } = Typography

const fmtNum = (n: number) => n.toLocaleString('en-US')
const fmtCost = (c: number) => `¥${c.toFixed(c < 0.01 ? 4 : 2)}`

/** 自绘横向条形（不依赖图表库），用于按维度展示成本占比。 */
function BarList({ rows, empty }: { rows: CostBreakdownRow[]; empty: string }) {
  if (rows.length === 0) return <Text type="secondary">{empty}</Text>
  const max = Math.max(...rows.map((r) => r.cost), 0.0001)
  return (
    <div className="barlist">
      {rows.map((r) => (
        <div className="barlist-row" key={r.key}>
          <div className="barlist-head">
            <span className="barlist-key" title={r.key}>
              {r.key}
            </span>
            <span className="barlist-cost">{fmtCost(r.cost)}</span>
          </div>
          <div className="barlist-track">
            <div className="barlist-fill" style={{ width: `${(r.cost / max) * 100}%` }} />
          </div>
          <div className="barlist-meta">
            <Text type="secondary">
              in {fmtNum(r.tokens_in)} / out {fmtNum(r.tokens_out)} · {r.turns} 轮
            </Text>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function CostPage() {
  const [data, setData] = useState<CostStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    api
      .getCostStats()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e?.message || e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  if (loading) return <Spin style={{ margin: 24 }} />
  if (error) return <Alert type="error" message="加载成本数据失败" description={error} showIcon />

  const t = data?.totals
  const topCols: ColumnsType<CostBreakdownRow> = [
    { title: '会话', dataIndex: 'key', key: 'key', ellipsis: true },
    {
      title: '成本',
      dataIndex: 'cost',
      key: 'cost',
      sorter: (a, b) => a.cost - b.cost,
      defaultSortOrder: 'descend',
      render: (c: number) => <Tag color="blue">{fmtCost(c)}</Tag>,
    },
    { title: '输入 token', dataIndex: 'tokens_in', key: 'tokens_in', render: fmtNum },
    { title: '输出 token', dataIndex: 'tokens_out', key: 'tokens_out', render: fmtNum },
    { title: '轮数', dataIndex: 'turns', key: 'turns' },
  ]

  return (
    <div className="cost-page">
      <Title level={3}>成本与决策</Title>
      <Text type="secondary">
        把每轮面试落库的 token 折算成人民币成本，作为模型选型 / 路由策略的决策依据（单价为近似值，请以真实账单校准）。
      </Text>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title="累计成本" value={t?.cost ?? 0} precision={4} prefix="¥" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="总 Token" value={(t?.tokens_in ?? 0) + (t?.tokens_out ?? 0)} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="总轮数" value={t?.turns ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="会话数" value={t?.sessions ?? 0} />
          </Card>
        </Col>
      </Row>

      {data && data.recommendations.length > 0 && (
        <Alert
          style={{ marginTop: 16 }}
          type="info"
          showIcon
          message="决策建议"
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {data.recommendations.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          }
        />
      )}

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="按模型">
            <BarList rows={data?.by_model ?? []} empty="暂无数据" />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="按阶段 (kickoff / answer / summary)">
            <BarList rows={data?.by_stage ?? []} empty="暂无数据" />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="按天趋势">
            <BarList rows={data?.by_day ?? []} empty="暂无数据" />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="最贵会话 Top 10">
            <Table
              rowKey="key"
              size="small"
              pagination={false}
              columns={topCols}
              dataSource={data?.top_sessions ?? []}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
