import { useEffect, useMemo, useRef, useState } from 'react'
import type { VideoTrack } from '../types'

type Box = { x: number; y: number; width: number; height: number }

type VideoFrameCapable = HTMLVideoElement & {
  requestVideoFrameCallback?: (callback: (now: number, metadata: { mediaTime: number }) => void) => number
  cancelVideoFrameCallback?: (handle: number) => void
}

function interpolateBox(track: VideoTrack, timeMs: number): Box | null {
  const frames = track.keyframes
  if (!frames.length || timeMs < track.start_ms || timeMs > track.end_ms) return null
  if (frames.length === 1) return frames[0].bbox
  let previous = frames[0]
  for (let index = 1; index < frames.length; index += 1) {
    const current = frames[index]
    if (timeMs <= current.timestamp_ms) {
      const span = Math.max(1, current.timestamp_ms - previous.timestamp_ms)
      const ratio = Math.min(1, Math.max(0, (timeMs - previous.timestamp_ms) / span))
      return {
        x: previous.bbox.x + (current.bbox.x - previous.bbox.x) * ratio,
        y: previous.bbox.y + (current.bbox.y - previous.bbox.y) * ratio,
        width: previous.bbox.width + (current.bbox.width - previous.bbox.width) * ratio,
        height: previous.bbox.height + (current.bbox.height - previous.bbox.height) * ratio,
      }
    }
    previous = current
  }
  return previous.bbox
}

