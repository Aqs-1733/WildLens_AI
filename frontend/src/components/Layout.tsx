import {
  Activity,
  AlertTriangle,
  BarChart3,
  BookOpen,
  Bot,
  Camera,
  CircleUserRound,
  ClipboardCheck,
  CloudSun,
  FileText,
  FlaskConical,
  History,
  Home,
  LogOut,
  MapPinned,
  Menu,
  MessageCircle,
  Microscope,
  Network,
  Settings,
  Shield,
  Sparkles,
  Users,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Logo from './Logo'

type NavItem = { path: string; icon: LucideIcon; label: string; activePaths?: string[] }

const publicNav: NavItem[] = [
  { path: '/', icon: Home, label: '综合态势' },
  { path: '/identify', icon: Camera, label: '生态识别', activePaths: ['/identify', '/video'] },
  { path: '/jobs', icon: Activity, label: '分析任务' },
  { path: '/species', icon: BookOpen, label: '自然图鉴' },
  { path: '/classroom', icon: CloudSun, label: '自然现象' },
  { path: '/map', icon: MapPinned, label: '生态地图' },
  { path: '/qa', icon: MessageCircle, label: '自然问答' },
  { path: '/history', icon: History, label: '观察记录' },
  { path: '/analytics', icon: BarChart3, label: '数据分析' },
  { path: '/learning', icon: Microscope, label: '学习挑战' },
  { path: '/community', icon: Users, label: '林间社群' },
  { path: '/settings', icon: Settings, label: '个人信息' },
]

const regulatorNav: NavItem[] = [
  { path: '/alerts', icon: AlertTriangle, label: '风险事件' },
  { path: '/review', icon: ClipboardCheck, label: '人工复核' },
  { path: '/reports', icon: FileText, label: 'AI报告' },
  { path: '/models', icon: FlaskConical, label: '模型中心' },
  { path: '/datasets', icon: Network, label: '数据集管理' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const nav = user?.role === 'public' ? publicNav : [...publicNav, ...regulatorNav]
  const title = useMemo(() => {
    const item = nav.find((entry) => entry.path === location.pathname || entry.activePaths?.includes(location.pathname))
    return item?.label ?? '识境'
  }, [location.pathname, nav])

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
        <div className="sidebar-head">
          <Logo />
          <button className="icon-btn mobile-close" onClick={() => setMobileOpen(false)} aria-label="关闭菜单"><X /></button>
        </div>
        <nav className="nav-list">
          {nav.map(({ path, icon: Icon, label, activePaths }) => (
            <NavLink
              key={path}
              to={path}
              end={path === '/'}
              className={({ isActive }) => `nav-link ${isActive || activePaths?.includes(location.pathname) ? 'active' : ''}`}
              onClick={() => setMobileOpen(false)}
            >
              <Icon size={20} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-engine">
          <div className="engine-title"><Bot size={17} /> AI ENGINE</div>
          <div className="status-line"><span className="status-dot" />系统在线</div>
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-backdrop" aria-label="关闭菜单" onClick={() => setMobileOpen(false)} />}
      <main className="main-area">
        <header className="topbar">
          <button className="icon-btn mobile-menu" onClick={() => setMobileOpen(true)} aria-label="打开菜单"><Menu /></button>
          <div><h1>{title}</h1></div>
          <div className="topbar-actions">
            <div className={`role-chip role-${user?.role}`}><Shield size={15} />{user?.role === 'public' ? '公众探索者' : '环保监管端'}</div>
            <div className="user-chip"><CircleUserRound size={18} /><span>{user?.display_name}</span></div>
            <button className="icon-btn" onClick={logout} title="退出登录"><LogOut size={18} /></button>
          </div>
        </header>
        <section className="content"><Outlet /></section>
        <nav className="mobile-bottom-nav">
          {[
            { path: '/', icon: Home, label: '首页' },
            { path: '/identify', icon: Camera, label: '生态识别' },
            { path: '/species', icon: Sparkles, label: '图鉴' },
            { path: '/community', icon: Users, label: '社区' },
            { path: '/history', icon: History, label: '记录' },
          ].map(({ path, icon: Icon, label }) => (
            <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `mobile-nav-item ${isActive ? 'active' : ''}`}>
              <Icon size={19} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </main>
    </div>
  )
}
