import { useEffect, useRef, useState } from 'react'
import type { ReactNode, RefObject } from 'react'
import * as echarts from 'echarts'
import { Activity, CloudSun, Leaf, MapPinned, PawPrint, Repeat2, Sparkles } from 'lucide-react'
import { api } from '../api/client'
import { categoryNameZh, cleanChineseDisplayName } from '../utils/taxonNames'

type Item = { name: string; value: number }
type Analytics = {
  summary: { observations: number; unique_taxa: number; located: number; repeat_observations: number }
  species_counts: Item[]
  category_counts: Item[]
  animal_counts: Item[]
  plant_counts: Item[]
  nature_counts: Item[]
  behavior_counts: Item[]
  phenomenon_counts: Item[]
  timeline: { date: string; value: number }[]
}

const chartColors = ['#55b8ff', '#38f2ad', '#ffd45a', '#ff9b45', '#a87cff', '#2fd5c4', '#ff6f8a']

function EmptyChart({ text }: { text: string }) {
  return <div className="chart-empty"><Sparkles /><span>{text}</span></div>
}

function readableItems(items: Item[]): Item[] {
  return items.map((item) => ({
    ...item,
    name: cleanChineseDisplayName(categoryNameZh(item.name), item.name),
  }))
}

function CategoryDonut({ title, icon, items, chartRef, empty }: { title: string; icon: ReactNode; items: Item[]; chartRef: RefObject<HTMLDivElement | null>; empty: string }) {
  const rows = readableItems(items)
  return (
    <section className="panel category-donut-card">
      <div className="panel-head"><div><span className="eyebrow">CATEGORY</span><h3>{title}</h3></div>{icon}</div>
      {rows.length ? <><div className="category-donut-chart" ref={chartRef} /><ul className="category-legend-list">{rows.map((item, index) => <li key={item.name}><i style={{ background: chartColors[index % chartColors.length] }} /><span>{item.name}</span><strong>{item.value}</strong></li>)}</ul></> : <EmptyChart text={empty} />}
    </section>
  )
}

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null)
  const [error, setError] = useState('')
  const speciesRef = useRef<HTMLDivElement>(null)
  const animalRef = useRef<HTMLDivElement>(null)
  const plantRef = useRef<HTMLDivElement>(null)
  const natureRef = useRef<HTMLDivElement>(null)
  const timelineRef = useRef<HTMLDivElement>(null)

  useEffect(() => { void api<Analytics>('/api/identify/observations/analytics').then(setData).catch((err: Error) => setError(err.message)) }, [])

  useEffect(() => {
    if (!data) return
    const charts: echarts.ECharts[] = []
    const mountDonut = (ref: RefObject<HTMLDivElement | null>, items: Item[]) => {
      const rows = readableItems(items)
      if (!ref.current || !rows.length) return
      const chart = echarts.init(ref.current)
      chart.setOption({
        color: chartColors,
        tooltip: { trigger: 'item', formatter: '{b}: {c} 条' },
        series: [{
          type: 'pie',
          radius: ['58%', '78%'],
          center: ['50%', '50%'],
          label: { show: false },
          labelLine: { show: false },
          itemStyle: { borderColor: '#0d1d18', borderWidth: 4 },
          data: rows,
        }],
      })
      charts.push(chart)
    }

    if (speciesRef.current && data.species_counts.length) {
      const chart = echarts.init(speciesRef.current)
      chart.setOption({
        grid: { left: 110, right: 24, top: 20, bottom: 28 },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'value', axisLabel: { color: '#8ca9a0' }, splitLine: { lineStyle: { color: '#1a332a' } } },
        yAxis: { type: 'category', inverse: true, data: data.species_counts.map((item) => cleanChineseDisplayName(item.name)), axisLabel: { color: '#b4d0c6' }, axisLine: { lineStyle: { color: '#27473c' } } },
        series: [{ type: 'bar', data: data.species_counts.map((item) => item.value), itemStyle: { borderRadius: [0, 7, 7, 0], color: '#38f2ad' } }],
      })
      charts.push(chart)
    }
    mountDonut(animalRef, data.animal_counts || [])
    mountDonut(plantRef, data.plant_counts || [])
    mountDonut(natureRef, data.nature_counts || [])
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

  return (
    <div className="page-stack">
      <div className="page-intro"><div><span className="eyebrow">MY OBSERVATION ANALYTICS</span><h2>真实观察数据分析</h2><p>图表只统计已保存且名称规范的观察记录，异常候选和乱码记录会被排除。</p></div></div>
      <div className="analytics-cards"><div><Activity /><strong>{summary.observations}</strong><span>观察记录</span></div><div><Sparkles /><strong>{summary.unique_taxa}</strong><span>独立物种/现象</span></div><div><Repeat2 /><strong>{summary.repeat_observations}</strong><span>重复发现</span></div><div><MapPinned /><strong>{summary.located}</strong><span>带位置记录</span></div></div>
      <section className="panel panel-wide"><h3>发现次数最多的物种</h3>{data.species_counts.length ? <div className="chart-large" ref={speciesRef} /> : <EmptyChart text="保存观察后生成物种频次图" />}</section>
      <div className="category-chart-grid">
        <CategoryDonut title="动物记录分布" icon={<PawPrint />} items={data.animal_counts || []} chartRef={animalRef} empty="暂无动物观察" />
        <CategoryDonut title="植物与真菌记录分布" icon={<Leaf />} items={data.plant_counts || []} chartRef={plantRef} empty="暂无植物或真菌观察" />
        <CategoryDonut title="自然现象记录分布" icon={<CloudSun />} items={data.nature_counts || []} chartRef={natureRef} empty="暂无自然现象观察" />
      </div>
      <section className="panel"><h3>观察时间趋势</h3>{data.timeline.length ? <div className="chart-large" ref={timelineRef} /> : <EmptyChart text="暂无观察时间序列" />}</section>
      <div className="dashboard-grid"><section className="panel"><h3>动物行为记录</h3><div className="tag-cloud">{data.behavior_counts.length ? data.behavior_counts.map((item) => <span key={item.name}>{item.name} · {item.value}</span>) : <small>尚未保存动物行为观察</small>}</div></section><section className="panel"><h3>自然现象记录</h3><div className="tag-cloud">{data.phenomenon_counts.length ? data.phenomenon_counts.map((item) => <span key={item.name}>{item.name} · {item.value}</span>) : <small>尚未保存自然现象观察</small>}</div></section></div>
    </div>
  )
}
