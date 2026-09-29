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
    api("/api/election-history").then(function (d) {
      var parties = d.parties.map(function (p) { return { code: p[0], label: p[1] }; });
      // Always the 2 most recent elections + the next one, rolling forward automatically
      // (election_core.loksabha_years) -- never a fixed year list.
      var years = d.party.loksabha_years.map(String);
      var nextYear = years[years.length - 1];
      var lsRow = $("eh-loksabha");
      years.forEach(function (y) {
        var wrap = el("div", "pv-lang");
        wrap.appendChild(el("label", "", y + (y === nextYear ? " (planning to)" : "")));
        wrap.appendChild(partySelect("eh-ls-" + y, d.party.loksabha[y] || "", parties));
        lsRow.appendChild(wrap);
      });
      var vsRow = $("eh-vidhansabha");
      [["last", "Last election"], ["next", "Next election"]].forEach(function (k) {
        var wrap = el("div", "pv-lang");
        wrap.appendChild(el("label", "", k[1]));
        wrap.appendChild(partySelect("eh-vs-" + k[0], d.party.vidhansabha[k[0]] || "", parties));
        vsRow.appendChild(wrap);
      });
      $("eh-save-btn").addEventListener("click", function () {
        var payload = { loksabha: {}, vidhansabha: {} };
        years.forEach(function (y) { payload.loksabha[y] = $("eh-ls-" + y).value; });
        payload.vidhansabha.last = $("eh-vs-last").value; payload.vidhansabha.next = $("eh-vs-next").value;
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

  // ---- Kundali (North Indian style) ----
  var CELLS = { // house -> polygon in a 400x400 square
    1: [[100, 100], [200, 0], [300, 100], [200, 200]], 2: [[0, 0], [200, 0], [100, 100]], 3: [[0, 0], [100, 100], [0, 200]],
    4: [[100, 100], [0, 200], [100, 300], [200, 200]], 5: [[0, 200], [100, 300], [0, 400]], 6: [[0, 400], [100, 300], [200, 400]],
    7: [[100, 300], [200, 400], [300, 300], [200, 200]], 8: [[200, 400], [300, 300], [400, 400]], 9: [[400, 400], [300, 300], [400, 200]],
    10: [[300, 300], [400, 200], [300, 100], [200, 200]], 11: [[400, 200], [300, 100], [400, 0]], 12: [[400, 0], [300, 100], [200, 0]]
  };
  var SIGN_NO = { Aries: 1, Taurus: 2, Gemini: 3, Cancer: 4, Leo: 5, Virgo: 6, Libra: 7, Scorpio: 8, Sagittarius: 9, Capricorn: 10, Aquarius: 11, Pisces: 12 };
  var ABBR = { Sun: "Su", Moon: "Mo", Mars: "Ma", Mercury: "Me", Jupiter: "Ju", Venus: "Ve", Saturn: "Sa", Rahu: "Ra", Ketu: "Ke" };

  function chartSvg(houses, ascLabel) {
    var ns = "http://www.w3.org/2000/svg", NS = function (n, a) { var e = document.createElementNS(ns, n); for (var k in a) e.setAttribute(k, a[k]); return e; };
    var svg = NS("svg", { viewBox: "0 0 400 400", role: "img", "aria-label": "Kundali chart" });
    houses.forEach(function (h) {
      var pts = CELLS[h.n], cx = 0, cy = 0;
      pts.forEach(function (p) { cx += p[0]; cy += p[1]; }); cx /= pts.length; cy /= pts.length;
      svg.appendChild(NS("polygon", { points: pts.map(function (p) { return p.join(","); }).join(" "), fill: h.n === 1 ? "rgba(255,138,31,0.18)" : "rgba(255,255,255,0.03)", stroke: "#ffd24a", "stroke-width": 1.6 }));
      var t = NS("text", { x: cx, y: cy - (h.planets.length ? 8 : 0), "text-anchor": "middle", "font-size": 13, fill: "#8fa3ba" });
      t.textContent = SIGN_NO[h.sign]; svg.appendChild(t);
      if (h.planets.length) {
        var pl = NS("text", { x: cx, y: cy + 10, "text-anchor": "middle", "font-size": 13, "font-weight": 700, fill: "#fff" });
        pl.textContent = h.planets.map(function (p) { return ABBR[p] || p; }).join(" "); svg.appendChild(pl);
      }
    });
    svg.appendChild(NS("rect", { x: 0.8, y: 0.8, width: 398.4, height: 398.4, fill: "none", stroke: "#ffd24a", "stroke-width": 2.4 }));
    return svg;
  }

  var kBtn = $("kundali-btn"), kModal = $("kundali-modal");
  if (kBtn && window.QM_KUNDALI) {
    var built = false;
    kBtn.addEventListener("click", function () {
      if (!built) {
        var k = window.QM_KUNDALI;
        $("kundali-chart").appendChild(chartSvg(k.houses));
        var cap = document.createElement("p"); cap.className = "qm-timeline-note";
        cap.textContent = "North Indian style · numbers are signs (1 = Aries … 12 = Pisces), house 1 (top) is the ascendant.";
        $("kundali-chart").appendChild(cap);
        var tb = $("kundali-rows");
        k.rows.forEach(function (r) {
          var tr_ = document.createElement("tr");
          [r.planet, r.sign, r.degree, r.nakshatra, r.pada, r.lord].forEach(function (v) { var td = document.createElement("td"); td.textContent = v; tr_.appendChild(td); });
          tb.appendChild(tr_);
        });
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
})();
