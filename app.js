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
    chips: document.getElementById("chips"),
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

  function chipLabel(b) {
    // Prefer short date + slot for the chip row
    const d = b.date || "";
    const parts = d.split("-");
    if (parts.length === 3) {
      const month = Number(parts[1]);
      const day = Number(parts[2]);
      const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const slot = (b.slot || "").charAt(0).toUpperCase() + (b.slot || "").slice(1);
      return months[month - 1] + " " + day + " · " + slot;
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

    // Update chip pressed state
    Array.prototype.forEach.call(els.chips.querySelectorAll(".chip"), function (btn) {
      btn.setAttribute("aria-pressed", btn.dataset.id === b.id ? "true" : "false");
    });

    // Reflect selection in the URL hash without scrolling noise
    if (history.replaceState) {
      history.replaceState(null, "", "#" + encodeURIComponent(b.id));
    } else {
      location.hash = encodeURIComponent(b.id);
    }
  }

  function renderChips() {
    els.chips.innerHTML = briefings
      .map(function (b) {
        return (
          "<li>" +
          '<button type="button" class="chip" data-id="' +
          escapeAttr(b.id) +
          '" aria-pressed="false">' +
          escapeHtml(chipLabel(b)) +
          "</button>" +
          "</li>"
        );
      })
      .join("");

    els.chips.addEventListener("click", function (e) {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      const found = briefings.find(function (b) {
        return b.id === btn.dataset.id;
      });
      if (found) renderBriefing(found);
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
      renderChips();
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
