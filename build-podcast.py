#!/usr/bin/env python3
"""Generate a spoken MP3 for a Newsy briefing via edge-tts, with a soft ambient bed.

Structure of each episode (podcast only; the website layout is independent):
  [intro swell] -> anchor: "Welcome back to Newsy." -> anchor: "Here's what's ahead: ..."
  (3-4 top items) -> each beat in site order: section name (beat voice), then each
  story BODY read directly (headlines are never read), short silence between stories,
  longer silence between sections -> anchor: "Viva Cristo Rey." -> [outro swell].

There is no separate "New at this hour" / breaking segment. Evening newAtThisHour items
are folded into their own beat and read first there (if the beat already has a fuller
version of the same story, that story is moved to the front instead of read twice).

Text goes through normalize_for_speech() (abbreviations, money, papal numerals, months,
scores) and pronunciations.json (phonetic respellings) before TTS. No SSML/markup is ever
sent: edge-tts only allows rate/volume/pitch and reads tags like <break/> out loud.

Usage:
  build-podcast.py                 # newest briefing
  build-podcast.py <briefing-id>   # one briefing
  build-podcast.py --all           # every briefing that already has an audio field
  build-podcast.py --show [<id>]   # print the exact TTS text per clip, no audio
"""
from __future__ import annotations

import asyncio
import html
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIEFINGS = ROOT / "data" / "briefings.json"
AUDIO_DIR = ROOT / "audio"

# --- Voices -----------------------------------------------------------------
# Anchor reads the opener and sign-off. Each beat gets its own "reporter".
ANCHOR_VOICE = "en-US-AndrewNeural"
DEFAULT_BEAT_VOICE = "en-US-GuyNeural"  # unknown / new beat titles
FALLBACK_VOICE = "en-US-GuyNeural"      # if a voice errors at synthesis time

# Matched case-insensitively by keyword against the beat title (first match wins,
# so specific keys come before generic ones: "Musk world" must hit "musk").
BEAT_VOICES: dict[str, str] = {
    "maga": "en-US-ChristopherNeural",
    "maha": "en-US-ChristopherNeural",
    "promise": "en-US-ChristopherNeural",
    "musk": "en-US-BrianNeural",
    "nasa": "en-US-AvaNeural",       # checked before "space"
    "space": "en-US-EmmaNeural",
    "catholic": "en-US-AriaNeural",
    "signs": "en-US-JennyNeural",
    "miami": "en-US-SteffanNeural",
    "pick": "en-US-EricNeural",
    "world": "en-GB-RyanNeural",
}

# Prosody per voice (the only knobs edge-tts allows). A touch slower than default reads
# less clipped/robotic; pitch is left alone (shifting it sounds synthetic).
DEFAULT_PROSODY = {"rate": "-5%", "pitch": "+0Hz", "volume": "+0%"}
VOICE_PROSODY: dict[str, dict[str, str]] = {
    "en-US-AndrewNeural": {"rate": "-3%"},     # anchor: keep the open snappy
    "en-GB-RyanNeural": {"rate": "-4%"},
    "en-US-BrianNeural": {"rate": "-3%"},
    "en-US-JennyNeural": {"rate": "-7%"},      # reads fast by default
    "en-US-AriaNeural": {"rate": "-6%"},
}


def prosody_for(voice: str) -> dict[str, str]:
    return {**DEFAULT_PROSODY, **VOICE_PROSODY.get(voice, {})}


# Exact spoken bookends (anchor voice).
OPENER_TEXT = "Welcome back to Newsy."
PREVIEW_PREFIX = "Here's what's ahead:"
PREVIEW_MAX_ITEMS = 4
CLOSER_TEXT = "Viva Cristo Rey."

# --- Timing / levels ----------------------------------------------------------
STORY_PAUSE_S = 0.95           # silence between stories inside a section
TITLE_PAUSE_S = 0.6            # after the section name, before its first story
OPENER_PAUSE_S = 0.45          # between "Welcome back to Newsy." and the preview
SECTION_PAUSE_S = 1.6          # silence between sections (longer than story pause)
LEVEL_TARGET_DB = -20.0        # per-clip mean loudness, so voice changes don't jump
AMBIENT_REL_DB = -28.0         # bed under the voice
SWELL_REL_DB = -15.0           # intro/outro swell level (same scale)
INTRO_HOLD_S = 5.5             # ambient alone at swell level
RAMP_S = 2.0                   # swell <-> bed ramps
VOICE_START_S = INTRO_HOLD_S + 1.5   # voice enters as the ramp down finishes
OUTRO_GAP_S = 0.6              # after last word, before the ramp up
OUTRO_HOLD_S = 4.5
OUTRO_FADE_S = 3.0
SAMPLE_RATE = 44100


