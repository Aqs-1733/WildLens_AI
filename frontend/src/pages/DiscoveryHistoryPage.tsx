import { useEffect, useMemo, useState } from 'react'
import { Bird, CloudSun, Footprints, History, Image as ImageIcon, Repeat2, Search, Share2, Sparkles, Star } from 'lucide-react'
import { api, mediaUrl } from '../api/client'
import { categoryNameZh, cleanChineseDisplayName, hasChinese, isUncertainName, localTaxonName } from '../utils/taxonNames'

type ObservationSummary = {
  species_id: number | null
  title: string
  scientific_name: string
  category: string
  count: number
  first_discovered_at: string
  last_discovered_at: string
  latest_record_id: number
  latest_image_url: string
}

const filters = [
  { value: '', label: '全部发现', icon: History },
  { value: 'species', label: '动植物', icon: Bird },
  { value: 'behavior', label: '动物行为', icon: Footprints },
  { value: 'phenomenon', label: '自然现象', icon: CloudSun },
]

export default function DiscoveryHistoryPage() {
  const [records, setRecords] = useState<ObservationSummary[]>([])
  const [filter, setFilter] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [shareId, setShareId] = useState<number | null>(null)
  const [shareText, setShareText] = useState('')

  const load = () => {
    setLoading(true)
    api<ObservationSummary[]>('/api/identify/observations/summary')
      .then(setRecords)
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const filtered = useMemo(() => records.filter((item) => {
    const title = cleanChineseDisplayName(localTaxonName({
      label: item.title,
      scientificName: item.scientific_name,
      category: item.category,
      fallback: item.title,
    }), item.title)
    const type = item.category === 'phenomenon' || item.category === 'fire' || item.category === 'smoke' || item.category === 'weather'
      ? 'phenomenon'
      : item.category === 'behavior'
        ? 'behavior'
        : 'species'
    return hasChinese(title) && !isUncertainName(title) && (!filter || type === filter) && `${title}${item.title}${item.scientific_name}${item.category}`.toLowerCase().includes(query.toLowerCase())
  }), [filter, query, records])
  const observations = records.reduce((sum, item) => sum + item.count, 0)

  const share = async (record: ObservationSummary) => {
    await api('/api/social/posts', {
      method: 'POST',
      body: JSON.stringify({
        species_id: record.species_id,
        discovery_id: record.latest_record_id,
        content: shareText || `我观察到${record.title}，累计记录 ${record.count} 次，一起来了解它吧！`,
        image_url: record.latest_image_url,
        visibility: 'public',
      }),
    })
    setShareId(null)
    setShareText('')
  }

  return (
    <div className="page-stack history-page">
      <section className="collection-hero discovery-hero">
        <div><span className="eyebrow">MY NATURE JOURNAL</span><h2>我的观察记录</h2><p>同一动植物合并为一个词条，重复观察会增加次数；每一次识别事件和地点仍保存在明细数据中。</p></div>
        <div className="collection-summary"><div><Star /><strong>{records.length}</strong><span>独立词条</span></div><div><Sparkles /><strong>{observations}</strong><span>观察事件</span></div></div>
      </section>

      <section className="history-toolbar panel">
        <div className="filter-pills">{filters.map(({ value, label, icon: Icon }) => <button key={value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}><Icon />{label}</button>)}</div>
        <label className="search-box"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、学名或类别" /></label>
      </section>

      {loading ? <div className="page-loader">正在整理自然手账…</div> : filtered.length === 0 ? <div className="empty-state panel"><History /><h3>还没有匹配的发现</h3><p>从“拍照/视频识别”开始你的第一条自然观察吧。</p></div> : (
        <section className="discovery-timeline compact-history">
          {filtered.map((record) => {
            const title = cleanChineseDisplayName(localTaxonName({
              label: record.title,
              scientificName: record.scientific_name,
              category: record.category,
              fallback: record.title,
            }), record.title)
            return (
            <article key={`${record.species_id}-${record.scientific_name}-${record.title}`} className="discovery-entry type-species">
              <div className="discovery-date"><strong>{new Date(record.last_discovered_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}</strong><span>最近</span></div>
              <div className="discovery-card">
                <div className="discovery-image">{record.latest_image_url ? <img src={mediaUrl(record.latest_image_url)} alt={title} /> : <div><ImageIcon /></div>}<span>{categoryNameZh(record.category)}</span></div>
                <div className="discovery-content"><div className="discovery-title"><div><h3>{title}</h3></div><strong><Repeat2 /> {record.count}</strong></div><p>首次：{new Date(record.first_discovered_at).toLocaleString('zh-CN')} · 最近：{new Date(record.last_discovered_at).toLocaleString('zh-CN')}</p><div className="discovery-meta"><span><Sparkles />累计 {record.count} 次观察</span><span>最新记录 #{record.latest_record_id}</span></div></div>
                <button className="share-record-btn" onClick={() => { setShareId(record.latest_record_id); setShareText(`我观察到${title}，累计记录 ${record.count} 次。`) }}><Share2 />分享</button>
              </div>
              {shareId === record.latest_record_id && <div className="inline-share panel"><textarea value={shareText} onChange={(event) => setShareText(event.target.value)} /><button className="primary-btn" onClick={() => void share(record)}>发布到自然社区</button><button className="ghost-btn" onClick={() => setShareId(null)}>取消</button></div>}
            </article>
          )})}
        </section>
      )}
    </div>
  )
}
