import { useEffect, useState } from 'react'
import { Download, FileBarChart, FileText } from 'lucide-react'
import { api, mediaUrl } from '../api/client'
import type { VideoJob } from '../types'

export default function ReportsPage(){
  const[jobs,setJobs]=useState<VideoJob[]>([]);useEffect(()=>{api<VideoJob[]>('/api/videos/jobs').then(setJobs)},[])
  const download=(id:number)=>{const token=localStorage.getItem('wildlens_token');fetch(mediaUrl(`/api/reports/jobs/${id}`),{headers:token?{Authorization:`Bearer ${token}`}:{}}).then(async r=>{if(!r.ok)throw new Error('报告生成失败');const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`shijing-report-${id}.pdf`;a.click();URL.revokeObjectURL(url)}).catch(e=>alert(e instanceof Error?e.message:'报告生成失败'))}
  return <div className="page-stack"><div className="page-intro"><div><span className="eyebrow">AI REPORT CENTER</span><h2>报告中心</h2><p>从真实分析任务生成单视频PDF，包含检测、物种、风险与边界说明。</p></div></div><div className="report-grid">{jobs.filter(j=>j.status==='completed').map(job=><article className="report-card" key={job.id}><div className="report-cover"><FileBarChart/><span>识境</span></div><div><span className="eyebrow">任务 #{job.id}</span><h3>{job.media.filename}</h3><p>检测记录 {String(job.summary.detections??0)} 条 · 模式 {job.mode}</p><div className="report-actions"><button onClick={()=>void download(job.id)}><Download/>生成并导出 PDF</button></div></div></article>)}</div>{!jobs.some(j=>j.status==='completed')&&<section className="panel empty-state"><FileText/>暂无已完成任务，请先分析示例视频或上传视频。</section>}</div>
}
