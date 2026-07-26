import { useState } from 'react'
import { BookOpen, CloudFog, CloudLightning, CloudRain, Footprints, MessageCircle, MoonStar, Rainbow, Send, Snowflake, Sparkles, Sun, Wind } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'

const phenomena = [
  { name: '彩虹', icon: Rainbow, tone: '#65D6FF', desc: '阳光经过空气中的水滴发生折射、反射和色散后形成。', question: '彩虹为什么通常是弧形的？' },
  { name: '雾', icon: CloudFog, tone: '#A8C6D2', desc: '近地面空气中的水汽凝结成大量微小水滴，使能见度下降。', question: '雾和云有什么区别？' },
  { name: '雷暴', icon: CloudLightning, tone: '#A87CFF', desc: '强对流云团中电荷分离并放电，常伴随短时强降水和阵风。', question: '看到积雨云时应该注意什么？' },
  { name: '降雨', icon: CloudRain, tone: '#55B8FF', desc: '云中水滴或冰晶增长到一定程度后落向地面。', question: '为什么有时云很黑却不下雨？' },
  { name: '霜雪', icon: Snowflake, tone: '#D7F3FF', desc: '低温条件下水汽凝华或冰晶降落形成不同的固态水现象。', question: '霜和雪的形成过程一样吗？' },
  { name: '风', icon: Wind, tone: '#78E3C1', desc: '空气因气压差产生水平运动，并受到地形与地球自转影响。', question: '树林中的风为什么忽强忽弱？' },
  { name: '日晕', icon: Sun, tone: '#FFD36B', desc: '高空冰晶对太阳光折射或反射，形成环状或弧状光学现象。', question: '日晕一定预示要下雨吗？' },
  { name: '极光', icon: MoonStar, tone: '#69FFC0', desc: '太阳风带电粒子进入高层大气，与气体碰撞发光。', question: '为什么极光主要出现在高纬度？' },
]

const behaviors = [
  { name: '觅食', desc: '动物寻找、获取和处理食物的行为。', clues: ['低头搜索', '啄食或撕咬', '反复移动到食物点'] },
  { name: '警戒', desc: '动物感知潜在威胁时提高注意并调整姿态。', clues: ['突然停止', '抬头转耳', '朝固定方向观察'] },
  { name: '梳理', desc: '清洁毛羽、去除寄生物或维持社会关系。', clues: ['舔毛或理羽', '同伴互相清理', '重复局部动作'] },
  { name: '求偶', desc: '为吸引配偶进行鸣叫、展示或舞蹈。', clues: ['夸张姿态', '特定鸣声', '围绕同类展示'] },
  { name: '迁徙', desc: '动物在季节性资源、繁殖或气候驱动下进行较长距离移动。', clues: ['群体定向移动', '季节重复', '跨区域出现'] },
  { name: '育幼', desc: '亲代照料幼体、喂食、防护与引导。', clues: ['成幼体紧邻', '喂食动作', '保护性站位'] },
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
      <section className="page-intro"><div><span className="eyebrow">PHENOMENA & BEHAVIOR</span><h2>自然现象与动物行为</h2><p>识别不仅要知道“是什么”，也要理解“为什么发生”和“动物正在做什么”。这里分成自然现象和动物行为两组线索。</p></div></section>
      <div className="mode-switch"><Link to="/species"><BookOpen/>物种百科</Link><Link to="/collection"><Sparkles/>我的收藏</Link><Link className="active" to="/classroom"><CloudFog/>现象与行为</Link></div>

      <section className="phenomena-grid">
        {phenomena.map(({ name, icon: Icon, tone, desc, question: preset }) => (
          <article key={name} className="phenomenon-card" style={{ '--phenomenon-tone': tone } as React.CSSProperties}>
            <div><Icon /></div><h3>{name}</h3><p>{desc}</p><button onClick={() => void ask(preset)}>继续了解：{preset}</button>
          </article>
        ))}
      </section>

      <section className="panel behavior-panel">
        <div className="panel-head"><div><span className="eyebrow">ANIMAL BEHAVIOR</span><h3>常见动物行为观察线索</h3></div><Footprints /></div>
        <div className="behavior-grid">{behaviors.map((item) => <article key={item.name}><h3>{item.name}</h3><p>{item.desc}</p><div>{item.clues.map((clue) => <span key={clue}>{clue}</span>)}</div><button className="text-link" onClick={() => void ask(`怎样从单张照片或短视频判断动物是否在${item.name}？`)}>继续提问</button></article>)}</div>
      </section>

      <section className="classroom-chat panel">
        <div className="classroom-chat-head"><div className="ai-orb mini"><MessageCircle /></div><div><h3>自然问答</h3><p>可以询问现象形成原因、行为判断依据、拍摄技巧和安全注意事项。</p></div></div>
        <div className="qa-hub-messages classroom-messages">
          {messages.length === 0 && <div className="empty-chat">点击上面的“继续了解”，或直接输入你在自然中遇到的问题。</div>}
          {messages.map((item, index) => <div key={index} className={`qa-bubble ${item.role}`}>{item.content}</div>)}
          {loading && <div className="qa-bubble assistant">正在检索自然知识库…</div>}
        </div>
        <div className="qa-hub-input"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="例如：这张照片里的鸟为什么张开翅膀晒太阳？" /><button className="primary-btn" onClick={() => void ask()}><Send /></button></div>
      </section>
    </div>
  )
}
