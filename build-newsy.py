#!/usr/bin/env python3
"""Rebuild self-contained newsy.html from index.html, styles.css, app.js, and briefings.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    briefings = json.loads((ROOT / "data" / "briefings.json").read_text(encoding="utf-8"))

    # Drop external stylesheet / script tags; we'll inline.
    index = re.sub(
        r'\s*<link rel="stylesheet" href="styles\.css">\s*',
        "\n",
        index,
        count=1,
    )
    index = re.sub(
        r'\s*<script src="app\.js" defer></script>\s*',
        "\n",
        index,
        count=1,
    )

    # Insert offline-reader note after title if missing
    if "Self-contained offline reader" not in index:
        index = index.replace(
            "  <title>Newsy</title>\n",
            "  <title>Newsy</title>\n"
            "  <!-- Self-contained offline reader. PWA install (Add to Home Screen) needs the\n"
            "       multi-file HTTPS deploy (index.html + manifest + sw.js + icons). Service\n"
            "       workers do not run from file://. See HOME-SCREEN.md. -->\n",
            1,
        )

    # Remove PWA-only head bits that don't apply to the single-file reader
    # (keep fonts + theme). Leave apple-touch / manifest if present — harmless.
    style_block = f"  <style>\n{css}\n  </style>\n"
    index = index.replace("</head>", style_block + "</head>", 1)

    embedded = json.dumps(briefings, ensure_ascii=False, indent=2)
    # Escape </script> sequences inside JSON strings just in case
    embedded = embedded.replace("</", "<\\/")

    # Replace fetch boot with embedded briefings
    js_embedded = js
    # Remove DATA_URL constant usage path: replace the fetch(...).then...catch block
    fetch_pattern = re.compile(
        r"\n  fetch\(DATA_URL\)\s*"
        r"\.then\(function \(res\) \{[\s\S]*?\}\)\s*"
        r"\.then\(function \(data\) \{[\s\S]*?\}\)\s*"
        r"\.catch\(function \(err\) \{[\s\S]*?\}\);\n",
        re.M,
    )
    boot = f"""
  const EMBEDDED_BRIEFINGS = {embedded};

  function boot(data) {{
    if (!Array.isArray(data) || !data.length) {{
      showError("No briefings yet.");
      return;
    }}
    briefings = data;
    renderPicker();
    renderBriefing(pickInitial());
  }}

  boot(EMBEDDED_BRIEFINGS);
"""
    if not fetch_pattern.search(js_embedded):
        raise SystemExit("Could not find fetch(DATA_URL) boot block in app.js")
    js_embedded = fetch_pattern.sub("\n" + boot + "\n", js_embedded, count=1)
    # Drop unused DATA_URL
    js_embedded = re.sub(
        r'\n  const DATA_URL = "data/briefings\.json";\n',
        "\n",
        js_embedded,
        count=1,
    )

    script = f"  <script>\n{js_embedded}\n  </script>\n"
    if "</body>" not in index:
        raise SystemExit("index.html missing </body>")
    index = index.replace("</body>", script + "</body>", 1)

    out = ROOT / "newsy.html"
    out.write_text(index, encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} with {len(briefings)} embedded briefing(s)")


if __name__ == "__main__":
    main()
