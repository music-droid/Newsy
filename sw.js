/* Newsy service worker — cache the shell; keep briefings fresh. */
const SHELL_CACHE = "newsy-shell-v1";
const DATA_CACHE = "newsy-data-v1";

const SHELL_URLS = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(function (cache) {
      return cache.addAll(SHELL_URLS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (k) {
            return k !== SHELL_CACHE && k !== DATA_CACHE;
          })
          .map(function (k) {
            return caches.delete(k);
          })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

function isBriefingsRequest(url) {
  return (
    url.pathname.endsWith("/data/briefings.json") ||
    url.pathname.endsWith("briefings.json")
  );
}

self.addEventListener("fetch", function (event) {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Network-first for briefing data so updates show up; fall back to cache offline
  if (isBriefingsRequest(url)) {
    event.respondWith(
      caches.open(DATA_CACHE).then(function (cache) {
        return fetch(req)
          .then(function (res) {
            if (res && res.ok) {
              cache.put(req, res.clone());
            }
            return res;
          })
          .catch(function () {
            return cache.match(req).then(function (cached) {
              return cached || Response.error();
            });
          });
      })
    );
    return;
  }

  // Same-origin shell: network-first, fall back to cache (offline)
  if (url.origin === self.location.origin) {
    event.respondWith(
      fetch(req)
        .then(function (res) {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(SHELL_CACHE).then(function (cache) {
              cache.put(req, copy);
            });
          }
          return res;
        })
        .catch(function () {
          return caches.match(req).then(function (cached) {
            if (cached) return cached;
            if (req.mode === "navigate") {
              return caches.match("./index.html");
            }
            return undefined;
          });
        })
    );
  }
});
