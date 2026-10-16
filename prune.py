#!/usr/bin/env python3
"""Keep only the newest KEEP bulletins. Trims briefings.json and deletes audio/,
images/ and data/briefing-*.json files that don't belong to a kept bulletin.
Prints deleted repo paths (one per line after 'DELETED:') so the pusher can `git rm` them.
Usage: python3 prune.py [--dry-run]"""
import json, sys
from pathlib import Path
KEEP = 7
ROOT = Path(__file__).resolve().parent
P = ROOT / "data" / "briefings.json"
dry = "--dry-run" in sys.argv
data = json.loads(P.read_text())
kept = data[:KEEP]
ids = {b["id"] for b in kept}
gone = []
for f in list((ROOT / "audio").glob("*.mp3")) + list((ROOT / "images").glob("*")) + list((ROOT / "data").glob("briefing-*.json")):
    stem = f.stem.replace("briefing-", "")
    if not any(stem == i or stem.startswith(i + "-") for i in ids):
        gone.append(f)
if not dry:
    P.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n")
    for f in gone: f.unlink()
print(f"kept {len(kept)}: {[b['id'] for b in kept]} (dropped {len(data)-len(kept)} from briefings.json)")
print("DELETED:")
for f in gone: print(f.relative_to(ROOT))
