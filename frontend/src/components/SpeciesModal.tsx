import { useEffect, useMemo, useState } from 'react'
import { BookOpen, Check, ExternalLink, Images, MessageCircle, Network, Send, ShieldCheck, Sparkles, X } from 'lucide-react'
import { api, mediaUrl } from '../api/client'
import type { Species } from '../types'
import SpeciesAvatar from './SpeciesAvatar'
import { categoryNameZh, cleanChineseDisplayName, localTaxonName } from '../utils/taxonNames'

type ReferenceImage = { image_url: string; thumbnail_url: string; source: string; source_page: string; author: string; license_code: string; attribution: string }
type SimilarSpecies = { species_id?: number; taxon_id?: number; common_name: string; scientific_name: string; relationship: string; taxonomy_score: number; reason: string; image_url?: string; image_source?: string; license_code?: string }
type GraphData = { nodes: { id: string; rank: string; name: string }[]; links: { source: string; target: string; type: string }[] }
type ObservationDistribution = { count: number; located_count: number; events: Array<{ id: number; title: string; image_url: string; confidence: number; created_at: string; latitude?: number | null; longitude?: number | null; province: string; city: string; district: string }> }
type Tab = 'knowledge' | 'relations' | 'observe' | 'ask'

const rankNames: Record<string, string> = { kingdom: '界', phylum: '门', class: '纲', order: '目', family: '科', genus: '属', species: '种' }

