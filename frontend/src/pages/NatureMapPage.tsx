import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { api, mediaUrl } from '../api/client'
import { Bird, CloudSun, Leaf, LocateFixed, MapPinned, ShieldCheck } from 'lucide-react'

type LayerKey = 'animal' | 'plant' | 'phenomenon'
type ObservationPoint = {
  id: number
  title: string
  scientific_name: string
  category: string
  image_url: string
  confidence: number
  behavior: string
  phenomenon: string
  observed_at: string
  latitude: number | null
  longitude: number | null
  province: string
  city: string
  district: string
  privacy_level: string
  is_first: boolean
}

const layerMeta: Record<LayerKey, { label: string; icon: typeof Bird; color: string; description: string }> = {
  animal: { label: '动物足迹', icon: Bird, color: '#ffb34d', description: '动物发现、行为与重复观察次数' },
  plant: { label: '植物与真菌', icon: Leaf, color: '#38f2ad', description: '植物、真菌、地衣及物候观察' },
  phenomenon: { label: '自然现象', icon: CloudSun, color: '#55b8ff', description: '彩虹、雾、雪、雷电、云系与烟火现象' },
}

function formatPlace(item: ObservationPoint) {
  return [item.province, item.city, item.district].filter(Boolean).join(' · ') || '未填写地点'
}

export default function NatureMapPage() {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)
  const [layer, setLayer] = useState<LayerKey>('animal')
  const [points, setPoints] = useState<ObservationPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<ObservationPoint | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    api<ObservationPoint[]>(`/api/identify/observations/map?layer=${layer}`)
      .then((rows) => { if (active) setPoints(rows.filter((row) => row.latitude != null && row.longitude != null)) })
      .catch((err: Error) => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [layer])

  const aggregates = useMemo(() => {
    const map = new Map<string, ObservationPoint & { count: number }>()
    for (const point of points) {
      const key = `${point.title}|${Number(point.longitude).toFixed(2)}|${Number(point.latitude).toFixed(2)}`
      const current = map.get(key)
      if (current) current.count += 1
      else map.set(key, { ...point, count: 1 })
    }
    return [...map.values()]
  }, [points])

  useEffect(() => {
    let cancelled = false
    async function render() {
      if (!chartRef.current) return
      try {
        const response = await fetch('/maps/china_adm0.geojson')
        if (!response.ok) throw new Error('中国地图边界文件加载失败')
        const geojson = await response.json()
        if (cancelled || !chartRef.current) return
        echarts.registerMap('wildlens-china', geojson)
        const chart = chartInstance.current || echarts.init(chartRef.current)
        chartInstance.current = chart
        const meta = layerMeta[layer]
        const data = aggregates.map((item) => ({
          name: item.title,
          value: [Number(item.longitude), Number(item.latitude), item.count],
          item,
          symbolSize: Math.min(14, 5 + Math.log2(item.count + 1) * 2.4),
          itemStyle: { color: item.is_first ? '#ffe278' : meta.color, borderColor: '#06130f', borderWidth: 2 },
        }))
        chart.setOption({
          backgroundColor: 'transparent',
          tooltip: {
            trigger: 'item',
            backgroundColor: '#0d1d18',
            borderColor: '#2d5e4c',
            textStyle: { color: '#e8f7f1' },
            formatter: (params: any) => {
              const item = params.data?.item as ObservationPoint | undefined
              if (!item) return params.name || ''
              return `<strong>${item.title}</strong><br/><em>${item.scientific_name || '待确认学名'}</em><br/>${formatPlace(item)}<br/>置信度 ${(item.confidence * 100).toFixed(1)}%${item.is_first ? '<br/>★ 首次发现' : ''}`
            },
          },
          geo: {
            map: 'wildlens-china',
            roam: true,
            scaleLimit: { min: 0.9, max: 12 },
            zoom: 1.08,
            label: { show: false },
            itemStyle: { areaColor: '#102920', borderColor: '#36705b', borderWidth: 1 },
            emphasis: { itemStyle: { areaColor: '#15392c' } },
          },
          series: [{
            type: 'effectScatter',
            coordinateSystem: 'geo',
            data,
            rippleEffect: { scale: 2.1, brushType: 'stroke' },
            showEffectOn: 'emphasis',
          }],
        }, true)
        chart.off('click')
        chart.on('click', (params: any) => {
          const item = params.data?.item as ObservationPoint | undefined
          if (item) setSelected(item)
        })
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '地图加载失败')
      }
    }
    void render()
    const onResize = () => chartInstance.current?.resize()
    window.addEventListener('resize', onResize)
    return () => { cancelled = true; window.removeEventListener('resize', onResize) }
  }, [aggregates, layer])

  useEffect(() => () => { chartInstance.current?.dispose(); chartInstance.current = null }, [])

  const meta = layerMeta[layer]
  return <div className="page-stack nature-map-page">
    <div className="page-intro">
      <div><span className="eyebrow">MY NATURE FOOTPRINT</span><h2>我的自然足迹</h2><p>只展示你确认保存的真实观察。重复发现会保留为独立记录，首次发现以金色星标显示。</p></div>
      <div className="privacy-chip"><ShieldCheck size={17}/>珍稀物种公开分享时自动模糊精确坐标</div>
    </div>
    <div className="map-layer-tabs">
      {(Object.keys(layerMeta) as LayerKey[]).map((key) => { const item = layerMeta[key]; const Icon = item.icon; return <button key={key} className={layer === key ? 'active' : ''} onClick={() => { setLayer(key); setSelected(null) }}><Icon size={19}/><span><strong>{item.label}</strong><small>{item.description}</small></span></button> })}
    </div>
    <section className="panel nature-map-panel">
      <div className="map-panel-head"><div><h3><MapPinned size={19}/>{meta.label}</h3><p>{loading ? '正在载入观察点…' : `共 ${points.length} 条带位置记录，${aggregates.length} 个地图聚合点`}</p></div><div className="map-legend"><span><i className="dot first"/>首次发现</span><span><i className="dot repeat" style={{ background: meta.color }}/>重复观察</span></div></div>
      {error && <div className="inline-error">{error}</div>}
      {!loading && !error && points.length === 0 && <div className="map-empty"><LocateFixed size={38}/><strong>还没有带位置的{meta.label}记录</strong><span>拍照识别后确认保存，并授权GPS或手动填写地点，观察点就会出现在这里。</span></div>}
      <div className="nature-map-canvas" ref={chartRef}/>
    </section>
    {selected && <section className="panel map-selection-card">
      {selected.image_url ? <img src={mediaUrl(selected.image_url)} alt={selected.title}/> : <div className="selection-placeholder"><MapPinned/></div>}
      <div><span className="eyebrow">OBSERVATION #{selected.id}</span><h3>{selected.title}</h3><em>{selected.scientific_name || '学名待确认'}</em><p>{formatPlace(selected)} · {new Date(selected.observed_at).toLocaleString('zh-CN')}</p><div className="selection-tags">{selected.is_first && <span>★ 首次发现</span>}{selected.behavior && <span>行为：{selected.behavior}</span>}{selected.phenomenon && <span>现象：{selected.phenomenon}</span>}<span>位置权限：{selected.privacy_level}</span></div></div>
    </section>}
    <p className="map-attribution">地图轮廓：Natural Earth 公共领域数据，仅用于自然观察分布展示，不作为测绘或行政边界依据。</p>
  </div>
}
