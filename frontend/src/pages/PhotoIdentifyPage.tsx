import { useEffect, useRef, useState } from 'react'
import { Camera, CheckCircle2, ImagePlus, Leaf, Loader2, MapPin, RefreshCw, ScanLine, UploadCloud, WandSparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, mediaUrl } from '../api/client'
import RecognitionModal from '../components/RecognitionModal'
import SpeciesModal from '../components/SpeciesModal'
import type { PhotoIdentifyResult, PhotoObject } from '../types'

const categoryLabels: Record<string, string> = {
  mammal: '哺乳动物', bird: '鸟类', reptile: '爬行动物', amphibian: '两栖动物', fish: '鱼类',
  insect: '昆虫', arachnid: '蛛形动物', mollusk: '软体动物', crustacean: '甲壳动物', invertebrate: '其他无脊椎动物',
  plant: '植物', angiosperm: '被子植物', gymnosperm: '裸子植物', fern: '蕨类', moss: '苔藓', algae: '藻类',
  fungus: '真菌', lichen: '地衣', phenomenon: '自然现象', weather: '天气现象', fire: '火焰候选', smoke: '烟雾候选', unknown: '待确认',
}

export default function PhotoIdentifyPage() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [hint, setHint] = useState('')
  const [address, setAddress] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<PhotoIdentifyResult | null>(null)
  const [selected, setSelected] = useState<PhotoObject | null>(null)
  const [speciesId, setSpeciesId] = useState<number | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const saved = sessionStorage.getItem('shijing_last_photo_result')
    if (!saved) return
    try {
      const data = JSON.parse(saved) as PhotoIdentifyResult
      setResult(data)
      setPreview(mediaUrl(data.image_url))
    } catch {
      sessionStorage.removeItem('shijing_last_photo_result')
    }
  }, [])

  const setPhoto = (next: File) => {
    setFile(next)
    setResult(null)
    setSelected(null)
    setError('')
    sessionStorage.removeItem('shijing_last_photo_result')
    setPreview(URL.createObjectURL(next))
  }

  const takeNativePhoto = async () => {
    try {
      const { Camera: NativeCamera, CameraResultType, CameraSource } = await import('@capacitor/camera')
      const photo = await NativeCamera.getPhoto({
        quality: 88,
        allowEditing: false,
        resultType: CameraResultType.Uri,
        source: CameraSource.Camera,
      })
      if (!photo.webPath) return
      const blob = await fetch(photo.webPath).then((response) => response.blob())
      setPhoto(new File([blob], `camera-${Date.now()}.${photo.format || 'jpeg'}`, { type: blob.type || 'image/jpeg' }))
    } catch {
      inputRef.current?.click()
    }
  }

  const identify = async () => {
    if (!file) return
    setLoading(true)
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('hint', hint)
      form.append('address', address)
      const data = await api<PhotoIdentifyResult>('/api/identify/photo', { method: 'POST', body: form })
      setResult(data)
      sessionStorage.setItem('shijing_last_photo_result', JSON.stringify(data))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '识别失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  const reidentify = async () => {
    if (!result) return
    setLoading(true)
    setError('')
    setSelected(null)
    try {
      const data = await api<PhotoIdentifyResult>(`/api/identify/jobs/${result.job_id}/reidentify`, {
        method: 'POST',
        body: JSON.stringify({ hint, address }),
      })
      setResult(data)
      sessionStorage.setItem('shijing_last_photo_result', JSON.stringify(data))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '重新识别失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  const modelModeLabel = (mode: string) => {
    const normalized = mode.toLowerCase()
    if (normalized.includes('speciesnet') && normalized.includes('bioclip')) return '本地 SpeciesNet + BioCLIP'
    if (normalized.includes('speciesnet')) return '本地 SpeciesNet'
    if (normalized.includes('bioclip')) return '本地 BioCLIP'
    if (normalized.includes('ark')) return 'ARK 增强'
    if (normalized.includes('heuristic')) return '本地启发式'
    return mode || '待确认'
  }

  const imageSource = result ? mediaUrl(result.image_url) : preview

  return (
    <div className="page-stack photo-page">
      <section className="page-intro">
        <div><span className="eyebrow">CAMERA · IDENTIFY · LEARN</span><h2>拍照识别自然万物</h2><p>拍摄或上传动物、植物、真菌、自然现象照片。系统会用可点击边框标注目标，解释判断依据，并把发现收入你的自然图鉴。</p></div>
        <div className="mode-switch"><Link className="active" to="/identify"><Camera />图片识别</Link><Link to="/video"><UploadCloud />视频识别</Link></div>
      </section>

      <section className="photo-workspace">
        <div className="photo-stage panel">
          {!imageSource ? (
            <div className="camera-empty">
              <div className="camera-orbit"><ScanLine /><i /><i /></div>
              <h3>对准一种动植物或自然现象</h3>
              <p>尽量保持主体清晰、光线充足。植物建议同时拍摄叶、花、果或树皮。</p>
              <div className="camera-actions">
                <button className="primary-btn" onClick={() => void takeNativePhoto()}><Camera />打开相机</button>
                <button className="ghost-btn" onClick={() => inputRef.current?.click()}><ImagePlus />从相册选择</button>
              </div>
            </div>
          ) : (
            <div className="photo-canvas">
              <img src={imageSource} alt="待识别自然照片" />
              {result?.objects.map((object) => (
                <button
                  key={object.id}
                  className="photo-box"
                  style={{
                    left: `${object.bbox.x * 100}%`, top: `${object.bbox.y * 100}%`,
                    width: `${object.bbox.width * 100}%`, height: `${object.bbox.height * 100}%`,
                    borderColor: object.color, '--box-tone': object.color,
                  } as React.CSSProperties}
                  onClick={() => setSelected(object)}
                >
                  <span style={{ background: object.color }}>{object.label} · {Math.round(object.confidence * 100)}%</span>
                </button>
              ))}
              {loading && <div className="photo-scanning"><div className="scan-line" /><Loader2 className="spin" /><strong>正在分析形态、纹理、场景与行为…</strong></div>}
            </div>
          )}
          <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" hidden onChange={(event) => event.target.files?.[0] && setPhoto(event.target.files[0])} />
          {imageSource && (
            <div className="photo-stage-toolbar">
              <button className="ghost-btn" onClick={() => inputRef.current?.click()}><UploadCloud />选择下一张</button>
              <button className="ghost-btn" onClick={() => void takeNativePhoto()}><Camera />重新拍摄</button>
              <span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : '已识别照片'}</span>
            </div>
          )}
        </div>

        <aside className="photo-control panel">
          <div className="panel-head"><div><span className="eyebrow">识别设置</span><h3>补充拍摄场景</h3></div><WandSparkles /></div>
          <label className="field-label">可选场景提示<textarea value={hint} onChange={(event) => setHint(event.target.value)} placeholder="例如：天津水上公园拍摄、夜间林地、叶片背面近景……" /></label>
          <label className="field-label">观察地点（可选）<input value={address} onChange={(event) => setAddress(event.target.value)} placeholder="例如：天津水上公园、北京奥森、杭州西湖" /></label>
          <div className="identify-scope">
            {['动物', '植物', '真菌昆虫', '自然现象', '动物行为'].map((item) => <span key={item}><CheckCircle2 />{item}</span>)}
          </div>
          <button className="primary-btn full identify-button" onClick={() => result ? void reidentify() : void identify()} disabled={(!file && !result) || loading}>
            {loading ? <><Loader2 className="spin" />识别中</> : result ? <><RefreshCw />按提示重新识别</> : <><ScanLine />开始智能识别</>}
          </button>
          {result && <button className="ghost-btn full" onClick={() => void identify()} disabled={!file || loading}><ScanLine />作为新记录再次识别</button>}
          {result && <div className="save-status-card"><CheckCircle2 /><div><strong>识别结果已自动保存</strong><span>记录会保留到“观察记录”，选择下一张照片前当前结果也不会消失。</span></div><Link className="ghost-btn" to="/history">查看记录</Link></div>}
          {loading && <div className="recognition-progress indeterminate"><i /></div>}
          {error && <div className="form-error">{error}</div>}
          <div className="recognition-note"><Leaf /><p>识别后结果会保留在当前页；只有选择下一张照片时才会清空。</p></div>
          <div className="recognition-note"><MapPin /><p>填写地点后，保存的识别记录会尽量加入地图；珍稀物种公开分享时仍会保护精确位置。</p></div>
        </aside>
      </section>

      {result && (
        <>
          <section className="result-summary panel">
            <div><span className="eyebrow">识别摘要</span><h3>{result.summary}</h3><p>场景类型：{result.scene_type} · 模式：{modelModeLabel(result.model_mode)}</p></div>
            <div className="result-count"><strong>{result.objects.length}</strong><span>个可交互目标</span></div>
          </section>
          {result.warnings.length > 0 && <div className="warning-strip">{result.warnings.map((item) => <span key={item}>{item}</span>)}</div>}
          <section className="identified-grid">
            {result.objects.map((object) => (
              <button key={object.id} className="identified-card" onClick={() => setSelected(object)}>
                <div className="identified-icon" style={{ color: object.color, background: `${object.color}18` }}><ScanLine /></div>
                <div><span>{categoryLabels[object.category] || object.category}</span><h3>{object.phenomenon || object.behavior || object.label}</h3><em>{object.scientific_name || '学名待确认'}</em><p>{object.explanation || '点击查看识别解释和中文科普。'}</p></div>
                <strong>{Math.round(object.confidence * 100)}%</strong>
              </button>
            ))}
          </section>
        </>
      )}

      {selected && result && (
        <RecognitionModal object={selected} jobId={result.job_id} imageUrl={mediaUrl(result.image_url)} onClose={() => setSelected(null)} onOpenSpecies={(id) => { setSelected(null); setSpeciesId(id) }} />
      )}
      {speciesId && <SpeciesModal speciesId={speciesId} onClose={() => setSpeciesId(null)} />}
    </div>
  )
}
