# Newsy

A calm, static page for Justin’s bounded news briefings. Not a news portal — just the latest write-up with sources under each beat.

## Files

- `index.html` — viewer
- `styles.css` — warm, quiet typography
- `app.js` — loads and renders briefings
- `data/briefings.json` — array of briefing objects, **newest first** (each beat has a short `headline`)
- `data/latest.json` — newest briefing only (id, label, generatedAt, url, beat titles + headlines); for the Scriptable widget
- `build-latest.py` — regenerates `data/latest.json` from `briefings.json` (includes `audio` when set)
- `build-podcast.py` — TTS + soft ambient bed → `audio/{id}.mp3`; sets `audio` on the briefing
- `build-newsy.py` — rebuilds self-contained `newsy.html` with embedded briefings
- `audio/` — MP3 podcast files for briefings that have a Listen player
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

## Podcast / Listen

Each briefing can have a spoken version with a quiet ambient bed under the voice.

```bash
# one-time: venv + edge-tts (system pip is PEP 668 locked)
python3 -m venv .venv
.venv/bin/pip install edge-tts

# newest briefing, or pass an id
.venv/bin/python build-podcast.py
.venv/bin/python build-podcast.py 2026-10-07-morning

# refresh widget feed + offline reader after audio is written
python3 build-latest.py
python3 build-newsy.py
```

`build-podcast.py` reads the briefing, strips HTML to spoken prose, synthesizes with edge-tts (`en-US-AndrewNeural`), then mixes a soft sine-pad + filtered pink-noise bed about **−28 dB** under the voice (ffmpeg), with fade in/out. Output: `audio/{id}.mp3`. The site header shows a Listen control when `audio` is set on that briefing.

