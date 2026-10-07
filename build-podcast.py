#!/usr/bin/env python3
"""Generate a spoken MP3 for a Newsy briefing via edge-tts, with a soft ambient bed."""
from __future__ import annotations

import asyncio
import html
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIEFINGS = ROOT / "data" / "briefings.json"
AUDIO_DIR = ROOT / "audio"
VOICE = "en-US-AndrewNeural"
FALLBACK_VOICE = "en-US-GuyNeural"

# Short pause between beats (edge-tts passes break tags through).
BEAT_BREAK = ' <break time="700ms"/> '

# Ambient bed ~-28 dB relative to the voice (10^(-28/20) ≈ 0.04).
AMBIENT_REL_DB = -28.0
AMBIENT_VOLUME = 10 ** (AMBIENT_REL_DB / 20.0)  # ~0.0398
FADE_IN_S = 2.5
FADE_OUT_S = 3.5


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    import re

    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", ". ", text)
    text = re.sub(r"(?i)</p>", ". ", text)
    text = re.sub(r"(?i)</li>", ". ", text)
    text = re.sub(r"(?i)</h[1-6]>", ". ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\.\s*\.", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def is_quiet_only(plain: str) -> bool:
    """Skip beats whose entire body is just 'quiet' (optional punctuation)."""
    import re

    cleaned = re.sub(r"[.!?…]+", "", plain or "").strip()
    return bool(re.fullmatch(r"(?i)quiet", cleaned))


def build_script(briefing: dict) -> str:
    label = (briefing.get("label") or briefing.get("id") or "Briefing").strip()
    if not label.endswith("."):
        label = label + "."
    parts: list[str] = ["Newsy.", label]
    for beat in briefing.get("beats") or []:
        plain = strip_html(beat.get("body") or "")
        if not plain or is_quiet_only(plain):
            continue
        title = (beat.get("title") or beat.get("id") or "Beat").strip()
        parts.append(f"{title}. {plain}")
    return BEAT_BREAK.join(parts)


async def synthesize(script: str, out_path: Path, voice: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(script, voice)
    await communicate.save(str(out_path))


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def mix_with_ambient(voice_path: Path, final_path: Path) -> None:
    """Lay a quiet soft-drone bed under the narration.

    Bed is three gentle sine pads (A2 / E3 / A3-ish) plus a whisper of
    filtered pink noise, mixed at AMBIENT_REL_DB below the voice, with
    fade-in/out so it never crowds the words. Requires ffmpeg.
    """
    if not shutil.which("ffmpeg"):
        shutil.copyfile(voice_path, final_path)
        print("ffmpeg not found; wrote voice-only MP3")
        return

    duration = probe_duration(voice_path)
    if not math.isfinite(duration) or duration <= 0:
        raise SystemExit(f"Bad voice duration for {voice_path}")

    fade_out_start = max(0.0, duration - FADE_OUT_S)
    # Soft calming pad: low fifths + filtered pink noise, very quiet.
    # Frequencies chosen to sit under speech (110 / 164.8 / 220 Hz).
    lavfi = (
        f"aevalsrc="
        f"exprs="
        f"0.55*sin(2*PI*110*t)"
        f"+0.40*sin(2*PI*164.81*t)"
        f"+0.28*sin(2*PI*220*t)"
        f"+0.08*sin(2*PI*329.63*t)"
        f":d={duration:.3f}:s=44100"
    )
    noise = f"anoisesrc=color=pink:amplitude=0.15:d={duration:.3f}:sample_rate=44100"

    filter_complex = (
        # Soften the sine pad
        f"[1]lowpass=f=900,highpass=f=60,volume=0.7[pad];"
        # Whisper of pink noise, heavily filtered
        f"[2]highpass=f=120,lowpass=f=600,volume=0.25[noise];"
        f"[pad][noise]amix=inputs=2:duration=first:dropout_transition=0,"
        f"volume={AMBIENT_VOLUME:.6f},"
        f"afade=t=in:st=0:d={FADE_IN_S},"
        f"afade=t=out:st={fade_out_start:.3f}:d={FADE_OUT_S}[amb];"
        # Voice slightly above unity so it stays clear; mix ambient under
        f"[0]volume=1.0[vox];"
        f"[vox][amb]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[out]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(voice_path),
        "-f",
        "lavfi",
        "-i",
        lavfi,
        "-f",
        "lavfi",
        "-i",
        noise,
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        "-ar",
        "44100",
        "-ac",
        "1",
        str(final_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    print(
        f"Mixed ambient bed at {AMBIENT_REL_DB:.0f} dB under voice "
        f"(fade in {FADE_IN_S}s / out {FADE_OUT_S}s)"
    )


def pick_briefing(data: list, briefing_id: str | None) -> dict:
    if briefing_id:
        for item in data:
            if item.get("id") == briefing_id:
                return item
        raise SystemExit(f"Briefing id not found: {briefing_id}")
    if not data:
        raise SystemExit("briefings.json is empty")
    return data[0]


def update_briefings_audio(data: list, briefing_id: str, rel_path: str) -> None:
    for item in data:
        if item.get("id") == briefing_id:
            item["audio"] = rel_path
            return
    raise SystemExit(f"Could not update audio field for {briefing_id}")


def main() -> None:
    briefing_id = sys.argv[1] if len(sys.argv) > 1 else None
    data = json.loads(BRIEFINGS.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise SystemExit("briefings.json is empty or not an array")

    briefing = pick_briefing(data, briefing_id)
    bid = briefing["id"]
    script = build_script(briefing)
    if not script.strip():
        raise SystemExit(f"No speakable content for {bid}")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    rel = f"audio/{bid}.mp3"
    out_path = ROOT / rel

    print(f"Generating podcast for {bid} ({len(script)} chars)…")
    voice = VOICE
    with tempfile.TemporaryDirectory(prefix="newsy-pod-") as tmp:
        voice_path = Path(tmp) / f"{bid}-voice.mp3"
        try:
            asyncio.run(synthesize(script, voice_path, voice))
        except Exception as first_err:
            print(f"Voice {voice} failed ({first_err}); trying {FALLBACK_VOICE}…")
            voice = FALLBACK_VOICE
            asyncio.run(synthesize(script, voice_path, voice))

        print(f"TTS ready ({voice_path.stat().st_size} bytes, {voice})")
        mix_with_ambient(voice_path, out_path)

    size = out_path.stat().st_size
    print(f"Wrote {rel} ({size} bytes)")

    update_briefings_audio(data, bid, rel)
    BRIEFINGS.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Updated audio field on {bid} in briefings.json")

    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_latest", ROOT / "build-latest.py")
    if spec and spec.loader:
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()


if __name__ == "__main__":
    main()
