# Add Newsy to your Home Screen

PWA install works only after the multi-file site is served over a stable **HTTPS** URL (or `localhost` while testing). Opening `newsy.html` as a single file works for offline reading, but browsers will not install it as an app from `file://`.

## iPhone / iPad (Safari)

1. Open the Newsy HTTPS URL in **Safari** (not Chrome or in-app browsers).
2. Tap the **Share** button (square with an upward arrow).
3. Scroll and tap **Add to Home Screen**.
4. Confirm the name (**Newsy**) and tap **Add**.

The icon opens Newsy in standalone mode (no Safari chrome).

## Android (Chrome)

1. Open the Newsy HTTPS URL in **Chrome**.
2. Tap the menu (⋮), then **Install app** or **Add to Home screen** (wording varies by Chrome version).
3. Confirm **Install** / **Add**.

You can also use the install banner if Chrome shows one. The icon opens Newsy as a standalone app.

## Notes

- After deploy, hard-refresh once so the service worker can cache the shell.
- Briefings update via the network when available; the last cached `data/briefings.json` is used offline.
