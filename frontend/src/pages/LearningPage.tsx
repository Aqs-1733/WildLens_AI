import { useEffect, useMemo, useState } from 'react'
import { BookOpenCheck, CheckCircle2, Clock3, Flame, Gift, GraduationCap, Search, Sparkles, Star } from 'lucide-react'
import { api } from '../api/client'

interface Task { id: number; title: string; description: string; category: string; reward_points: number; reward_stars: number; target_value: number; progress: number; completed: boolean; claimed: boolean }
interface Badge { id: number; name: string; description: string; category: string; progress: number; target: number; earned: boolean }

export default function LearningPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [badges, setBadges] = useState<Badge[]>([])
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [claiming, setClaiming] = useState<number | null>(null)

  const load = () => Promise.all([
    api<Task[]>('/api/species/learning/tasks'),
    api<Badge[]>('/api/species/learning/badges'),
  ]).then(([taskRows, badgeRows]) => { setTasks(taskRows); setBadges(badgeRows) })

  useEffect(() => { void load() }, [])

  const claim = async (id: number) => {
    setClaiming(id)
    try {
      await api(`/api/species/learning/tasks/${id}/claim`, { method: 'POST' })
      await load()
    } finally {
      setClaiming(null)
    }
  }

  const filteredTasks = useMemo(() => {
    const rows = tasks.filter((task) => !query || `${task.title}${task.description}${task.category}`.toLowerCase().includes(query.toLowerCase()))
    return showAll ? rows : rows.slice(0, 60)
  }, [query, showAll, tasks])
  const earned = badges.filter((item) => item.earned).length

  return <div className="page-stack">
    <div className="learning-hero">
      <div><span className="eyebrow">LEARN & PROTECT</span><h2>知识越多，星光越亮。</h2><p>挑战进度来自真实观察、分享、视频分析和智能问答；完成后可领取奖励。</p></div>
      <div className="streak-card"><Flame/><strong>{tasks.length}</strong><span>挑战总数</span></div>
      <div className="streak-card"><Gift/><strong>{earned}/{badges.length}</strong><span>已获徽章</span></div>
    </div>
    <div className="learning-layout">
      <section className="panel">
        <div className="panel-head"><div><span className="eyebrow">ACTIVE MISSIONS</span><h3>学习任务</h3></div><GraduationCap/></div>
        <label className="search-box learning-search"><Search/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 1000 个挑战"/></label>
        <div className="task-list">{filteredTasks.map((task) => {
          const percent = Math.min(100, task.target_value ? task.progress / task.target_value * 100 : 0)
          return <article className={`task-card ${task.completed ? 'completed' : ''}`} key={task.id}>
            <div className="task-icon">{task.completed ? <CheckCircle2/> : <Clock3/>}</div>
            <div className="task-copy"><strong>{task.title}</strong><p>{task.description}</p><div className="task-progress"><i style={{ width: `${percent}%` }}/><span>{task.progress}/{task.target_value}</span></div></div>
            <div className="task-reward"><span><Sparkles/>+{task.reward_points}</span><span><Star/>+{task.reward_stars}</span><button disabled={!task.completed || task.claimed || claiming === task.id} onClick={() => void claim(task.id)}>{task.claimed ? '已领取' : claiming === task.id ? '领取中' : '领取'}</button></div>
          </article>
        })}</div>
        {!showAll && tasks.length > filteredTasks.length && <button className="ghost-btn full" onClick={() => setShowAll(true)}>显示全部挑战</button>}
      </section>
      <aside className="panel reward-cabinet">
        <div className="panel-head"><div><span className="eyebrow">BADGES</span><h3>徽章成就</h3></div><Gift/></div>
        {badges.map((badge) => <div className={`badge-row ${badge.earned ? 'earned' : ''}`} key={badge.id}><div className="badge-medal"><BookOpenCheck/></div><div><strong>{badge.name}</strong><span>{badge.category} · {badge.progress}/{badge.target} · {badge.description}</span></div>{badge.earned && <CheckCircle2/>}</div>)}
      </aside>
    </div>
  </div>
}
