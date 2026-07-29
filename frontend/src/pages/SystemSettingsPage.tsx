import { useCallback, useEffect, useState } from 'react'
import { Camera, ImagePlus, MapPin, Save, UserRound } from 'lucide-react'
import { api, mediaUrl } from '../api/client'
import { useAuth } from '../context/AuthContext'

type ProfilePayload = {
  user: { display_name: string; bio: string; avatar_url: string | null }
  home_location: string
  frequent_locations: string[]
}

export default function SystemSettingsPage() {
  const { user, refresh } = useAuth()
  const [profile, setProfile] = useState({
    display_name: '',
    bio: '',
    avatar_url: '',
    locations: '',
  })
  const [loading, setLoading] = useState(false)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api<ProfilePayload>('/api/auth/profile')
      setProfile({
        display_name: data.user.display_name || user?.display_name || '',
        bio: data.user.bio || '',
        avatar_url: data.user.avatar_url || '',
        locations: [data.home_location, ...(data.frequent_locations || [])]
          .map((item) => item.trim())
          .filter((item, index, list) => item && list.indexOf(item) === index)
          .join('，'),
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '个人信息读取失败')
    } finally {
      setLoading(false)
    }
  }, [user?.display_name])

  useEffect(() => { void load() }, [load])

  const saveProfile = async () => {
    setSaved(false)
    setError('')
    try {
      const locations = profile.locations.split(/[，,、;\n]/).map((item) => item.trim()).filter(Boolean)
      await api('/api/auth/profile', {
        method: 'PATCH',
        body: JSON.stringify({
          display_name: profile.display_name,
          bio: profile.bio,
          avatar_url: profile.avatar_url,
          home_location: locations[0] || '',
          frequent_locations: locations,
        }),
      })
      await refresh()
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2200)
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    }
  }

  const avatarText = (profile.display_name || user?.display_name || '识').slice(0, 1)

  const uploadAvatar = async (file: File) => {
    setUploadingAvatar(true)
    setSaved(false)
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const result = await api<{ image_url: string }>('/api/social/attachments', { method: 'POST', body: form })
      setProfile((current) => ({ ...current, avatar_url: result.image_url }))
      setSaved(true)
      window.setTimeout(() => setSaved(false), 1800)
    } catch (err) {
      setError(err instanceof Error ? err.message : '头像上传失败')
    } finally {
      setUploadingAvatar(false)
    }
  }

  return (
    <div className="page-stack profile-page">
      <div className="page-intro">
        <div>
          <span className="eyebrow">MY PROFILE</span>
          <h2>个人信息</h2>
          <p>头像、昵称和常去地点会用于社群展示、好友推荐和自然问答记忆。</p>
        </div>
      </div>
      {error && <div className="inline-error">{error}</div>}
      {saved && <div className="save-toast"><Save/>个人信息已保存</div>}
      <section className="panel profile-settings-panel profile-only-panel">
        <div className="panel-head"><div><span className="eyebrow">PROFILE</span><h3>资料与常去位置</h3></div><UserRound/></div>
        <div className="profile-settings-grid">
          <div className="profile-avatar-box">
            <div className="avatar-preview">{profile.avatar_url ? <img src={mediaUrl(profile.avatar_url)} alt="头像预览"/> : <span>{avatarText}</span>}</div>
            <label className="ghost-btn avatar-upload-btn">
              <ImagePlus size={16}/>{uploadingAvatar ? '上传中' : '上传头像'}
              <input type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(event) => event.target.files?.[0] && void uploadAvatar(event.target.files[0])}/>
            </label>
          </div>
          <label>昵称<input value={profile.display_name} onChange={(event) => setProfile((current) => ({ ...current, display_name: event.target.value }))}/></label>
          <label className="profile-wide"><MapPin size={16}/>所在或常去位置<textarea value={profile.locations} onChange={(event) => setProfile((current) => ({ ...current, locations: event.target.value }))} placeholder="例如：天津水上公园，北京奥森。多个地点用逗号分隔。"/></label>
          <label className="profile-wide">个人简介<textarea value={profile.bio} onChange={(event) => setProfile((current) => ({ ...current, bio: event.target.value }))} placeholder="写一点你的自然观察兴趣"/></label>
          <button className="primary-btn" onClick={() => void saveProfile()} disabled={loading}><Save/>{loading ? '读取中' : '保存个人信息'}</button>
        </div>
      </section>
      <section className="panel profile-memory-note">
        <div><Camera/><strong>问答记忆</strong></div>
        <p>识境会在本机记录你的兴趣、常问主题、常去地点和已加入图鉴的物种，用来让问答和社群推荐更贴近你。</p>
      </section>
    </div>
  )
}