# --- Text cleanup -------------------------------------------------------------
def strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", ". ", text)
    text = re.sub(r"(?i)</(p|li|h[1-6])>", ". ", text)
    text = re.sub(r"<[^>]*>", " ", text)
    return text


def sanitize_for_tts(raw: str) -> str:
    """Turn briefing HTML/markdown-ish text into plain speakable prose."""
    text = strip_html(raw)
    # Entities, twice to catch double-encoded "&amp;amp;"
    text = html.unescape(html.unescape(text))
    text = re.sub(r"<[^>]*>", " ", text)          # tags revealed by unescape
    text = text.replace("<", " ").replace(">", " ")
    text = text.replace("\xa0", " ")
    # URLs / bare domains with paths
    text = re.sub(r"(?i)\bhttps?://\S+", " ", text)
    text = re.sub(r"(?i)\bwww\.\S+", " ", text)
    # Markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("&", " and ")
    # Slashes: "A / B" -> "A and B"; keep digit/digit (dates, scores); else space
    text = re.sub(r"\s+/\s+", " and ", text)
    text = re.sub(r"(?<!\d)/|/(?!\d)", " ", text)
    text = re.sub(r"#(\d)", r"number \1", text)
    # Stray markup symbols
    text = re.sub(r"[*_#|\\\[\]{}~^`=+]", " ", text)
    text = re.sub(r"[ \t\r\n]+", " ", text)
    text = re.sub(r"(\s*\.\s*){2,}", ". ", text)
    text = re.sub(r"([.!?…][\"'”’)]+)\s*\.", r"\1", text)  # '.”.' -> '.”'
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"^[\s.,;:]+", "", text)
    return text.strip()


# --- Speech normalization (podcast only) -----------------------------------------
_ORD = ["", "First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth",
        "Ninth", "Tenth", "Eleventh", "Twelfth", "Thirteenth", "Fourteenth", "Fifteenth",
        "Sixteenth", "Seventeenth", "Eighteenth", "Nineteenth", "Twentieth",
        "Twenty-first", "Twenty-second", "Twenty-third"]
_CARD = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
         "Eighteen", "Nineteen", "Twenty"]
_REGNAL = (r"Leo|Pius|Benedict|Gregory|Innocent|Clement|Urban|Boniface|Paul|John Paul|John|"
           r"Francis|Sixtus|Alexander|Charles|Henry|Edward|George|Elizabeth|Louis|Philip|"
           r"Felipe|William|Richard|James|Frederick|Constantine")
_CARDINAL_AFTER = r"World War|Artemis|Apollo|Vatican|Gemini|Super Bowl|Season|Part|Chapter|Title|Phase|Starship V|Falcon|Block"
_MONTHS = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
           "Jun": "June", "Jul": "July", "Aug": "August", "Sep": "September",
           "Sept": "September", "Oct": "October", "Nov": "November", "Dec": "December"}
_QUARTERS = {"1": "first", "2": "second", "3": "third", "4": "fourth"}
_SCALE = {"K": "thousand", "M": "million", "B": "billion", "T": "trillion",
          "bn": "billion", "mn": "million", "tn": "trillion"}
