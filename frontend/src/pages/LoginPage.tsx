import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Eye, EyeOff, Leaf, Link2, LockKeyhole, ShieldCheck, Sparkles, Wifi } from 'lucide-react'
import { getApiBase, setApiBase } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Logo from '../components/Logo'

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('explorer')
  const [password, setPassword] = useState('Wild1234!')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [apiAddress, setApiAddress] = useState(getApiBase())
  const [connectionState, setConnectionState] = useState('')

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError(''); setLoading(true)
    setApiBase(apiAddress)
    try { await login(username, password) } catch (err) { setError(err instanceof Error ? err.message : '登录失败') } finally { setLoading(false) }
  }

  const checkConnection = async () => {
    setApiBase(apiAddress)
    setConnectionState('正在连接…')
    try {
      const base = getApiBase()
      const response = await fetch(`${base}/api/health`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const result = await response.json()
      setConnectionState(`连接成功：${result.app}`)
    } catch (err) {
      setConnectionState(`连接失败：${err instanceof Error ? err.message : '请检查地址'}`)
    }
  }

  return <div className="auth-page">
    <div className="auth-visual">
      <div className="auth-glow" />
      <Logo />
      <div className="auth-copy"><span className="auth-kicker"><Sparkles size={15} /> 让每一次发现都有意义</span><h1>看见荒野，<br />理解生命。</h1><p>拍照识别动植物、动物行为与自然现象，把每一次发现变成可学习、可分享的自然记录。</p></div>
      <div className="auth-feature-row"><div><Leaf /><strong>多目标识别</strong><span>动物、植物、行为与现象</span></div><div><ShieldCheck /><strong>可信科普</strong><span>依据、候选项与人工纠错</span></div><div><Sparkles /><strong>星级收集</strong><span>学习、收集与好友分享</span></div></div>
    </div>
    <div className="auth-panel"><form className="auth-card" onSubmit={submit}><span className="eyebrow">WELCOME BACK</span><h2>登录识境</h2><p>继续你的识别记录、自然图鉴与好友探索。</p>
      <label>用户名或邮箱<input value={username} onChange={e => setUsername(e.target.value)} placeholder="请输入用户名" autoComplete="username" /></label>
      <label>密码<div className="password-field"><input type={show ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" /><button type="button" onClick={() => setShow(!show)}>{show ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div></label>
      <div className="api-connection-box"><div><Link2 size={16}/><strong>App后端地址</strong></div><p>电脑网页可留空；Android模拟器使用 http://10.0.2.2:8010；真机填写电脑局域网IP。</p><div className="api-address-row"><input value={apiAddress} onChange={e => setApiAddress(e.target.value)} placeholder="例如 http://192.168.1.20:8010"/><button type="button" className="ghost-btn" onClick={() => void checkConnection()}><Wifi size={15}/>测试</button></div>{connectionState && <small>{connectionState}</small>}</div>
      {error && <div className="form-error">{error}</div>}
      <button className="primary-btn full" disabled={loading}><LockKeyhole size={17}/>{loading ? '正在登录…' : '登录'}<ArrowRight size={17}/></button>
      <div className="demo-accounts"><span>公众演示：explorer / Wild1234!</span><span>监管演示：ranger / Wild1234!</span></div>
      <p className="auth-switch">还没有账号？<Link to="/register">立即注册</Link></p>
    </form></div>
  </div>
}
