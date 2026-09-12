const CACHE_NAME = "gwi-mobile-v2";
const PRECACHE_URLS = [
  "/manifest.json",
  "/manifest-admin.json",
  "/manifest-student.json",
  "/static/icons/admin-192.png",
  "/static/icons/admin-512.png",
  "/static/icons/student-192.png",
  "/static/icons/student-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
