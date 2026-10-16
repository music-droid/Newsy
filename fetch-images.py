#!/usr/bin/env python3
"""Download one image per beat (og:image of the top story's first source, or a
`imageUrl` already set on the beat) into images/{id}-{beat}.jpg, ~720px, small.

Usage: python3 fetch-images.py [briefing-id]   (default newest)
Uses system python3 (needs Pillow). Failures are fine: beat simply has no image.
"""
from __future__ import annotations
import io, json, re, sys, urllib.request
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse
from PIL import Image

ROOT = Path(__file__).resolve().parent
P = ROOT / "data" / "briefings.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def get(url: str, n: int = 4_000_000) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return r.read(n)


def og_image(page_url: str) -> str | None:
    try:
        h = get(page_url, 600_000).decode("utf-8", "ignore")
    except Exception:
        return None
    for prop in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        for m in re.finditer(r"<meta\b[^>]*>", h, re.I):
            tag = m.group(0)
            if re.search(r'(?:property|name)\s*=\s*["\']%s["\']' % re.escape(prop), tag, re.I):
                c = re.search(r'content\s*=\s*["\']([^"\']+)', tag, re.I)
                if c:
                    return urljoin(page_url, unescape(c.group(1)))
    return None


def candidates(beat: dict):
    if beat.get("imageUrl"):
        yield beat["imageUrl"], beat.get("imageSource")
    stories = beat.get("stories") or []
    srcs = []
    for st in stories[:2]:
        srcs += st.get("sources") or []
    srcs += beat.get("sources") or []
    for s in srcs[:4]:
        if s.get("url"):
            img = og_image(s["url"])
            if img:
                yield img, s


def main() -> None:
    data = json.loads(P.read_text())
    b = next((x for x in data if x["id"] == sys.argv[1]), None) if len(sys.argv) > 1 else data[0]
    (ROOT / "images").mkdir(exist_ok=True)
    for beat in b["beats"]:
        out = ROOT / "images" / f"{b['id']}-{beat['id']}.jpg"
        done = False
        for url, src in candidates(beat):
            try:
                im = Image.open(io.BytesIO(get(url))).convert("RGB")
                if im.width < 300:
                    continue
                im.thumbnail((720, 720))
                im.save(out, "JPEG", quality=68, optimize=True, progressive=True)
            except Exception:
                continue
            top = (beat.get("stories") or [{}])[0]
            name = (src or {}).get("name") or urlparse(url).netloc
            credit = name.split(":")[0].strip()
            beat["image"] = {"src": f"images/{out.name}", "alt": top.get("headline", beat.get("title", "")),
                             "credit": credit, "sourceUrl": (src or {}).get("url", "")}
            beat.pop("imageUrl", None)
            print(f"{beat['id']}: {out.name} {out.stat().st_size//1024} KB ← {credit}")
            done = True
            break
        if not done:
            print(f"{beat['id']}: no image (fallback, fine)")
    P.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
