import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { User } from '../types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (payload: { username: string; email: string; password: string; display_name: string; role: string; invite_code?: string }) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const token = localStorage.getItem('wildlens_token')
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      setUser(await api<User>('/api/auth/me'))
    } catch {
      localStorage.removeItem('wildlens_token')
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const login = useCallback(async (username: string, password: string) => {
    const result = await api<{ access_token: string }>('/api/auth/login', {
      method: 'POST', body: JSON.stringify({ username, password })
    })
    localStorage.setItem('wildlens_token', result.access_token)
    localStorage.setItem('wildlens_qa_start_new', '1')
    await refresh()
  }, [refresh])

  const register = useCallback(async (payload: { username: string; email: string; password: string; display_name: string; role: string; invite_code?: string }) => {
    const result = await api<{ access_token: string }>('/api/auth/register', {
      method: 'POST', body: JSON.stringify(payload)
    })
    localStorage.setItem('wildlens_token', result.access_token)
    localStorage.setItem('wildlens_qa_start_new', '1')
    await refresh()
  }, [refresh])

  const logout = () => {
    localStorage.removeItem('wildlens_token')
    setUser(null)
  }

  const value = useMemo(() => ({ user, loading, login, register, logout, refresh }), [user, loading, login, register, refresh])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