# (pattern, replacement) — applied in order, all case-sensitive unless (?i)
_ABBREV: list[tuple[str, str]] = [
    (r"\bRFK Jr\.", "R F K Junior"),
    (r"\bJr\.", "Junior"),
    (r"\bSr\.(?=\s+[A-Z])", "Sister"),
    (r"\bSts\.(?=\s+[A-Z])", "Saints"),
    (r"\bSt\.(?=\s+[A-Z])", "Saint"),
    (r"\bFr\.(?=\s+[A-Z])", "Father"),
    (r"\bMsgr\.(?=\s+[A-Z])", "Monsignor"),
    (r"\bAbp\.(?=\s+[A-Z])", "Archbishop"),
    (r"\bBp\.(?=\s+[A-Z])", "Bishop"),
    (r"\bCard\.(?=\s+[A-Z])", "Cardinal"),
    (r"\bProf\.(?=\s+[A-Z])", "Professor"),
    (r"\bGen\.(?=\s+[A-Z])", "General"),
    (r"\bGov\.(?=\s+[A-Z])", "Governor"),
    (r"\bSen\.(?=\s+[A-Z])", "Senator"),
    (r"\bRep\.(?=\s+[A-Z])", "Representative"),
    (r"\bCapt?\.(?=\s+[A-Z])", "Captain"),
    (r"\bAve\.", "Avenue"),
    (r"\bBlvd\.", "Boulevard"),
    (r"\bHwy\.", "Highway"),
    (r"\bvs?\.(?=\s)", "versus"),
    (r"\bapprox\.", "approximately"),
    (r"\be\.g\.,?", "for example,"),
    (r"\bi\.e\.,?", "that is,"),
    (r"\betc\.", "et cetera."),
    (r"\bthe WHO\b", "the W.H.O."),
    (r"\bmph\b", "miles per hour"),
    (r"\bkm/h\b|(?<=\d)\s?km h\b", " kilometers per hour"),
    (r"(?<=\d)\s?km\b", " kilometers"),
    (r"(?<=\d)\s?mi\b", " miles"),
    (r"\bLC-(\d+)([A-Z]?)\b", r"Launch Complex \1 \2"),
    (r"\bRS-25\b", "R S 25"),
    (r"\bQ([1-4])\b", lambda m: f"the {_QUARTERS[m.group(1)]} quarter"),
    (r"\b(?:ET|EDT|EST)\b", "Eastern"),
    (r"\b(?:PT|PDT|PST)\b", "Pacific"),
    (r"\bGMT\b|\bUTC\b", "G M T"),
]


def _money(m: re.Match) -> str:
    num, scale = m.group(1), m.group(2) or ""
    word = _SCALE.get(scale.strip(), scale.strip())
    if word:
        return f"{num} {word} dollars"
    return f"{num} dollars" if num != "1" else "1 dollar"


def normalize_for_speech(text: str) -> str:
    t = text
    # Dashes as pauses; digit–digit (scores, ranges) -> "to"
    t = re.sub(r"(?<=\d)\s?[–—]\s?(?=\d)", " to ", t)
    t = re.sub(r"\s+[—–]\s+|—", ", ", t)
    t = re.sub(r"(?<=[A-Za-z.])\s?–\s?(?=\d)", " to ", t)          # "noon–5" -> "noon to 5"
    t = re.sub(r"(?<=\w)–(?=\w)", "-", t)                   # "Tesla–SpaceX" -> hyphen
    # Money: $1.2B, $330 million, $250,000
    t = re.sub(r"\$(\d[\d,]*(?:\.\d+)?)\s?(bn|mn|tn|[KMBT])\b", _money, t)
    # Plain "$250,000 deposits" / "$330 million factory" are left to the engine, which
    # already reads currency correctly (and handles adjective use: "a 330 million dollar ...").
    t = re.sub(r"(\d)\s?%", r"\1 percent", t)
    for pat, rep in _ABBREV:
        t = re.sub(pat, rep, t)
    # Months: "Oct. 16" / "Sept." -> full
    t = re.sub(r"\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.(?=\s*\d|\s+[a-z,])",
               lambda m: _MONTHS[m.group(1)], t)
    # Roman numerals: regnal names -> "the Fourteenth"; programs/events -> cardinal
    def roman(s: str) -> int:
        vals = {"I": 1, "V": 5, "X": 10, "L": 50}
        n = 0
        for i, ch in enumerate(s):
            v = vals[ch]
            n += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
        return n
    t = re.sub(rf"\b({_REGNAL})\s+([IVXL]+)\b(?![-’'])",
               lambda m: f"{m.group(1)} the {_ORD[roman(m.group(2))]}"
               if 0 < roman(m.group(2)) < len(_ORD) else m.group(0), t)
    t = re.sub(rf"\b({_CARDINAL_AFTER})\s+([IVXL]{{1,5}})\b",
               lambda m: f"{m.group(1)} {_CARD[roman(m.group(2))]}"
               if 0 < roman(m.group(2)) < len(_CARD) else m.group(0), t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r",\s*,", ",", t)
    return t.strip()


