import { useState } from 'react'
import type { CSSProperties } from 'react'
import { BookOpen, CloudFog, CloudLightning, CloudRain, MessageCircle, MoonStar, Rainbow, Send, Snowflake, Sparkles, Sun, Wind } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'

const phenomena = [
  { name: '彩虹', icon: Rainbow, tone: '#65D6FF', desc: '阳光经过空气中的水滴折射、反射和色散后形成。', question: '彩虹为什么通常是弧形的？' },
  { name: '雾', icon: CloudFog, tone: '#A8C6D2', desc: '近地面空气中的水汽凝结成大量微小水滴，使能见度下降。', question: '雾和云有什么区别？' },
  { name: '雷暴', icon: CloudLightning, tone: '#A87CFF', desc: '强对流云团中电荷分离并放电，常伴随短时强降水和阵风。', question: '看到积雨云时应该注意什么？' },
  { name: '降雨', icon: CloudRain, tone: '#55B8FF', desc: '云中水滴或冰晶增长到一定程度后落向地面。', question: '为什么有时云很黑却不下雨？' },
  { name: '霜雪', icon: Snowflake, tone: '#D7F3FF', desc: '低温条件下水汽凝华或冰晶降落形成不同的固态水现象。', question: '霜和雪的形成过程一样吗？' },
  { name: '风', icon: Wind, tone: '#78E3C1', desc: '空气因气压差产生水平运动，并受到地形与地球自转影响。', question: '树林中的风为什么忽强忽弱？' },
  { name: '日晕', icon: Sun, tone: '#FFD36B', desc: '高空冰晶对太阳光折射或反射，形成环状或弧状光学现象。', question: '日晕一定预示要下雨吗？' },
  { name: '极光', icon: MoonStar, tone: '#69FFC0', desc: '太阳风带电粒子进入高层大气，与气体碰撞发光。', question: '为什么极光主要出现在高纬度？' },
]

export default function NatureClassroomPage() {
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)

  const ask = async (preset?: string) => {
    const text = (preset ?? question).trim()
    if (!text) return
    setMessages((items) => [...items, { role: 'user', content: text }])
    setQuestion('')
    setLoading(true)
    try {
      const result = await api<{ answer: string }>('/api/qa/ask', { method: 'POST', body: JSON.stringify({ question: text }) })
      setMessages((items) => [...items, { role: 'assistant', content: result.answer }])
    } catch (error) {
      setMessages((items) => [...items, { role: 'assistant', content: error instanceof Error ? error.message : '回答失败' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-stack classroom-page">
      <section className="page-intro"><div><span className="eyebrow">NATURAL PHENOMENA</span><h2>自然现象</h2></div></section>
      <div className="mode-switch"><Link to="/species"><BookOpen />物种科普</Link><Link to="/collection"><Sparkles />我的收藏</Link><Link className="active" to="/classroom"><CloudFog />自然现象</Link></div>

      <section className="phenomena-grid">
        {phenomena.map(({ name, icon: Icon, tone, desc, question: preset }) => (
          <article key={name} className="phenomenon-card" style={{ '--phenomenon-tone': tone } as CSSProperties}>
            <div><Icon /></div><h3>{name}</h3><p>{desc}</p><button onClick={() => void ask(preset)}>继续了解：{preset}</button>
          </article>
        ))}
      </section>

      <section className="classroom-chat panel">
        <div className="classroom-chat-head"><div className="ai-orb mini"><MessageCircle /></div><div><h3>自然问答</h3></div></div>
        <div className="qa-hub-messages classroom-messages">
          {messages.length === 0 && <div className="empty-chat">可以直接提问自然现象的形成原因、观察条件和安全注意事项。</div>}
          {messages.map((item, index) => <div key={index} className={`qa-bubble ${item.role}`}>{item.content}</div>)}
          {loading && <div className="qa-bubble assistant">正在分析…</div>}
        </div>
        <div className="qa-hub-input"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="输入自然现象问题" /><button className="primary-btn" onClick={() => void ask()}><Send /></button></div>
      </section>
    </div>
  )
}
