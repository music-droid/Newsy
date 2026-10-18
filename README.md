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

`build-podcast.py` reads the briefing, strips HTML to spoken prose, synthesizes each clip with edge-tts (anchor `en-US-AndrewNeural`, one "reporter" voice per beat), then mixes a soft sine-pad + filtered pink-noise bed about **−28 dB** under the voice (ffmpeg), with intro/outro swells. Output: `audio/{id}.mp3`. The site header shows a Listen control when `audio` is set on that briefing.

### Podcast format (Oct 17, 2026; podcast only, the website layout is separate)

1. Intro swell → anchor: **"Welcome back to Newsy."** → **"Here's what's ahead: A, B, C, and D."**
   Built from beat-headline clauses (lead beat's top two, then beats with new-at-this-hour items).
   Override per briefing with a top-level `"podcastPreview": "..."` string.
2. Beats in site order. The section name is said once (beat voice), then each story's **body**
   is read directly. **Headlines are never read.** ~0.95 s silence between stories, 0.6 s after the
   section name, 1.6 s between sections.
3. **No separate "New at this hour" segment.** Each `newAtThisHour` item is folded into its own beat
   and read first there; if the beat already has a fuller version of the story (word-overlap match),
   that story is moved to the front instead of being read twice.
4. Anchor: **"Viva Cristo Rey."** → outro swell.

Speech cleanup before TTS (`speakable()`): HTML/markup sanitization → `normalize_for_speech()`
(St./Fr./Msgr./Card. → Saint/Father/Monsignor/Cardinal, ET → Eastern, Q3 → the third quarter,
% → percent, $1.2B → 1.2 billion dollars, vs. → versus, Oct. → October, mph/km/h, Leo XIV → Leo the
Fourteenth, Artemis III → Artemis Three, 43–21 / 10 a.m.–6 p.m. → "to", RFK Jr., LC-36A) →
`pronunciations.json` (whole-word, case-insensitive phonetic respellings such as
Medjugorje → Med-joo-gor-yeh; add names there as they come up). Clips are level-matched to about
−20 dB mean so voice changes don't jump. Per-voice prosody lives in `VOICE_PROSODY` (default rate −5%).

edge-tts cannot take custom SSML (no `<break>`, `<phoneme>`, `<lexicon>`, `express-as` styles);
only rate, volume, and pitch. Any markup sent as text is read aloud, so the script asserts no
`<`/`>`, no "ms"/"break time" artifacts, and no "nothing to report" phrasing.

`.venv/bin/python build-podcast.py --show [id]` prints every clip (kind, voice, pause, exact text).

## v2 schema (Oct 16, 2026)

Each beat: `{id, title, headline, image?, stories:[{headline, body, sources, why?, image?}], sources?, carried?}`.
Legacy beats with only `body` still render. Evening bulletins add top-level
`newAtThisHour: [{beat, headline, body, sources}]`; beats with no new news repeat the
morning's stories with `"carried": true` (shown as "Continuing from this morning"). Optional `topLine`.

Per-run pipeline: write briefing → `python3 fetch-images.py` → `.venv/bin/python build-podcast.py`
→ `python3 prune.py` (keeps newest 7; prints DELETED paths to `git rm`) → `python3 build-latest.py` → `python3 build-newsy.py`.
