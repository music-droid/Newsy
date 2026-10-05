#!/usr/bin/env python3
"""Regenerate data/latest.json from data/briefings.json (newest briefing only)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIEFINGS = ROOT / "data" / "briefings.json"
LATEST = ROOT / "data" / "latest.json"
SITE_URL = "https://music-droid.github.io/Newsy/"


def main() -> None:
    data = json.loads(BRIEFINGS.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise SystemExit("briefings.json is empty or not an array")

    newest = data[0]
    out = {
        "id": newest["id"],
        "label": newest["label"],
        "generatedAt": newest["generatedAt"],
        "url": SITE_URL,
        "beats": [
            {
                "title": beat["title"],
                "headline": beat.get("headline", ""),
            }
            for beat in newest.get("beats", [])
        ],
    }
    LATEST.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {LATEST.relative_to(ROOT)} from {newest['id']}")


if __name__ == "__main__":
    main()
