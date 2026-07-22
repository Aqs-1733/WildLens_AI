import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ImagePlus, MessageCirclePlus, Search, Send, Sparkles } from 'lucide-react'
import { api, mediaUrl } from '../api/client'
import { useAuth } from '../context/AuthContext'
import type { Species } from '../types'

type Conversation = { id: number; title: string; species_id?: number | null; created_at: string; last_message_at?: string | null }
type Message = { id: number; role: string; content: string; created_at: string }

const QA_START_NEW_KEY = 'wildlens_qa_start_new'
const QA_ACTIVE_PREFIX = 'wildlens_qa_active_conversation_'

export default function QAHubPage() {
  const { user } = useAuth()
  const fileRef = useRef<HTMLInputElement>(null)
  const [species, setSpecies] = useState<Species[]>([])
  const [speciesId, setSpeciesId] = useState('')
  const [question, setQuestion] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversation, setConversation] = useState<number>()
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyReady, setHistoryReady] = useState(false)

  const activeConversationKey = user ? `${QA_ACTIVE_PREFIX}${user.id}` : ''

  const loadConversations = useCallback(async () => {
    const items = await api<Conversation[]>('/api/qa/conversations')
    setConversations(items)
    return items
  }, [])

  useEffect(() => { void api<Species[]>('/api/species').then(setSpecies) }, [])

  useEffect(() => {
    if (!user || !activeConversationKey) return
    let cancelled = false
    setHistoryReady(false)
    setConversation(undefined)
    setMessages([])
    void loadConversations()
      .then((items) => {
        if (cancelled) return
        const startNew = localStorage.getItem(QA_START_NEW_KEY) === '1'
        if (startNew) {
          localStorage.removeItem(QA_START_NEW_KEY)
          localStorage.removeItem(activeConversationKey)
          return
        }
        const savedId = Number(localStorage.getItem(activeConversationKey) || '')
        if (savedId && items.some((item) => item.id === savedId)) setConversation(savedId)
      })
      .finally(() => {
        if (!cancelled) setHistoryReady(true)
      })
    return () => { cancelled = true }
  }, [activeConversationKey, loadConversations, user])

  useEffect(() => {
    if (!historyReady || !activeConversationKey) return
    if (conversation) localStorage.setItem(activeConversationKey, String(conversation))
    else localStorage.removeItem(activeConversationKey)
  }, [activeConversationKey, conversation, historyReady])

  useEffect(() => {
    if (!conversation) { setMessages([]); return }
    void api<Message[]>(`/api/qa/conversations/${conversation}/messages`).then(setMessages)
  }, [conversation])

  const filteredConversations = useMemo(() => conversations.filter((item) => !query || item.title.toLowerCase().includes(query.toLowerCase())), [conversations, query])

  const startNew = async () => {
    const item = await api<Conversation>('/api/qa/conversations', { method: 'POST' })
    setConversation(item.id)
    setMessages([])
    await loadConversations()
  }

  const uploadImage = async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const result = await api<{ image_url: string }>('/api/qa/attachments', { method: 'POST', body: form })
    setImageUrl(result.image_url)
  }

  const ask = async (preset?: string) => {
    const text = (preset || question).trim()
    if (!text && !imageUrl) return
    const optimistic = { id: Date.now(), role: 'user', content: imageUrl ? `${text}\n\n[图片附件] ${imageUrl}` : text, created_at: new Date().toISOString() }
    setMessages((current) => [...current, optimistic])
    setQuestion('')
    setLoading(true)
    try {
      const result = await api<{ answer: string; conversation_id: number; mode: string; fallback_reason?: string | null }>('/api/qa/ask', {
        method: 'POST',
        body: JSON.stringify({ question: text || '请结合这张图片进行自然科普分析', image_url: imageUrl, species_id: speciesId ? Number(speciesId) : null, conversation_id: conversation }),
      })
      setConversation(result.conversation_id)
      setImageUrl('')
      await Promise.all([
        api<Message[]>(`/api/qa/conversations/${result.conversation_id}/messages`).then(setMessages),
        loadConversations(),
      ])
    } catch (error) {
      setMessages((current) => [...current, { id: Date.now() + 1, role: 'assistant', content: error instanceof Error ? error.message : '科普服务暂时不可用，请稍后重试', created_at: new Date().toISOString() }])
    } finally { setLoading(false) }
  }

  return <div className="page-stack">
    <div className="page-intro"><div><span className="eyebrow">NATURE SCIENCE Q&A</span><h2>智能科普与观察问答</h2><p>支持文字和图片附件；聊天记录会自动保存标题，切换页面后可以继续。</p></div><select className="species-select" value={speciesId} onChange={(event) => setSpeciesId(event.target.value)}><option value="">不限定物种，直接问自然问题</option>{species.map((item) => <option key={item.id} value={item.id}>{item.common_name} · {item.scientific_name}</option>)}</select></div>
    <section className="qa-hub qa-hub-history">
      <aside className="qa-hub-side"><div className="ai-orb"><Sparkles /></div><h3>识境自然问答</h3><button className="primary-btn full" onClick={() => void startNew()}><MessageCirclePlus/>新建聊天</button><label className="search-box qa-history-search"><Search/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="查找历史记录"/></label><div className="qa-history-list">{filteredConversations.map((item) => <button key={item.id} className={conversation === item.id ? 'active' : ''} onClick={() => setConversation(item.id)}><strong>{item.title}</strong><span>{new Date(item.last_message_at || item.created_at).toLocaleString('zh-CN')}</span></button>)}</div><div className="quick-questions">{['怎样拍摄更利于物种识别？', '为什么动物会迁徙？', '雾和霾怎么区分？'].map((item) => <button key={item} onClick={() => void ask(item)}><Sparkles />{item}</button>)}</div></aside>
      <div className="qa-hub-main"><div className="qa-hub-messages">{messages.length === 0 && <div className="qa-bubble assistant">你好，我是识境自然科普问答。你可以发文字，也可以附一张图片让我结合自然观察语境解释。</div>}{messages.map((message) => <div className={`qa-bubble ${message.role}`} key={message.id}>{message.content.includes('[图片附件]') ? <MessageWithImage content={message.content}/> : message.content}</div>)}{loading && <div className="qa-bubble assistant typing">正在分析问题、图片附件和可选观察上下文…</div>}</div><div className="qa-attachment-row">{imageUrl && <span>已附图：{imageUrl.split('/').pop()}</span>}<input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(event) => event.target.files?.[0] && void uploadImage(event.target.files[0])}/><button className="ghost-btn" onClick={() => fileRef.current?.click()}><ImagePlus/>添加图片</button></div><div className="qa-hub-input"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void ask() } }} placeholder="输入任何自然观察或科普问题…" /><button onClick={() => void ask()}><Send /></button></div></div>
    </section>
  </div>
}

function MessageWithImage({ content }: { content: string }) {
  const [text, rawUrl = ''] = content.split('[图片附件]')
  const url = rawUrl.trim()
  return <><span>{text.trim()}</span>{url && <img className="qa-message-image" src={mediaUrl(url)} alt="聊天图片附件"/>}</>
}