PRONUNCIATIONS_FILE = ROOT / "pronunciations.json"
_PRON_RE: re.Pattern | None = None
_PRON_MAP: dict[str, str] = {}


def apply_pronunciations(text: str) -> str:
    global _PRON_RE, _PRON_MAP
    if _PRON_RE is None:
        raw = {}
        if PRONUNCIATIONS_FILE.exists():
            raw = json.loads(PRONUNCIATIONS_FILE.read_text(encoding="utf-8"))
        _PRON_MAP = {k.lower(): v for k, v in raw.items() if not k.startswith("_") and v}
        keys = sorted(_PRON_MAP, key=len, reverse=True)
        _PRON_RE = re.compile(r"(?<![\w-])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w-])",
                              re.IGNORECASE) if keys else re.compile(r"(?!x)x")
    return _PRON_RE.sub(lambda m: _PRON_MAP[m.group(1).lower()], text)


def speakable(raw: str) -> str:
    """HTML -> sanitized prose -> spoken-form normalization -> pronunciation respellings."""
    return apply_pronunciations(normalize_for_speech(sanitize_for_tts(raw)))


def is_quiet_only(plain: str) -> bool:
    """Skip beats whose entire body is just 'quiet' (optional punctuation)."""
    cleaned = re.sub(r"[.!?…]+", "", plain or "").strip()
    return bool(re.fullmatch(r"(?i)quiet", cleaned))


def voice_for_beat(title: str) -> str:
    t = (title or "").lower()
    for key, voice in BEAT_VOICES.items():
        if key in t:
            return voice
    return DEFAULT_BEAT_VOICE


def with_period(s: str) -> str:
    s = s.strip()
    return s if re.search(r"[.!?…][\"'”’)]*$", s) else s + "."


# --- Episode structure -------------------------------------------------------------
_STOP = set("""the a an and or of to in on at for from with by as is are was were be been this
that these those its it his her their our your after before over under into about than then
says said will would could also just more most still now new news who what when where which
while amid near only some into onto off out up down sunday monday tuesday wednesday thursday
friday saturday tonight today morning evening""".split())


def _tokens(*parts: str) -> set[str]:
    words = re.findall(r"[a-z0-9’']+", " ".join(sanitize_for_tts(p or "") for p in parts).lower())
    return {w.strip("’'") for w in words if len(w) >= 4 and w not in _STOP}


def _beat_for_item(item: dict, beats: list[dict]) -> dict | None:
    key = (item.get("beat") or "").lower()
    for b in beats:
        if (b.get("id") or "").lower() == key:
            return b
    for b in beats:
        if key and key in (b.get("title") or "").lower():
            return b
    return None


def ordered_stories(beat: dict, fresh: list[dict]) -> list[dict]:
    """Beat stories with this beat's new-at-this-hour items first. A fresh item that matches
    an existing (fuller) story promotes that story; an unmatched one is read as its own story."""
    stories = list(beat.get("stories") or [])
    if not stories and beat.get("body"):
        stories = [{"body": beat.get("body")}]
    front: list[dict] = []
    used: set[int] = set()
    for item in fresh:
        it = _tokens(item.get("headline", ""), item.get("body", ""))
        best, best_score = None, 0.0
        for i, st in enumerate(stories):
            if i in used:
                continue
            stt = _tokens(st.get("headline", ""), st.get("body", ""))
            if it and stt:
                score = len(it & stt) / min(len(it), len(stt))
                if score > best_score:
                    best, best_score = i, score
        if best is not None and best_score >= 0.3:
            used.add(best)
            front.append(stories[best])
        else:
            front.append({"headline": item.get("headline"), "body": item.get("body")})
    return front + [st for i, st in enumerate(stories) if i not in used]


def _clause_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + ", and " + items[-1]


