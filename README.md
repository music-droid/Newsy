# Newsy

A calm, static page for Justin’s bounded news briefings. Not a news portal — just the latest write-up with sources under each beat.

## Files

- `index.html` — viewer
- `styles.css` — warm, quiet typography
- `app.js` — loads and renders briefings
- `data/briefings.json` — array of briefing objects, **newest first** (each beat has a short `headline`)
- `data/latest.json` — newest briefing only (id, label, generatedAt, url, beat titles + headlines); for the Scriptable widget
- `build-latest.py` — regenerates `data/latest.json` from `briefings.json`
- `widget/` — Scriptable iPhone Home Screen widget (`newsy-widget.js` + setup notes)

## View locally

Serve the folder (browsers block `fetch` of local JSON via `file://`):

```bash
cd news-briefing-site
python3 -m http.server 8080
```

Open `http://localhost:8080/`.

On GitHub Pages, publish from this folder (or the repo root if this *is* the root). Paths are relative.

## Add a briefing

1. Open `data/briefings.json`.
2. **Prepend** a new object at the top of the array (keep newest first).
3. Shape:

```json
{
  "id": "YYYY-MM-DD-morning",
  "date": "YYYY-MM-DD",
  "slot": "morning",
  "label": "Monday morning",
  "generatedAt": "YYYY-MM-DDTHH:MM:SS-04:00",
  "beats": [
    {
      "id": "world",
      "title": "World",
      "headline": "Short factual line, 12 words max.",
      "body": "<p>Prose here.</p>",
      "sources": [
        { "name": "Outlet", "url": "https://..." }
      ]
    }
  ]
}
```

`slot` is one of: `morning` | `noon` | `evening`.

Beats in order when present: **World**, **Catholic**, **Signs of the times**, **Miami**, **Pick-me-up**. Omit a beat only if truly empty; otherwise include a quiet one-liner. Put sources under that beat only. Use real URLs; if you cannot verify a URL, omit `url` and keep the outlet `name`.

4. Save. Reload the page. The new chip appears first; the default view is the newest briefing.

## Widget / latest.json

After editing `data/briefings.json` (and adding a `headline` on each beat, 12 words max), regenerate the widget feed:

```bash
python3 build-latest.py
```

That writes `data/latest.json` for the Scriptable widget. See `widget/README.md` for iPhone setup.