export default function VideoOverlay({
  src,
  tracks,
  onSelect,
  onTimeChange,
  onRepair,
}: {
  src: string
  tracks: VideoTrack[]
  onSelect: (track: VideoTrack) => void
  onTimeChange?: (ms: number) => void
  onRepair?: () => Promise<void>
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const frameHandle = useRef<number | null>(null)
  const [timeMs, setTimeMs] = useState(0)
  const [showLabels, setShowLabels] = useState(true)
  const [threshold, setThreshold] = useState(0.55)
  const [videoState, setVideoState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [videoError, setVideoError] = useState('')
  const [layout, setLayout] = useState({ left: 0, top: 0, width: 1, height: 1 })
  const [repairing, setRepairing] = useState(false)

  useEffect(() => {
    const video = videoRef.current as VideoFrameCapable | null
    if (!video) return
    let stopped = false

    const update = (_now?: number, metadata?: { mediaTime: number }) => {
      if (stopped) return
      const current = (metadata?.mediaTime ?? video.currentTime) * 1000
      setTimeMs(current)
      onTimeChange?.(current)
      if (video.requestVideoFrameCallback) {
        frameHandle.current = video.requestVideoFrameCallback(update)
      }
    }

    if (video.requestVideoFrameCallback) {
      frameHandle.current = video.requestVideoFrameCallback(update)
    } else {
      const fallback = () => update()
      video.addEventListener('timeupdate', fallback)
      return () => video.removeEventListener('timeupdate', fallback)
    }

    return () => {
      stopped = true
      if (frameHandle.current !== null && video.cancelVideoFrameCallback) {
        video.cancelVideoFrameCallback(frameHandle.current)
      }
    }
  }, [onTimeChange, src])

  useEffect(() => {
    const video = videoRef.current
    const stage = stageRef.current
    if (!video || !stage) return
    const calculate = () => {
      const stageWidth = stage.clientWidth || 1
      const stageHeight = stage.clientHeight || 1
      const sourceWidth = video.videoWidth || stageWidth
      const sourceHeight = video.videoHeight || stageHeight
      const scale = Math.min(stageWidth / sourceWidth, stageHeight / sourceHeight)
      const width = sourceWidth * scale
      const height = sourceHeight * scale
      setLayout({
        left: (stageWidth - width) / 2,
        top: (stageHeight - height) / 2,
        width,
        height,
      })
    }
    const observer = new ResizeObserver(calculate)
    observer.observe(stage)
    video.addEventListener('loadedmetadata', calculate)
    calculate()
    return () => {
      observer.disconnect()
      video.removeEventListener('loadedmetadata', calculate)
    }
  }, [src])

  const active = useMemo(
    () =>
      tracks
        .filter((track) => track.confidence >= threshold)
        .map((track) => ({ track, bbox: interpolateBox(track, timeMs) }))
        .filter((item): item is { track: VideoTrack; bbox: Box } => Boolean(item.bbox)),
    [tracks, timeMs, threshold],
  )

  const seek = (ms: number) => {
    if (!videoRef.current) return
    videoRef.current.currentTime = ms / 1000
    void videoRef.current.play().catch(() => undefined)
  }

  const repair = async () => {
    if (!onRepair) return
    setRepairing(true)
    try {
      await onRepair()
      setVideoError('播放版本已重新生成，请稍候重新加载。')
    } finally {
      setRepairing(false)
    }
  }

  const durationMs = Math.max(1, (videoRef.current?.duration || 0) * 1000)

  return (
    <div className="video-workbench">
      <div className="video-stage" ref={stageRef}>
        <video
          key={src}
          ref={videoRef}
          src={src}
          controls
          playsInline
          preload="metadata"
          crossOrigin="anonymous"
          onLoadStart={() => { setVideoState('loading'); setVideoError('') }}
          onLoadedMetadata={() => setVideoState('ready')}
          onCanPlay={() => setVideoState('ready')}
          onError={() => {
            const code = videoRef.current?.error?.code
            setVideoState('error')
            setVideoError(`浏览器无法解码当前视频${code ? `（错误码 ${code}）` : ''}。请重新生成 H.264 播放版本。`)
          }}
        />
        <div
          className="detection-layer"
          style={{ left: layout.left, top: layout.top, width: layout.width, height: layout.height }}
        >
          {active.map(({ track, bbox }) => (
            <button
              key={track.id}
              className="detection-box"
              onClick={() => onSelect(track)}
              style={{
                left: `${bbox.x * 100}%`,
                top: `${bbox.y * 100}%`,
                width: `${bbox.width * 100}%`,
                height: `${bbox.height * 100}%`,
                borderColor: track.color,
                color: track.color,
              }}
            >
              <span style={{ background: track.color }}>
                {showLabels ? `${track.label} #${track.track_id} · ${(track.confidence * 100).toFixed(0)}%` : ''}
              </span>
            </button>
          ))}
        </div>
        {videoState === 'loading' && <div className="video-message">正在读取兼容播放视频…</div>}
        {videoState === 'error' && (
          <div className="video-message video-error-message">
            <strong>视频播放失败</strong>
            <span>{videoError}</span>
            {onRepair && <button className="primary-btn" disabled={repairing} onClick={() => void repair()}>{repairing ? '正在转码…' : '修复播放版本'}</button>}
          </div>
        )}
        <div className="video-status"><span className="status-dot" />动态轨迹标注已启用 · 点击移动框查看科普</div>
      </div>
      <div className="overlay-controls">
        <label><input type="checkbox" checked={showLabels} onChange={(event) => setShowLabels(event.target.checked)} />显示中文名和学名</label>
        <label>置信度阈值 <input type="range" min="0.3" max="0.95" step="0.05" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} /><b>{Math.round(threshold * 100)}%</b></label>
      </div>
      <div className="timeline">
        <div className="timeline-track">
          {tracks.map((track) => (
            <button
              key={track.id}
              title={`${(track.start_ms / 1000).toFixed(1)}s ${track.label}`}
              onClick={() => seek(track.start_ms)}
              style={{ left: `${Math.min(99, (track.start_ms / durationMs) * 100)}%`, background: track.color }}
            />
          ))}
        </div>
        <div className="timeline-labels">
          <span>0:00</span>
          <span>{Math.floor(timeMs / 60000)}:{String(Math.floor((timeMs / 1000) % 60)).padStart(2, '0')}</span>
          <span>{videoRef.current?.duration ? `${Math.floor(videoRef.current.duration / 60)}:${String(Math.floor(videoRef.current.duration % 60)).padStart(2, '0')}` : '--:--'}</span>
        </div>
      </div>
    </div>
  )
}
