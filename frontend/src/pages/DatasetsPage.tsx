import { useEffect, useState } from 'react'
import { Database, ExternalLink, FileCheck2, HardDrive, Layers3, ShieldCheck } from 'lucide-react'
import { api } from '../api/client'

interface DatasetInfo {
  id: string
  name: string
  domain: string
  scale: string
  license: string
  access: string
  usage: string
  homepage: string
  bundled: boolean
}

export default function DatasetsPage() {
  const [items, setItems] = useState<DatasetInfo[]>([])
  useEffect(() => { api<DatasetInfo[]>('/api/system/datasets').then(setItems) }, [])
  return <div className="page-stack">
    <div className="page-intro"><div><span className="eyebrow">DATASET FACTORY</span><h2>大规模数据集与训练准备</h2><p>统一管理动植物、动物行为、自然现象和人工纠错数据；保留来源、许可、规模和用途。</p></div></div>
    <div className="dataset-grid">{items.map(item => <article className="dataset-card" key={item.id}>
      <div><Database/><span>{item.bundled ? '本地回流' : '官方外部数据'}</span></div>
      <h3>{item.name}</h3><strong>{item.scale}</strong><p>{item.usage}</p><small>{item.domain} · {item.access}</small>
      <div className="dataset-foot"><ShieldCheck/>{item.license}</div>
      {item.homepage && !item.homepage.startsWith('local://') && <a href={item.homepage} target="_blank" rel="noreferrer" className="text-link">查看数据源<ExternalLink size={14}/></a>}
    </article>)}</div>
    <section className="panel"><div className="panel-head"><div><span className="eyebrow">PIPELINE</span><h3>数据工程流水线</h3></div><Layers3/></div><div className="pipeline-steps">{['许可登记','下载元数据','按类别抽样','损坏与重复检查','分类学统一','按相机/观察分组','训练评估','ONNX部署与纠错回流'].map((x,i)=><div key={x}><span>{i+1}</span><strong>{x}</strong></div>)}</div></section>
    <section className="panel storage-panel"><HardDrive/><div><strong>源码包不直接携带数百GB训练数据</strong><p>项目提供iNaturalist、WCS/SWG、Pl@ntNet、Animal Kingdom、MammalNet、D-Fire和自然现象数据的准备脚本。首轮建议500类、15万～60万张；GPU充足时扩展到1000类。</p></div><FileCheck2/></section>
  </div>
}
