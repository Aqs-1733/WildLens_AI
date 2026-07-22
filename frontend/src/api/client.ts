import { Capacitor } from '@capacitor/core'

const DEFAULT_NATIVE_API = import.meta.env.VITE_NATIVE_API_BASE || 'http://10.0.2.2:8010'

export function getApiBase(): string {
  const saved = localStorage.getItem('wildlens_api_base')?.trim()
  if (saved) return saved.replace(/\/$/, '')
  const configured = import.meta.env.VITE_API_BASE?.trim()
  if (configured) return configured.replace(/\/$/, '')
  return Capacitor.isNativePlatform() ? DEFAULT_NATIVE_API : ''
}

export function setApiBase(value: string): void {
  const normalized = value.trim().replace(/\/$/, '')
  if (normalized) localStorage.setItem('wildlens_api_base', normalized)
  else localStorage.removeItem('wildlens_api_base')
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('wildlens_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  Object.entries(authHeaders()).forEach(([key, value]) => headers.set(key, String(value)))
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${getApiBase()}${path}`, { ...options, headers })
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const data = await response.json()
      message = data.detail || data.message || message
    } catch {
      // non-JSON error
    }
    throw new ApiError(response.status, message)
  }
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return response.json() as Promise<T>
  return response as unknown as T
}

export function mediaUrl(url: string): string {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:')) return url
  return `${getApiBase()}${url}`
}
