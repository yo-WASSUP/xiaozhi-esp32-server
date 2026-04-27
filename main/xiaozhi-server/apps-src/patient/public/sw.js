// 患者端 Service Worker - 仅做壳缓存，API/SSE/WS/上传不拦截
// v3: index.html 改 network-first，避免 Vite 新构建后引用旧 hash 资源
const CACHE_NAME = 'hospice-patient-v3';
const SHELL = [
    '/patient/manifest.json',
];

self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(SHELL).catch(() => { })));
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    if (url.pathname.startsWith('/api/')
        || url.pathname.startsWith('/hospice-media/')
        || url.pathname.startsWith('/shared/')
        || url.pathname.startsWith('/test-assets/')
        || url.pathname.startsWith('/xiaozhi/')
        || url.pathname.includes('/assets/')
        || event.request.method !== 'GET') {
        return;
    }
    // index.html 走 network-first
    if (url.pathname === '/patient/' || url.pathname === '/patient/index.html') {
        event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request))
        );
        return;
    }
    event.respondWith(
        caches.match(event.request).then(r => r || fetch(event.request))
    );
});
