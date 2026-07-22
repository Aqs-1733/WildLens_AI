const CACHE = 'wildlens-shell-v2'
const SHELL = ['/', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png']
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL))))
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))))
self.addEventListener('fetch', event => {
  const request = event.request
  if (request.method !== 'GET' || new URL(request.url).pathname.startsWith('/api/')) return
  event.respondWith(fetch(request).then(response => {
    const copy = response.clone()
    caches.open(CACHE).then(cache => cache.put(request, copy))
    return response
  }).catch(() => caches.match(request).then(hit => hit || caches.match('/'))))
})
