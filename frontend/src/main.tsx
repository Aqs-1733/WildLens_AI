import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import './styles.css'
import './pagination.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)


if ('serviceWorker' in navigator) {
  if (import.meta.env.PROD) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => undefined))
  } else {
    window.addEventListener('load', async () => {
      const registrations = await navigator.serviceWorker.getRegistrations().catch(() => [])
      await Promise.all(registrations.map((registration) => registration.unregister()))
      if ('caches' in window) {
        const keys = await caches.keys().catch(() => [])
        await Promise.all(keys.filter((key) => key.startsWith('wildlens') || key.startsWith('shijing')).map((key) => caches.delete(key)))
      }
    })
  }
}
