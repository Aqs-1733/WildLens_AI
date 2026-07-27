import { useEffect, useMemo, useState } from 'react'
import { AlertOctagon, CheckCircle2, Filter, ShieldAlert } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import type { AlertEvent } from '../types'

const severityText: Record<string, string> = { high: '高风险', medium: '中风险', low: '低风险' }
const statusText: Record<string, string> = { pending: '待处理', processing: '处理中', confirmed: '已确认', dismissed: '已排除' }

export default function AlertsPage() {
  const { user } = useAuth()
  const [items, setItems] = useState<AlertEvent[]>([])
  const [status, setStatus] = useState('all')
  const [error, setError] = useState('')
  const canReview = user?.role === 'regulator' || user?.role === 'admin'
  const load = () => api<AlertEvent[]>('/api/alerts').then((rows) => { setItems(rows); setError('') }).catch((err: Error) => setError(err.message))
  useEffect(() => { void load() }, [])
  const visible = useMemo(() => status === 'all' ? items : items.filter((item) => item.status === status), [items, status])
  const review = async (id: number, next: string) => {
    if (!canReview) return
    await api(`/api/alerts/${id}`, { method: 'PATCH', body: JSON.stringify({ status: next, note: '网页端复核' }) })
    await load()
  }

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><span className="eyebrow">REGULATORY ALERTS</span><h2>环保风险预警中心</h2><p>展示保护区干扰、污染、栖息地破坏和异常行为等风险事件；监管账号可复核处理。</p></div>
        <label className="filter-control"><Filter /><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">全部事件</option><option value="pending">待处理</option><option value="processing">处理中</option><option value="confirmed">已确认</option><option value="dismissed">已排除</option></select></label>
      </div>
      {error && <div className="inline-error">{error}</div>}
      <div className="alert-summary"><div><ShieldAlert /><strong>{items.filter((item) => item.status === 'pending').length}</strong><span>待处理</span></div><div><AlertOctagon /><strong>{items.filter((item) => item.severity === 'high').length}</strong><span>高风险</span></div><div><CheckCircle2 /><strong>{items.filter((item) => item.status === 'confirmed').length}</strong><span>已确认</span></div></div>
      <section className="panel">
        <div className="data-table alerts-table">
          <div className="table-row table-head"><span>事件</span><span>等级</span><span>置信度</span><span>发生时间</span><span>状态</span><span>操作</span></div>
          {visible.map((item) => (
            <div className="table-row" key={item.id}>
              <span className="table-title"><AlertOctagon /><div><strong>{item.title}</strong><small>{item.description}</small>{item.ai_advice && <small>建议：{item.ai_advice}</small>}</div></span>
              <span className={`severity-pill severity-${item.severity}`}>{severityText[item.severity] || item.severity}</span>
              <span>{Math.round(item.confidence * 100)}%</span>
              <span>{item.timestamp_ms ? `${(item.timestamp_ms / 1000).toFixed(1)} 秒` : new Date(item.created_at).toLocaleString('zh-CN')}</span>
              <span>{statusText[item.status] || item.status}</span>
              <span className="row-actions">{canReview ? <><button onClick={() => void review(item.id, 'confirmed')}>确认</button><button onClick={() => void review(item.id, 'dismissed')}>排除</button></> : <small className="muted">仅监管账号可复核</small>}</span>
            </div>
          ))}
          {!visible.length && <div className="empty-state">暂无符合筛选条件的风险事件。</div>}
        </div>
      </section>
    </div>
  )
}
