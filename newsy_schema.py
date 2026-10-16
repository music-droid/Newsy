"""Shared helpers for the Newsy story schema (v2).

Beat (v2): {id, title, headline, image?: {src, alt, credit, sourceUrl},
            stories: [{headline, body, sources?, image?}], sources?, carried?}
Briefing (v2, evening): newAtThisHour: [{beat, headline, body, sources?}]
Older beats with only `body` still render (app.js falls back).
"""
from __future__ import annotations
import html, re


def beat_stories(beat: dict) -> list[dict]:
    if beat.get("stories"):
        return beat["stories"]
    if beat.get("body"):
        return [{"headline": beat.get("headline") or beat.get("title", ""), "body": beat["body"],
                 "sources": beat.get("sources", [])}]
    return []


def beat_body_html(beat: dict) -> str:
    """Flatten stories back to HTML (for podcast / legacy readers)."""
    if not beat.get("stories"):
        return beat.get("body") or ""
    return "".join(f"<p><strong>{html.escape(s.get('headline',''))}.</strong></p>{s.get('body','')}"
                   for s in beat["stories"])


def split_legacy_body(beat: dict) -> list[dict]:
    """Split a legacy body into stories at <p><strong>Label.</strong> paragraphs."""
    paras = re.findall(r"<p>(.*?)</p>", beat.get("body") or "", re.S)
    stories, srcs = [], list(beat.get("sources") or [])
    for p in paras:
        m = re.match(r"\s*<strong>(.*?)</strong>\s*(.*)", p, re.S)
        if m:
            label = re.sub(r"<[^>]+>", "", html.unescape(m.group(1))).strip().rstrip(".:")
            rest = m.group(2)
        else:
            label, rest = "", p
        plain = re.sub(r"<[^>]+>", "", html.unescape(rest)).strip()
        first = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"])", plain, 1)[0]
        if len(first) > 120:
            first = first[:117].rsplit(" ", 1)[0] + "…"
        headline = f"{label}: {first}" if label else first
        stories.append({"headline": headline.rstrip("."), "body": f"<p>{rest.strip()}</p>", "sources": []})
    # attach each source to the story sharing the most distinctive words
    unused = []
    for s in srcs:
        words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z’'-]{3,}", s.get("name", ""))}
        best, score = None, 0
        for st in stories:
            text = (st["headline"] + " " + st["body"]).lower()
            sc = sum(1 for w in words if w in text)
            if sc > score:
                best, score = st, sc
        (best["sources"] if best and score >= 2 else unused).append(s)
    return stories, unused
