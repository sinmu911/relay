// 중계현황 설치 앱 서비스워커: 저장(캐시) 안 함. 폰 알림(위험 차량) 받아서 띄움.
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
// 09-30 사용자 '업데이트해도 재설치 없이': 화면(html)은 늘 서버에서 새로 받는다(깃허브 페이지 10분 캐시도 건너뜀) → 올리면 다음 열 때 바로 새 화면
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method === 'GET' && (r.mode === 'navigate' || /\.(html|json|js)$/.test(new URL(r.url).pathname)) && new URL(r.url).origin === self.location.origin) {
    e.respondWith(fetch(r, {cache: 'no-store'}).catch(() => fetch(r)));
  }
});
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = {body: e.data ? e.data.text() : ''}; }
  const opt = {body: d.body || '', icon: 'icon-192.png', badge: 'icon-192.png', tag: d.tag || 'relay', renotify: true,
               silent: !!d.silent, requireInteraction: !!d.sticky, data: {url: './?app=1'}};
  if (!d.silent) opt.vibrate = [200, 100, 200];
  e.waitUntil(self.registration.showNotification(d.title || '중계현황', opt));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(ws => {
    for (const w of ws) { if ('focus' in w) return w.focus(); }
    return self.clients.openWindow('./?app=1');
  }));
});
