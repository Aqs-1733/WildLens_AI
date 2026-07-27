import { useEffect, useMemo, useState } from 'react'
import { BookOpenCheck, CheckCircle2, Clock3, Flame, Gift, GraduationCap, Loader2, Search, Sparkles, Star } from 'lucide-react'
import { api } from '../api/client'

interface Task {
  id: number
  title: string
  description: string
  category: string
  reward_points: number
  reward_stars: number
  target_value: number
  progress: number
  completed: boolean
  claimed: boolean
  remaining?: number
}

interface Badge {
  id: number
  name: string
  description: string
  category: string
  progress: number
  target: number
  earned: boolean
  claimed?: boolean
  remaining?: number
  reward_points?: number
  reward_stars?: number
}

type ClaimResponse = { message: string; points: number; stars: number }

export default function LearningPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [badges, setBadges] = useState<Badge[]>([])
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [claimingTask, setClaimingTask] = useState<number | null>(null)
  const [claimingBadge, setClaimingBadge] = useState<number | null>(null)
  const [claimToast, setClaimToast] = useState('')
  const [claimError, setClaimError] = useState('')
  const [claimBurst, setClaimBurst] = useState('')

  const load = () => Promise.all([
    api<Task[]>('/api/species/learning/tasks'),
    api<Badge[]>('/api/species/learning/badges'),
  ]).then(([taskRows, badgeRows]) => {
    setTasks(taskRows)
    setBadges(badgeRows)
  })

  useEffect(() => { void load() }, [])

  const showSuccess = (result: ClaimResponse) => {
    setClaimToast(`${result.message} · 当前 ${result.points} EXP / ${result.stars} 星`)
    setClaimBurst(result.message.includes('徽章') ? 'badge' : 'task')
    window.setTimeout(() => setClaimToast(''), 2600)
    window.setTimeout(() => setClaimBurst(''), 900)
  }

  const claimTask = async (task: Task) => {
    if (task.claimed) {
      setClaimToast('这个奖励已经领取过了')
      window.setTimeout(() => setClaimToast(''), 1800)
      return
    }
    if (!task.completed) {
      setClaimError(`任务尚未完成，还差 ${task.remaining ?? Math.max(0, task.target_value - task.progress)} 次`)
      return
    }
    setClaimingTask(task.id)
    setClaimError('')
    try {
      const result = await api<ClaimResponse>(`/api/species/learning/tasks/${task.id}/claim`, { method: 'POST' })
      showSuccess(result)
      await load()
    } catch (error) {
      setClaimError(error instanceof Error ? error.message : `还差 ${task.remaining ?? Math.max(0, task.target_value - task.progress)} 次`)
    } finally {
      setClaimingTask(null)
    }
  }

  const claimBadge = async (badge: Badge) => {
    if (badge.claimed) {
      setClaimToast('这个徽章已经领取过了')
      window.setTimeout(() => setClaimToast(''), 1800)
      return
    }
    if (!badge.earned) {
      setClaimError(`徽章尚未达成，还差 ${badge.remaining ?? Math.max(0, badge.target - badge.progress)} 次`)
      return
    }
    setClaimingBadge(badge.id)
    setClaimError('')
    try {
      const result = await api<ClaimResponse>(`/api/species/learning/badges/${badge.id}/claim`, { method: 'POST' })
      showSuccess(result)
      await load()
    } catch (error) {
      setClaimError(error instanceof Error ? error.message : `还差 ${badge.remaining ?? Math.max(0, badge.target - badge.progress)} 次`)
    } finally {
      setClaimingBadge(null)
    }
  }

  const filteredTasks = useMemo(() => {
    const lower = query.toLowerCase()
    const rows = tasks.filter((task) => !lower || `${task.title}${task.description}${task.category}`.toLowerCase().includes(lower))
    return showAll ? rows : rows.slice(0, 60)
  }, [query, showAll, tasks])

  const earned = badges.filter((item) => item.earned).length

  return (
    <div className="page-stack">
      {claimToast && <div className={`claim-toast ${claimBurst ? `claim-burst-${claimBurst}` : ''}`}><Gift /><strong>{claimToast}</strong><span /><span /><span /></div>}
      <div className="learning-hero">
        <div><span className="eyebrow">LEARN & PROTECT</span><h2>知识越多，星光越亮。</h2></div>
        <div className="streak-card"><Flame /><strong>{tasks.length}</strong><span>挑战总数</span></div>
        <div className="streak-card"><Gift /><strong>{earned}/{badges.length}</strong><span>已获徽章</span></div>
      </div>
      {claimError && <div className="form-error">{claimError}</div>}
      <div className="learning-layout">
        <section className="panel">
          <div className="panel-head"><div><span className="eyebrow">ACTIVE MISSIONS</span><h3>学习任务</h3></div><GraduationCap /></div>
          <label className="search-box learning-search"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 1000 个挑战" /></label>
          <div className="task-list">
            {filteredTasks.map((task) => {
              const percent = Math.min(100, task.target_value ? (task.progress / task.target_value) * 100 : 0)
              const remaining = task.remaining ?? Math.max(0, task.target_value - task.progress)
              return (
                <article className={`task-card ${task.completed ? 'completed' : ''}`} key={task.id}>
                  <div className="task-icon">{task.completed ? <CheckCircle2 /> : <Clock3 />}</div>
                  <div className="task-copy"><strong>{task.title}</strong><p>{task.description}</p><div className="task-progress"><i style={{ width: `${percent}%` }} /><span>{task.progress}/{task.target_value}</span></div></div>
                  <div className="task-reward">
                    <span><Sparkles />+{task.reward_points}</span>
                    <span><Star />+{task.reward_stars}</span>
                    <button className={claimBurst === 'task' && task.claimed ? 'claimed-pop' : ''} disabled={claimingTask === task.id} onClick={() => void claimTask(task)}>
                      {task.claimed ? '已领取' : claimingTask === task.id ? '领取中' : task.completed ? '领取' : `还差 ${remaining}`}
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
          {!showAll && tasks.length > filteredTasks.length && <button className="ghost-btn full" onClick={() => setShowAll(true)}>显示全部挑战</button>}
        </section>
        <aside className="panel reward-cabinet">
          <div className="panel-head"><div><span className="eyebrow">BADGES</span><h3>徽章成就</h3></div><Gift /></div>
          {badges.map((badge) => {
            const remaining = badge.remaining ?? Math.max(0, badge.target - badge.progress)
            return (
              <div className={`badge-row ${badge.earned ? 'earned' : ''}`} key={badge.id}>
                <div className="badge-medal"><BookOpenCheck /></div>
                <div><strong>{badge.name}</strong><span>{badge.category} · {badge.progress}/{badge.target} · {badge.description}</span></div>
                <button className={`badge-claim-btn ${claimBurst === 'badge' && badge.claimed ? 'claimed-pop' : ''}`} disabled={claimingBadge === badge.id} onClick={() => void claimBadge(badge)}>
                  {badge.claimed ? <CheckCircle2 /> : claimingBadge === badge.id ? <Loader2 className="spin" /> : badge.earned ? '领取' : `差 ${remaining}`}
                </button>
              </div>
            )
          })}
        </aside>
      </div>
    </div>
  )
}