def build_preview(briefing: dict) -> str:
    """'Here's what's ahead: A, B, C, and D.' — from beat headline clauses, preferring beats
    with new-at-this-hour items. Override with a briefing-level 'podcastPreview' string."""
    custom = (briefing.get("podcastPreview") or "").strip()
    if custom:
        return with_period(custom if custom.lower().startswith("here") else f"{PREVIEW_PREFIX} {custom}")
    beats = [b for b in briefing.get("beats") or [] if b.get("headline")]
    fresh_beats = {(n.get("beat") or "").lower() for n in briefing.get("newAtThisHour") or []}

    def clauses(b: dict) -> list[str]:
        h = sanitize_for_tts(b.get("headline") or "").rstrip(".!")
        return [c.strip() for c in re.split(r";\s*", h) if c.strip()]

    ordered: list[str] = []
    if beats:
        ordered += clauses(beats[0])[:2]                      # lead beat: top two
    for b in beats[1:]:
        if (b.get("id") or "").lower() in fresh_beats:
            ordered += clauses(b)[:1]
    for b in beats[1:]:
        if (b.get("id") or "").lower() not in fresh_beats:
            ordered += clauses(b)[:1]
    picked: list[str] = []
    seen: list[set[str]] = []
    for c in ordered:
        tk = _tokens(c)
        if any(tk and len(tk & s) / max(1, min(len(tk), len(s))) >= 0.5 for s in seen):
            continue
        picked.append(c[0].lower() + c[1:] if re.match(r"[A-Z][a-z]+\b", c) and c.split()[0].lower() in _STOP | {"record-low"} else c)
        seen.append(tk)
        if len(picked) >= PREVIEW_MAX_ITEMS:
            break
    if not picked:
        top = sanitize_for_tts(briefing.get("topLine") or "")
        return f"{PREVIEW_PREFIX} {with_period(top)}" if top else ""
    return f"{PREVIEW_PREFIX} {_clause_list(picked)}."


def build_segments(briefing: dict) -> list[dict]:
    """Return clips [{voice, text, pause, kind}] in play order. 'pause' is the silence
    after the clip. Headlines are never spoken."""
    segs: list[dict] = [{"voice": ANCHOR_VOICE, "text": OPENER_TEXT, "pause": OPENER_PAUSE_S, "kind": "opener"}]
    preview = build_preview(briefing)
    if preview:
        segs.append({"voice": ANCHOR_VOICE, "text": apply_pronunciations(normalize_for_speech(preview)),
                     "pause": SECTION_PAUSE_S, "kind": "preview"})
    else:
        segs[-1]["pause"] = SECTION_PAUSE_S
    beats = briefing.get("beats") or []
    fresh_by_beat: dict[int, list[dict]] = {}
    for item in briefing.get("newAtThisHour") or []:
        b = _beat_for_item(item, beats)
        if b is not None:
            fresh_by_beat.setdefault(id(b), []).append(item)
    for beat in beats:
        voice = voice_for_beat(beat.get("title") or "")
        bodies = []
        for st in ordered_stories(beat, fresh_by_beat.get(id(beat), [])):
            body = speakable(st.get("body") or "")
            if body and not is_quiet_only(body):
                bodies.append(with_period(body))
        if not bodies:
            continue
        title = apply_pronunciations(sanitize_for_tts(beat.get("title") or beat.get("id") or "Next").rstrip("."))
        segs.append({"voice": voice, "text": f"{title}.", "pause": TITLE_PAUSE_S, "kind": "section"})
        for i, body in enumerate(bodies):
            last = i == len(bodies) - 1
            segs.append({"voice": voice, "text": body, "kind": "story",
                         "pause": SECTION_PAUSE_S if last else STORY_PAUSE_S})
    segs.append({"voice": ANCHOR_VOICE, "text": CLOSER_TEXT, "pause": 0.0, "kind": "closer"})
    for s in segs:
        text = s["text"]
        assert "<" not in text and ">" not in text, f"markup left in TTS text: {text[:120]}"
        assert not re.search(r"(?i)break\s*time|\d+\s*ms\b", text), f"break artifact: {text[:120]}"
        assert not re.search(r"(?i)nothing (new )?to report|no new (news|reports?)", text), \
            f"'nothing to report' phrasing — repeat or develop the story instead: {text[:120]}"
        assert not re.match(r"(?i)new at this hour", text), "separate breaking segment must not be spoken"
    return segs


