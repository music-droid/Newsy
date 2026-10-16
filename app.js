(function () {
  "use strict";

  const DATA_URL = "data/briefings.json";

  const els = {
    brand: document.getElementById("brand"),
    title: document.getElementById("briefing-title"),
    meta: document.getElementById("briefing-meta"),
    podcast: document.getElementById("podcast"),
    listenBtn: document.getElementById("listen-btn"),
    audio: document.getElementById("podcast-audio"),
    select: document.getElementById("briefing-select"),
    beats: document.getElementById("beats"),
    status: document.getElementById("status"),
  };

  let briefings = [];

  function formatGeneratedAt(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    try {
      return new Intl.DateTimeFormat("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
      }).format(d);
    } catch (_) {
      return iso;
    }
  }

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const SLOT_NAMES = { morning: "Morning", noon: "Noon", evening: "Night" };

  function slotOf(b) {
    const m = /-(morning|noon|evening)$/.exec(b.id || "");
    return m ? m[1] : (b.slot || "").toLowerCase();
  }

  function optionLabel(b) {
    // e.g. "Wed, Oct 7 · Night"
    const src = b.date || (b.id || "").slice(0, 10);
    const parts = src.split("-");
    const slot = SLOT_NAMES[slotOf(b)] || (b.slot ? b.slot.charAt(0).toUpperCase() + b.slot.slice(1) : "");
    if (parts.length === 3) {
      const y = Number(parts[0]);
      const mo = Number(parts[1]);
      const day = Number(parts[2]);
      const wd = WEEKDAYS[new Date(Date.UTC(y, mo - 1, day)).getUTCDay()];
      return wd + ", " + MONTHS[mo - 1] + " " + day + (slot ? " · " + slot : "");
    }
    return b.label || b.id;
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return "";
    const parts = sources.map(function (s) {
      const name = s.name || "Source";
      if (s.url) {
        return (
          '<a href="' +
          escapeAttr(s.url) +
          '" rel="noopener noreferrer" target="_blank">' +
          escapeHtml(name) +
          "</a>"
        );
      }
      return '<span class="name-only">' + escapeHtml(name) + "</span>";
    });
    return (
      '<p class="sources"><span class="sources-label">Sources</span> ' +
      parts.join('<span class="sep">·</span>') +
      "</p>"
    );
  }

  function bodyHtml(body) {
    if (!body) return "";
    // Allow simple HTML paragraphs; if plain text, wrap paragraphs
    if (/<[a-z][\s\S]*>/i.test(body)) return body;
    return body
      .split(/\n\n+/)
      .map(function (p) {
        return "<p>" + escapeHtml(p.trim()) + "</p>";
      })
      .join("");
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(str) {
    return escapeHtml(str).replace(/'/g, "&#39;");
  }


  function setPodcast(b) {
    if (!els.podcast || !els.audio) return;
    const src = b && b.audio ? b.audio : "";
    if (!src) {
      els.audio.pause();
      els.audio.removeAttribute("src");
      els.audio.load();
      els.podcast.hidden = true;
      if (els.listenBtn) {
        els.listenBtn.setAttribute("aria-pressed", "false");
        els.listenBtn.textContent = "Listen";
      }
      return;
    }
    const abs = new URL(src, location.href).href;
    const current = els.audio.currentSrc || els.audio.src || "";
    if (current !== abs) {
      els.audio.pause();
      els.audio.src = src;
      els.audio.load();
      if (els.listenBtn) {
        els.listenBtn.setAttribute("aria-pressed", "false");
        els.listenBtn.textContent = "Listen";
      }
    }
    els.podcast.hidden = false;
  }

  function storyHtml(st, open) {
    const why = st.why ? '<p class="why"><span>Why it matters</span> ' + escapeHtml(st.why) + "</p>" : "";
    const img = st.image && st.image.src
      ? '<img class="story-img" loading="lazy" src="' + escapeAttr(st.image.src) + '" alt="' + escapeAttr(st.image.alt || "") + '" onerror="this.remove()">'
      : "";
    return (
      '<li class="story"><details' + (open ? " open" : "") + ">" +
      '<summary><span class="story-head">' + escapeHtml(st.headline || "") + "</span></summary>" +
      '<div class="story-body">' + img + why + bodyHtml(st.body || "") + renderSources(st.sources) + "</div>" +
      "</details></li>"
    );
  }

  function storiesOf(beat) {
    if (Array.isArray(beat.stories) && beat.stories.length) return beat.stories;
    if (beat.body) return [{ headline: beat.headline || beat.title || "", body: beat.body, sources: beat.sources }];
    return [];
  }

  function beatImageHtml(beat) {
    const im = beat.image;
    if (!im || !im.src) return "";
    const credit = im.credit
      ? '<figcaption>' + (im.sourceUrl
          ? '<a href="' + escapeAttr(im.sourceUrl) + '" rel="noopener noreferrer" target="_blank">' + escapeHtml(im.credit) + "</a>"
          : escapeHtml(im.credit)) + "</figcaption>"
      : "";
    return '<figure class="beat-figure"><img loading="lazy" src="' + escapeAttr(im.src) + '" alt="' + escapeAttr(im.alt || "") +
      '" onerror="this.closest(\'figure\').remove()">' + credit + "</figure>";
  }

  function wordCount(b) {
    let txt = "";
    (b.newAtThisHour || []).forEach(function (n) { txt += " " + (n.headline || "") + " " + (n.body || ""); });
    (b.beats || []).forEach(function (beat) {
      storiesOf(beat).forEach(function (st) { txt += " " + (st.headline || "") + " " + (st.body || ""); });
    });
    return txt.replace(/<[^>]+>/g, " ").split(/\s+/).filter(Boolean).length;
  }

  function renderBriefing(b) {
    if (!b) {
      els.title.textContent = "No briefing";
      els.meta.textContent = "";
      els.beats.innerHTML = "";
      setPodcast(null);
      els.status.hidden = false;
      els.status.textContent = "No briefing selected.";
      return;
    }

    els.status.hidden = true;
    els.title.textContent = b.label || b.id;
    const when = formatGeneratedAt(b.generatedAt);
    const mins = Math.max(1, Math.round(wordCount(b) / 230));
    els.meta.textContent = (when ? "Prepared " + when + " · " : "") + mins + " min read";
    setPodcast(b);

    document.title = (b.label || "Briefing") + " · Newsy";

    const beats = b.beats || [];
    let html = "";

    if (b.topLine) {
      html += '<p class="top-line">' + escapeHtml(b.topLine) + "</p>";
    }

    // At a glance: one tappable line per beat (NYT/Axios-style index)
    html += '<nav class="glance" aria-label="At a glance"><p class="glance-label">At a glance</p><ol>' +
      beats.map(function (beat) {
        return '<li><a href="#beat-' + escapeAttr(beat.id || "") + '" data-jump="beat-' + escapeAttr(beat.id || "") + '"><span class="glance-beat">' +
          escapeHtml(beat.title || "") + "</span> " + escapeHtml(beat.headline || "") + "</a></li>";
      }).join("") + "</ol></nav>";

    const fresh = b.newAtThisHour || [];
    if (fresh.length) {
      html += '<section class="beat new-hour" id="beat-new"><h2 class="beat-title">New at this hour</h2><ul class="stories">' +
        fresh.map(function (n, i) {
          const tag = n.beat ? '<span class="tag">' + escapeHtml(n.beat) + "</span> " : "";
          return storyHtml({ headline: "", body: n.body, sources: n.sources, why: n.why, image: n.image }, i === 0)
            .replace('<span class="story-head"></span>', '<span class="story-head">' + tag + escapeHtml(n.headline || "") + "</span>");
        }).join("") + "</ul></section>";
    }

    html += beats.map(function (beat) {
      const stories = storiesOf(beat);
      const carried = beat.carried ? '<p class="carried">' + escapeHtml(beat.carried === true ? "Continuing from this morning" : beat.carried) + "</p>" : "";
      return (
        '<article class="beat" id="beat-' + escapeAttr(beat.id || "") + '">' +
        '<h2 class="beat-title">' + escapeHtml(beat.title || "") + "</h2>" +
        beatImageHtml(beat) + carried +
        '<ul class="stories">' + stories.map(function (st) { return storyHtml(st, false); }).join("") + "</ul>" +
        (beat.stories && beat.stories.length ? renderSources(beat.sources) : "") +
        "</article>"
      );
    }).join("");

    els.beats.innerHTML = html;

    // in-page jumps without clobbering the briefing hash
    els.beats.querySelectorAll("[data-jump]").forEach(function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        const t = document.getElementById(a.getAttribute("data-jump"));
        if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    if (els.select && els.select.value !== b.id) els.select.value = b.id;

    if (history.replaceState) {
      history.replaceState(null, "", "#" + encodeURIComponent(b.id));
    } else {
      location.hash = encodeURIComponent(b.id);
    }
  }

  function findBriefing(id) {
    return briefings.find(function (b) {
      return b.id === id;
    });
  }

  function renderPicker() {
    if (!els.select) return;
    // Newest first (briefings.json is already newest-first; sort defensively by id)
    const ordered = briefings.slice().sort(function (a, b) {
      const ka = (a.date || a.id || "") + " " + ({ morning: 1, noon: 2, evening: 3 }[slotOf(a)] || 0);
      const kb = (b.date || b.id || "") + " " + ({ morning: 1, noon: 2, evening: 3 }[slotOf(b)] || 0);
      return ka < kb ? 1 : ka > kb ? -1 : 0;
    });
    els.select.innerHTML = ordered
      .map(function (b) {
        return '<option value="' + escapeAttr(b.id) + '">' + escapeHtml(optionLabel(b)) + "</option>";
      })
      .join("");

    els.select.addEventListener("change", function () {
      const found = findBriefing(els.select.value);
      if (found) {
        renderBriefing(found);
        window.scrollTo(0, 0);
      }
    });

    window.addEventListener("hashchange", function () {
      const id = decodeURIComponent((location.hash || "").replace(/^#/, ""));
      const found = findBriefing(id);
      if (found && (!els.select || els.select.value !== id || els.title.textContent !== (found.label || found.id))) {
        renderBriefing(found);
      }
    });
  }

  function pickInitial() {
    const hash = (location.hash || "").replace(/^#/, "");
    if (hash) {
      const decoded = decodeURIComponent(hash);
      const match = briefings.find(function (b) {
        return b.id === decoded;
      });
      if (match) return match;
    }
    return briefings[0] || null;
  }

  function showError(msg) {
    els.status.hidden = false;
    els.status.textContent = msg;
    els.title.textContent = "Briefing";
    els.meta.textContent = "";
    els.beats.innerHTML = "";
    setPodcast(null);
  }


  if (els.listenBtn && els.audio) {
    els.listenBtn.addEventListener("click", function () {
      if (els.podcast.hidden || !els.audio.src) return;
      if (els.audio.paused) {
        els.audio.play().then(function () {
          els.listenBtn.setAttribute("aria-pressed", "true");
          els.listenBtn.textContent = "Pause";
        }).catch(function () {
          /* autoplay blocked; controls still work */
        });
      } else {
        els.audio.pause();
        els.listenBtn.setAttribute("aria-pressed", "false");
        els.listenBtn.textContent = "Listen";
      }
    });
    els.audio.addEventListener("play", function () {
      els.listenBtn.setAttribute("aria-pressed", "true");
      els.listenBtn.textContent = "Pause";
    });
    els.audio.addEventListener("pause", function () {
      els.listenBtn.setAttribute("aria-pressed", "false");
      els.listenBtn.textContent = "Listen";
    });
    els.audio.addEventListener("ended", function () {
      els.listenBtn.setAttribute("aria-pressed", "false");
      els.listenBtn.textContent = "Listen";
    });
  }

  fetch(DATA_URL)
    .then(function (res) {
      if (!res.ok) throw new Error("Could not load briefings (" + res.status + ").");
      return res.json();
    })
    .then(function (data) {
      if (!Array.isArray(data) || !data.length) {
        showError("No briefings yet. Add one to data/briefings.json.");
        return;
      }
      briefings = data;
      renderPicker();
      renderBriefing(pickInitial());
    })
    .catch(function (err) {
      showError(err.message || "Could not load briefings.");
    });

  // Progressive Web App: register only on secure origins (or localhost).
  // Service workers cannot run from file://; use the multi-file HTTPS deploy to install.
  (function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    var host = location.hostname;
    var ok =
      location.protocol === "https:" ||
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "[::1]";
    if (!ok) return;
    navigator.serviceWorker.register("./sw.js").catch(function () {
      /* ignore registration failures */
    });
  })();

})();
