// 설치 조건용 최소 서비스워커: 저장(캐시) 안 함, 그대로 네트워크로 보냄
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {});
