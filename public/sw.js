// No personal records or API responses are cached. Local pilot remains online-first.
const VERSION = 'opulent-1.2.2';
self.addEventListener('install', () => {});
self.addEventListener('activate', event => event.waitUntil(Promise.all([self.clients.claim(), caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('opulent-')).map(k => caches.delete(k))))])));
self.addEventListener('message', event => { if(event.data === 'ACTIVATE') self.skipWaiting(); });
self.addEventListener('fetch', event => { if(event.request.mode === 'navigate') event.respondWith(fetch(event.request).catch(() => new Response('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width"><title>Opulent offline</title><body><h1>Opulent cannot reach the server</h1><p>Start Opulent on the server PC, then reconnect and refresh. Financial changes cannot be saved offline.</p></body></html>', {headers:{'Content-Type':'text/html; charset=utf-8'}}))); });