# --- Audio ----------------------------------------------------------------------
async def synth_one(text: str, voice: str, out_path: Path) -> str:
    import edge_tts

    last: Exception | None = None
    for attempt, v in enumerate([voice, voice, FALLBACK_VOICE]):
        try:
            await edge_tts.Communicate(text, v, **prosody_for(v)).save(str(out_path))
            if out_path.exists() and out_path.stat().st_size > 1000:
                return v
            raise RuntimeError("empty TTS output")
        except Exception as err:  # network hiccups, bad voice, etc.
            last = err
            print(f"  TTS {v} attempt {attempt + 1} failed: {err}")
            await asyncio.sleep(2 + attempt * 2)
    raise SystemExit(f"TTS failed for segment: {last}")


async def synth_all(segs: list[dict], tmp: Path) -> list[Path]:
    sem = asyncio.Semaphore(3)
    paths = [tmp / f"seg{i:03d}.mp3" for i in range(len(segs))]

    async def run(i: int) -> None:
        async with sem:
            used = await synth_one(segs[i]["text"], segs[i]["voice"], paths[i])
            print(f"  seg{i:03d} {segs[i]['kind']:<7} {used} ({len(segs[i]['text'])} chars)")

    await asyncio.gather(*(run(i) for i in range(len(segs))))
    return paths


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    ).strip()
    return float(out)


def mean_volume_db(path: Path) -> float | None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect",
                           "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", proc.stderr)
    return float(m.group(1)) if m else None


