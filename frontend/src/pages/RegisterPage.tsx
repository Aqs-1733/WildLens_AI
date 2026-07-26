import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, UserPlus } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import Logo from '../components/Logo'

export default function RegisterPage() {
  const { register } = useAuth()
  const [form, setForm] = useState({ username: '', email: '', password: '', display_name: '', role: 'public', invite_code: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const update = (key: string, value: string) => setForm(current => ({ ...current, [key]: value }))
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError(''); setLoading(true)
    try { await register(form) } catch (err) { setError(err instanceof Error ? err.message : '注册失败') } finally { setLoading(false) }
  }
  return <div className="auth-page auth-register"><div className="auth-visual"><Logo/><div className="auth-copy"><span className="auth-kicker">CREATE YOUR FIELD NOTEBOOK</span><h1>建立你的<br />自然观察身份。</h1><p>公众账号用于学习、收集和分享；公众账号可直接注册；环保监管账号需要管理员邀请码，可进入风险预警与人工复核工作台。</p></div></div><div className="auth-panel"><form className="auth-card" onSubmit={submit}><Link className="back-link" to="/login"><ArrowLeft size={16}/>返回登录</Link><h2>创建账号</h2><div className="role-select"><button type="button" className={form.role==='public'?'selected':''} onClick={()=>update('role','public')}>公众探索者<span>收集图鉴、学习与好友分享</span></button><button type="button" className={form.role==='regulator'?'selected':''} onClick={()=>update('role','regulator')}>环保监管员<span>预警复核、报告与模型管理</span></button></div>
    <div className="form-grid"><label>用户名<input value={form.username} onChange={e=>update('username',e.target.value)} minLength={3} required/></label><label>显示名称<input value={form.display_name} onChange={e=>update('display_name',e.target.value)} required/></label></div>
    {form.role==='regulator'&&<label>监管邀请码<input value={form.invite_code} onChange={e=>update('invite_code',e.target.value)} placeholder="由项目管理员提供" required/></label>}<label>邮箱<input type="email" value={form.email} onChange={e=>update('email',e.target.value)} required/></label><label>密码<input type="password" value={form.password} onChange={e=>update('password',e.target.value)} minLength={8} required/></label>
    {error && <div className="form-error">{error}</div>}<button className="primary-btn full" disabled={loading}><UserPlus size={17}/>{loading?'正在创建…':'注册并进入'}<ArrowRight size={17}/></button></form></div></div>
}
