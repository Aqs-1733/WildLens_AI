import { useCallback, useEffect, useState } from 'react'
import { Activity, Camera, Database, HardDrive, RefreshCcw, Save, Settings, ShieldAlert, TerminalSquare } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'

type StatusBlock = Record<string, unknown>

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未配置'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return value.toLocaleString()
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function StatusList({ data }: { data: StatusBlock | null }) {
  if (!data) return <div className="empty-state">暂无状态数据</div>
  return (
    <div className="settings-kv">
      {Object.entries(data).slice(0, 12).map(([key, value]) => (
        <div key={key}><span>{key}</span><strong>{valueText(value)}</strong></div>
      ))}
    </div>
  )
}

export default function SystemSettingsPage() {
  const { user, refresh } = useAuth()
  const [status, setStatus] = useState<StatusBlock | null>(null)
  const [modelStatus, setModelStatus] = useState<StatusBlock | null>(null)
  const [trainingStatus, setTrainingStatus] = useState<StatusBlock | null>(null)
  const [storageStatus, setStorageStatus] = useState<StatusBlock | null>(null)
  const [dataStatus, setDataStatus] = useState<StatusBlock | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [profile, setProfile] = useState({ display_name: '', bio: '', avatar_url: '', home_location: '', frequent_locations: '' })
  const canInspectOps = user?.role === 'regulator' || user?.role === 'admin'

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setStatus(await api<StatusBlock>('/api/system/status'))
      const profileData = await api<{ user: { display_name: string; bio: string; avatar_url: string | null }; home_location: string; frequent_locations: string[] }>('/api/auth/profile')
      setProfile({
        display_name: profileData.user.display_name,
        bio: profileData.user.bio,
        avatar_url: profileData.user.avatar_url || '',
        home_location: profileData.home_location || '',
        frequent_locations: (profileData.frequent_locations || []).join('，'),
      })
      if (canInspectOps) {
        const [models, training, storage, data] = await Promise.all([
          api<StatusBlock>('/api/system/model-status'),
          api<StatusBlock>('/api/system/training-status'),
          api<StatusBlock>('/api/system/storage-status'),
          api<StatusBlock>('/api/system/data-status'),
        ])
        setModelStatus(models)
        setTrainingStatus(training)
        setStorageStatus(storage)
        setDataStatus(data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '系统状态读取失败')
    } finally {
      setLoading(false)
    }
  }, [canInspectOps])

  const saveProfile = async () => {
    await api('/api/auth/profile', {
      method: 'PATCH',
      body: JSON.stringify({
        display_name: profile.display_name,
        bio: profile.bio,
        avatar_url: profile.avatar_url,
        home_location: profile.home_location,
        frequent_locations: profile.frequent_locations.split(/[，,]/).map((item) => item.trim()).filter(Boolean),
      }),
    })
    await refresh()
  }

  useEffect(() => { void load() }, [load])

  const counts = (status?.counts || {}) as StatusBlock
  const paths = (status?.paths || {}) as StatusBlock
  const disk = (storageStatus?.disk || {}) as StatusBlock

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="eyebrow">SYSTEM SETTINGS</span>
          <h2>系统设置与能力状态</h2>
          <p>识境当前运行配置、模型能力和只读训练数据状态。</p>
        </div>
        <button className="ghost-btn" onClick={() => void load()} disabled={loading}><RefreshCcw className={loading ? 'spin' : ''}/>刷新状态</button>
      </div>
      {error && <div className="inline-error">{error}</div>}
      <section className="panel profile-settings-panel">
        <div className="panel-head"><div><span className="eyebrow">PROFILE</span><h3>个人资料与常去位置</h3></div><Camera/></div>
        <div className="profile-settings-grid">
          <div className="avatar-preview">{profile.avatar_url ? <img src={profile.avatar_url} alt="头像预览"/> : <span>{(profile.display_name || user?.display_name || '识').slice(0, 1)}</span>}</div>
          <label>昵称<input value={profile.display_name} onChange={(event) => setProfile((current) => ({ ...current, display_name: event.target.value }))}/></label>
          <label>头像 URL<input value={profile.avatar_url} onChange={(event) => setProfile((current) => ({ ...current, avatar_url: event.target.value }))} placeholder="可粘贴图片链接；留空使用默认头像"/></label>
          <label>所在或常去位置<input value={profile.home_location} onChange={(event) => setProfile((current) => ({ ...current, home_location: event.target.value }))} placeholder="例如 北京奥森、天津水上公园"/></label>
          <label className="profile-wide">更多常去地点<textarea value={profile.frequent_locations} onChange={(event) => setProfile((current) => ({ ...current, frequent_locations: event.target.value }))} placeholder="用逗号分隔，方便推荐附近观察者和相似记录"/></label>
          <button className="primary-btn" onClick={() => void saveProfile()}><Save/>保存个人设置</button>
        </div>
      </section>
      <div className="settings-grid">
        <section className="panel">
          <div className="panel-head"><div><span className="eyebrow">RUNTIME</span><h3>运行状态</h3></div><Settings/></div>
          <StatusList data={status ? {
            app: status.app,
            environment: status.environment,
            vision_mode: status.vision_mode,
            ark_enabled: status.ark_enabled,
            database_url: status.database_url,
          } : null} />
        </section>
        <section className="panel">
          <div className="panel-head"><div><span className="eyebrow">COUNTS</span><h3>业务数据</h3></div><Activity/></div>
          <StatusList data={counts} />
        </section>
        <section className="panel">
          <div className="panel-head"><div><span className="eyebrow">PATHS</span><h3>关键目录</h3></div><TerminalSquare/></div>
          <StatusList data={paths} />
        </section>
        <section className="panel">
          <div className="panel-head"><div><span className="eyebrow">DISK</span><h3>存储概览</h3></div><HardDrive/></div>
          <StatusList data={canInspectOps ? disk : { 权限: '监管端可查看完整存储状态' }} />
        </section>
      </div>
      {canInspectOps ? (
        <div className="settings-grid">
          <section className="panel"><div className="panel-head"><div><span className="eyebrow">MODELS</span><h3>模型路由</h3></div><ShieldAlert/></div><StatusList data={modelStatus} /></section>
          <section className="panel"><div className="panel-head"><div><span className="eyebrow">TRAINING</span><h3>训练任务</h3></div><Activity/></div><StatusList data={trainingStatus} /></section>
          <section className="panel"><div className="panel-head"><div><span className="eyebrow">DATA</span><h3>训练数据</h3></div><Database/></div><StatusList data={dataStatus} /></section>
        </div>
      ) : (
        <section className="panel"><div className="panel-head"><div><span className="eyebrow">ACCESS</span><h3>状态可见范围</h3></div><ShieldAlert/></div><p>当前账号可查看应用运行状态；训练库、模型注册和存储详情仅向监管或管理员角色开放。</p></section>
      )}
    </div>
  )
}
