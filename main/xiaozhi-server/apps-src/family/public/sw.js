// 家属端 Service Worker - 仅做壳缓存，API/SSE/上传不拦截
// v3: index.html 改 network-first，避免 Vite 重新构建后引用了不存在的 hash 资源
const CACHE_NAME = 'hospice-family-v3';
const SHELL = [
    '/family/manifest.json',
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
    // API / SSE / WS / 媒体 / 共享脚本 / hash 资源都走网络
    if (url.pathname.startsWith('/api/')
        || url.pathname.startsWith('/hospice-media/')
        || url.pathname.startsWith('/shared/')
        || url.pathname.includes('/assets/')
        || event.request.method !== 'GET') {
        return;
    }
    // index.html 走 network-first：每次构建新 hash，缓存的旧 HTML 会引用 404 资源
    if (url.pathname === '/family/' || url.pathname === '/family/index.html') {
        event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request))
        );
        return;
    }
    event.respondWith(
        caches.match(event.request).then(r => r || fetch(event.request))
    );
});
