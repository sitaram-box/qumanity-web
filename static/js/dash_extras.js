/**
 * dash_extras.js — Kundali modal, Time-box popup, daily-language setting, modal plumbing for the dashboard.
 */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var tr = function (k, f) { return window.qmTr ? window.qmTr(k, f) : f; };

  function openModal(m) { m.hidden = false; }
  function closeModal(m) { m.hidden = true; }
  Array.prototype.forEach.call(document.querySelectorAll(".dq-modal"), function (m) {
    m.addEventListener("click", function (e) { if (e.target === m || e.target.hasAttribute("data-close")) closeModal(m); });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") Array.prototype.forEach.call(document.querySelectorAll(".dq-modal"), closeModal);
  });

  function api(url, body) {
    var opt = body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }

  // ---- Item 10: Logout rating gate ----
  // First logout of the lunar cycle -> Rating screen; any later logout this same
  // cycle -> straight to the "Are you sure?" confirm (server tracks this, not the
  // browser, so it holds across devices/sessions too).
  var ratingModal = $("rating-modal"), logoutConfirmModal = $("logout-confirm-modal");
  var ratingStarsRow = $("rating-stars");
  var ratingStars = ratingStarsRow ? Array.prototype.slice.call(ratingStarsRow.querySelectorAll(".qm-star")) : [];
  var currentRating = 0;

  function paintStars(value) {
    ratingStars.forEach(function (btn) {
      btn.classList.toggle("is-filled", parseInt(btn.getAttribute("data-value"), 10) <= value);
    });
  }
  ratingStars.forEach(function (btn) {
    var v = parseInt(btn.getAttribute("data-value"), 10);
    btn.addEventListener("click", function () { currentRating = v; paintStars(currentRating); });
    btn.addEventListener("mouseenter", function () { paintStars(v); });
  });
  if (ratingStarsRow) ratingStarsRow.addEventListener("mouseleave", function () { paintStars(currentRating); });

  function openLogoutConfirm() {
    if (ratingModal) closeModal(ratingModal);
    openModal(logoutConfirmModal);
  }

  Array.prototype.forEach.call(document.querySelectorAll(".qm-logout-btn"), function (btn) {
    btn.addEventListener("click", function () {
      api("/api/user/review-status")
        .then(function (res) {
          if (res.reviewed || !ratingModal) {
            openModal(logoutConfirmModal);
          } else {
            currentRating = 0;
            paintStars(0);
            $("rating-review-text").value = "";
            openModal(ratingModal);
          }
        })
        .catch(function () { openModal(logoutConfirmModal); }); // never trap logout behind a failed check
    });
  });

  var ratingSkipBtn = $("rating-skip-btn"), ratingSubmitBtn = $("rating-submit-btn");
  if (ratingSkipBtn) ratingSkipBtn.addEventListener("click", openLogoutConfirm); // Skip never saves
  if (ratingSubmitBtn) ratingSubmitBtn.addEventListener("click", function () {
    var review = $("rating-review-text").value.trim();
    api("/api/user/review", { rating: currentRating || null, review: review || null })
      .then(openLogoutConfirm)
      .catch(openLogoutConfirm); // don't trap the user behind a failed save either
  });

  // ---- Notification bell: unread Personal-timeline chats + pending people-requests ----
  var notifBtn = $("notif-btn"), notifBadge = $("notif-badge");
  if (notifBtn) {
    function refreshNotifs() {
      api("/api/notifications/summary").then(function (d) {
        if (d.total > 0) { notifBadge.textContent = d.total > 99 ? "99+" : d.total; notifBadge.hidden = false; }
        else { notifBadge.hidden = true; }
      }).catch(function () {});
    }
    notifBtn.addEventListener("click", function () {
      var personalTab = document.querySelector('.qm-dash-tab[data-tab="personal"]');
      if (personalTab) personalTab.click();
      setTimeout(refreshNotifs, 1000); // opening Personal usually reads something; re-check shortly after
    });
    refreshNotifs();
    setInterval(refreshNotifs, 30000);
  }

  // ---- Item 8: Announcements megaphone — separate from the bell above on purpose (unread
  // council broadcasts, not personal chats/requests); dropdown + click-through-marks-read ----
  var annBtn = $("announce-bell-btn"), annBadge = $("announce-bell-badge"), annMenu = $("announce-bell-menu"), annWrap = $("announce-bell-wrap");
  if (annBtn) {
    function refreshAnnounceBadge() {
      api("/api/announcements/unread-count").then(function (d) {
        if (d.total > 0) { annBadge.textContent = d.total > 99 ? "99+" : d.total; annBadge.hidden = false; }
        else { annBadge.hidden = true; }
      }).catch(function () {});
    }
    function closeAnnounceMenu() { annMenu.hidden = true; annBtn.setAttribute("aria-expanded", "false"); }
    function renderAnnounceMenu(items) {
      annMenu.innerHTML = "";
      if (!items.length) {
        var li = el("li", "", "No unread announcements"); li.style.padding = "9px 12px"; annMenu.appendChild(li);
        return;
      }
      items.forEach(function (a) {
        var li = el("li");
        var b = document.createElement("button"); b.type = "button";
        b.innerHTML = "<span></span>";
        b.firstChild.textContent = (a.title ? a.title + " — " : "") + a.body.slice(0, 60) + (a.body.length > 60 ? "…" : "");
        b.addEventListener("click", function () {
          api("/api/announcements/" + a.id + "/read", {}).then(function () {
            closeAnnounceMenu();
            refreshAnnounceBadge();
            var targetTab = (a.location_level === "continent" || a.location_level === "country" || a.location_level === "earth") ? "global" : "public";
            var tabBtn = document.querySelector('.qm-dash-tab[data-tab="' + targetTab + '"]');
            if (tabBtn) tabBtn.click();
          }).catch(function () {});
        });
        li.appendChild(b); annMenu.appendChild(li);
      });
    }
    annBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var opening = annMenu.hidden;
      closeAnnounceMenu();
      if (opening) {
        annMenu.hidden = false; annBtn.setAttribute("aria-expanded", "true");
        api("/api/announcements/unread-recent?limit=5").then(function (d) { renderAnnounceMenu(d.announcements); }).catch(function () { renderAnnounceMenu([]); });
      }
    });
    document.addEventListener("click", function (e) { if (!annWrap.contains(e.target)) closeAnnounceMenu(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeAnnounceMenu(); });
    refreshAnnounceBadge();
    setInterval(refreshAnnounceBadge, 30000);
  }

  // ---- Public search ID + past Account IDs ----
  var scEl = $("pv-search-code");
  if (scEl) api("/api/people/me").then(function (d) {
    scEl.textContent = d.search_code ? d.search_code.replace(/(\d{4})(?=\d)/g, "$1 ") : "—";
    var histBtn = $("account-history-btn"), histBox = $("account-history-box");
    function renderHistory() {
      histBox.innerHTML = "";
      d.account_history.forEach(function (a) {
        var loc = JSON.parse(a.present_location_json);
        var place = (loc.village || loc.district || loc.state || loc.country || {}).name || "";
        var row = el("div", "pv-field");
        var lbl = el("label", "", (a.is_current ? "✅ Active" : "⏸️ Inactive") + " · " + new Date(a.created_at).toLocaleDateString());
        row.appendChild(lbl);
        var line = el("span", "", a.account_id + " — " + place + " ");
        if (!a.is_current) {
          var sw = document.createElement("button"); sw.type = "button"; sw.className = "sg-btn"; sw.textContent = "Switch to this";
          sw.addEventListener("click", function () {
            api("/api/people/account-ids/switch", { row_id: a.id }).then(function () { location.reload(); }).catch(function (e) { alert(e.message); });
          });
          line.appendChild(sw);
        }
        row.appendChild(line);
        histBox.appendChild(row);
      });
      var reqBtn = el("button", "sg-btn", "📍 Request new Account ID (moved to a new place)"); reqBtn.type = "button";
      reqBtn.addEventListener("click", function () {
        var state = window.prompt("What state/province have you moved to?"); if (!state) return;
        var village = window.prompt("Village/area name (if you know it — optional):");
        var present = { state: { name: state } };
        if (village) present.village = { name: village };
        api("/api/people/account-ids/request", { present_location: present })
          .then(function () { alert("Sent — a council member in your new area will review and confirm it."); })
          .catch(function (e) { alert(e.message); });
      });
      histBox.appendChild(reqBtn);
    }
    histBtn.addEventListener("click", function () {
      histBox.hidden = !histBox.hidden;
      if (histBox.hidden || histBox.dataset.loaded) return;
      histBox.dataset.loaded = "1";
      renderHistory();
    });
  }).catch(function () {});

  // ---- Election history ----
  var ehCard = $("election-history-card");
  if (ehCard) {
    function partySelect(id, value, parties) {
      var s_ = document.createElement("select"); s_.id = id;
      var blank = document.createElement("option"); blank.value = ""; blank.textContent = "— not recorded —"; s_.appendChild(blank);
      parties.forEach(function (p) { var o = document.createElement("option"); o.value = p.code; o.textContent = p.label; if (p.code === value) o.selected = true; s_.appendChild(o); });
      return s_;
    }
    // A locked slot (a past election that's already been answered) renders as a read-only chip,
    // not a <select> -- matches election_core.save_party_history's own immutability rule exactly:
    // once a past slot has a real saved value, any attempt to change it is rejected server-side,
    // so the UI shouldn't offer to change it at all. A past slot with NO saved value yet (never
    // answered) still gets the normal editable dropdown, since that first save is still allowed.
    function partyLockedChip(value, parties) {
      var label = (parties.filter(function (p) { return p.code === value; })[0] || {}).label || value;
      return el("span", "eh-locked-chip", "🔒 " + label);
    }
    api("/api/election-history").then(function (d) {
      var parties = d.parties.map(function (p) { return { code: p[0], label: p[1] }; });
      // Always the 2 most recent elections + the next one, rolling forward automatically
      // (election_core.loksabha_years) -- never a fixed year list.
      var years = d.party.loksabha_years.map(String);
      var nextYear = years[years.length - 1];
      var lsRow = $("eh-loksabha");
      years.forEach(function (y) {
        var value = d.party.loksabha[y] || "";
        var locked = y !== nextYear && !!value;
        var wrap = el("div", "pv-lang");
        wrap.appendChild(el("label", "", y + (y === nextYear ? " (planning to)" : "")));
        wrap.appendChild(locked ? partyLockedChip(value, parties) : partySelect("eh-ls-" + y, value, parties));
        lsRow.appendChild(wrap);
      });
      var vsRow = $("eh-vidhansabha");
      [["last", "Last election"], ["next", "Next election"]].forEach(function (k) {
        var value = d.party.vidhansabha[k[0]] || "";
        var locked = k[0] === "last" && !!value;
        var wrap = el("div", "pv-lang");
        wrap.appendChild(el("label", "", k[1]));
        wrap.appendChild(locked ? partyLockedChip(value, parties) : partySelect("eh-vs-" + k[0], value, parties));
        vsRow.appendChild(wrap);
      });
      $("eh-save-btn").addEventListener("click", function () {
        var payload = { loksabha: {}, vidhansabha: {} };
        // Only read editable slots -- a locked slot has no <select> to read from anymore, and
        // resubmitting its already-saved value isn't needed (the backend only rejects a CHANGE).
        years.forEach(function (y) { var s_ = $("eh-ls-" + y); if (s_) payload.loksabha[y] = s_.value; });
        var vsLast = $("eh-vs-last"); if (vsLast) payload.vidhansabha.last = vsLast.value;
        var vsNext = $("eh-vs-next"); if (vsNext) payload.vidhansabha.next = vsNext.value;
        api("/api/election-history", payload).then(function () { $("eh-saved").hidden = false; setTimeout(function () { $("eh-saved").hidden = true; }, 2500); }).catch(function (e) { alert(e.message); });
      });
      var qp = $("eh-qpunch"); $("eh-qpunch-empty").hidden = d.qpunch.length > 0;
      d.qpunch.forEach(function (v) {
        var li = document.createElement("li");
        li.textContent = v.year + " " + v.sign + " cycle: voted for " + v.candidate + " " + (v.won ? "✅ Won" : "❌ Lost");
        qp.appendChild(li);
      });
    }).catch(function () {});
  }

  // ---- Wallet weekly history ----
  var whBtn = $("qm-wallet-history-btn");
  if (whBtn) whBtn.addEventListener("click", function () {
    var box = $("qm-wallet-history-box");
    box.hidden = !box.hidden;
    if (box.hidden || box.dataset.loaded) return;
    box.dataset.loaded = "1";
    api("/api/wallet/history").then(function (h) {
      box.innerHTML = "";
      if (h.older_weeks_hidden) box.appendChild(el("p", "qm-dash-empty", h.older_weeks_hidden + " older week(s) — council members only."));
      if (!h.weeks.length) box.appendChild(el("p", "qm-dash-empty", "No transactions yet."));
      h.weeks.forEach(function (wk) {
        var w = el("div", "wh-week");
        w.appendChild(el("b", "", wk.start + " – " + wk.end + " · " + (wk.change >= 0 ? "+" : "") + wk.change + " Qoins"));
        wk.rows.forEach(function (r) { w.appendChild(el("small", "", (r.amount >= 0 ? "+" : "") + r.amount + " · " + r.reason)); });
        box.appendChild(w);
      });
    }).catch(function (e) { box.innerHTML = ""; box.appendChild(el("p", "qm-dash-empty", e.message)); });
  });

  // ---- Kundali (North Indian style, Moon-based -- House 1 = the Moon's own sign) ----
  // The chart SVG itself is built server-side (kundali_analyser.chart_svg) from verified
  // ephemeris data; the client only injects it and renders the analysis around it.
  var kBtn = $("kundali-btn"), kModal = $("kundali-modal");
  if (kBtn && window.QM_KUNDALI) {
    var built = false;
    kBtn.addEventListener("click", function () {
      if (!built) {
        var k = window.QM_KUNDALI;
        $("kundali-chart").innerHTML = k.chart_svg;
        var cap = document.createElement("p"); cap.className = "qm-timeline-note";
        cap.textContent = "North Indian style · House 1 (top) is the sign the Moon occupies (Chandra Lagna).";
        $("kundali-chart").appendChild(cap);
        if (k.ascendant_note) {
          var ascNote = document.createElement("p"); ascNote.className = "qm-timeline-note";
          ascNote.textContent = k.ascendant_note;
          $("kundali-chart").appendChild(ascNote);
        }

        var tb = $("kundali-rows");
        k.table.forEach(function (r) {
          var tr_ = document.createElement("tr");
          [r.point, r.sign, r.element, r.degree, r.nakshatra, r.pada, r.house].forEach(function (v) {
            var td = document.createElement("td"); td.textContent = v; tr_.appendChild(td);
          });
          tb.appendChild(tr_);
        });

        var elWrap = $("kd-elements");
        var maxEl = Math.max.apply(null, Object.keys(k.elemental_balance.counts).map(function (e) { return k.elemental_balance.counts[e]; })) || 1;
        Object.keys(k.elemental_balance.counts).forEach(function (name) {
          var count = k.elemental_balance.counts[name];
          var row = el("div", "kd-el-row");
          row.appendChild(el("span", "kd-el-label", name + (name === k.elemental_balance.dominant ? " (dominant)" : "")));
          var track = el("div", "kd-el-track");
          var fill = el("div", "kd-el-fill"); fill.style.width = Math.round(100 * count / maxEl) + "%";
          track.appendChild(fill); row.appendChild(track);
          row.appendChild(el("span", "kd-el-count", String(count)));
          elWrap.appendChild(row);
        });

        var housesWrap = $("kd-houses");
        for (var n = 1; n <= 12; n++) {
          var h = k.house_strength[n];
          var card = el("div", "kd-house kd-house--" + h.status);
          card.appendChild(el("b", "", "House " + n + " · " + h.sign));
          card.appendChild(el("span", "", h.status.charAt(0).toUpperCase() + h.status.slice(1) + (h.occupants.length ? " — " + h.occupants.join(", ") : " — empty")));
          housesWrap.appendChild(card);
        }

        var aspWrap = $("kd-aspects");
        Object.keys(k.aspects).forEach(function (planet) {
          var row = el("p", "kd-aspect-row");
          row.appendChild(el("b", "", planet + ": "));
          row.appendChild(document.createTextNode("views house" + (k.aspects[planet].length > 1 ? "s " : " ") + k.aspects[planet].join(", ")));
          aspWrap.appendChild(row);
        });

        var dashaWrap = $("kd-dasha");
        if (k.dasha.current) {
          dashaWrap.appendChild(el("p", "kd-dasha-current", "Current Mahadasha: " + k.dasha.current.lord + " (" + k.dasha.current.start + " → " + k.dasha.current.end + ")"));
        }
        if (k.dasha.upcoming.length) {
          dashaWrap.appendChild(el("p", "qm-dash-empty", "Upcoming periods:"));
          var list = el("ul", "kd-dasha-list");
          k.dasha.upcoming.forEach(function (p) {
            list.appendChild(el("li", "", p.lord + ": " + p.start + " → " + p.end));
          });
          dashaWrap.appendChild(list);
        }
        built = true;
      }
      openModal(kModal);
    });
  } else if (kBtn) { kBtn.disabled = true; }

  // ---- Private ID: hidden until the user types their PIN again ----
  var pcBtn = $("private-code-btn"), pcCode = $("private-code"), pcTimer = null;
  if (pcBtn) pcBtn.addEventListener("click", function () {
    if (pcBtn.textContent === "Hide") { pcCode.textContent = "•••••••••"; pcBtn.textContent = "Show"; return; }
    var pin = window.prompt("Enter your 5-digit PIN to show your Private ID");
    if (!pin) return;
    fetch("/api/user/private-code", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pin: pin }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Could not show the ID"); return j; }); })
      .then(function (j) {
        pcCode.textContent = j.private_code.replace(/(\d{3})(\d{3})(\d{3})/, "$1 $2 $3"); pcBtn.textContent = "Hide";
        clearTimeout(pcTimer); pcTimer = setTimeout(function () { pcCode.textContent = "•••••••••"; pcBtn.textContent = "Show"; }, 30000);
      })
      .catch(function (e) { alert(e.message); });
  });

  // ---- Daily-use (third) language ----
  var saveBtn = $("daily-lang-save");
  if (saveBtn) saveBtn.addEventListener("click", function () {
    saveBtn.disabled = true;
    fetch("/api/user/languages", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ daily: $("daily-lang").value }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Could not save"); return j; }); })
      .then(function () { location.reload(); })
      .catch(function (e) { alert(e.message); saveBtn.disabled = false; });
  });

  // ---- Preferred language (which of the user's up-to-3 languages the whole UI shows in) ----
  var prefWrap = $("pref-lang-options");
  if (prefWrap && window.QM_LANGS) {
    window.QM_LANGS.forEach(function (l) {
      var label = document.createElement("label");
      label.style.cssText = "display:inline-flex;align-items:center;gap:4px;margin-right:12px;font-weight:400;text-transform:none;letter-spacing:0;";
      var radio = document.createElement("input");
      radio.type = "radio"; radio.name = "pref-lang"; radio.value = l.code;
      radio.checked = (window.QM_PREFERRED_LANG || "en") === l.code;
      radio.addEventListener("change", function () {
        fetch("/api/user/languages", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preferred: l.code }) })
          .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Could not save"); return j; }); })
          .then(function () { location.reload(); })
          .catch(function (e) { alert(e.message); });
      });
      label.appendChild(radio);
      label.appendChild(document.createTextNode(" " + l.native + (l.native !== l.name ? " (" + l.name + ")" : "")));
      prefWrap.appendChild(label);
    });
  }

  // ---- Change PIN ----
  var pinForm = $("pin-change-form");
  if (pinForm) {
    var pinErr = $("pin-change-error"), pinOk = $("pin-change-success");
    pinForm.addEventListener("submit", function (e) {
      e.preventDefault();
      pinErr.hidden = true; pinOk.hidden = true;
      var current = $("pin-current").value, next = $("pin-new").value;
      api("/api/user/pin", { current_pin: current, new_pin: next })
        .then(function () {
          pinOk.hidden = false;
          pinForm.reset();
        })
        .catch(function (e) { pinErr.textContent = e.message; pinErr.hidden = false; });
    });
  }

  // ---- Time-box ----
  var tBtn = $("timebox-btn"), tModal = $("timebox-modal"), tBody = $("timebox-body"), timer = null, tData = null;

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function tile(label, value) { var t = el("div", "tb-tile"); t.appendChild(el("label", "", label)); t.appendChild(el("b", "", value || "—")); return t; }
  var WMO = { 0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain", 80: "Showers", 81: "Showers", 82: "Heavy showers", 95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm" };

  function clock() {
    if (!tData) return;
    var c = $("tb-clock-time"); if (!c) return;
    try {
      c.textContent = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: tData.timezone }).format(new Date());
    } catch (e) { c.textContent = tData.time; }
  }

  function render(d) {
    tData = d; tBody.innerHTML = "";
    var top = el("div", "tb-clock");
    var big = el("span", "tb-time", d.time); big.id = "tb-clock-time"; top.appendChild(big);
    top.appendChild(el("span", "", d.date));
    tBody.appendChild(top);
    tBody.appendChild(el("p", "tb-place", "📍 " + d.place + " · " + d.timezone + " (" + d.tz_abbr + ")"));
    var row = el("div", "tb-row");
    var wx = tile("Weather", "Loading…"); wx.id = "tb-weather"; row.appendChild(wx);
    row.appendChild(tile("🌅 Sunrise", d.sunrise)); row.appendChild(tile("🌇 Sunset", d.sunset));
    tBody.appendChild(row);

    tBody.appendChild(el("div", "tb-sec", "Vedic calendar"));
    var p = d.panchang, vr = el("div", "tb-row");
    [["Tithi", p.tithi], ["Vaar", p.vaar], ["Nakshatra", p.nakshatra], ["Chandra Maas", p.chandra_maas], ["Surya Maas", p.surya_maas]].forEach(function (x) { vr.appendChild(tile(x[0], x[1])); });
    tBody.appendChild(vr);

    tBody.appendChild(el("div", "tb-sec", "Planets today · 12 houses (rising sign " + d.sky.ascendant + ")"));
    var hs = el("div", "tb-houses");
    d.sky.houses.forEach(function (h) {
      var b = el("div", "tb-house" + (h.planets.length ? " has" : ""));
      b.appendChild(el("b", "", h.n + ". " + h.sign + (h.asc ? " ↑" : "")));
      if (h.planets.length) h.planets.forEach(function (x) { b.appendChild(el("em", "", x.planet + " " + x.text)); });
      hs.appendChild(b);
    });
    tBody.appendChild(hs);
    tBody.appendChild(el("p", "qm-timeline-note", d.note));

    fetch("https://api.open-meteo.com/v1/forecast?latitude=" + d.lat + "&longitude=" + d.lng + "&current=temperature_2m,weather_code")
      .then(function (r) { return r.json(); })
      .then(function (w) {
        var c = w.current, t = $("tb-weather"); if (!t) return;
        t.replaceWith(tile("Weather", Math.round(c.temperature_2m) + "°C · " + (WMO[c.weather_code] || "—")));
      })
      .catch(function () { var t = $("tb-weather"); if (t) t.querySelector("b").textContent = "Unavailable"; });
    clock(); clearInterval(timer); timer = setInterval(clock, 1000);
  }

  if (tBtn) tBtn.addEventListener("click", function () {
    openModal(tModal);
    fetch("/api/timebox").then(function (r) { if (!r.ok) throw new Error(); return r.json(); }).then(render)
      .catch(function () { tBody.innerHTML = ""; tBody.appendChild(el("p", "qm-dash-empty", "Could not load the time-box right now.")); });
  });
  tModal.addEventListener("click", function () { if (tModal.hidden) clearInterval(timer); });

  // ---- Item 9: My Reports (Private tab) ----
  var myReportsList = $("qm-myreports-list"), myReportsEmpty = $("qm-myreports-empty");
  function slaLeft(iso) {
    var days = Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000);
    return days <= 0 ? "overdue" : days + "d left";
  }
  if (myReportsList) {
    api("/api/reports/mine").then(function (d) {
      myReportsList.innerHTML = "";
      myReportsEmpty.hidden = d.reports.length > 0;
      d.reports.forEach(function (r) {
        var li = el("li", "qm-announce-item"); li.style.cursor = "pointer";
        li.appendChild(el("b", "", r.status.replace("_", " ")));
        li.appendChild(el("p", "", r.body.slice(0, 100) + (r.body.length > 100 ? "…" : "")));
        li.appendChild(el("small", "", "Holder: " + r.current_holder_level + " · SLA " + slaLeft(r.sla_deadline)));
        li.addEventListener("click", function () { if (window.qmOpenReportDetail) window.qmOpenReportDetail(r.id); });
        myReportsList.appendChild(li);
      });
    }).catch(function () {});
  }
})();
