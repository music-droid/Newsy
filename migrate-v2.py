#!/usr/bin/env python3
"""One-off: convert a legacy briefing (default: newest) to the stories schema."""
import json, sys
from pathlib import Path
from newsy_schema import split_legacy_body
P = Path(__file__).resolve().parent / "data" / "briefings.json"
data = json.loads(P.read_text())
target = sys.argv[1] if len(sys.argv) > 1 else data[0]["id"]
for b in data:
    if b["id"] != target: continue
    for beat in b["beats"]:
        if beat.get("stories"): continue
        stories, rest = split_legacy_body(beat)
        beat["stories"] = stories
        beat["sources"] = rest      # unmatched sources stay at beat level
        beat.pop("body", None)
    b["schema"] = 2
P.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print("migrated", target)
