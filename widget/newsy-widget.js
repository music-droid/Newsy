// Newsy — Scriptable Home Screen widget
// Fetches the latest briefing and shows titles + headlines at a glance.
// Colors match the live site (cream #f7f3ec, accent #6b4f3a, ink #2c2925).

const SITE_URL = "https://music-droid.github.io/Newsy/";
const LATEST_URL = SITE_URL + "data/latest.json";
const BRIEFINGS_URL = SITE_URL + "data/briefings.json";
const CACHE_NAME = "newsy-latest.json";
const REFRESH_MINUTES = 30;

const COLORS = {
  bg: new Color("#f7f3ec"),
  accent: new Color("#6b4f3a"),
  ink: new Color("#2c2925"),
  muted: new Color("#5c564e"),
  faint: new Color("#8a8278"),
  soft: new Color("#f0eae0"),
};

async function loadBriefing() {
  const fm = FileManager.local();
  const cachePath = fm.joinPath(fm.documentsDirectory(), CACHE_NAME);

  let data = null;
  try {
    data = await fetchLatest();
  } catch (e) {
    // fall through to cache
  }

  if (data) {
    try {
      fm.writeString(cachePath, JSON.stringify(data));
    } catch (_) {}
    return data;
  }

  if (fm.fileExists(cachePath)) {
    try {
      return JSON.parse(fm.readString(cachePath));
    } catch (_) {}
  }

  throw new Error("Could not load Newsy (offline and no cache).");
}

async function fetchLatest() {
  let req = new Request(LATEST_URL);
  req.timeoutInterval = 15;
  try {
    const res = await req.loadJSON();
    if (res && res.id && Array.isArray(res.beats)) return normalize(res);
  } catch (e) {
    // 404 or network — try full briefings list
  }

  req = new Request(BRIEFINGS_URL);
  req.timeoutInterval = 15;
  const list = await req.loadJSON();
  if (!Array.isArray(list) || !list.length) {
    throw new Error("No briefings");
  }
  return normalizeFromBriefing(list[0]);
}

function normalize(latest) {
  return {
    id: latest.id,
    label: latest.label || "Briefing",
    generatedAt: latest.generatedAt || "",
    url: latest.url || SITE_URL,
    beats: (latest.beats || []).map((b) => ({
      title: b.title || "",
      headline: b.headline || "",
    })),
  };
}

function normalizeFromBriefing(b) {
  return {
    id: b.id,
    label: b.label || "Briefing",
    generatedAt: b.generatedAt || "",
    url: SITE_URL,
    beats: (b.beats || []).map((beat) => ({
      title: beat.title || "",
      headline: beat.headline || "",
    })),
  };
}

function formatPrepared(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const df = new DateFormatter();
  df.useMediumDateStyle();
  df.useShortTimeStyle();
  return df.string(d);
}

function truncate(text, max) {
  if (!text) return "";
  const t = String(text);
  if (t.length <= max) return t;
  return t.slice(0, Math.max(0, max - 1)).trimEnd() + "…";
}

function addHeader(widget, data, { compact } = {}) {
  const brand = widget.addText("Newsy");
  brand.font = Font.boldSystemFont(compact ? 11 : 12);
  brand.textColor = COLORS.accent;
  brand.textOpacity = 1;

  widget.addSpacer(compact ? 2 : 4);

  const label = widget.addText(data.label || "Briefing");
  label.font = Font.semiboldSystemFont(compact ? 15 : 17);
  label.textColor = COLORS.ink;
  label.lineLimit = 1;
  label.minimumScaleFactor = 0.85;

  if (data.generatedAt) {
    widget.addSpacer(2);
    const when = widget.addText("Prepared " + formatPrepared(data.generatedAt));
    when.font = Font.systemFont(compact ? 10 : 11);
    when.textColor = COLORS.faint;
    when.lineLimit = 1;
  }
}

function addBeatRow(widget, beat, { titleSize, headSize, headLines }) {
  const title = widget.addText(beat.title || "");
  title.font = Font.semiboldSystemFont(titleSize);
  title.textColor = COLORS.accent;
  title.lineLimit = 1;

  if (beat.headline) {
    const head = widget.addText(truncate(beat.headline, 120));
    head.font = Font.systemFont(headSize);
    head.textColor = COLORS.muted;
    head.lineLimit = headLines;
    head.minimumScaleFactor = 0.8;
  }
}

function buildSmall(data) {
  const w = new ListWidget();
  w.backgroundColor = COLORS.bg;
  w.setPadding(12, 14, 12, 14);
  addHeader(w, data, { compact: true });
  w.addSpacer();
  return w;
}

function buildMedium(data) {
  const w = new ListWidget();
  w.backgroundColor = COLORS.bg;
  w.setPadding(12, 14, 12, 14);
  addHeader(w, data, { compact: true });
  w.addSpacer(8);

  const beats = (data.beats || []).slice(0, 4);
  beats.forEach((beat, i) => {
    addBeatRow(w, beat, { titleSize: 12, headSize: 11, headLines: 1 });
    if (i < beats.length - 1) w.addSpacer(5);
  });
  w.addSpacer();
  return w;
}

function buildLarge(data) {
  const w = new ListWidget();
  w.backgroundColor = COLORS.bg;
  w.setPadding(14, 16, 14, 16);
  addHeader(w, data, { compact: false });
  w.addSpacer(10);

  const beats = data.beats || [];
  const maxBeats = Math.min(beats.length, 9);
  for (let i = 0; i < maxBeats; i++) {
    addBeatRow(w, beats[i], { titleSize: 13, headSize: 12, headLines: 2 });
    if (i < maxBeats - 1) w.addSpacer(6);
  }
  w.addSpacer();
  return w;
}

function buildWidget(data, family) {
  let w;
  if (family === "small") w = buildSmall(data);
  else if (family === "large") w = buildLarge(data);
  else w = buildMedium(data);

  w.url = data.url || SITE_URL;

  const refresh = new Date();
  refresh.setMinutes(refresh.getMinutes() + REFRESH_MINUTES);
  w.refreshAfterDate = refresh;
  return w;
}

function buildError(message) {
  const w = new ListWidget();
  w.backgroundColor = COLORS.bg;
  w.setPadding(14, 14, 14, 14);
  const t = w.addText("Newsy");
  t.font = Font.boldSystemFont(12);
  t.textColor = COLORS.accent;
  w.addSpacer(6);
  const m = w.addText(message);
  m.font = Font.systemFont(12);
  m.textColor = COLORS.muted;
  w.url = SITE_URL;
  return w;
}

async function run() {
  let data;
  try {
    data = await loadBriefing();
  } catch (e) {
    const err = buildError(String(e.message || e));
    if (config.runsInWidget) {
      Script.setWidget(err);
    } else {
      await err.presentMedium();
    }
    Script.complete();
    return;
  }

  const family = config.widgetFamily || "medium";
  const widget = buildWidget(data, family);

  if (config.runsInWidget) {
    Script.setWidget(widget);
  } else {
    await widget.presentMedium();
  }
  Script.complete();
}

await run();
