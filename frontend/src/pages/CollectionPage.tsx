import { useEffect, useMemo, useState } from 'react'
import { BookOpen, CalendarDays, CloudSun, Heart, MapPin, Search, Share2, Sparkles, Star } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import SpeciesAvatar from '../components/SpeciesAvatar'
import SpeciesModal from '../components/SpeciesModal'
import type { CollectionItem } from '../types'
import { cleanChineseDisplayName, hasChinese, isUncertainName, localTaxonName } from '../utils/taxonNames'

type ObservationSummary = {
  species_id: number | null
  title: string
  scientific_name: string
  category: string
  count: number
  first_discovered_at: string
  last_discovered_at: string
}

export default function CollectionPage() {
  const [collection, setCollection] = useState<CollectionItem[]>([])
  const [summaries, setSummaries] = useState<ObservationSummary[]>([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<number | null>(null)

  const load = () => Promise.all([
    api<CollectionItem[]>('/api/species/collection'),
    api<ObservationSummary[]>('/api/identify/observations/summary'),
  ]).then(([items, stats]) => { setCollection(items); setSummaries(stats) })

  useEffect(() => { void load() }, [])

  const displayName = (item: CollectionItem) => cleanChineseDisplayName(localTaxonName({
    label: item.species.common_name,
    scientificName: item.species.scientific_name,
    category: item.species.category,
    fallback: item.species.common_name,
  }), item.species.common_name)
  const cards = useMemo(
    () => collection.filter((item) => {
      const name = displayName(item)
      const haystack = `${name}${item.species.common_name}${item.species.scientific_name}`.toLowerCase()
      return hasChinese(name) && !isUncertainName(name) && !isUncertainName(item.species.common_name) && (!query || haystack.includes(query.toLowerCase()))
    }),
    [collection, query],
  )
  const stars = collection.reduce((total, item) => total + item.stars_earned, 0)
  const observations = summaries.reduce((total, item) => total + item.count, 0)

  const favorite = async (id: number) => {
    await api(`/api/species/${id}/favorite`, { method: 'PATCH' })
    await load()
  }

  const share = async () => {
    const text = `我的识境图鉴已记录 ${collection.length} 种生命，共完成 ${observations} 次真实观察，获得 ${stars} 颗生态星。`
    if (navigator.share) await navigator.share({ title: '我的自然观察图鉴', text, url: window.location.href })
    else {
      await navigator.clipboard.writeText(`${text}\n${window.location.href}`)
      alert('观察成果已复制到剪贴板')
    }
  }

  return (
    <div className="page-stack">
      <div className="collection-hero">
        <div>
          <span className="eyebrow">MY LIFE LIST</span>
          <h2>我的真实发现图鉴</h2>
          <p>这里不会预设物种或显示虚假的完成度。拍照和视频识别到的具体动植物会进入个人图鉴，重复观察会增加次数。</p>
        </div>
        <div className="collection-summary">
          <div><Sparkles /><strong>{collection.length}</strong><span>已发现物种</span></div>
          <div><MapPin /><strong>{observations}</strong><span>观察记录</span></div>
          <div><Star /><strong>{stars}</strong><span>生态星</span></div>
        </div>
      </div>
      <div className="mode-switch"><Link to="/species"><BookOpen/>物种百科</Link><Link className="active" to="/collection"><Sparkles/>我的收藏</Link><Link to="/classroom"><CloudSun/>自然现象</Link></div>

      <div className="reward-strip">
        <div className="reward-level"><CalendarDays /><div><strong>每一次重复发现都会保留</strong><span>系统分别统计首次发现、最近发现、总次数和不同地点。</span></div></div>
        <button className="ghost-btn" onClick={() => void share()}><Share2 />分享我的发现</button>
      </div>

      <div className="page-tools">
        <div className="search-box"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索我真实发现过的物种" /></div>
        <span className="muted">同一物种只显示一个收藏词条，事件明细保存在观察记录中。</span>
      </div>

      {cards.length === 0 ? (
        <section className="panel empty-collection">
          <Sparkles size={44} />
          <h3>图鉴还是空的</h3>
          <p>去拍照识别或视频识别，确认结果并保存第一条自然观察。</p>
        </section>
      ) : (
        <div className="album-grid">
          {cards.map((item) => {
            const summary = summaries.find((value) => value.species_id === item.species_id)
            return (
              <article className="album-card unlocked" key={item.id} onClick={() => setSelected(item.species_id)}>
                <div className="album-card-image">
                  <SpeciesAvatar species={item.species} large />
                  <button className={`favorite-btn ${item.favorite ? 'active' : ''}`} onClick={(event) => { event.stopPropagation(); void favorite(item.species_id) }}><Heart /></button>
                </div>
                <div className="album-card-body">
                  <div><h3>{displayName(item)}</h3></div>
                  <div className="album-meta"><span>发现 {summary?.count ?? item.discovered_count} 次</span><span>{'★'.repeat(Math.max(1, item.stars_earned))}</span></div>
                  {summary && <p className="unlock-hint">首次：{new Date(summary.first_discovered_at).toLocaleDateString()} · 最近：{new Date(summary.last_discovered_at).toLocaleDateString()}</p>}
                </div>
              </article>
            )
          })}
        </div>
      )}
      {selected && <SpeciesModal speciesId={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