export default function SpeciesModal({ speciesId, jobId, onClose }: { speciesId: number; jobId?: number; onClose: () => void }) {
  const [species, setSpecies] = useState<Species | null>(null)
  const [tab, setTab] = useState<Tab>('knowledge')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([])
  const [conversationId, setConversationId] = useState<number>()
  const [loading, setLoading] = useState(false)
  const [referenceImages, setReferenceImages] = useState<ReferenceImage[]>([])
  const [similar, setSimilar] = useState<SimilarSpecies[]>([])
  const [graph, setGraph] = useState<GraphData | null>(null)
  const [observations, setObservations] = useState<ObservationDistribution | null>(null)
  const [observeAddress, setObserveAddress] = useState('')

  useEffect(() => {
    setSpecies(null)
    void api<Species>(`/api/species/${speciesId}`).then(setSpecies)
    void Promise.allSettled([
      api<ReferenceImage[]>(`/api/species/${speciesId}/reference-images?limit=8`).then(setReferenceImages),
      api<SimilarSpecies[]>(`/api/species/${speciesId}/similar?limit=6`).then(setSimilar),
      api<GraphData>(`/api/species/${speciesId}/graph`).then(setGraph),
      api<ObservationDistribution>(`/api/species/${speciesId}/observations`).then(setObservations),
    ])
  }, [speciesId])

  const taxonomyNodes = useMemo(() => graph?.nodes.filter((node) => rankNames[node.rank]) ?? [], [graph])
  if (!species) return <div className="modal-backdrop"><div className="species-modal loading">正在打开物种档案…</div></div>
  const displayName = cleanChineseDisplayName(localTaxonName({
    label: species.common_name,
    scientificName: species.scientific_name,
    category: species.category,
    fallback: species.common_name,
  }), species.common_name)

  const ask = async (suggestion?: string) => {
    const text = suggestion || question
    if (!text.trim()) return
    setMessages((current) => [...current, { role: 'user', content: text }])
    setQuestion('')
    setLoading(true)
    try {
      const result = await api<{ answer: string; conversation_id: number; mode: string; fallback_reason?: string }>(`/api/qa/ask`, {
        method: 'POST',
        body: JSON.stringify({ question: text, species_id: species.id, job_id: jobId, conversation_id: conversationId }),
      })
      setConversationId(result.conversation_id)
      setMessages((current) => [...current, { role: 'assistant', content: result.answer }])
      if (result.mode === 'database_update') {
        void api<ObservationDistribution>(`/api/species/${species.id}/observations`).then(setObservations)
      }
    } catch (error) {
      setMessages((current) => [...current, { role: 'assistant', content: error instanceof Error ? error.message : '科普服务暂时不可用，请稍后重试' }])
    } finally { setLoading(false) }
  }

  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <div className="species-modal species-modal-expanded">
      <button className="modal-close" onClick={onClose}><X /></button>
      <div className="species-hero"><SpeciesAvatar species={species} large /><div><span className="species-category" style={{ color: species.color }}>{categoryNameZh(species.category)} · 稀有度 {species.rarity}/5</span><h2>{displayName}</h2></div><div className="protection-chip"><ShieldCheck size={18} />{species.protection_level}</div></div>
      <div className="modal-tabs">
        <button className={tab === 'knowledge' ? 'active' : ''} onClick={() => setTab('knowledge')}><BookOpen />物种科普</button>
        <button className={tab === 'relations' ? 'active' : ''} onClick={() => setTab('relations')}><Network />图谱与相似种</button>
        <button className={tab === 'observe' ? 'active' : ''} onClick={() => setTab('observe')}><Sparkles />本次观察</button>
        <button className={tab === 'ask' ? 'active' : ''} onClick={() => setTab('ask')}><MessageCircle />继续提问</button>
      </div>
      <div className="modal-body">
        {tab === 'knowledge' && <div className="knowledge-grid">
          <article><span>外观特征</span><p>{species.traits}</p></article><article><span>栖息环境</span><p>{species.habitat}</p></article><article><span>分布区域</span><p>{species.distribution}</p></article><article><span>食性</span><p>{species.diet}</p></article><article><span>活动规律</span><p>{species.activity}</p></article><article><span>生态价值</span><p>{species.ecology_value}</p></article><article className="knowledge-wide warning"><span>主要威胁</span><p>{species.threats}</p></article><article className="knowledge-wide"><span>保护行动</span><p>{species.conservation}</p></article>
          <div className="fact-strip">{species.facts.map((fact) => <span key={fact}><Check size={14} />{fact}</span>)}</div>
          {referenceImages.length > 0 && <article className="knowledge-wide"><span><Images size={15}/> 开放许可参考图片</span><div className="reference-image-grid">{referenceImages.map((item, index) => <a href={item.source_page} target="_blank" rel="noreferrer" key={`${item.image_url}-${index}`}><img src={item.thumbnail_url || item.image_url} alt={`${species.common_name}参考图`} /><small>{item.source} · {item.license_code || '许可信息见原页'}<ExternalLink size={12}/></small></a>)}</div></article>}
        </div>}
        {tab === 'relations' && <div className="relations-panel">
          <section><h3>分类层级</h3>{taxonomyNodes.length ? <div className="taxonomy-path">{taxonomyNodes.map((node, index) => <div key={node.id}><span>{rankNames[node.rank]}</span><strong>{node.name}</strong>{index < taxonomyNodes.length - 1 && <i>→</i>}</div>)}</div> : <p className="muted">当前物种的本地分类层级还在补全中。</p>}</section>
          <section><h3>生物学相近物种</h3><div className="similar-species-grid">{similar.length ? similar.map((item) => {
            const name = cleanChineseDisplayName(localTaxonName({ label: item.common_name, scientificName: item.scientific_name }), item.common_name || item.scientific_name)
            return <article key={`${item.scientific_name}-${item.relationship}`}>{item.image_url && <img src={item.image_url} alt={name} />}<span>{item.relationship}</span><h4>{name}</h4><div className="similar-score">分类相近度 {(item.taxonomy_score * 100).toFixed(0)}%</div><p>{item.reason}</p>{item.image_source && <small>{item.image_source} · {item.license_code || '许可见来源'}</small>}</article>
          }) : <div className="empty-inline">暂无可核验的相近物种记录</div>}</div></section>
        </div>}
        {tab === 'observe' && <div className="observation-panel"><div className="observation-metric"><strong>{observations?.count ?? 0} 次观察</strong><span>{observations?.located_count ?? 0} 条带地点{jobId ? ` · 当前任务 #${jobId}` : ''}</span></div><div className="inline-observation-form"><input value={observeAddress} onChange={(event) => setObserveAddress(event.target.value)} placeholder="填写观察地点，例如 天津水上公园" /><button className="primary-btn" onClick={() => { if (observeAddress.trim()) { setTab('ask'); void ask(`将今天看到的${displayName}登记在${observeAddress.trim()}`); setObserveAddress('') } }}>登记观察</button></div><div className="species-distribution-list">{observations?.events.length ? observations.events.slice(0, 8).map((event) => <article key={event.id}>{event.image_url ? <img src={mediaUrl(event.image_url)} alt={event.title} /> : <Sparkles />}<div><strong>{new Date(event.created_at).toLocaleString('zh-CN')}</strong><span>{[event.province, event.city, event.district].filter(Boolean).join(' · ') || '未填写地点'} · 置信度 {(event.confidence * 100).toFixed(1)}%</span></div></article>) : <div className="empty-inline">还没有这个物种的真实观察事件。</div>}</div></div>}
        {tab === 'ask' && <div className="qa-panel"><div className="qa-context"><MessageCircle /><div><strong>围绕 {displayName} 连续提问</strong></div></div><div className="qa-messages">{messages.length === 0 && <div className="suggestion-grid">{['它有哪些明显特征？', '它和生物学相近物种怎么区分？', '当前识别还需要补拍什么角度？'].map((suggestion) => <button key={suggestion} onClick={() => void ask(suggestion)}>{suggestion}</button>)}</div>}{messages.map((message, index) => <div key={index} className={`qa-message ${message.role}`}>{message.content}</div>)}{loading && <div className="qa-message assistant typing">正在结合问题与观察上下文分析…</div>}</div><div className="qa-input"><input value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void ask() }} placeholder={`问问 ${displayName}…`} /><button onClick={() => void ask()}><Send /></button></div></div>}
      </div>
    </div>
  </div>
}
