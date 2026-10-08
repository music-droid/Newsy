#!/usr/bin/env python3
"""Generate a spoken MP3 for a Newsy briefing via edge-tts, with a soft ambient bed.

Structure of each episode:
  [intro swell: ambient alone, louder] -> anchor opener ("Welcome back to Newsy.") -> one clip per beat
  (each read by its own "reporter" voice, starting with the section name) ->
  anchor sign-off ("Viva Cristo Rey.") -> [outro swell: ambient back up, hold, fade out].

Sections are separated by real digital silence in the voice track (the
ambient bed keeps playing underneath). No SSML/markup is ever sent to TTS:
edge-tts reads tags like <break/> out loud as text.

Usage:
  build-podcast.py                 # newest briefing
  build-podcast.py <briefing-id>   # one briefing
  build-podcast.py --all           # every briefing that already has an audio field
  build-podcast.py --show <id>     # print the exact TTS text per segment, no audio
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

# Exact spoken bookends (anchor voice). No other bookend text.
OPENER_TEXT = "Welcome back to Newsy."
CLOSER_TEXT = "Viva Cristo Rey."

# --- Timing / levels ----------------------------------------------------------
SECTION_PAUSE_S = 1.3          # true silence between sections (voice track)
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


def build_segments(briefing: dict) -> list[tuple[str, str]]:
    """Return [(voice, text)] — opener, one per beat, sign-off."""
    segs: list[tuple[str, str]] = [(ANCHOR_VOICE, OPENER_TEXT)]
    for beat in briefing.get("beats") or []:
        plain = sanitize_for_tts(beat.get("body") or "")
        if not plain or is_quiet_only(plain):
            continue
        title = sanitize_for_tts(beat.get("title") or beat.get("id") or "Next").rstrip(".")
        segs.append((voice_for_beat(beat.get("title") or ""), f"{title}. {with_period(plain)}"))
    segs.append((ANCHOR_VOICE, CLOSER_TEXT))
    for voice, text in segs:
        assert "<" not in text and ">" not in text, f"markup left in TTS text: {text[:120]}"
        assert not re.search(r"(?i)break\s*time|\d+\s*ms\b", text), f"break artifact: {text[:120]}"
    return segs


# --- Audio ----------------------------------------------------------------------
async def synth_one(text: str, voice: str, out_path: Path) -> str:
    import edge_tts

    last: Exception | None = None
    for attempt, v in enumerate([voice, voice, FALLBACK_VOICE]):
        try:
            await edge_tts.Communicate(text, v).save(str(out_path))
            if out_path.exists() and out_path.stat().st_size > 1000:
                return v
            raise RuntimeError("empty TTS output")
        except Exception as err:  # network hiccups, bad voice, etc.
            last = err
            print(f"  TTS {v} attempt {attempt + 1} failed: {err}")
            await asyncio.sleep(2 + attempt * 2)
    raise SystemExit(f"TTS failed for segment: {last}")


async def synth_all(segs: list[tuple[str, str]], tmp: Path) -> list[Path]:
    sem = asyncio.Semaphore(3)
    paths = [tmp / f"seg{i:02d}.mp3" for i in range(len(segs))]

    async def run(i: int) -> None:
        async with sem:
            used = await synth_one(segs[i][1], segs[i][0], paths[i])
            print(f"  seg{i:02d} {used} ({len(segs[i][1])} chars)")

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


def build_voice_track(seg_paths: list[Path], tmp: Path) -> Path:
    """Decode clips to PCM and join with true silence between sections."""
    silence = tmp / "silence.wav"
    ff("-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
       "-t", f"{SECTION_PAUSE_S}", "-c:a", "pcm_s16le", str(silence))
    wavs: list[Path] = []
    for p in seg_paths:
        w = p.with_suffix(".wav")
        # trim TTS leading/trailing near-silence so pauses are consistent
        ff("-i", str(p), "-af",
           "silenceremove=start_periods=1:start_threshold=-50dB,"
           "areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
           "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(w))
        wavs.append(w)
    lst = tmp / "concat.txt"
    lines: list[str] = []
    for i, w in enumerate(wavs):
        if i:
            lines.append(f"file '{silence}'")
        lines.append(f"file '{w}'")
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
    print(f"Generating podcast for {bid} ({len(segs)} segments)…")
    with tempfile.TemporaryDirectory(prefix="newsy-pod-") as tmpd:
        tmp = Path(tmpd)
        seg_paths = asyncio.run(synth_all(segs, tmp))
        voice = build_voice_track(seg_paths, tmp)
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
        for voice, text in build_segments(b):
            print(f"[{voice}] {text}\n")
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
