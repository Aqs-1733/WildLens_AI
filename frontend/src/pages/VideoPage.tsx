import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, FileVideo, LoaderCircle, Play, Settings2, UploadCloud } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, mediaUrl } from '../api/client'
import type { PhotoObject, VideoJob, VideoTrack } from '../types'
import RecognitionModal from '../components/RecognitionModal'
import VideoOverlay from '../components/VideoOverlay'

const activeStatuses = ['queued', 'preprocessing', 'extracting_frames', 'detecting', 'tracking', 'classifying', 'risk_analysis', 'rendering', 'processing']

export default function VideoPage() {
  const [jobs, setJobs] = useState<VideoJob[]>([])
  const [job, setJob] = useState<VideoJob | null>(null)
  const [tracks, setTracks] = useState<VideoTrack[]>([])
  const [selected, setSelected] = useState<VideoTrack | null>(null)
  const [currentTimeMs, setCurrentTimeMs] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [mode, setMode] = useState('standard')
  const [targets, setTargets] = useState({ animals: true, plants: true, people: true, fire: true })
  const [autoRepairing, setAutoRepairing] = useState(false)

  const loadJobs = useCallback(
    () => api<VideoJob[]>('/api/videos/jobs').then((items) => {
      setJobs(items)
      setJob((current) => current ?? items[0] ?? null)
    }),
    [],
  )

  useEffect(() => { void loadJobs() }, [loadJobs])

  useEffect(() => {
    if (!job || job.status !== 'completed') {
      setTracks([])
      return
    }
    void api<VideoTrack[]>(`/api/videos/jobs/${job.id}/tracks`).then(setTracks)
  }, [job])

  useEffect(() => {
    if (!job || !activeStatuses.includes(job.status)) return
    const timer = window.setInterval(async () => {
      const updated = await api<VideoJob>(`/api/videos/jobs/${job.id}`)
      setJob(updated)
      if (updated.status === 'completed' || updated.status === 'failed') {
        window.clearInterval(timer)
        await loadJobs()
      }
    }, 1800)
    return () => window.clearInterval(timer)
  }, [job, loadJobs])

  const upload = async () => {
    if (!file) return
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    form.append('mode', mode)
    form.append('targets', Object.entries(targets).filter(([, enabled]) => enabled).map(([key]) => key).join(','))
    try {
      const result = await api<{ job_id: number }>('/api/videos/upload', { method: 'POST', body: form })
      const created = await api<VideoJob>(`/api/videos/jobs/${result.job_id}`)
      setJob(created)
      await loadJobs()
    } finally {
      setUploading(false)
    }
  }

  const repairPlayback = async () => {
    if (!job) return
    await api(`/api/videos/jobs/${job.id}/repair-playback`, { method: 'POST' })
    const updated = await api<VideoJob>(`/api/videos/jobs/${job.id}`)
    setJob(updated)
    await loadJobs()
  }

  useEffect(() => {
    if (!job || job.status !== 'completed' || !job.media.needs_transcode || autoRepairing) return
    setAutoRepairing(true)
    void repairPlayback().finally(() => setAutoRepairing(false))
  }, [autoRepairing, job])

  const selectedObject = useMemo<PhotoObject | null>(() => {
    if (!selected || !selected.detection_id) return null
    return {
      id: selected.detection_id,
      species_id: selected.species_id,
      discovery_id: null,
      track_id: selected.track_id,
      category: selected.category,
      label: selected.label,
      scientific_name: selected.scientific_name,
      confidence: selected.confidence,
      bbox: selected.keyframes[0]?.bbox ?? { x: 0, y: 0, width: 1, height: 1 },
      color: selected.color,
      behavior: selected.behavior,
      phenomenon: selected.phenomenon,
      explanation: selected.explanation,
      evidence: selected.evidence,
      alternatives: selected.alternatives,
    }
  }, [selected])

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="eyebrow">INTERACTIVE VIDEO INTELLIGENCE</span>
          <h2>上传视频，点击画面里的生命。</h2>
          <p>上传后先统一转码为浏览器兼容 H.264，再生成可连续跟随目标的动态轨迹框。</p>
        </div>
        <div className="mode-switch"><Link to="/identify"><UploadCloud />图片识别</Link><Link className="active" to="/video"><FileVideo />视频识别</Link></div>
      </div>
      <div className="mode-note"><AlertTriangle size={18} /><span>植物优先处理近景和明显前景；低置信度物种只显示候选，不强行确定。</span></div>

      <section className="panel upload-panel">
        <div className="upload-drop" onClick={() => document.getElementById('video-file')?.click()}>
          <UploadCloud size={34} />
          <strong>{file ? file.name : '选择本地自然观察视频'}</strong>
          <span>MP4 / WebM / MOV / AVI / MKV，后台自动转码为 H.264</span>
          <input id="video-file" type="file" accept="video/*" hidden onChange={(event) => setFile(event.target.files?.[0] || null)} />
        </div>
        <div className="upload-config">
          <label>分析模式
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="fast">快速模式</option>
              <option value="standard">标准模式</option>
              <option value="precise">精细模式</option>
            </select>
          </label>
          <div className="target-toggles">
            {Object.entries(targets).map(([key, value]) => (
              <button key={key} className={value ? 'active' : ''} onClick={() => setTargets((current) => ({ ...current, [key]: !value }))}>
                {key === 'animals' ? '动物' : key === 'plants' ? '植物' : key === 'people' ? '人员车辆' : '火烟'}
              </button>
            ))}
          </div>
          <button className="primary-btn" disabled={!file || uploading} onClick={() => void upload()}>
            {uploading ? <LoaderCircle className="spin" /> : <Play />}{uploading ? '正在上传' : '创建分析任务'}
          </button>
        </div>
      </section>

      <div className="analysis-layout">
        <section className="panel video-panel">
          <div className="panel-head">
            <div><span className="eyebrow">ACTIVE JOB</span><h3>{job?.media.filename || '请选择分析任务'}</h3></div>
            {job && <div className={`status-badge status-${job.status}`}>{autoRepairing ? '正在修复播放版本' : `${job.status} · ${job.progress}%`}</div>}
          </div>
          {job && job.status === 'completed' ? (
            <VideoOverlay
              src={mediaUrl(job.media.playback_url || job.media.url)}
              tracks={tracks}
              onSelect={setSelected}
              onTimeChange={setCurrentTimeMs}
              onRepair={repairPlayback}
            />
          ) : (
            <div className="analysis-wait">
              <LoaderCircle className={job && activeStatuses.includes(job.status) ? 'spin' : ''} />
              <strong>{job ? `任务${job.status}，进度 ${job.progress}%` : '暂无任务'}</strong>
              <span>{job?.error_message || '上传视频后会依次完成转码、检测、追踪、分类和报告。'}</span>
            </div>
          )}
        </section>

        <aside className="panel job-selector">
          <div className="panel-head"><div><span className="eyebrow">TASK QUEUE</span><h3>任务列表</h3></div><Settings2 /></div>
          <div className="job-mini-list">
            {jobs.map((item) => (
              <button key={item.id} className={job?.id === item.id ? 'selected' : ''} onClick={() => setJob(item)}>
                <FileVideo />
                <div><strong>{item.media.filename}</strong><span>{item.status} · {item.progress}%</span></div>
                {item.status === 'completed' && <CheckCircle2 size={16} />}
              </button>
            ))}
          </div>
          <div className="legend"><h4>标注颜色</h4><span><i style={{ background: '#F5A623' }} />哺乳动物</span><span><i style={{ background: '#55B8FF' }} />鸟类</span><span><i style={{ background: '#35E58C' }} />植物</span><span><i style={{ background: '#A87CFF' }} />昆虫/蛛形</span><span><i style={{ background: '#2FD5C4' }} />两栖/爬行</span><span><i style={{ background: '#FF5A67' }} />人员/风险</span></div>
        </aside>
      </div>

      {selectedObject && job && (
        <RecognitionModal
          object={selectedObject}
          jobId={job.id}
          imageUrl=""
          observationTimestampMs={currentTimeMs}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