def build_voice_track(seg_paths: list[Path], segs: list[dict], tmp: Path) -> Path:
    """Decode clips to PCM (trimmed, level-matched) and join them with true digital silence:
    STORY_PAUSE_S between stories, SECTION_PAUSE_S between sections, etc."""
    silences: dict[float, Path] = {}

    def silence(sec: float) -> Path:
        key = round(sec, 3)
        if key not in silences:
            p = tmp / f"silence_{int(key * 1000)}.wav"
            ff("-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
               "-t", f"{key}", "-c:a", "pcm_s16le", str(p))
            silences[key] = p
        return silences[key]

    wavs: list[Path] = []
    for p in seg_paths:
        raw = p.with_suffix(".raw.wav")
        # trim TTS leading/trailing near-silence so pauses are consistent
        ff("-i", str(p), "-af",
           "silenceremove=start_periods=1:start_threshold=-50dB,"
           "areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
           "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(raw))
        mv = mean_volume_db(raw)
        gain = max(-6.0, min(6.0, LEVEL_TARGET_DB - mv)) if mv is not None else 0.0
        w = p.with_suffix(".wav")
        ff("-i", str(raw), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.95",
           "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(w))
        wavs.append(w)
    lst = tmp / "concat.txt"
    lines: list[str] = []
    for i, w in enumerate(wavs):
        lines.append(f"file '{w}'")
        pause = segs[i]["pause"]
        if i < len(wavs) - 1 and pause > 0:
            lines.append(f"file '{silence(pause)}'")
    lst.write_text("\n".join(lines) + "\n")
    voice = tmp / "voice.wav"
    ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "pcm_s16le", str(voice))
    return voice


def gain_expr(voice_dur: float) -> tuple[str, float]:
    """dB envelope on t for the ambient bed; returns (volume expr, total length)."""
    s, b = SWELL_REL_DB, AMBIENT_REL_DB
    r1 = INTRO_HOLD_S
    r2 = INTRO_HOLD_S + RAMP_S
    o1 = VOICE_START_S + voice_dur + OUTRO_GAP_S
    o2 = o1 + RAMP_S
    total = o2 + OUTRO_HOLD_S + OUTRO_FADE_S
    ease = lambda a, w: f"(1-cos(PI*(t-{a:.3f})/{w:.3f}))/2"  # noqa: E731
    db = (
        f"if(lt(t,{r1:.3f}),{s},"
        f"if(lt(t,{r2:.3f}),{s}+({b}-({s}))*{ease(r1, RAMP_S)},"
        f"if(lt(t,{o1:.3f}),{b},"
        f"if(lt(t,{o2:.3f}),{b}+({s}-({b}))*{ease(o1, RAMP_S)},"
        f"{s}))))"
    )
    return f"pow(10,({db})/20)", total


def mix_episode(voice_wav: Path, final_path: Path) -> dict:
    voice_dur = probe_duration(voice_wav)
    if not math.isfinite(voice_dur) or voice_dur <= 0:
        raise SystemExit(f"Bad voice duration for {voice_wav}")
    vol, total = gain_expr(voice_dur)
    fade_st = total - OUTRO_FADE_S
    # Same soft bed as before: low sine fifths + whisper of filtered pink noise.
    pad = (
        "aevalsrc=exprs="
        "0.55*sin(2*PI*110*t)+0.40*sin(2*PI*164.81*t)"
        "+0.28*sin(2*PI*220*t)+0.08*sin(2*PI*329.63*t)"
        f":d={total:.3f}:s={SAMPLE_RATE}"
    )
    noise = f"anoisesrc=color=pink:amplitude=0.15:d={total:.3f}:sample_rate={SAMPLE_RATE}"
    delay_ms = int(round(VOICE_START_S * 1000))
    fc = (
        "[1]lowpass=f=900,highpass=f=60,volume=0.7[pad];"
        "[2]highpass=f=120,lowpass=f=600,volume=0.25[noise];"
        "[pad][noise]amix=inputs=2:duration=first:dropout_transition=0,"
        f"volume='{vol}':eval=frame,"
        "afade=t=in:st=0:d=1.5,"
        f"afade=t=out:st={fade_st:.3f}:d={OUTRO_FADE_S}[amb];"
        f"[0]aresample={SAMPLE_RATE},adelay={delay_ms}:all=1,apad,"
        f"atrim=0:{total:.3f}[vox];"
        "[vox][amb]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
        f"atrim=0:{total:.3f}[out]"
    )
    ff("-i", str(voice_wav), "-f", "lavfi", "-i", pad, "-f", "lavfi", "-i", noise,
       "-filter_complex", fc, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "4",
       "-ar", str(SAMPLE_RATE), "-ac", "1", str(final_path))
    return {"voice": voice_dur, "total": total, "voice_start": VOICE_START_S,
            "outro_ramp": VOICE_START_S + voice_dur + OUTRO_GAP_S}


# --- Data -----------------------------------------------------------------------
def update_briefings_audio(data: list, briefing_id: str, rel_path: str) -> None:
    for item in data:
        if item.get("id") == briefing_id:
            item["audio"] = rel_path
            return
    raise SystemExit(f"Could not update audio field for {briefing_id}")


def generate(briefing: dict) -> str:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required")
    bid = briefing["id"]
    segs = build_segments(briefing)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    rel = f"audio/{bid}.mp3"
    out_path = ROOT / rel
    print(f"Generating podcast for {bid} ({len(segs)} clips)…")
    with tempfile.TemporaryDirectory(prefix="newsy-pod-") as tmpd:
        tmp = Path(tmpd)
        seg_paths = asyncio.run(synth_all(segs, tmp))
        voice = build_voice_track(seg_paths, segs, tmp)
        info = mix_episode(voice, tmp / "final.mp3")
        shutil.move(str(tmp / "final.mp3"), out_path)
    print(f"Wrote {rel} ({out_path.stat().st_size} bytes; voice {info['voice']:.1f}s, "
          f"total {info['total']:.1f}s, voice starts {info['voice_start']:.1f}s)")
    return rel


def main() -> None:
    args = sys.argv[1:]
    data = json.loads(BRIEFINGS.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise SystemExit("briefings.json is empty or not an array")
    by_id = {b.get("id"): b for b in data}

    if args and args[0] == "--show":
        b = by_id.get(args[1]) if len(args) > 1 else data[0]
        if not b:
            raise SystemExit("Briefing id not found")
        for s in build_segments(b):
            print(f"[{s['kind']} | {s['voice']} | pause {s['pause']}s] {s['text']}\n")
        return

    if args and args[0] == "--all":
        targets = [b for b in data if b.get("audio")]
    elif args:
        if args[0] not in by_id:
            raise SystemExit(f"Briefing id not found: {args[0]}")
        targets = [by_id[args[0]]]
    else:
        targets = [data[0]]

    for b in targets:
        rel = generate(b)
        update_briefings_audio(data, b["id"], rel)

    BRIEFINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated audio field(s) in briefings.json: {[b['id'] for b in targets]}")

    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_latest", ROOT / "build-latest.py")
    if spec and spec.loader:
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()


if __name__ == "__main__":
    main()
