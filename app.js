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
    els.meta.textContent = when ? "Prepared " + when : "";
    setPodcast(b);

    document.title = (b.label || "Briefing") + " · Newsy";

    const beats = b.beats || [];
    els.beats.innerHTML = beats
      .map(function (beat) {
        return (
          '<article class="beat" id="beat-' +
          escapeAttr(beat.id || "") +
          '">' +
          "<h2 class=\"beat-title\">" +
          escapeHtml(beat.title || "") +
          "</h2>" +
          '<div class="beat-body">' +
          bodyHtml(beat.body || "") +
          "</div>" +
          renderSources(beat.sources) +
          "</article>"
        );
      })
      .join("");

    // Keep the picker in sync
    if (els.select && els.select.value !== b.id) els.select.value = b.id;

    // Reflect selection in the URL hash without scrolling noise
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
