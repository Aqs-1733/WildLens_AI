import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { Activity, MapPinned, Repeat2, Sparkles } from 'lucide-react'
import { api } from '../api/client'

type Item = { name: string; value: number }
type Analytics = {
  summary: { observations: number; unique_taxa: number; located: number; repeat_observations: number }
  species_counts: Item[]
  category_counts: Item[]
  behavior_counts: Item[]
  phenomenon_counts: Item[]
  timeline: { date: string; value: number }[]
}

const categoryNames: Record<string, string> = {
  mammal: '哺乳动物', bird: '鸟类', reptile: '爬行动物', amphibian: '两栖动物', fish: '鱼类',
  insect: '昆虫', arachnid: '蛛形动物', mollusk: '软体动物', crustacean: '甲壳动物', invertebrate: '其他无脊椎动物',
  plant: '植物', angiosperm: '被子植物', gymnosperm: '裸子植物', fern: '蕨类', moss: '苔藓', algae: '藻类',
  fungus: '真菌', lichen: '地衣', phenomenon: '自然现象', fire: '火焰', smoke: '烟雾', unknown: '待确认',
}

function EmptyChart({ text }: { text: string }) { return <div className="chart-empty"><Sparkles/><span>{text}</span></div> }

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null)
  const [error, setError] = useState('')
  const speciesRef = useRef<HTMLDivElement>(null)
  const categoryRef = useRef<HTMLDivElement>(null)
  const timelineRef = useRef<HTMLDivElement>(null)

  useEffect(() => { void api<Analytics>('/api/identify/observations/analytics').then(setData).catch((err: Error) => setError(err.message)) }, [])

  useEffect(() => {
    if (!data) return
    const charts: echarts.ECharts[] = []
    if (speciesRef.current && data.species_counts.length) {
      const chart = echarts.init(speciesRef.current)
      chart.setOption({
        grid: { left: 100, right: 24, top: 20, bottom: 28 },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'value', axisLabel: { color: '#8ca9a0' }, splitLine: { lineStyle: { color: '#1a332a' } } },
        yAxis: { type: 'category', inverse: true, data: data.species_counts.map((item) => item.name), axisLabel: { color: '#b4d0c6' }, axisLine: { lineStyle: { color: '#27473c' } } },
        series: [{ type: 'bar', data: data.species_counts.map((item) => item.value), itemStyle: { borderRadius: [0, 7, 7, 0], color: '#38f2ad' } }],
      })
      charts.push(chart)
    }
    if (categoryRef.current && data.category_counts.length) {
      const chart = echarts.init(categoryRef.current)
      chart.setOption({
        tooltip: { trigger: 'item' },
        legend: { bottom: 0, textStyle: { color: '#8ca9a0' } },
        series: [{ type: 'pie', radius: ['45%', '70%'], center: ['50%', '43%'], label: { color: '#b8d3ca' }, itemStyle: { borderColor: '#0d1d18', borderWidth: 3 }, data: data.category_counts.map((item) => ({ name: categoryNames[item.name] || item.name, value: item.value })) }],
      })
      charts.push(chart)
    }
    if (timelineRef.current && data.timeline.length) {
      const chart = echarts.init(timelineRef.current)
      chart.setOption({
        grid: { left: 45, right: 18, top: 25, bottom: 38 },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: data.timeline.map((item) => item.date.slice(5)), axisLabel: { color: '#8ca9a0' }, axisLine: { lineStyle: { color: '#27473c' } } },
        yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#8ca9a0' }, splitLine: { lineStyle: { color: '#1a332a' } } },
        series: [{ type: 'line', smooth: true, data: data.timeline.map((item) => item.value), lineStyle: { color: '#55b8ff', width: 3 }, itemStyle: { color: '#55b8ff' }, areaStyle: { color: 'rgba(85,184,255,.12)' } }],
      })
      charts.push(chart)
    }
    const resize = () => charts.forEach((chart) => chart.resize())
    window.addEventListener('resize', resize)
    return () => { window.removeEventListener('resize', resize); charts.forEach((chart) => chart.dispose()) }
  }, [data])

  if (error) return <div className="inline-error">{error}</div>
  if (!data) return <div className="page-loader">正在汇总真实观察记录…</div>
  const summary = data.summary
  return <div className="page-stack">
    <div className="page-intro"><div><span className="eyebrow">MY OBSERVATION ANALYTICS</span><h2>真实观察数据分析</h2><p>所有图表只统计你确认保存的发现，不再使用预设物种数量或模拟完成度。</p></div></div>
    <div className="analytics-cards"><div><Activity/><strong>{summary.observations}</strong><span>观察记录</span></div><div><Sparkles/><strong>{summary.unique_taxa}</strong><span>独立物种/现象</span></div><div><Repeat2/><strong>{summary.repeat_observations}</strong><span>重复发现</span></div><div><MapPinned/><strong>{summary.located}</strong><span>带位置记录</span></div></div>
    <div className="dashboard-grid"><section className="panel panel-wide"><h3>发现次数最多的物种</h3>{data.species_counts.length ? <div className="chart-large" ref={speciesRef}/> : <EmptyChart text="保存观察后生成物种频次图"/>}</section><section className="panel"><h3>生物类群分布</h3>{data.category_counts.length ? <div className="chart-large" ref={categoryRef}/> : <EmptyChart text="暂无已确认分类"/>}</section></div>
    <section className="panel"><h3>观察时间趋势</h3>{data.timeline.length ? <div className="chart-large" ref={timelineRef}/> : <EmptyChart text="暂无观察时间序列"/>}</section>
    <div className="dashboard-grid"><section className="panel"><h3>动物行为记录</h3><div className="tag-cloud">{data.behavior_counts.length ? data.behavior_counts.map((item) => <span key={item.name}>{item.name} · {item.value}</span>) : <small>尚未保存动物行为观察</small>}</div></section><section className="panel"><h3>自然现象记录</h3><div className="tag-cloud">{data.phenomenon_counts.length ? data.phenomenon_counts.map((item) => <span key={item.name}>{item.name} · {item.value}</span>) : <small>尚未保存自然现象观察</small>}</div></section></div>
  </div>
}
