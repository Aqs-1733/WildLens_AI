import { useEffect, useMemo, useState } from 'react'
import {
  BookOpen,
  CheckCircle2,
  HelpCircle,
  Loader2,
  MapPin,
  MessageCircle,
  PencilLine,
  Save,
  Send,
  Share2,
  Sparkles,
  Volume2,
  X,
} from 'lucide-react'
import { api } from '../api/client'
import type { DiscoveryRecord, PhotoObject, SpeciesGuide } from '../types'

type LocationPayload = {
  latitude?: number
  longitude?: number
  location_accuracy?: number
  location_source: 'gps' | 'exif' | 'manual' | 'unknown'
  privacy_level: 'precise' | 'obscured' | 'private'
}

async function requestLocation(): Promise<LocationPayload> {
  if (!('geolocation' in navigator)) return { location_source: 'unknown', privacy_level: 'precise' }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        location_accuracy: position.coords.accuracy,
        location_source: 'gps',
        privacy_level: 'precise',
      }),
      () => resolve({ location_source: 'unknown', privacy_level: 'precise' }),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    )
  })
}

function evidenceText(item: unknown): string {
  if (typeof item === 'string') return item
  if (!item || typeof item !== 'object') return '结构化模型证据'
  const value = item as Record<string, unknown>
  if (typeof value.fusion_reason === 'string') return value.fusion_reason
  if (typeof value.kind === 'string') return value.kind
  return '结构化模型证据'
}

