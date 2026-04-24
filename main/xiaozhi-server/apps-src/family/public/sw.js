// 家属端 Service Worker - 仅做壳缓存，API/SSE/上传不拦截
const CACHE_NAME = 'hospice-family-v2';
const SHELL = [
    '/family/',
    '/family/index.html',
    '/family/manifest.json',
];

self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(SHELL).catch(() => {})));
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
    event.respondWith(
        caches.match(event.request).then(r => r || fetch(event.request))
    );
});
