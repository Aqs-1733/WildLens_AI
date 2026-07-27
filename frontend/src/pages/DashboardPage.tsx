import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { AlertTriangle, ArrowRight, Bird, BookOpenCheck, Camera, CircleDot, Film, Leaf, ShieldAlert, Sparkles, UploadCloud } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import StatCard from '../components/StatCard'
import { categoryNameZh } from '../utils/taxonNames'

interface DashboardData { stats: Record<string, number>; category_distribution: {name:string;value:number}[]; latest_jobs: any[]; latest_events: any[] }
const excludedCategories = new Set(['unknown', 'person', 'vehicle', 'human', '未确定目标', '未分类', '人物', '车辆'])

export default function DashboardPage() {
 const [data,setData]=useState<DashboardData|null>(null); const chartRef=useRef<HTMLDivElement>(null)
 useEffect(()=>{ api<DashboardData>('/api/dashboard').then(setData) },[])
 const distribution=useMemo(()=>data?.category_distribution
  .filter(i=>!excludedCategories.has(String(i.name).toLowerCase())&&!excludedCategories.has(categoryNameZh(i.name)))
  .map(i=>({name:categoryNameZh(i.name),value:i.value}))||[],[data])
 useEffect(()=>{ if(!chartRef.current||!data)return; const chart=echarts.init(chartRef.current); chart.setOption({tooltip:{trigger:'item'},legend:{bottom:0,textStyle:{color:'#89a89e'}},series:[{type:'pie',radius:['55%','78%'],center:['50%','43%'],label:{show:false},itemStyle:{borderColor:'#0d1d18',borderWidth:4},data:distribution.length?distribution:[{name:'暂无数据',value:1,itemStyle:{color:'#253c34'}}]}]}); const resize=()=>chart.resize(); window.addEventListener('resize',resize); return()=>{window.removeEventListener('resize',resize);chart.dispose()}},[data,distribution])
 if(!data)return <div className="page-loader">正在加载生态态势…</div>
 const s=data.stats
 return <div className="page-stack">
  <div className="hero-banner"><div><span className="hero-pill"><CircleDot size={14}/>多模态自然识别在线</span><h2>拍一下，认识眼前的生命与自然。</h2><p>拍照或上传图片，自动标注动物、植物和自然现象；动物结果会同步显示行为判断。</p><div className="hero-actions"><Link className="primary-btn" to="/identify"><Camera size={17}/>拍照识别</Link><Link className="ghost-btn" to="/video"><UploadCloud size={17}/>分析自然视频</Link><Link className="ghost-btn" to="/collection"><Sparkles size={17}/>我的观察收集册</Link></div></div><div className="hero-orbit"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><Leaf size={62}/><span>SHIJING VISION</span></div></div>
  <div className="stat-grid"><StatCard label="分析任务" value={s.analysis_jobs||0} hint="视频与示例任务" icon={Film}/><StatCard label="识别目标" value={s.detections||0} hint="时序检测记录" icon={Bird} tone="orange"/><StatCard label="物种知识库" value={s.species_total||0} hint="动物与植物条目" icon={BookOpenCheck} tone="blue"/><StatCard label="待处理预警" value={s.pending_alerts||0} hint="环保监管工作台" icon={ShieldAlert} tone="red"/></div>
  <div className="dashboard-grid"><section className="panel panel-wide"><div className="panel-head"><div><span className="eyebrow">RECENT ANALYSIS</span><h3>最近分析任务</h3></div><Link to="/jobs" className="text-link">查看全部<ArrowRight size={16}/></Link></div><div className="job-list">{data.latest_jobs.map(job=><div className="job-row" key={job.id}><div className="job-icon"><Film/></div><div className="job-main"><strong>{job.filename}</strong><span>{new Date(job.created_at).toLocaleString()}</span></div><div className={`status-badge status-${job.status}`}>{job.status==='completed'?'分析完成':job.status}</div><div className="mini-progress"><i style={{width:`${job.progress}%`}}/></div></div>)}</div></section>
   <section className="panel"><div className="panel-head"><div><span className="eyebrow">BIODIVERSITY</span><h3>目标类别分布</h3></div></div><div className="chart-box" ref={chartRef}/></section>
  </div>
  <div className="dashboard-grid"><section className="panel"><div className="panel-head"><div><span className="eyebrow">MY JOURNEY</span><h3>本周探索进度</h3></div></div><div className="journey-card"><div className="level-ring"><strong>Lv.{s.level}</strong><span>{s.points} EXP</span></div><div className="journey-copy"><h4>已经点亮 {s.collection_count} 个物种</h4><p>累计获得 <b>{s.stars}</b> 颗生态星。只有确认保存的真实观察才会增加物种记录与发现次数。</p><Link to="/learning" className="text-link">继续学习<ArrowRight size={16}/></Link></div></div></section>
   <section className="panel panel-wide"><div className="panel-head"><div><span className="eyebrow">RISK CENTER</span><h3>最新环保事件</h3></div><Link to="/alerts" className="text-link">进入预警中心<ArrowRight size={16}/></Link></div><div className="event-cards">{data.latest_events.length?data.latest_events.map(event=><div className={`event-card severity-${event.severity}`} key={event.id}><AlertTriangle/><div><strong>{event.title}</strong><span>{new Date(event.created_at).toLocaleString()} · {event.status}</span></div></div>):<div className="empty-state">暂无新增风险事件</div>}</div></section>
  </div>
 </div>
}