export default function RecognitionModal({
  object,
  jobId,
  imageUrl,
  observationTimestampMs,
  onClose,
  onOpenSpecies,
}: {
  object: PhotoObject
  jobId: number
  imageUrl?: string
  observationTimestampMs?: number
  onClose: () => void
  onOpenSpecies?: (speciesId: number) => void
}) {
  const [tab, setTab] = useState<'explain' | 'ask' | 'share'>('explain')
  const [question, setQuestion] = useState('')
  const [conversationId, setConversationId] = useState<number>()
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([])
  const [loading, setLoading] = useState(false)
  const [feedbackSent, setFeedbackSent] = useState(false)
  const [feedbackLoading, setFeedbackLoading] = useState(false)
  const [savedRecord, setSavedRecord] = useState<DiscoveryRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [shareText, setShareText] = useState(`我用识境识别到了${object.label}，一起来看看这次自然发现吧！`)
  const [shared, setShared] = useState(false)
  const [guide, setGuide] = useState<SpeciesGuide | null>(null)
  const [guideLoading, setGuideLoading] = useState(true)
  const [guideError, setGuideError] = useState('')
  const [observationAddress, setObservationAddress] = useState('')
  const [correctionOpen, setCorrectionOpen] = useState(false)
  const [correctedLabel, setCorrectedLabel] = useState(object.label)
  const [correctedScientific, setCorrectedScientific] = useState(object.scientific_name)
  const [correctionNote, setCorrectionNote] = useState('')

  useEffect(() => {
    let active = true
    setGuide(null)
    setGuideError('')
    setGuideLoading(true)
    setCorrectionOpen(false)
    setFeedbackSent(false)
    setCorrectedLabel(object.label)
    setCorrectedScientific(object.scientific_name)
    api<SpeciesGuide>(`/api/identify/detections/${object.id}/guide`)
      .then((data) => {
        if (!active) return
        setGuide(data)
        setCorrectedLabel(data.common_name_zh || data.label || object.label)
        setCorrectedScientific(data.scientific_name || object.scientific_name)
        setShareText(`我用识境识别到了${data.common_name_zh || data.label || object.label}，一起来看看这次自然发现吧！`)
      })
      .catch((err: Error) => {
        if (active) setGuideError(err.message || '中文科普加载失败')
      })
      .finally(() => {
        if (active) setGuideLoading(false)
      })
    return () => {
      active = false
    }
  }, [object.id, object.label, object.scientific_name])

  const title = object.phenomenon || object.behavior || guide?.common_name_zh || guide?.label || object.label
  const scientificName = guide?.scientific_name || object.scientific_name
  const typeLabel = useMemo(() => {
    if (object.phenomenon) return '自然现象'
    if (object.behavior) return '动物行为'
    return guide?.category_zh || '物种识别'
  }, [guide?.category_zh, object])
  const evidenceItems = (object.evidence.length ? object.evidence : ['暂无结构化依据']).map(evidenceText)

  const ask = async (preset?: string) => {
    const text = (preset ?? question).trim()
    if (!text) return
    setMessages((items) => [...items, { role: 'user', content: text }])
    setQuestion('')
    setLoading(true)
    try {
      const result = await api<{ answer: string; conversation_id: number; mode: string; fallback_reason?: string | null }>(`/api/qa/ask`, {
        method: 'POST',
        body: JSON.stringify({
          question: text,
          species_id: object.species_id,
          job_id: jobId,
          detection_id: object.id,
          conversation_id: conversationId,
        }),
      })
      setConversationId(result.conversation_id)
      const suffix = result.mode === 'unavailable' && result.fallback_reason ? `\n\n原因：${result.fallback_reason}` : ''
      setMessages((items) => [...items, { role: 'assistant', content: `${result.answer}${suffix}` }])
    } catch (error) {
      setMessages((items) => [
        ...items,
        { role: 'assistant', content: error instanceof Error ? error.message : '回答失败，请稍后重试' },
      ])
    } finally {
      setLoading(false)
    }
  }

  const feedback = async (isCorrect: boolean) => {
    setFeedbackLoading(true)
    try {
      await api(`/api/identify/detections/${object.id}/feedback`, {
        method: 'POST',
        body: JSON.stringify({ is_correct: isCorrect, note: isCorrect ? '用户确认识别正确' : '用户认为需要复核' }),
      })
      setFeedbackSent(true)
    } finally {
      setFeedbackLoading(false)
    }
  }

  const submitCorrection = async () => {
    const label = correctedLabel.trim()
    const scientific = correctedScientific.trim()
    const note = correctionNote.trim()
    if (!label && !scientific && !note) return
    setFeedbackLoading(true)
    try {
      await api(`/api/identify/detections/${object.id}/feedback`, {
        method: 'POST',
        body: JSON.stringify({
          is_correct: false,
          corrected_label: label,
          corrected_scientific_name: scientific,
          note: note || '用户提交了识别修正',
        }),
      })
      setFeedbackSent(true)
      setCorrectionOpen(false)
    } finally {
      setFeedbackLoading(false)
    }
  }

  const saveObservation = async (): Promise<DiscoveryRecord> => {
    if (savedRecord) return savedRecord
    setSaving(true)
    try {
      const location = await requestLocation()
      const record = await api<DiscoveryRecord>('/api/identify/observations', {
        method: 'POST',
        body: JSON.stringify({
          detection_id: object.id,
          note: observationTimestampMs === undefined ? '' : `视频时间 ${(observationTimestampMs / 1000).toFixed(1)} 秒`,
          address: observationAddress,
          ...location,
        }),
      })
      setSavedRecord(record)
      return record
    } finally {
      setSaving(false)
    }
  }

  const speak = () => {
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const guideText = guide ? `${guide.summary} ${guide.appearance} ${guide.observation_tips}` : object.explanation
    const content = `${title}。${scientificName ? `学名${scientificName}。` : ''}${guideText || ''}`
    const utterance = new SpeechSynthesisUtterance(content)
    utterance.lang = 'zh-CN'
    utterance.rate = 0.92
    window.speechSynthesis.speak(utterance)
  }

  const share = async () => {
    let finalDiscoveryId = savedRecord?.id ?? object.discovery_id
    if (!finalDiscoveryId) {
      const created = await saveObservation()
      finalDiscoveryId = created.id
    }
    await api('/api/social/posts', {
      method: 'POST',
      body: JSON.stringify({
        species_id: object.species_id,
        discovery_id: finalDiscoveryId,
        content: shareText,
        image_url: imageUrl || savedRecord?.image_url || '',
        visibility: 'public',
      }),
    })
    setShared(true)
  }

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="recognition-modal">
        <button className="modal-close" onClick={onClose}><X /></button>
        <div className="recognition-head">
          <div className="recognition-badge" style={{ borderColor: object.color, color: object.color }}>{typeLabel}</div>
          <div>
            <h2>{title}</h2>
            <em>{scientificName || '学名待确认'}</em>
            <p>置信度 {(object.confidence * 100).toFixed(1)}%</p>
          </div>
          <div className="confidence-orb" style={{ '--confidence': `${object.confidence * 100}%`, '--tone': object.color } as React.CSSProperties}>
            <strong>{Math.round(object.confidence * 100)}</strong><span>%</span>
          </div>
        </div>

        <div className="modal-tabs recognition-tabs">
          <button className={tab === 'explain' ? 'active' : ''} onClick={() => setTab('explain')}><BookOpen />中文科普</button>
          <button className={tab === 'ask' ? 'active' : ''} onClick={() => setTab('ask')}><MessageCircle />继续提问</button>
          <button className={tab === 'share' ? 'active' : ''} onClick={() => setTab('share')}><Share2 />记录与分享</button>
        </div>

        <div className="modal-body">
          {tab === 'explain' && (
            <div className="recognition-explain">
              <article className="recognition-wide">
                <span>物种科普</span>
                <p>{guideLoading ? '正在生成中文科普…' : guideError || guide?.summary || '暂无中文科普，建议先确认具体物种。'}</p>
              </article>
              {guide && (
                <>
                  <article><span>外形识别</span><p>{guide.appearance}</p></article>
                  <article><span>栖息环境</span><p>{guide.habitat}</p></article>
                  <article><span>行为习性</span><p>{guide.behavior}</p></article>
                  <article><span>相似物种</span><p>{guide.similar_species}</p></article>
                  <article className="recognition-wide"><span>观察建议</span><p>{guide.observation_tips}</p>{guide.caution && <p>{guide.caution}</p>}</article>
                </>
              )}
              <article><span>模型解释</span><p>{object.explanation || '暂无详细解释，建议补充更多角度照片。'}</p></article>
              <article><span>可见依据</span><div className="evidence-list">{evidenceItems.map((item, index) => <b key={`${item}-${index}`}><CheckCircle2 />{item}</b>)}</div></article>
              {object.alternatives.length > 0 && (
                <article className="recognition-wide"><span>Top 候选与相似物种</span><div className="alternative-list">{object.alternatives.map((item, index) => <div key={`${item.name}-${index}`}><strong>{item.name}</strong><em>{item.scientific_name || '学名待确认'}</em><small>{Math.round((item.confidence ?? 0) * 100)}%</small></div>)}</div></article>
              )}
              <article className="recognition-wide location-save-panel">
                <span>观察地点</span>
                <label>
                  <input value={observationAddress} onChange={(event) => setObservationAddress(event.target.value)} placeholder="可选：例如 天津水上公园、杭州西湖、北京奥森" />
                </label>
                <p>保存时会先请求 GPS；如果你填写了城市或地点文字，也会写入观察记录并在地图中显示可解析的位置。</p>
              </article>
              {correctionOpen && (
                <article className="recognition-wide correction-panel">
                  <span>提交识别修正</span>
                  <div className="correction-grid">
                    <label>正确中文名<input value={correctedLabel} onChange={(event) => setCorrectedLabel(event.target.value)} placeholder="例如 树麻雀甘肃亚种" /></label>
                    <label>正确学名<input value={correctedScientific} onChange={(event) => setCorrectedScientific(event.target.value)} placeholder="例如 Passer montanus kansuensis" /></label>
                  </div>
                  <textarea value={correctionNote} onChange={(event) => setCorrectionNote(event.target.value)} placeholder="可写判断依据、拍摄地点、用户提示词或为什么需要修正" />
                  <div className="recognition-actions">
                    <button className="primary-btn" disabled={feedbackLoading} onClick={() => void submitCorrection()}>{feedbackLoading ? <Loader2 className="spin" /> : <PencilLine />}提交修正并加入学习记录</button>
                    <button className="ghost-btn" onClick={() => setCorrectionOpen(false)}>取消</button>
                  </div>
                </article>
              )}
              <div className="recognition-actions">
                <button className="ghost-btn" onClick={speak}><Volume2 />朗读中文科普</button>
                <button className="primary-btn" disabled={saving || Boolean(savedRecord || object.discovery_id)} onClick={() => void saveObservation()}>
                  {savedRecord || object.discovery_id ? <CheckCircle2 /> : <Save />}{savedRecord || object.discovery_id ? '已保存为观察记录' : saving ? '正在保存…' : '确认并保存观察'}
                </button>
                {object.species_id && <button className="ghost-btn" onClick={() => onOpenSpecies?.(object.species_id!)}><Sparkles />打开内置图鉴</button>}
                {!feedbackSent ? (
                  <>
                    <button className="ghost-btn" disabled={feedbackLoading} onClick={() => void feedback(true)}><CheckCircle2 />识别正确</button>
                    <button className="ghost-btn" disabled={feedbackLoading} onClick={() => setCorrectionOpen(true)}><HelpCircle />我要修正</button>
                  </>
                ) : <span className="feedback-thanks">感谢反馈，已加入模型改进数据和识别记录</span>}
              </div>
              <div className="location-hint"><MapPin size={16} /><span>低置信度、幼体、局部照片和近似物种仍建议补拍或人工复核；珍稀物种不要公开精确位置。</span></div>
            </div>
          )}

          {tab === 'ask' && (
            <div className="qa-panel">
              <div className="qa-context"><MessageCircle /><div><strong>围绕当前识别结果继续提问</strong><span>会结合当前识别结果、用户提示和观察记录回答。</span></div></div>
              <div className="qa-messages">
                {messages.length === 0 && <div className="suggestion-grid">{['为什么会这样识别？', '怎样拍摄能提高准确率？', object.behavior ? '这个行为是否正常？' : '它和相似物种怎么区分？'].map((item) => <button key={item} onClick={() => void ask(item)}>{item}</button>)}</div>}
                {messages.map((item, index) => <div key={index} className={`qa-message ${item.role}`}>{item.content}</div>)}
                {loading && <div className="qa-message assistant typing">正在结合识别目标、观察数据和科普资料分析…</div>}
              </div>
              <div className="qa-input"><input value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void ask()} placeholder={`继续问问“${title}”…`} /><button onClick={() => void ask()}><Send /></button></div>
            </div>
          )}

          {tab === 'share' && (
            <div className="share-discovery-panel">
              {(imageUrl || savedRecord?.image_url) && <img src={imageUrl || savedRecord?.image_url} alt={title} />}
              <label className="field-label">观察地点<input value={observationAddress} onChange={(event) => setObservationAddress(event.target.value)} placeholder="可选：填写城市、公园或保护区" /></label>
              <textarea value={shareText} onChange={(event) => setShareText(event.target.value)} maxLength={2000} />
              <div className="share-tags"><span>#{title}</span><span>#自然观察</span><span>#识境</span></div>
              <button className="primary-btn full" onClick={() => void share()} disabled={shared}>{shared ? '已发布到自然社区' : '保存记录并发布发现'}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
