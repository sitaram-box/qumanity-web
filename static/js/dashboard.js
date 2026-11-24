/**
 * dashboard.js — 4-tab dashboard shell + Edit Profile request queueing.
 *
 * Private is fully built out; Global/Public have real sub-tabs wired to
 * the user's present location (Earth/Continent/Country and Zone/State/
 * District/Tehsil/Village respectively, via /api/location/stats/<level>/
 * <id>?basis=present — see app.py); Personal is an honest "Coming Soon"
 * placeholder, matching Karma Summary/Recent Activities' same pattern
 * elsewhere on this page (no backing system built for either yet).
 */
(function () {
  "use strict";

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }

  var tabs = Array.prototype.slice.call(document.querySelectorAll(".qm-dash-tab"));
  var panels = {
    // "home" (2026-11-24, Chat-as-Dashboard Phase 2 Step 2): the only new entry -- everything
    // else in this map, and the click-handling loop below it, is unchanged from the old
    // horizontal tab bar.
    home: document.getElementById("qm-dash-home"),
    private: document.getElementById("qm-dash-private"),
    personal: document.getElementById("qm-dash-personal"),
    public: document.getElementById("qm-dash-public"),
    global: document.getElementById("qm-dash-global"),
  };

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var name = tab.getAttribute("data-tab");
      tabs.forEach(function (t) { t.classList.toggle("is-active", t === tab); });
      Object.keys(panels).forEach(function (key) {
        var panel = panels[key];
        if (panel) panel.hidden = key !== name;
      });
    });
  });

  // Settings (2026-11-24): lives inside the Private panel's own pv-settings card (Language/PIN/
  // sign-out) -- always has. Rather than build a second settings surface, the rail's gear just
  // opens Private (by reusing the SAME click handler above, not a second copy of the panel-switch
  // logic) and expands that card.
  var settingsBtn = document.getElementById("qm-dash-settings-btn");
  if (settingsBtn) {
    settingsBtn.addEventListener("click", function () {
      var privateTab = document.querySelector('.qm-dash-tab[data-tab="private"]');
      if (privateTab) privateTab.click();
      var settingsCard = document.querySelector(".pv-settings");
      if (settingsCard) {
        settingsCard.open = true;
        settingsCard.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  // ==================== Home tab: Unified Chat (Chat-as-Dashboard Phase 2 Step 2, 2026-11-24) ====================
  // Promoted verbatim from the standalone /chat page (templates/chat.html + static/js/chat.js,
  // now retired -- app.py's /chat redirects here). The ONLY thing dropped is that page's own
  // icon rail (Activity/Chat/Channels/Karma/Profile) -- always non-functional placeholders (see
  // that file's own module docstring), now replaced by this dashboard's real one above. Every
  // other function below -- the aggregator fetch, the list/filter/presence/feed/composer/Members-
  // panel/Karma-badge logic -- is unchanged. `el()` is reused from this file's own top-of-file
  // helper (identical signature) rather than redefined a second time.
  function $(id) { return document.getElementById(id); }
  function chatApi(url, body) {
    var opt = body !== undefined
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {};
    return fetch(url, opt).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) throw new Error(j.error || "Something went wrong");
        return j;
      });
    });
  }
  function chatAgo(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    var sameDay = d.toDateString() === new Date().toDateString();
    return sameDay ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : d.toLocaleDateString();
  }

  // ---- Per-kind message routes -- mirrors Qumanity_App/mobile/src/api/qumanity.ts exactly ----
  var CHAT_ROUTE = {
    sub: function (id) { return "/api/chat/" + id; },
    local: function (id) { return "/api/local-areas/" + id + "/chat"; },
    family: function (id) { return "/api/family-groups/" + id + "/messages"; },
    group: function (id) { return "/api/people/groups/" + id + "/messages"; },
    private: function (id) { return "/api/people/chats/" + id; },
  };

  var CHAT_PRESENCE_COLOR = { green: "#3DBE6B", yellow: "#F2B705", grey: "#8A97A3", red: "#E0483E" };
  var CHAT_PRESENCE_LABEL = { green: "Active now", yellow: "Away", grey: "Offline", red: "Busy" };

  var chatState = {
    conversations: [],
    filter: "all",
    active: null,       // the open conversation's own row from chatState.conversations
    activeMembers: [],  // [{user_id, name}], refreshed each time a conversation opens
  };

  function loadConversations() {
    return chatApi("/api/chat/conversations").then(function (r) {
      chatState.conversations = r.conversations;
      renderChatList();
      refreshPrivatePresence();
    });
  }

  function matchesChatFilter(c) {
    if (chatState.filter === "unread") return c.unread_count > 0;
    if (chatState.filter === "mentions") return false; // no @mention detection exists yet
    return true;
  }

  function renderChatList() {
    var list = $("qm-chat-list");
    if (!list) return;
    list.innerHTML = "";
    var visible = chatState.conversations.filter(matchesChatFilter);
    if (!visible.length) {
      var emptyText = chatState.filter === "unread" ? "No unread conversations."
        : chatState.filter === "mentions" ? "No mentions yet."
        : "Nothing here yet.";
      list.appendChild(el("p", "qm-chat-empty", emptyText));
      return;
    }

    var privateItems = visible.filter(function (c) { return c.pane === "private"; });
    var channelItems = visible.filter(function (c) { return c.pane === "channel"; });

    if (privateItems.length) {
      list.appendChild(el("div", "qm-chat-list-section-title", "Private"));
      privateItems.forEach(function (c) { list.appendChild(buildChatRow(c)); });
    }

    if (channelItems.length) {
      list.appendChild(el("div", "qm-chat-list-section-title", "Channels"));
      var groups = {};
      var order = [];
      channelItems.forEach(function (c) {
        var key = (c.location_level || "") + ":" + (c.location_id || "");
        if (!groups[key]) { groups[key] = []; order.push(key); }
        groups[key].push(c);
      });
      order.forEach(function (key) {
        var group = groups[key];
        var level = group[0].location_level;
        var label = level ? level.charAt(0).toUpperCase() + level.slice(1) + " · " + group[0].location_id : "Channel";
        list.appendChild(el("div", "qm-chat-list-group-label", label));
        group.forEach(function (c) { list.appendChild(buildChatRow(c)); });
      });
    }
  }

  function buildChatRow(c) {
    var row = el("button", "qm-chat-row" + (chatState.active && chatState.active.kind === c.kind && chatState.active.id === c.id ? " is-active" : ""));
    row.type = "button";
    row.setAttribute("data-kind", c.kind);
    row.setAttribute("data-id", c.id);

    var avatar = el("span", "qm-chat-row-avatar", (c.title || "?").trim().charAt(0).toUpperCase());
    if (c.pane === "private") {
      var dot = el("span", "qm-presence-dot qm-presence-dot--grey");
      dot.setAttribute("data-presence-for", c.other_user_id);
      avatar.appendChild(dot);
    }
    row.appendChild(avatar);

    var body = el("div", "qm-chat-row-body");
    var titleRow = el("div", "qm-chat-row-title-row");
    titleRow.appendChild(el("span", "qm-chat-row-title", c.title));
    titleRow.appendChild(el("span", "qm-chat-row-time", chatAgo(c.last_message_at)));
    body.appendChild(titleRow);
    var sub = el("div", "qm-chat-row-sub", c.pane === "channel" ? (c.location_level ? c.location_level.charAt(0).toUpperCase() + c.location_level.slice(1) + " Channel" : "Channel") : "Private chat");
    body.appendChild(sub);
    row.appendChild(body);

    if (c.unread_count > 0) row.appendChild(el("span", "qm-chat-row-badge", String(c.unread_count)));

    row.addEventListener("click", function () { openConversation(c); });
    return row;
  }

  function refreshPrivatePresence() {
    var ids = chatState.conversations.filter(function (c) { return c.pane === "private" && c.other_user_id; }).map(function (c) { return c.other_user_id; });
    if (!ids.length) return;
    chatApi("/api/presence/batch?user_ids=" + ids.join(",")).then(function (r) {
      Object.keys(r.statuses).forEach(function (uid) {
        document.querySelectorAll('[data-presence-for="' + uid + '"]').forEach(function (dot) {
          dot.className = "qm-presence-dot qm-presence-dot--" + r.statuses[uid];
          dot.title = CHAT_PRESENCE_LABEL[r.statuses[uid]] || "";
        });
      });
    }).catch(function () { /* presence is advisory; a failed fetch just leaves the grey default */ });
  }

  document.querySelectorAll(".qm-chat-filter-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".qm-chat-filter-tab").forEach(function (t) {
        t.classList.toggle("is-active", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      chatState.filter = tab.getAttribute("data-filter");
      renderChatList();
    });
  });

  function openConversation(c) {
    chatState.active = c;
    renderChatList();
    $("qm-chat-feed-empty").hidden = true;
    $("qm-chat-feed-active").hidden = false;
    $("qm-chat-feed-name").textContent = c.title;
    $("qm-chat-feed-desc").textContent = c.pane === "channel"
      ? (c.location_level ? c.location_level.charAt(0).toUpperCase() + c.location_level.slice(1) + " · " + c.location_id : "")
      : "";
    $("qm-chat-messages").innerHTML = "<p class=\"qm-chat-empty\">Loading…</p>";

    chatApi(CHAT_ROUTE[c.kind](c.id)).then(function (r) {
      chatState.activeMembers = (r.extra && r.extra.members) || [];
      $("qm-chat-members-count").textContent = chatState.activeMembers.length ? String(chatState.activeMembers.length) : "";
      renderChatMessages(r.messages || [], c.pane === "channel");
    }).catch(function (e) {
      $("qm-chat-messages").innerHTML = "";
      $("qm-chat-messages").appendChild(el("p", "qm-chat-empty", e.message));
    });
  }

  function renderChatMessages(messages, isChannel) {
    var box = $("qm-chat-messages");
    box.innerHTML = "";
    messages.forEach(function (m) {
      var row = el("div", "qm-chat-message" + (m.mine ? " qm-chat-message--mine" : ""));
      if (!m.mine) row.appendChild(el("div", "qm-chat-message-who", m.who || ""));
      var bubble = el("div", "qm-chat-message-bubble");
      bubble.appendChild(el("span", "qm-chat-message-text", m.text));
      var badge = el("span", "qm-karma-badge");
      badge.hidden = true; // filled in by applyKarmaBadges() once the lookup resolves, Governance pane only
      badge.setAttribute("data-karma-for", m.user_id || "");
      bubble.appendChild(badge);
      row.appendChild(bubble);
      row.appendChild(el("div", "qm-chat-message-at", chatAgo(m.at)));
      box.appendChild(row);
    });
    box.scrollTop = box.scrollHeight;
    if (isChannel) applyKarmaBadges(messages);
  }

  function applyKarmaBadges(messages) {
    var ids = Array.from(new Set(messages.map(function (m) { return m.user_id; }).filter(Boolean)));
    if (!ids.length) return;
    var since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    chatApi("/api/karma/recent?user_ids=" + ids.join(",") + "&since=" + encodeURIComponent(since)).then(function (r) {
      Object.keys(r.karma).forEach(function (uid) {
        var entry = r.karma[uid];
        document.querySelectorAll('[data-karma-for="' + uid + '"]').forEach(function (badge) {
          badge.hidden = false;
          badge.textContent = "✦ +" + entry.points + " Karma";
          badge.title = entry.reason + " · " + chatAgo(entry.at);
        });
      });
    }).catch(function () { /* the badge is a bonus; a failed lookup just means no badge shows */ });
  }

  var chatComposer = $("qm-chat-composer");
  if (chatComposer) {
    chatComposer.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!chatState.active) return;
      var input = $("qm-chat-input");
      var text = input.value.trim();
      if (!text) return;
      input.disabled = true;
      chatApi(CHAT_ROUTE[chatState.active.kind](chatState.active.id), { text: text }).then(function () {
        input.value = "";
        input.disabled = false;
        openConversation(chatState.active); // reload so the new message (and anyone else's since) shows
      }).catch(function (err) {
        input.disabled = false;
        window.alert(err.message);
      });
    });
  }

  var chatMembersBtn = $("qm-chat-members-btn");
  if (chatMembersBtn) {
    chatMembersBtn.addEventListener("click", function () {
      if (!chatState.active) return;
      var overlay = $("qm-chat-members-overlay");
      var listEl = $("qm-chat-members-list");
      listEl.innerHTML = "<p class=\"qm-chat-empty\">Loading…</p>";
      overlay.hidden = false;

      chatMembersFor(chatState.active).then(function (members) {
        listEl.innerHTML = "";
        if (!members.length) {
          listEl.appendChild(el("p", "qm-chat-empty", "No other members yet."));
          return;
        }
        members.forEach(function (m) {
          var row = el("div", "qm-chat-members-row");
          var avatar = el("span", "qm-chat-row-avatar", (m.name || "?").trim().charAt(0).toUpperCase());
          var dot = el("span", "qm-presence-dot qm-presence-dot--grey");
          dot.setAttribute("data-presence-for", m.user_id);
          avatar.appendChild(dot);
          row.appendChild(avatar);
          row.appendChild(el("span", "qm-chat-members-name", m.name));
          listEl.appendChild(row);
        });
        var ids = members.map(function (m) { return m.user_id; });
        chatApi("/api/presence/batch?user_ids=" + ids.join(",")).then(function (r) {
          Object.keys(r.statuses).forEach(function (uid) {
            listEl.querySelectorAll('[data-presence-for="' + uid + '"]').forEach(function (dot) {
              dot.className = "qm-presence-dot qm-presence-dot--" + r.statuses[uid];
              dot.title = CHAT_PRESENCE_LABEL[r.statuses[uid]] || "";
            });
          });
        }).catch(function () { /* advisory only */ });
      });
    });
  }

  function chatMembersFor(c) {
    if (c.kind === "family" || c.kind === "group") return Promise.resolve(chatState.activeMembers);
    if (c.kind === "private") return Promise.resolve(c.other_user_id ? [{ user_id: c.other_user_id, name: c.title }] : []);
    if (c.kind === "local") return chatApi("/api/local-areas/" + c.id + "/members").then(function (r) { return r.members; });
    return chatApi("/api/subgroups/" + c.id + "/members").then(function (r) { return r.members; }); // kind === 'sub'
  }

  var chatMembersClose = $("qm-chat-members-close");
  if (chatMembersClose) chatMembersClose.addEventListener("click", function () { $("qm-chat-members-overlay").hidden = true; });

  if ($("qm-chat-list")) {
    loadConversations();
    // Same 30-second cadence dash_extras.js's own notification poll already uses elsewhere on
    // this page -- not a new, more aggressive loop. Keeps running regardless of which rail tab
    // is active, same as that poll.
    setInterval(loadConversations, 30000);
  }

  // ---- Statistics Dashboard Upgrade (2026-11-16) ----
  // Both /api/location/stats/<level>/<id> and /api/earth/stats return small-count-suppressed
  // person-counts: any true value of 1-4 comes back as the literal string "<5", never a number
  // (app.py's _suppress_small_count) -- so every helper below must treat "<5" as "a real but
  // UNKNOWABLE small number", never coerce it to 0 or fabricate a percentage from it.
  //
  // Dict-shaped fields (gender/elements/signs) are NOT returned in a stable order: Flask's
  // jsonify() alphabetizes dict keys on the wire (confirmed directly: jsonify({"male":11,
  // "female":7,"both":0}) -> {"both":0,"female":7,"male":11}), independent of the Python dict's
  // own insertion order -- this, not a display bug, is why "Third gender" used to render first.
  // age_bands is a JSON ARRAY, so it was never affected. Fix: every one of these three fields is
  // now walked in an explicit, hardcoded order below -- Object.keys() on any of them is never
  // trusted again.
  function isSuppressed(v) { return v === "<5"; }
  function formatCount(v) { return isSuppressed(v) ? "<5" : String(v); }

  // A suppressed slice/bar's TRUE value (1-4) is deliberately unknowable -- 2 is just a plausible
  // stand-in used ONLY to size its wedge/bar so it reads as "a small amount" relative to the rest,
  // never shown as a number anywhere; the displayed label is always the literal "<5".
  var SUPPRESSED_SIZE_ESTIMATE = 2;

  function sliceFraction(value, total) {
    if (isSuppressed(total) || !total) return 0;
    return Math.max(0, (isSuppressed(value) ? SUPPRESSED_SIZE_ESTIMATE : value) / total);
  }

  // null means "can't be computed" (either side suppressed, or no total) -- callers render "<5"
  // in that case rather than a fabricated number.
  function computePct(value, total) {
    if (isSuppressed(value) || isSuppressed(total) || !total) return null;
    return Math.round((value / total) * 100);
  }
  function pctLabel(value, total) {
    var pct = computePct(value, total);
    return pct === null ? "<5" : pct + "%";
  }
  function countAndPctLabel(value, total) {
    var pct = computePct(value, total);
    return pct === null ? formatCount(value) : formatCount(value) + " · " + pct + "%";
  }

  var GENDER_LABELS = { male: "Male", female: "Female", both: "Third gender" };
  var GENDER_ORDER = ["female", "male", "both"];
  var GENDER_COLORS = { female: "#E85D9E", male: "#4FA3E0", both: "#B08BF0" };

  var ELEMENT_ORDER = ["Fire", "Earth", "Air", "Water"];
  var ELEMENT_COLORS = { Fire: "#FF5B45", Earth: "#5FB85C", Air: "#4FC3D9", Water: "#4A7FE0" };

  // Canonical Aries->Pisces wheel order and element groupings, matching zodiac_core.py's own
  // ZODIAC_RANGES -- reused here rather than re-derived, so the two can never drift apart.
  var ZODIAC_ORDER = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio",
                       "Sagittarius", "Capricorn", "Aquarius", "Pisces"];
  var SIGN_ELEMENT = {
    Aries: "Fire", Leo: "Fire", Sagittarius: "Fire",
    Taurus: "Earth", Virgo: "Earth", Capricorn: "Earth",
    Gemini: "Air", Libra: "Air", Aquarius: "Air",
    Cancer: "Water", Scorpio: "Water", Pisces: "Water",
  };
  // Same grouping, element-first -- matches the Phone App's statsCharts.logic.ts ELEMENT_SIGNS,
  // which is what the four-pies design (2026-11-20) is built from.
  var ELEMENT_SIGNS = {
    Fire: ["Aries", "Leo", "Sagittarius"],
    Earth: ["Taurus", "Virgo", "Capricorn"],
    Air: ["Gemini", "Libra", "Aquarius"],
    Water: ["Cancer", "Scorpio", "Pisces"],
  };

  function hexToHsl(hex) {
    var r = parseInt(hex.slice(1, 3), 16) / 255, g = parseInt(hex.slice(3, 5), 16) / 255, b = parseInt(hex.slice(5, 7), 16) / 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b), h = 0, s = 0, l = (max + min) / 2;
    if (max !== min) {
      var d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
      else if (max === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h *= 60;
    }
    return { h: h, s: s * 100, l: l * 100 };
  }
  function hslToHex(h, s, l) {
    s /= 100; l /= 100;
    var c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = l - c / 2, r, g, b;
    if (h < 60) { r = c; g = x; b = 0; } else if (h < 120) { r = x; g = c; b = 0; }
    else if (h < 180) { r = 0; g = c; b = x; } else if (h < 240) { r = 0; g = x; b = c; }
    else if (h < 300) { r = x; g = 0; b = c; } else { r = c; g = 0; b = x; }
    var toHex = function (v) { var n = Math.round((v + m) * 255); return ("0" + n.toString(16)).slice(-2); };
    return "#" + toHex(r) + toHex(g) + toHex(b);
  }

  // Three shades per element (slightly darker / base / slightly lighter), assigned in wheel order
  // so e.g. Aries/Leo/Sagittarius -- the three Fire signs -- read as a visually related family
  // without being identical, same idea as a single-hue sequential palette.
  var SIGN_COLORS = (function () {
    var seen = {}, colors = {};
    ZODIAC_ORDER.forEach(function (sign) {
      var element = SIGN_ELEMENT[sign], idx = seen[element] || 0;
      var hsl = hexToHsl(ELEMENT_COLORS[element]);
      var delta = [-12, 0, 14][idx] || 0;
      colors[sign] = hslToHex(hsl.h, hsl.s, Math.max(15, Math.min(85, hsl.l + delta)));
      seen[element] = idx + 1;
    });
    return colors;
  })();

  // Builds a donut (ring) chart as inline SVG: one <circle> per slice, stroke-dasharray/-dashoffset
  // carving out its own arc of the ring -- the standard lightweight, no-library SVG donut technique.
  // slices: [{frac (0..1 of the full circle), color, title}].
  function buildDonutSVG(slices, size, strokeWidth) {
    var r = (size - strokeWidth) / 2, cx = size / 2, cy = size / 2, circumference = 2 * Math.PI * r;
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + size + " " + size);
    svg.setAttribute("class", "qm-donut-svg");
    var offset = 0;
    slices.forEach(function (s) {
      if (s.frac <= 0) return;
      var len = s.frac * circumference;
      var circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", cx); circle.setAttribute("cy", cy); circle.setAttribute("r", r);
      circle.setAttribute("fill", "none");
      circle.setAttribute("stroke", s.color);
      circle.setAttribute("stroke-width", strokeWidth);
      circle.setAttribute("stroke-dasharray", len + " " + (circumference - len));
      circle.setAttribute("stroke-dashoffset", -offset);
      circle.setAttribute("transform", "rotate(-90 " + cx + " " + cy + ")");
      circle.setAttribute("class", "qm-donut-slice");
      var title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = s.title;
      circle.appendChild(title);
      svg.appendChild(circle);
      offset += len;
    });
    return svg;
  }

  // Filled pie wedges as inline SVG <path> elements, starting at 12 o'clock, clockwise -- the
  // Phone App's own per-element pie design (components/statsCharts.logic.ts's pieWedges()),
  // ported here for the four-element Zodiac layout (2026-11-20). Unlike buildDonutSVG() above,
  // slices here are shares of THIS pie's own total (one element's 3 signs), not of everyone --
  // the caller passes raw sign counts and this normalizes them itself, same as the mobile logic.
  // A single slice covering the whole pie is drawn as a full circle, since an arc path can't.
  function buildPieSVG(slices, size) {
    var r = size / 2, cx = r, cy = r;
    var total = slices.reduce(function (s, x) { return s + Math.max(0, x.frac); }, 0);
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + size + " " + size);
    svg.setAttribute("class", "qm-pie-svg");
    var bg = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    bg.setAttribute("cx", cx); bg.setAttribute("cy", cy); bg.setAttribute("r", r);
    bg.setAttribute("class", "qm-pie-bg");
    svg.appendChild(bg);
    if (total <= 0) return svg;
    function point(a) { return (cx + r * Math.sin(a)).toFixed(3) + " " + (cy - r * Math.cos(a)).toFixed(3); }
    var angle = 0;
    slices.forEach(function (s) {
      if (s.frac <= 0) return;
      var share = s.frac / total, node, title;
      if (share >= 0.9999) {
        node = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        node.setAttribute("cx", cx); node.setAttribute("cy", cy); node.setAttribute("r", r);
      } else {
        var start = angle;
        angle += share * 2 * Math.PI;
        var large = share > 0.5 ? 1 : 0;
        node = document.createElementNS("http://www.w3.org/2000/svg", "path");
        node.setAttribute("d", "M" + cx + " " + cy + " L" + point(start) + " A" + r + " " + r + " 0 " + large + " 1 " + point(angle) + " Z");
        node.setAttribute("class", "qm-pie-wedge");
      }
      node.setAttribute("fill", s.color);
      title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = s.title;
      node.appendChild(title);
      svg.appendChild(node);
    });
    return svg;
  }

  function legendRow(color, label, value, total) {
    var row = el("div", "qm-legend-row");
    var swatch = el("span", "qm-legend-swatch"); swatch.style.background = color;
    row.appendChild(swatch);
    row.appendChild(el("span", "qm-legend-label", label));
    row.appendChild(el("span", "qm-legend-pct", pctLabel(value, total)));
    return row;
  }

  function renderGenderBars(prefix, stats) {
    var container = document.getElementById(prefix + "-gender-list");
    if (!container) return;
    container.innerHTML = "";
    var total = stats.total_humans;
    GENDER_ORDER.forEach(function (key) {
      var value = stats.gender[key];
      var row = el("div", "qm-stat-row");
      row.appendChild(el("span", "qm-stat-row-label", GENDER_LABELS[key]));
      var barWrap = el("div", "qm-stat-row-bar");
      var barFill = el("div", "qm-stat-row-bar-fill");
      barFill.style.width = (sliceFraction(value, total) * 100) + "%";
      barFill.style.background = GENDER_COLORS[key];
      barWrap.appendChild(barFill);
      row.appendChild(barWrap);
      row.appendChild(el("span", "qm-stat-row-value", countAndPctLabel(value, total)));
      container.appendChild(row);
    });
  }

  function renderAgeColumns(prefix, stats) {
    var container = document.getElementById(prefix + "-age-chart");
    if (!container) return;
    container.innerHTML = "";
    var total = stats.total_humans;
    stats.age_bands.forEach(function (band) {
      var col = el("div", "qm-age-col");
      col.appendChild(el("div", "qm-age-col-value", countAndPctLabel(band.count, total)));
      var track = el("div", "qm-age-col-track");
      var fill = el("div", "qm-age-col-fill");
      fill.style.height = Math.max(sliceFraction(band.count, total) * 100, band.count === 0 ? 0 : 3) + "%";
      track.appendChild(fill);
      col.appendChild(track);
      col.appendChild(el("div", "qm-age-col-label", band.label));
      container.appendChild(col);
    });
  }

  function renderElementDonut(prefix, stats) {
    var chart = document.getElementById(prefix + "-element-chart"), legend = document.getElementById(prefix + "-element-legend");
    if (!chart || !legend) return;
    chart.innerHTML = ""; legend.innerHTML = "";
    var total = stats.total_humans;
    chart.appendChild(buildDonutSVG(ELEMENT_ORDER.map(function (name) {
      return { frac: sliceFraction(stats.elements[name], total), color: ELEMENT_COLORS[name], title: name };
    }), 120, 20));
    ELEMENT_ORDER.forEach(function (name) { legend.appendChild(legendRow(ELEMENT_COLORS[name], name, stats.elements[name], total)); });
  }

  // Four small pies, one per element, each showing its own 3 signs -- matches the Phone App's
  // design (app/place/[level]/[id].tsx's SignPies, 2026-11-18), replacing the single 12-slice
  // donut this used to be. Each pie's wedges are sized by the 3 signs relative to EACH OTHER
  // (buildPieSVG normalizes within the element); every displayed percentage (the cell title and
  // each legend row) is still of everyone here, same as before -- only the wedge geometry's own
  // denominator changed, matching the Phone App's identical choice.
  function renderZodiacPies(prefix, stats) {
    var chart = document.getElementById(prefix + "-sign-chart"), legend = document.getElementById(prefix + "-sign-legend");
    if (!chart || !legend) return;
    chart.innerHTML = ""; legend.innerHTML = "";
    var total = stats.total_humans;
    var grid = el("div", "qm-sign-grid");
    ELEMENT_ORDER.forEach(function (name) {
      var signs = ELEMENT_SIGNS[name];
      var cell = el("div", "qm-sign-cell");
      var title = el("div", "qm-sign-cell-title", name + " · " + pctLabel(stats.elements[name], total));
      title.style.color = ELEMENT_COLORS[name];
      cell.appendChild(title);
      cell.appendChild(buildPieSVG(signs.map(function (s) {
        return { frac: isSuppressed(stats.signs[s]) ? SUPPRESSED_SIZE_ESTIMATE : (stats.signs[s] || 0), color: SIGN_COLORS[s], title: s };
      }), 104));
      var cellLegend = el("div", "qm-sign-cell-legend");
      signs.forEach(function (s) { cellLegend.appendChild(legendRow(SIGN_COLORS[s], s, stats.signs[s], total)); });
      cell.appendChild(cellLegend);
      grid.appendChild(cell);
    });
    chart.appendChild(grid);
  }

  function renderRegisteredStats(prefix, stats) {
    var totalEl = document.getElementById(prefix + "-total");
    if (!totalEl) return;
    totalEl.textContent = formatCount(stats.total_humans);
    var trulyEmpty = stats.total_humans === 0, suppressedTotal = isSuppressed(stats.total_humans);
    var emptyNote = document.getElementById(prefix + "-empty-note");
    if (emptyNote) {
      emptyNote.hidden = !(trulyEmpty || suppressedTotal);
      // A location with 1-4 people hides every breakdown outright, not just the raw numbers --
      // showing "<5" split four ways across gender/age/element/sign rows would still visually
      // narrow down who's who far more than the flat total alone, defeating the suppression this
      // is meant to provide. Same message either way; only the wording differs.
      emptyNote.textContent = suppressedTotal
        ? "Fewer than 5 registered here — detailed breakdown hidden to protect their privacy."
        : "No one has registered here yet.";
    }
    ["gender", "age", "element", "sign"].forEach(function (key) {
      var section = document.getElementById(prefix + "-" + key + "-section");
      if (section) section.hidden = trulyEmpty || suppressedTotal;
    });
    if (trulyEmpty || suppressedTotal) return;
    renderGenderBars(prefix, stats);
    renderAgeColumns(prefix, stats);
    renderElementDonut(prefix, stats);
    renderZodiacPies(prefix, stats);
  }

  function loadStatsFor(prefix, url) {
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (stats) { renderRegisteredStats(prefix, stats); })
      .catch(function (err) { console.error("Failed to load dashboard stats from " + url, err); });
  }

  function loadWalletBalanceFor(prefix, locationType, locationId, showCurrency) {
    var el = document.getElementById(prefix + "-wallet");
    if (!el) return;
    fetch("/api/wallet/balance/" + locationType + "/" + encodeURIComponent(locationId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        // 2026-10-27: qoin_count is the PUBLIC figure every viewer gets back (board_core.py's own
        // board header already keys off it, never the private balance_qoins -- council/admin
        // only, and simply absent from this response for anyone else).
        // 2026-11-01: the always-on sidebar (qm-dg-stats/qm-dp-stats) now shows Qoins only, never
        // a currency figure -- that's what clicking it (openStatsModal) is for. showCurrency is
        // true only there, and even then the ₹ value only appears when the server actually sent
        // balance_qoins (council/admin) -- never derived client-side from qoin_count, which would
        // just be re-inventing the same leak this gate exists to prevent.
        var n = data.qoin_count || 0;
        el.textContent = n.toLocaleString() + " Qoins";
        if (showCurrency && data.balance_qoins !== undefined) {
          el.textContent += " ≈ ₹" + data.balance_qoins.toLocaleString() + ".00";
        }
      })
      .catch(function (err) { console.error("Failed to load wallet balance for " + prefix, err); });
  }

  // 2026-11-01: modal-only transaction list -- same GET /api/wallet/history/<level>/<id> and the
  // same week-grouped rendering board.js's Q-Punch panel's "Group wallet — weekly history" button
  // already uses, just always-open instead of toggled, and targeting the stats modal's own list.
  function loadWalletHistoryFor(prefix, locationType, locationId) {
    var list = document.getElementById(prefix + "-tx-list");
    var empty = document.getElementById(prefix + "-tx-empty");
    var note = document.getElementById(prefix + "-tx-note");
    if (!list) return;
    list.innerHTML = ""; empty.hidden = true; note.hidden = true;
    fetch("/api/wallet/history/" + locationType + "/" + encodeURIComponent(locationId))
      .then(function (r) { return r.json(); })
      .then(function (h) {
        if (!h.is_council) { note.textContent = "Showing the last 3 months; full history is for council members."; note.hidden = false; }
        else if (h.older_weeks_hidden) { note.textContent = h.older_weeks_hidden + " older week(s) available to council members."; note.hidden = false; }
        empty.hidden = (h.weeks || []).length !== 0;
        (h.weeks || []).forEach(function (wk) {
          var box = el("div", "wh-week");
          box.appendChild(el("b", "", wk.start + " – " + wk.end + " · " + (wk.change >= 0 ? "+" : "") + wk.change + " Qoins"));
          wk.rows.forEach(function (r) {
            var when = new Date((r.at || "").replace(" ", "T"));
            var whenText = isNaN(when.getTime()) ? r.at : when.toLocaleString();
            box.appendChild(el("small", "", (r.amount >= 0 ? "+" : "") + r.amount + " · " + r.reason + " · " + whenText));
          });
          list.appendChild(box);
        });
      })
      .catch(function (err) { console.error("Failed to load wallet history for " + prefix, err); });
  }

  function loadCollectiveKarmaFor(prefix, locationType, locationId) {
    var el = document.getElementById(prefix + "-karma");
    if (!el) return;
    fetch("/api/karma/collective/" + locationType + "/" + encodeURIComponent(locationId))
      .then(function (r) { return r.json(); })
      .then(function (data) { el.textContent = data.points; })
      .catch(function (err) { console.error("Failed to load collective karma for " + prefix, err); });
  }

  // ==================== Detailed Stats modal (2026-10-27) ====================
  // The "📊 Stats" button on a board used to just scroll to this same data already loading,
  // cramped, in the permanent explorer sidebar (qm-dp-stats/qm-dg-stats) -- it still does that
  // job for the explorer tree itself, untouched. This is a SEPARATE, spacious view of the exact
  // same three endpoints (loadStatsFor/loadWalletBalanceFor/loadCollectiveKarmaFor, reused
  // unchanged -- they're already generic over `prefix`), reusing the `stat_block` Jinja macro a
  // second time with prefix "qm-stats-modal" so no new rendering code was needed, just a new
  // target.
  var statsModal = document.getElementById("qm-stats-modal");
  if (statsModal) {
    statsModal.addEventListener("click", function (e) {
      if (e.target === statsModal || e.target.hasAttribute("data-close")) statsModal.hidden = true;
    });
  }

  function openStatsModal(level, locationId, name) {
    if (!statsModal) return;
    document.getElementById("qm-stats-modal-heading").textContent = name ? "📊 " + name : "Statistics";
    // stat_block's Announcements/Report Inbox sections are only ever populated by board.js's
    // renderAnnouncements()/renderReportInbox(), which are hardcoded to the sidebar's own two
    // prefixes -- nothing fills them in for this modal's prefix, so they'd just sit empty
    // forever. Hidden here rather than shown stale, keeping this view to the five items it's
    // actually for (the explorer sidebar still carries both, unaffected).
    ["announce", "reportinbox"].forEach(function (s) {
      var section = document.getElementById("qm-stats-modal-" + s + "-section");
      if (section) section.hidden = true;
    });
    statsModal.hidden = false;
    // "earth" has its own dedicated endpoint (no karma/wallet-shape difference -- just not part
    // of _LOCATION_STATS_LEVELS in app.py, the same special case renderGlobalExplorer() already
    // carves out for the sidebar version of this exact data).
    var statsUrl = level === "earth" ? "/api/earth/stats" : "/api/location/stats/" + level + "/" + encodeURIComponent(locationId) + "?basis=present";
    loadStatsFor("qm-stats-modal", statsUrl);
    loadWalletBalanceFor("qm-stats-modal", level, locationId, true);
    loadCollectiveKarmaFor("qm-stats-modal", level, locationId);
    loadWalletHistoryFor("qm-stats-modal", level, locationId);
    renderRequestJoin(level, locationId);
  }
  window.QMOpenStatsModal = openStatsModal;

  // ---- Request to Join (Chat-as-Dashboard Phase 2 Step 2, 2026-11-24) ----
  // Modal-only (see this section's own comment in dashboard.html) -- wired to chat_core.py's
  // 3-strike escalation built in Step 1 (GET/POST /api/chat/temporary-access, already live).
  // "Home" here means the viewer's OWN present-location chain at this exact level -- comparing
  // against window.QM_PRESENT_LOCATION, the same global this file already reads for the explorer
  // sidebar's own siblings-of-my-own-chain scoping, never re-derived a second way.
  function isHomeLocation(level, locationId) {
    var node = presentLocation[level];
    return !!(node && String(node.id) === String(locationId));
  }

  function renderRequestJoin(level, locationId) {
    var section = document.getElementById("qm-stats-modal-request-join");
    if (!section) return;
    if (level === "earth" || isHomeLocation(level, locationId)) { section.hidden = true; return; }
    section.hidden = false;
    var idEl = document.getElementById("qm-stats-modal-request-join-id");
    var statusEl = document.getElementById("qm-stats-modal-request-join-status");
    var btn = document.getElementById("qm-stats-modal-request-join-btn");
    var errEl = document.getElementById("qm-stats-modal-request-join-error");
    idEl.textContent = "Location ID: " + locationId;
    statusEl.hidden = true;
    btn.hidden = true;
    errEl.hidden = true;

    fetch("/api/chat/temporary-access").then(function (r) { return r.json(); }).then(function (data) {
      var mine = (data.requests || []).filter(function (r) { return r.location_level === level && r.location_id === locationId; });
      var live = mine.filter(function (r) { return r.status === "pending" || r.status === "active"; })[0];
      var deniedFinal = mine.filter(function (r) { return r.status === "denied_final"; })[0];
      if (live) {
        statusEl.hidden = false;
        statusEl.textContent = live.status === "pending"
          ? "⏳ Request pending — awaiting the " + (live.decision_level || level) + " council."
          : "✅ You have temporary access here.";
      } else if (deniedFinal) {
        statusEl.hidden = false;
        statusEl.textContent = "🚫 Request denied after 3 attempts — this location can't be requested again.";
      } else {
        btn.hidden = false;
      }
    }).catch(function () { /* advisory only -- a failed lookup just leaves the button hidden */ });

    btn.onclick = function () {
      btn.disabled = true;
      fetch("/api/chat/temporary-access", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ location_level: level, location_id: locationId }),
      }).then(function (r) {
        return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; });
      }).then(function () {
        renderRequestJoin(level, locationId);
      }).catch(function (e) {
        btn.disabled = false;
        errEl.hidden = false;
        errEl.textContent = e.message;
      });
    };
  }

  // 2026-11-01: the always-on sidebar itself (not just its "📊 Stats" board-header button) now
  // opens the same modal -- one delegated listener per sidebar rather than re-binding on every
  // selectLocation() call; the level/id/name it needs are read from data-* attributes that
  // selectLocation() (and the "earth" root case in renderGlobalExplorer()) keep current. Clicks on
  // an actual control inside the panel (View all / + New Announcement) are left alone.
  ["qm-dg-stats", "qm-dp-stats"].forEach(function (prefix) {
    var panel = document.getElementById(prefix + "-content");
    if (!panel) return;
    panel.classList.add("qm-stats-panel--clickable");
    panel.addEventListener("click", function (e) {
      if (e.target.closest("button, a")) return;
      if (!panel.dataset.level || !panel.dataset.locationId) return;
      openStatsModal(panel.dataset.level, panel.dataset.locationId, panel.dataset.name || null);
    });
  });

  // ==================== Location explorer (Global / Public tabs) ====================
  // A left-sidebar tree scoped to the user's own present-location lineage
  // (siblings at each level, not a free-roam browser of the whole Earth --
  // see docs/DASHBOARD_REDESIGN_PLAN.md). Reuses the same static JSON
  // endpoints register.js's own location pickers already consume; the one
  // per-tehsil village fetch stays lazy (fetched on expand/on root load),
  // everything else is fetched once and cached.
  var presentLocation = window.QM_PRESENT_LOCATION || {};
  var pilotVillageId = window.QM_PILOT_VILLAGE_ID || "";
  var worldData = null, indiaStates = null, indiaDistricts = null;
  // The 9 Indian Sub-continent countries have a Public timeline (zones down to
  // villages); indiaStates/indiaDistricts hold all of them, zones tagged with
  // their country_id.
  var SUBCONTINENT_CODES = ["IND", "NPL", "BTN", "BGD", "MMR", "LKA", "PAK", "BLC", "AFG", "MDV"];
  // Mirrors perception_core.SUBCONTINENT_COUNTRY_IDS / app.SUBCONTINENT_COUNTRY_IDS -- Country
  // Perception is only offered for these 10, matching the Founder's own UI scoping.
  var PERCEPTION_COUNTRY_IDS = [
    "O_AS_IND", "O_AS_NPL", "O_AS_BTN", "O_AS_BGD", "O_AS_MMR",
    "O_AS_LKA", "O_AS_PAK", "O_AS_BLC", "O_AS_AFG", "O_AS_MDV",
  ];
  var INDIA_COUNTRY_ID = "O_AS_IND";

  function loadTreeData() {
    var needsWorld = !!document.getElementById("global-explorer-tree");
    var needsIndia = !!document.getElementById("public-explorer-tree") ||
      (needsWorld && presentLocation.country && SUBCONTINENT_CODES.indexOf(presentLocation.country.code) !== -1);
    var jobs = [];
    if (needsWorld) jobs.push(fetch("/api/world-data").then(function (r) { return r.json(); }).then(function (d) { worldData = d; }));
    if (needsIndia) {
      jobs.push(fetch("/api/subcontinent").then(function (r) { return r.json(); }).then(function (d) {
        indiaStates = { zones: [] };
        d.countries.forEach(function (country) {
          country.zones.forEach(function (zone) {
            indiaStates.zones.push(Object.assign({ country_id: country.id }, zone));
          });
        });
      }));
      jobs.push(fetch("/api/subcontinent/districts").then(function (r) { return r.json(); }).then(function (d) { indiaDistricts = d; }));
    }
    return Promise.all(jobs);
  }

  function findContinentById(id) {
    return (worldData.continents || []).filter(function (c) { return c.id === id; })[0] || null;
  }
  function findZoneById(id) {
    return (indiaStates.zones || []).filter(function (z) { return z.id === id; })[0] || null;
  }
  function findDistrictById(stateId, districtId) {
    var stateData = indiaDistricts.states[stateId];
    if (!stateData) return null;
    return (stateData.districts || []).filter(function (d) { return d.id === districtId; })[0] || null;
  }

  // ---- Generic tree node: a toggle (if it has children) + a selectable
  // label. Children are built lazily on first expand -- getChildren may
  // return an array (already-cached data) or a Promise (the one live
  // per-tehsil village fetch). ----
  function buildNode(tab, label, idText, onSelect, getChildren, depth) {
    var li = document.createElement("li");
    li.className = "qm-explorer-node";

    var row = document.createElement("div");
    row.className = "qm-explorer-row";
    row.style.paddingLeft = (depth * 14) + "px";

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "qm-explorer-toggle";

    var labelBtn = document.createElement("button");
    labelBtn.type = "button";
    labelBtn.className = "qm-explorer-label";
    labelBtn.textContent = label;
    // Chat-as-Dashboard Phase 2 Step 2 (2026-11-24): the Location ID shown alongside every node,
    // not just the user's own -- "Request to Join" (the stats modal, selectLocation() below)
    // needs the viewer to actually see the id they're requesting against, same reason the old
    // Phase 1 proposal called this out as a real missing piece, not a cosmetic one.
    if (idText) {
      var idSpan = document.createElement("span");
      idSpan.className = "qm-explorer-node-id";
      idSpan.textContent = " (" + idText + ")";
      labelBtn.appendChild(idSpan);
    }

    var childList = document.createElement("ul");
    childList.className = "qm-explorer-tree";
    childList.hidden = true;
    var expanded = false, loaded = false;

    if (getChildren) {
      toggle.textContent = "▸";
      toggle.addEventListener("click", function () {
        if (!loaded) {
          loaded = true;
          var result = getChildren();
          var apply = function (items) { items.forEach(function (node) { childList.appendChild(node.li); }); };
          if (result && typeof result.then === "function") result.then(apply);
          else apply(result);
        }
        expanded = !expanded;
        childList.hidden = !expanded;
        toggle.textContent = expanded ? "▾" : "▸";
      });
    } else {
      toggle.disabled = true;
    }

    labelBtn.addEventListener("click", function () {
      var container = document.getElementById(tab + "-explorer-tree");
      Array.prototype.slice.call(container.querySelectorAll(".qm-explorer-label.is-active")).forEach(function (b) {
        b.classList.remove("is-active");
      });
      labelBtn.classList.add("is-active");
      onSelect();
    });

    row.appendChild(toggle);
    row.appendChild(labelBtn);
    li.appendChild(row);
    li.appendChild(childList);
    return { li: li, labelBtn: labelBtn };
  }

  function villageNode(tab, village, depth) {
    return buildNode(tab, village.name, village.id, function () { selectLocation(tab, "village", village.id, village.name); }, null, depth);
  }
  function tehsilNode(tab, tehsil, depth) {
    return buildNode(tab, tehsil.name, tehsil.id, function () { selectLocation(tab, "tehsil", tehsil.id, tehsil.name); }, function () {
      return fetch("/api/india-villages/" + encodeURIComponent(tehsil.id))
        .then(function (r) { return r.json(); })
        .then(function (data) { return (data.villages || []).map(function (v) { return villageNode(tab, v, depth + 1); }); });
    }, depth);
  }
  // A district's children: its tehsils, plus any villages that hang straight
  // off it (some countries have no tehsil tier there) -- fetched on demand.
  function districtChildren(tab, district, depth) {
    var tehsilNodes = (district.tehsils || []).map(function (t) { return tehsilNode(tab, t, depth); });
    if (!district.direct_villages) return tehsilNodes;
    return fetch("/api/india-villages/" + encodeURIComponent(district.id))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        return tehsilNodes.concat((data.villages || []).map(function (v) { return villageNode(tab, v, depth); }));
      });
  }
  function districtNode(tab, district, depth) {
    return buildNode(tab, district.name, district.id, function () { selectLocation(tab, "district", district.id, district.name); }, function () {
      return districtChildren(tab, district, depth + 1);
    }, depth);
  }
  function stateNode(tab, state, depth) {
    return buildNode(tab, state.name, state.id, function () { selectLocation(tab, "state", state.id, state.name); }, function () {
      var stateData = indiaDistricts.states[state.id];
      return (stateData ? stateData.districts : []).map(function (d) { return districtNode(tab, d, depth + 1); });
    }, depth);
  }
  function countryLeafNode(tab, country, depth) {
    return buildNode(tab, country.name, country.id, function () { selectLocation(tab, "country", country.id, country.name); }, null, depth);
  }
  function continentNode(tab, continent, depth) {
    return buildNode(tab, continent.name, continent.id, function () { selectLocation(tab, "continent", continent.id, continent.name); }, function () {
      return (continent.countries || []).map(function (c) { return countryLeafNode(tab, c, depth + 1); });
    }, depth);
  }

  function renderTreeRoot(containerId, nodes, emptyMessage) {
    var container = document.getElementById(containerId);
    container.innerHTML = "";
    Array.prototype.forEach.call(container.parentElement.querySelectorAll(".qm-explorer-note"), function (n) { n.remove(); });
    if (!nodes.length) {
      if (!emptyMessage) return;
      var note = document.createElement("p");
      note.className = "qm-explorer-note";
      note.textContent = emptyMessage;
      container.parentElement.insertBefore(note, container);
      return;
    }
    nodes.forEach(function (node) { container.appendChild(node.li); });
  }

  function renderGlobalExplorer(root) {
    if (root === "earth") {
      renderTreeRoot("global-explorer-tree", (worldData.continents || []).map(function (c) { return continentNode("global", c, 0); }), "No continents available.");
      loadStatsFor("qm-dg-stats", "/api/earth/stats");
      loadWalletBalanceFor("qm-dg-stats", "earth", "EARTH");
      loadCollectiveKarmaFor("qm-dg-stats", "earth", "EARTH");
      document.getElementById("qm-dg-stats-heading").textContent = "🌍 Earth statistics";
      var earthPanel = document.getElementById("qm-dg-stats-content");
      if (earthPanel) { earthPanel.dataset.level = "earth"; earthPanel.dataset.locationId = "EARTH"; earthPanel.dataset.name = "Earth"; }
    } else if (root === "continent") {
      var continent = presentLocation.continent && findContinentById(presentLocation.continent.id);
      renderTreeRoot("global-explorer-tree", continent ? continent.countries.map(function (c) { return countryLeafNode("global", c, 0); }) : [], "Continent not set.");
      if (presentLocation.continent) selectLocation("global", "continent", presentLocation.continent.id, presentLocation.continent.name);
    } else if (root === "country") {
      if (presentLocation.country && SUBCONTINENT_CODES.indexOf(presentLocation.country.code) !== -1) {
        renderTreeRoot("global-explorer-tree", (indiaStates.zones || []).filter(function (z) {
          return z.country_id === presentLocation.country.id;
        }).map(function (z) {
          return buildNode("global", z.name, z.id, function () { selectLocation("global", "zone", z.id, z.name); }, function () {
            return (z.states || []).map(function (s) { return stateNode("global", s, 1); });
          }, 0);
        }), "No zones available.");
      } else {
        renderTreeRoot("global-explorer-tree", [], "No further breakdown available for this country.");
      }
      if (presentLocation.country) selectLocation("global", "country", presentLocation.country.id, presentLocation.country.name);
    }
  }

  function renderPublicExplorer(root) {
    var p = presentLocation;
    if (root === "zone" && p.zone) {
      var zone = findZoneById(p.zone.id);
      renderTreeRoot("public-explorer-tree", zone ? zone.states.map(function (s) { return stateNode("public", s, 0); }) : [], "Zone not found.");
      selectLocation("public", "zone", p.zone.id, p.zone.name);
    } else if (root === "state" && p.state) {
      var stateData = indiaDistricts.states[p.state.id];
      renderTreeRoot("public-explorer-tree", stateData ? stateData.districts.map(function (d) { return districtNode("public", d, 0); }) : [], "State not found.");
      selectLocation("public", "state", p.state.id, p.state.name);
    } else if (root === "district" && p.district) {
      var district = findDistrictById(p.state.id, p.district.id);
      if (district) {
        Promise.resolve(districtChildren("public", district, 0)).then(function (nodes) {
          renderTreeRoot("public-explorer-tree", nodes, "No tehsils or villages found.");
        });
      } else {
        renderTreeRoot("public-explorer-tree", [], "District not found.");
      }
      selectLocation("public", "district", p.district.id, p.district.name);
    } else if (root === "tehsil" && p.tehsil) {
      document.getElementById("public-explorer-tree").innerHTML = "";
      fetch("/api/india-villages/" + encodeURIComponent(p.tehsil.id))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          renderTreeRoot("public-explorer-tree", (data.villages || []).map(function (v) { return villageNode("public", v, 0); }), "No villages found.");
        });
      selectLocation("public", "tehsil", p.tehsil.id, p.tehsil.name);
    } else if (root === "village" && p.village) {
      renderTreeRoot("public-explorer-tree", [], "");
      selectLocation("public", "village", p.village.id, p.village.name);
    }
  }

  function wireRootTabs(groupId, onPick) {
    var group = document.getElementById(groupId);
    if (!group) return;
    var buttons = Array.prototype.slice.call(group.querySelectorAll(".qm-panel-tab"));
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.disabled) return;
        buttons.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
        onPick(btn.getAttribute("data-root"));
      });
    });
  }

  function selectLocation(tab, level, id, name) {
    var prefix = tab === "global" ? "qm-dg-stats" : "qm-dp-stats";
    document.getElementById(prefix + "-heading").textContent = name ? "📊 " + name : "Statistics";
    var panel = document.getElementById(prefix + "-content");
    if (panel) { panel.dataset.level = level; panel.dataset.locationId = id; panel.dataset.name = name || ""; }
    loadStatsFor(prefix, "/api/location/stats/" + level + "/" + encodeURIComponent(id) + "?basis=present");
    loadWalletBalanceFor(prefix, level, id);
    loadCollectiveKarmaFor(prefix, level, id);
    if (tab === "public") {
      var isVillage = level === "village";
      var mc = document.getElementById("qm-village-members-card"); if (mc) mc.hidden = !isVillage;
      document.getElementById("qm-elections-card").hidden = !(isVillage && id === pilotVillageId);
      if (isVillage && document.getElementById("qm-village-member-list")) loadVillageMembers(id);

      var zoneCard = document.getElementById("qm-perception-zone-card");
      if (zoneCard) {
        var zone = level === "zone" ? findZoneById(id) : null;
        if (zone && zone.country_id === INDIA_COUNTRY_ID) {
          zoneCard.hidden = false;
          currentZonePerceptionId = id;
          loadZonePerception(id, name);
        } else {
          zoneCard.hidden = true;
        }
      }
    }
    if (tab === "global") {
      var countryCard = document.getElementById("qm-perception-country-card");
      if (countryCard) {
        if (level === "country" && PERCEPTION_COUNTRY_IDS.indexOf(id) !== -1) {
          countryCard.hidden = false;
          currentCountryPerceptionId = id;
          loadCountryPerception(id, name);
        } else {
          countryCard.hidden = true;
        }
      }
    }
  }

  // ---- Perception Calculator (annual Pro/Anti sentiment, see docs/perception_calculator.md) ----
  function renderPerception(prefix, name, data) {
    document.getElementById(prefix + "-name").textContent = name;
    document.getElementById(prefix + "-year").textContent = data.voting_year;
    var resultsBox = document.getElementById(prefix + "-results");
    if (!data.results_visible) {
      if (resultsBox) { resultsBox.hidden = true; }
      var hiddenNote = document.getElementById(prefix + "-hidden-note");
      if (hiddenNote) { hiddenNote.hidden = false; hiddenNote.textContent = "📊 " + (data.results_reason || "Results are not shown yet."); }
    } else {
      if (resultsBox) { resultsBox.hidden = false; }
      var hiddenNote2 = document.getElementById(prefix + "-hidden-note");
      if (hiddenNote2) { hiddenNote2.hidden = true; }
      var total = data.pro_count + data.anti_count;
      var proPct = total > 0 ? Math.round((data.pro_count / total) * 100) : 0;
      var antiPct = total > 0 ? Math.round((data.anti_count / total) * 100) : 0;
      document.getElementById(prefix + "-pro-bar").style.width = proPct + "%";
      document.getElementById(prefix + "-anti-bar").style.width = antiPct + "%";
      document.getElementById(prefix + "-pro-count").textContent = data.pro_count;
      document.getElementById(prefix + "-anti-count").textContent = data.anti_count;
    }

    var voteBlock = document.getElementById(prefix + "-vote-block");
    var note = document.getElementById(prefix + "-note");
    if (data.my_vote) {
      voteBlock.hidden = true;
      note.textContent = "You voted " + data.my_vote + " this year.";
    } else if (data.can_vote) {
      voteBlock.hidden = false;
      note.textContent = "";
    } else {
      voteBlock.hidden = true;
      note.textContent = data.vote_reason || "";
    }
  }

  function loadCountryPerception(countryId, name) {
    fetch("/api/perception/country/" + encodeURIComponent(countryId))
      .then(function (r) { return r.json(); })
      .then(function (data) { renderPerception("qm-perception-country", name, data); })
      .catch(function (err) { console.error("Failed to load country perception", err); });
  }

  function loadZonePerception(zoneId, name) {
    fetch("/api/perception/zone/" + encodeURIComponent(zoneId))
      .then(function (r) { return r.json(); })
      .then(function (data) { renderPerception("qm-perception-zone", name, data); })
      .catch(function (err) { console.error("Failed to load zone perception", err); });
  }

  function wirePerceptionVoting(prefix, kind, getCurrentId) {
    var block = document.getElementById(prefix + "-vote-block");
    if (!block) return;
    block.querySelectorAll("button[data-vote]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = getCurrentId();
        if (!id) return;
        fetch("/api/perception/" + kind + "/" + encodeURIComponent(id) + "/vote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ vote: btn.getAttribute("data-vote") }),
        })
          .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
          .then(function (result) {
            if (!result.ok) throw new Error(result.body.error || "Could not cast Perception vote");
            var name = document.getElementById(prefix + "-name").textContent;
            if (kind === "country") loadCountryPerception(id, name); else loadZonePerception(id, name);
          })
          .catch(function (err) { alert(err.message); });
      });
    });
  }
  var currentCountryPerceptionId = null, currentZonePerceptionId = null;
  wirePerceptionVoting("qm-perception-country", "country", function () { return currentCountryPerceptionId; });
  wirePerceptionVoting("qm-perception-zone", "zone", function () { return currentZonePerceptionId; });

  // ---- Village member directory + profile popup (privacy-scoped: name/
  // gender/age category only, see /api/location/members/village in app.py). ----
  var villageMembersCache = [];
  function loadVillageMembers(villageId) {
    fetch("/api/location/members/village/" + encodeURIComponent(villageId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        villageMembersCache = data.members || [];
        renderVillageMembers(villageMembersCache);
      })
      .catch(function (err) { console.error("Failed to load village members", err); });
  }
  function renderVillageMembers(members) {
    var list = document.getElementById("qm-village-member-list");
    var empty = document.getElementById("qm-village-members-empty");
    list.innerHTML = "";
    empty.hidden = members.length !== 0;
    members.forEach(function (m) {
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "qm-member-row";
      btn.innerHTML = m.name + ' <span class="qm-member-meta">(' + m.gender + ", " + m.age_category + ")</span>";
      btn.addEventListener("click", function () { openMemberPopup(m); });
      li.appendChild(btn);
      list.appendChild(li);
    });
  }
  var memberSearch = document.getElementById("qm-village-search");
  if (memberSearch) {
    memberSearch.addEventListener("input", function () {
      var q = memberSearch.value.trim().toLowerCase();
      renderVillageMembers(!q ? villageMembersCache : villageMembersCache.filter(function (m) {
        return m.name.toLowerCase().indexOf(q) !== -1;
      }));
    });
  }

  var memberPopup = document.createElement("div");
  memberPopup.className = "qm-gate-message qm-edit-modal";
  memberPopup.hidden = true;
  memberPopup.innerHTML =
    '<h3 id="qm-member-popup-name"></h3>' +
    '<p id="qm-member-popup-meta"></p>' +
    '<div class="qm-member-popup-actions">' +
    '<button type="button" class="qm-btn qm-btn-ghost" disabled>✉️ Send Message</button>' +
    '<button type="button" class="qm-btn qm-btn-ghost" disabled>🤝 Add Friend</button>' +
    '<button type="button" class="qm-btn qm-btn-ghost" disabled>👪 Add Family</button>' +
    '<p class="qm-member-popup-note">Coming soon — Message Box &amp; connections ship in a later update.</p>' +
    '</div>' +
    '<div class="qm-summary-actions" style="margin-top:14px;"><button type="button" class="qm-btn qm-btn-ghost" id="qm-member-popup-close">Close</button></div>';
  document.body.appendChild(memberPopup);
  memberPopup.querySelector("#qm-member-popup-close").addEventListener("click", function () { memberPopup.hidden = true; });

  function openMemberPopup(member) {
    memberPopup.querySelector("#qm-member-popup-name").textContent = member.name;
    memberPopup.querySelector("#qm-member-popup-meta").textContent = member.gender + " · " + member.age_category;
    memberPopup.hidden = false;
  }

  if (document.getElementById("global-explorer-tree") || document.getElementById("public-explorer-tree")) {
    loadTreeData().then(function () {
      if (document.getElementById("global-explorer-tree")) {
        wireRootTabs("global-root-tabs", renderGlobalExplorer);
        renderGlobalExplorer("earth");
      }
      if (document.getElementById("public-explorer-tree")) {
        wireRootTabs("public-root-tabs", renderPublicExplorer);
        renderPublicExplorer("zone");
      }
    }).catch(function (err) { console.error("Failed to load dashboard explorer data", err); });
  }

  // ---- Edit Profile -> queued change request (no auto-apply; see app.py) ----
  var editBtn = document.getElementById("edit-profile-btn");
  var editModal = document.getElementById("edit-profile-modal");
  var editForm = document.getElementById("edit-profile-form");
  var editCancel = document.getElementById("edit-profile-cancel");
  var editError = document.getElementById("edit-profile-error");
  var editSuccess = document.getElementById("edit-profile-success");

  editBtn.addEventListener("click", function () {
    editError.hidden = true;
    editSuccess.hidden = true;
    editModal.hidden = false;
  });
  editCancel.addEventListener("click", function () { editModal.hidden = true; });

  editForm.addEventListener("submit", function (e) {
    e.preventDefault();
    editError.hidden = true;
    editSuccess.hidden = true;

    fetch("/api/dashboard/edit-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("edit-name").value.trim(),
        middle_name: document.getElementById("edit-middle-name").value.trim(),
        email: document.getElementById("edit-email").value.trim(),
        phone: document.getElementById("edit-phone").value.trim(),
        reason: document.getElementById("edit-reason").value.trim(),
      }),
    })
      .then(function (res) {
        return res.json().then(function (body) { return { ok: res.ok, body: body }; });
      })
      .then(function (result) {
        if (!result.ok) throw new Error(result.body.error || "Could not queue request");
        editSuccess.hidden = false;
      })
      .catch(function (err) {
        editError.textContent = err.message;
        editError.hidden = false;
      });
  });

  // ---- Profile picture (2026-10-20): self-service, uploads immediately -- unlike Edit Profile
  // above, this never goes through council approval (see profile_picture_core.py). ----
  var avatarInput = document.getElementById("pv-avatar-input");
  var avatarUploadBtn = document.getElementById("pv-avatar-upload-btn");
  var avatarEl = document.getElementById("pv-avatar");
  var avatarInitialEl = document.getElementById("pv-avatar-initial");
  var avatarErrorEl = document.getElementById("pv-avatar-error");
  if (avatarUploadBtn) {
    avatarUploadBtn.addEventListener("click", function () { avatarInput.click(); });
    avatarInput.addEventListener("change", function () {
      var file = avatarInput.files[0];
      if (!file) return;
      avatarErrorEl.hidden = true;
      var formData = new FormData();
      formData.append("picture", file);
      avatarUploadBtn.disabled = true;
      fetch("/api/profile/picture", { method: "POST", body: formData })
        .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
        .then(function (result) {
          avatarUploadBtn.disabled = false;
          if (!result.ok) throw new Error(result.body.error || "Could not upload picture");
          avatarEl.style.backgroundImage = "url('/api/users/" + QM_USER_ID + "/profile-picture?v=" + Date.now() + "')";
          avatarInitialEl.hidden = true;
        })
        .catch(function (err) {
          avatarUploadBtn.disabled = false;
          avatarErrorEl.textContent = err.message;
          avatarErrorEl.hidden = false;
        });
    });
  }

  // ---- Qoins Wallet (Private tab) ----
  var walletBalanceEl = document.getElementById("qm-wallet-balance");

  function loadWallet() {
    if (!walletBalanceEl) return;
    fetch("/api/wallet/balance")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        // 2026-11-08: the always-visible card shows ONLY the Qoin count + locked-share note now
        // (Phase 1 workstream 1.5) -- the per-transaction list moved into #qm-wallet-history-modal
        // (dash_extras.js's openWalletHistoryModal()), which fetches its own history separately
        // (GET /api/wallet/history) only when actually opened, so a visitor who never opens it
        // never pays for that second request. The modal's own balance/locked-note line is mirrored
        // from this SAME response (no second /api/wallet/balance call needed when it opens).
        walletBalanceEl.textContent = data.balance_qoins;
        document.getElementById("qm-wallet-locked-note").hidden = !data.has_locked_share;
        var modalBalanceEl = document.getElementById("qm-wallet-modal-balance");
        var modalLockedEl = document.getElementById("qm-wallet-modal-locked-note");
        if (modalBalanceEl) modalBalanceEl.textContent = data.balance_qoins;
        if (modalLockedEl) modalLockedEl.hidden = !data.has_locked_share;
      })
      .catch(function (err) { console.error("Failed to load wallet", err); });
  }
  loadWallet();

  // ---- Your Karma (Private tab) — a Social Credit score, never money, separate from Qoins ----
  var karmaTotalEl = document.getElementById("qm-karma-total");

  function loadKarma() {
    if (!karmaTotalEl) return;
    fetch("/api/karma/me")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        karmaTotalEl.textContent = data.score.total;
        document.getElementById("qm-karma-commercial").textContent = data.score.commercial;
        document.getElementById("qm-karma-noncommercial").textContent = data.score.noncommercial;
        var list = document.getElementById("qm-karma-history-list");
        var empty = document.getElementById("qm-karma-history-empty");
        list.innerHTML = "";
        (data.history || []).forEach(function (entry) {
          var li = document.createElement("li");
          var sign = entry.points >= 0 ? "+" : "";
          li.textContent = sign + entry.points + " — " + entry.reason;
          list.appendChild(li);
        });
        empty.hidden = (data.history || []).length !== 0;
      })
      .catch(function (err) { console.error("Failed to load karma", err); });
  }
  loadKarma();

  var karmaHistoryBtn = document.getElementById("qm-karma-history-btn");
  if (karmaHistoryBtn) {
    karmaHistoryBtn.addEventListener("click", function () {
      var list = document.getElementById("qm-karma-history-list");
      var empty = document.getElementById("qm-karma-history-empty");
      var showing = !list.hidden;
      list.hidden = showing;
      empty.hidden = showing || list.children.length !== 0;
    });
  }

  // ---- Village Council Elections (Public → Village sub-tab) ----
  var electionsCard = document.getElementById("qm-elections-card");
  var lastElectionEligibility = null;

  function loadElectionCandidates() {
    fetch("/api/election/candidates")
      .then(function (r) { return r.json(); })
      .then(function (candidates) {
        var container = document.getElementById("qm-election-candidates");
        var empty = document.getElementById("qm-election-candidates-empty");
        container.innerHTML = "";
        if (candidates.restricted) {
          empty.hidden = false;
          empty.textContent = candidates.your_sign
            ? "This cycle's candidates are only shown to members born under " + candidates.cycle_sign + "."
            : "Sign in to see this cycle's candidates.";
          return;
        }
        var total = (candidates.male || []).length + (candidates.female || []).length;
        empty.hidden = total !== 0;
        empty.textContent = "No approved candidates yet.";

        ["male", "female"].forEach(function (gender) {
          (candidates[gender] || []).forEach(function (c) {
            var row = document.createElement("div");
            row.className = "qm-candidate-row";
            var karmaTotal = c.karma ? c.karma.total : 0;
            var report = document.createElement("div");
            report.className = "qm-candidate-report";
            var head = document.createElement("strong");
            head.textContent = c.name;
            report.appendChild(head);
            report.appendChild(document.createTextNode(
              " (" + gender + ") · Karma Score: " + karmaTotal
            ));
            var dl = document.createElement("dl");
            [
              ["Why running", c.form_reason || c.manifest || ""],
              ["Why vote for me", c.form_why_vote || ""],
              ["What I'll change", c.form_changes || ""],
            ].concat(c.form_past_work ? [["Past work", c.form_past_work]] : [])
              .forEach(function (pair) {
                var dt = document.createElement("dt");
                dt.textContent = pair[0];
                var dd = document.createElement("dd");
                dd.textContent = pair[1];
                dl.appendChild(dt);
                dl.appendChild(dd);
              });
            report.appendChild(dl);
            row.appendChild(report);

            var eligibility = lastElectionEligibility;
            var canVote = eligibility && eligibility.can_vote && eligibility.voted_genders.indexOf(gender) === -1;
            if (canVote) {
              var btn = document.createElement("button");
              btn.type = "button";
              btn.className = "qm-btn qm-btn-ghost";
              btn.textContent = "Vote";
              btn.addEventListener("click", function () {
                fetch("/api/election/vote", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ candidate_user_id: c.user_id, gender: gender }),
                })
                  .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
                  .then(function (result) {
                    if (!result.ok) throw new Error(result.body.error || "Could not vote");
                    loadElectionStatus();
                    loadElectionCandidates();
                    loadElectionSummary();
                  })
                  .catch(function (err) { alert(err.message); });
              });
              row.appendChild(btn);
            }
            container.appendChild(row);
          });
        });
      })
      .catch(function (err) { console.error("Failed to load candidates", err); });
  }

  function loadElectionCouncil() {
    fetch("/api/election/council")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var list = document.getElementById("qm-election-council");
        var empty = document.getElementById("qm-election-council-empty");
        list.innerHTML = "";
        empty.hidden = data.council.length !== 0;
        data.council.forEach(function (seat) {
          var li = document.createElement("li");
          li.textContent = seat.zodiac_sign + " " + seat.year + " — Nayak: " +
            (seat.male_head_name || "—") + ", Nayika: " + (seat.female_head_name || "—") +
            " (" + seat.term_status + ")";
          list.appendChild(li);
        });
      })
      .catch(function (err) { console.error("Failed to load council", err); });
  }

  function loadElectionStatus() {
    fetch("/api/election/status")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        lastElectionEligibility = data.eligibility;
        document.getElementById("qm-election-sign").textContent = data.cycle.zodiac_sign + " (" + data.cycle.element + ")";
        document.getElementById("qm-election-phase").textContent = data.cycle.status;
        document.getElementById("qm-election-window").textContent =
          "Nomination " + data.cycle.nomination_start + " – " + data.cycle.nomination_end +
          " · Voting " + data.cycle.voting_start + " – " + data.cycle.voting_end;
        // The 4-week rhythm and what THIS member should do (same guide as Q-Punch and the phone app).
        var guideEl = document.getElementById("qm-election-guide");
        if (!guideEl) {
          guideEl = document.createElement("p");
          guideEl.id = "qm-election-guide";
          guideEl.className = "qp-elec-guide";
          document.getElementById("qm-election-window").insertAdjacentElement("afterend", guideEl);
        }
        if (data.guide) {
          var wk = (data.weeks || []).filter(function (w) { return w.week === data.week; })[0];
          guideEl.textContent = (data.guide.action ? "📣 " : "ℹ️ ") + "Week " + data.week + " of 4" +
            (wk ? " · " + wk.title : "") + " — " + data.guide.text;
          guideEl.classList.toggle("is-action", !!data.guide.action);
        }

        var nominateBlock = document.getElementById("qm-election-nominate-block");
        var nominateNote = document.getElementById("qm-election-nominate-note");
        nominateBlock.hidden = !data.eligibility.can_nominate;
        if (data.eligibility.already_nominated) {
          nominateNote.textContent = "You've submitted a nomination for this cycle.";
          nominateNote.hidden = false;
        } else if (!data.eligibility.can_nominate && data.eligibility.nominate_reason) {
          nominateNote.textContent = data.eligibility.nominate_reason;
          nominateNote.hidden = false;
        } else {
          nominateNote.hidden = true;
        }
        loadElectionCandidates();
      })
      .catch(function (err) { console.error("Failed to load election status", err); });
  }

  // 2026-10-28 (Q-Punch transparency): turnout while voting is open, a results bar chart once the
  // cycle closes, and the 4-week progress strip. election_core.election_summary() already backs
  // the Q-Punch POPUP's own electionBlock() (static/js/board.js, via GET /api/qpunch/<level>) in
  // plain text -- turnout as a sentence, winners/candidates as a "N votes" suffix, no chart -- but
  // GET /api/election/summary, the dedicated endpoint for this same data, was never called from
  // the main board page at all. This reuses .qp-elec-weeks/.qp-elec-week (board.js's own classes
  // for the identical concept) rather than inventing a second visual language for it.
  function renderElectionWeeks(summary) {
    var box = document.getElementById("qm-election-weeks");
    box.innerHTML = "";
    var tl = el("div", "qp-elec-weeks");
    (summary.weeks || []).forEach(function (w) {
      var s = el("div", "qp-elec-week" + (w.week === summary.week ? " is-now" : w.week < summary.week ? " is-done" : ""));
      s.appendChild(el("b", "", w.week < summary.week ? "✓" : String(w.week)));
      s.appendChild(el("span", "", w.title));
      tl.appendChild(s);
    });
    box.appendChild(tl);
  }

  function renderElectionTurnout(summary) {
    var box = document.getElementById("qm-election-turnout");
    if (summary.status === "nomination") { box.hidden = true; return; }
    box.hidden = false;
    var pct = summary.eligible_voters > 0 ? Math.round((summary.turnout / summary.eligible_voters) * 100) : 0;
    document.getElementById("qm-election-turnout-text").textContent =
      "👥 Turnout: " + summary.turnout.toLocaleString() + " / " + summary.eligible_voters.toLocaleString() +
      " eligible voted (" + pct + "%)";
    document.getElementById("qm-election-turnout-fill").style.width = pct + "%";
    var note = document.getElementById("qm-election-turnout-note");
    note.textContent = summary.status === "closed"
      ? "Voting closed — final turnout for " + summary.sign + " " + summary.year + "."
      : "Votes are counted live — results stay sealed until voting closes.";
  }

  function renderElectionResults(summary) {
    var box = document.getElementById("qm-election-results");
    if (summary.status !== "closed") { box.hidden = true; return; }
    box.hidden = false;
    var body = document.getElementById("qm-election-results-body");
    body.innerHTML = "";
    var winners = summary.winners || {};
    ["male", "female"].forEach(function (gender) {
      var cands = (summary.candidates && summary.candidates[gender]) || [];
      if (!cands.length) return;
      var maxVotes = Math.max.apply(null, cands.map(function (c) { return c.votes || 0; }).concat([1]));
      var seat = gender === "male" ? "Nayak" : "Nayika";
      body.appendChild(el("h4", "qp-results-seat", seat + (winners[gender] ? " — " + winners[gender] : "")));
      cands.slice().sort(function (a, b) { return (b.votes || 0) - (a.votes || 0); }).forEach(function (c) {
        var votes = c.votes || 0;
        var row = el("div", "qp-results-row");
        row.appendChild(el("span", "qp-results-name", c.name));
        var bar = el("div", "qp-results-bar");
        var fill = el("div", "qp-results-fill");
        fill.style.width = Math.round((votes / maxVotes) * 100) + "%";
        bar.appendChild(fill);
        row.appendChild(bar);
        row.appendChild(el("span", "qp-results-count", votes.toLocaleString() + " vote" + (votes === 1 ? "" : "s")));
        body.appendChild(row);
      });
    });
  }

  function loadElectionSummary() {
    fetch("/api/election/summary")
      .then(function (r) { return r.json(); })
      .then(function (summary) {
        renderElectionWeeks(summary);
        renderElectionTurnout(summary);
        renderElectionResults(summary);
      })
      .catch(function (err) { console.error("Failed to load election summary", err); });
  }

  if (electionsCard) {
    loadElectionStatus();
    loadElectionCouncil();
    loadElectionSummary();

    var nominateForm = document.getElementById("qm-election-nominate-form");
    nominateForm.addEventListener("submit", function (e) {
      e.preventDefault();
      fetch("/api/election/nominate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: document.getElementById("qm-election-reason").value.trim(),
          why_vote: document.getElementById("qm-election-why-vote").value.trim(),
          changes: document.getElementById("qm-election-changes").value.trim(),
          past_work: document.getElementById("qm-election-past-work").value.trim(),
        }),
      })
        .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
        .then(function (result) {
          if (!result.ok) throw new Error(result.body.error || "Could not submit nomination");
          loadElectionStatus();
        })
        .catch(function (err) { alert(err.message); });
    });
  }

  // ---- Post Testing cycle admin panel (2026-10-17, docs/test_cycle_design.md) -- the markup
  // only exists in the page at all when is_admin was true at render time (dashboard.html's own
  // {% if is_admin %} gate), so every element here guards with `if (!el) return` exactly like
  // the wallet/karma loaders above -- a non-admin viewer's page simply has none of these ids.
  var testCycleCard = document.getElementById("qm-testcycle-card");

  function loadTestCycle() {
    if (!testCycleCard) return;
    fetch("/api/admin/test-cycle/panel")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var w = data.window;
        var empty = document.getElementById("qm-testcycle-empty");
        var body = document.getElementById("qm-testcycle-body");
        var renewBtn = document.getElementById("qm-testcycle-renew-btn");
        var stopBtn = document.getElementById("qm-testcycle-stop-btn");
        var startBtn = document.getElementById("qm-testcycle-start-btn");
        empty.hidden = !!w;
        body.hidden = !w;
        renewBtn.hidden = !w || w.status !== "active";
        stopBtn.hidden = !w || w.status !== "active";
        startBtn.hidden = !!w && w.status === "active";
        if (!w) return;
        document.getElementById("qm-testcycle-status").textContent = w.status;
        document.getElementById("qm-testcycle-count").textContent = w.demo_user_count;
        document.getElementById("qm-testcycle-posts").textContent = data.posts_this_month;
        document.getElementById("qm-testcycle-votes").textContent = data.votes_this_month;
        try {
          var start = new Date(w.start_date), end = new Date(w.end_date);
          document.getElementById("qm-testcycle-window-start").textContent = start.toLocaleDateString();
          document.getElementById("qm-testcycle-window-end").textContent = end.toLocaleDateString();
        } catch (e) { /* malformed date -- leave blank rather than crash the whole panel */ }
        try {
          var dist = JSON.parse(w.vote_distribution);
          document.getElementById("qm-testcycle-dist").textContent =
            Object.keys(dist).map(function (k) { return Math.round(dist[k] * 100) + "% " + k; }).join(", ");
        } catch (e) { document.getElementById("qm-testcycle-dist").textContent = w.vote_distribution; }
      })
      .catch(function (err) { console.error("Failed to load test cycle panel", err); });
  }
  loadTestCycle();

  function testCycleAction(url, confirmMsg) {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    var errEl = document.getElementById("qm-testcycle-error");
    fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (result) {
        if (!result.ok) throw new Error(result.body.error || "Could not complete that action");
        errEl.hidden = true;
        loadTestCycle();
      })
      .catch(function (err) { errEl.textContent = err.message; errEl.hidden = false; });
  }
  if (testCycleCard) {
    var renewBtnEl = document.getElementById("qm-testcycle-renew-btn");
    var stopBtnEl = document.getElementById("qm-testcycle-stop-btn");
    var startBtnEl = document.getElementById("qm-testcycle-start-btn");
    if (renewBtnEl) renewBtnEl.addEventListener("click", function () { testCycleAction("/api/admin/test-cycle/renew"); });
    if (stopBtnEl) stopBtnEl.addEventListener("click", function () {
      testCycleAction("/api/admin/test-cycle/stop", "Stop the active Post Testing window? Demo users are not retired by this.");
    });
    if (startBtnEl) startBtnEl.addEventListener("click", function () { testCycleAction("/api/admin/test-cycle/start"); });
  }

  // ---- Admin member export (2026-10-18) -- same is_admin gating as the Post Testing panel
  // above: the markup only exists when is_admin was true at render time, so every lookup here
  // guards with the same `if (!el) return` pattern.
  var memberExportCard = document.getElementById("qm-memberexport-card");
  if (memberExportCard) {
    var meLevel = document.getElementById("qm-memberexport-level");
    var meLocField = document.getElementById("qm-memberexport-locid-field");
    var meLocInput = document.getElementById("qm-memberexport-locid");
    var mePeriod = document.getElementById("qm-memberexport-period");
    var meErr = document.getElementById("qm-memberexport-error");
    var meResults = document.getElementById("qm-memberexport-results");
    var meCount = document.getElementById("qm-memberexport-count");
    var meTbody = document.getElementById("qm-memberexport-tbody");

    function meToggleLocField() { meLocField.hidden = meLevel.value === "earth"; }
    meToggleLocField();
    meLevel.addEventListener("change", meToggleLocField);

    function meQueryString() {
      var params = new URLSearchParams();
      params.set("level", meLevel.value);
      if (meLevel.value !== "earth" && meLocInput.value.trim()) params.set("location_id", meLocInput.value.trim());
      params.set("period", mePeriod.value);
      return params.toString();
    }

    document.getElementById("qm-memberexport-preview-btn").addEventListener("click", function () {
      meErr.hidden = true;
      meResults.hidden = true;
      if (meLevel.value !== "earth" && !meLocInput.value.trim()) {
        meErr.textContent = "Enter a Location ID, or choose Earth (everyone).";
        meErr.hidden = false;
        return;
      }
      fetch("/api/admin/users/export?" + meQueryString())
        .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
        .then(function (result) {
          if (!result.ok) throw new Error(result.body.error || "Could not load members");
          meTbody.innerHTML = "";
          result.body.members.forEach(function (m) {
            var tr = document.createElement("tr");
            [m.private_id, m.account_id, m.name, m.location, m.created_at].forEach(function (val) {
              var td = document.createElement("td");
              td.textContent = val || "";
              tr.appendChild(td);
            });
            meTbody.appendChild(tr);
          });
          meCount.textContent = result.body.count + " member" + (result.body.count === 1 ? "" : "s") + " found.";
          meResults.hidden = false;
        })
        .catch(function (err) { meErr.textContent = err.message; meErr.hidden = false; });
    });

    document.getElementById("qm-memberexport-csv-btn").addEventListener("click", function () {
      meErr.hidden = true;
      if (meLevel.value !== "earth" && !meLocInput.value.trim()) {
        meErr.textContent = "Enter a Location ID, or choose Earth (everyone).";
        meErr.hidden = false;
        return;
      }
      window.location.href = "/api/admin/users/export.csv?" + meQueryString();
    });
  }

  // ---- Admin Panel (2026-10-18): a combined inbox over Citizen Reports, ID recovery requests,
  // and general queries. The markup only exists in the DOM for is_admin_panel_user (dashboard.html's
  // {% if %} gate), so loadAdminPanel() itself no-ops for everyone else -- same pattern as the
  // Test Cycle / Member Export blocks above. Small local helpers (apEl/apApi/apAgo) rather than
  // reaching into board.js's own IIFE-scoped el()/api()/ago(), which aren't visible here. ----
  function apEl(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function apApi(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }
  function apAgo(iso) {
    if (!iso) return "";
    var s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + " min ago";
    if (s < 86400) return Math.floor(s / 3600) + " h ago";
    return Math.floor(s / 86400) + " d ago";
  }

  // qmRenderFormattedText (the formatted-text renderer apOpenCouncil below calls) now lives in
  // static/js/qmail_format.js, loaded before this file -- see that file's own header for why it
  // was extracted rather than kept here with a second copy in dash_extras.js.

  // Assigned inside the `if (apList)` block below, read by loadAdminPanel() at the bottom of this
  // IIFE -- a plain outer `var` assignment, not a function declaration, so it's unaffected by
  // strict mode's block-scoping of function declarations (apLoadFeed() itself IS declared inside
  // that block and wouldn't be reachable from outside it directly).
  var apRefreshFeed = null;
  var apList = document.getElementById("ap-list");
  if (apList) {
    var apDetail = document.getElementById("ap-detail");
    var apFilterBtns = Array.prototype.slice.call(document.querySelectorAll(".ap-filter"));
    var apRefreshBtn = document.querySelector(".ap-refresh-btn");
    var apCurrentFilter = "all";
    var apItemsCache = [];

    function apSourceLabel(source) {
      return { report: "Citizen Report", id_recovery: "ID Recovery", query: "Query", council: "Council Queue", identity: "Identity Request", account_recovery: "Account Recovery" }[source] || source;
    }

    function apRenderList() {
      apList.innerHTML = "";
      var filtered = apCurrentFilter === "all" ? apItemsCache : apItemsCache.filter(function (it) { return it.source === apCurrentFilter; });
      // 2026-10-28 fix: apList.innerHTML = "" (above) deletes #ap-list-empty too -- it's a child
      // of #ap-list in the template, not a sibling -- so the OLD cached `apListEmpty` reference
      // (document.getElementById, read once at page load) pointed at a detached node from the
      // very first render onward; toggling .hidden on it had no visible effect. Building this
      // fresh each render, the same way every other node in this list already is, instead of
      // relying on a template node surviving innerHTML wipes it sits inside.
      if (!filtered.length) apList.appendChild(apEl("p", "qm-dash-empty", "Nothing open right now."));
      filtered.forEach(function (it) {
        var row = apEl("button", "ap-row");
        row.type = "button";
        row.appendChild(apEl("span", "ap-badge ap-badge-" + it.status, it.status));
        row.appendChild(apEl("div", "ap-row-title", it.title || "(no subject)"));
        var metaText = apSourceLabel(it.source) + " · " + (it.author || "Unknown") + (it.location ? " · " + it.location : "") + " · " + apAgo(it.created_at);
        if (it.source === "account_recovery") {
          // Part 4.1 asks the ticket LIST, not only the detail view, to show DOB and contact
          // method -- appended here rather than widening every other source's own meta line.
          var contactLabel = { phone: "Phone", email: "Email", member_private_id: "Member Private ID" }[it.contact_method] || it.contact_method;
          metaText += " · DOB " + (it.date_of_birth || "—") + " · " + contactLabel + " · " + (it.verification_status || "pending");
        }
        row.appendChild(apEl("div", "ap-row-meta", metaText));
        row.addEventListener("click", function () { apOpenDetail(it); });
        apList.appendChild(row);
      });
    }

    function apLoadFeed() {
      fetch("/api/admin/panel/feed")
        .then(function (r) { return r.json(); })
        .then(function (data) { apItemsCache = data.items || []; apRenderList(); })
        .catch(function (err) { apList.innerHTML = ""; apList.appendChild(apEl("p", "qm-dash-empty", err.message)); });
    }

    apFilterBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        apFilterBtns.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
        apCurrentFilter = btn.getAttribute("data-filter");
        apRenderList();
      });
    });
    if (apRefreshBtn) apRefreshBtn.addEventListener("click", apLoadFeed);

    function apOpenDetail(item) {
      apDetail.innerHTML = "";
      apDetail.appendChild(apEl("p", "qm-dash-empty", "Loading…"));
      if (item.source === "report") apOpenReport(item.id);
      else if (item.source === "id_recovery") apOpenIdRecovery(item.id);
      else if (item.source === "query") apOpenQuery(item.id);
      else if (item.source === "council") apOpenCouncil(item.id);
      else if (item.source === "account_recovery") apOpenAccountRecovery(item.id);
    }

    function apOpenReport(id) {
      fetch("/api/reports/" + id).then(function (r) { return r.json(); }).then(function (r) {
        apDetail.innerHTML = "";
        apDetail.appendChild(apEl("h3", "ap-detail-title", "Citizen Report #" + r.id));
        apDetail.appendChild(apEl("p", "ap-detail-meta", (r.author_name || "Anonymous Citizen") + " · " + r.location_level + " " + r.location_id));
        apDetail.appendChild(apEl("p", "ap-detail-body", r.body));
        var updatesBox = apEl("div", "ap-updates");
        (r.updates || []).forEach(function (u) {
          var row = apEl("div", "ap-update-row");
          row.appendChild(apEl("b", "", (u.author_name || u.author_role || "System") + " "));
          row.appendChild(apEl("span", "", u.update_type + (u.message ? ": " + u.message : "") + " · " + apAgo(u.created_at)));
          updatesBox.appendChild(row);
        });
        apDetail.appendChild(updatesBox);

        var actions = apEl("div", "ap-actions");
        var replyInput = document.createElement("input");
        replyInput.type = "text"; replyInput.placeholder = "Add a comment…"; replyInput.className = "ap-reply-input";
        actions.appendChild(replyInput);

        function doUpdate(type) {
          apApi("/api/reports/" + id + "/update", { update_type: type, message: replyInput.value })
            .then(function () { apLoadFeed(); apOpenReport(id); })
            .catch(function (e) { alert(e.message); });
        }
        [["comment", "Comment"], ["acknowledged", "Acknowledge"], ["resolved", "Resolve"], ["denied", "Deny"]].forEach(function (x) {
          var btn = apEl("button", "qm-btn qm-btn-ghost", x[1]); btn.type = "button";
          btn.addEventListener("click", function () { doUpdate(x[0]); });
          actions.appendChild(btn);
        });
        var escBtn = apEl("button", "qm-btn qm-btn-primary", "Escalate"); escBtn.type = "button";
        escBtn.addEventListener("click", function () {
          apApi("/api/reports/" + id + "/escalate", {}).then(function () { apLoadFeed(); apOpenReport(id); }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(escBtn);
        apDetail.appendChild(actions);
      }).catch(function (e) { apDetail.innerHTML = ""; apDetail.appendChild(apEl("p", "qm-dash-empty", e.message)); });
    }

    function apOpenIdRecovery(id) {
      fetch("/api/admin/recover-id").then(function (r) { return r.json(); }).then(function (data) {
        var rq = (data.requests || []).filter(function (x) { return x.id === id; })[0];
        apDetail.innerHTML = "";
        if (!rq) { apDetail.appendChild(apEl("p", "qm-dash-empty", "Not found.")); return; }
        apDetail.appendChild(apEl("h3", "ap-detail-title", "ID Recovery — " + rq.name));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "DOB " + rq.dob + " · status: " + rq.status));
        apDetail.appendChild(apEl("p", "ap-detail-body", rq.note || "(no note)"));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "Contact: " + (rq.phone || rq.email || "—")));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "Mailing address: " + rq.mailing_address));

        var actions = apEl("div", "ap-actions");
        if (rq.candidate_user_id && rq.status !== "sent" && rq.status !== "rejected") {
          var revealBtn = apEl("button", "qm-btn qm-btn-primary", "Approve & reveal ID"); revealBtn.type = "button";
          revealBtn.addEventListener("click", function () {
            if (!window.confirm("Reveal this member's real Private ID for the physical letter? This is logged.")) return;
            apApi("/api/admin/recover-id/" + id + "/reveal", {}).then(function (res) {
              return apApi("/api/admin/recover-id/" + id + "/decide", { status: "sent" }).then(function () {
                alert("Private ID: " + res.private_code + "\n\nWrite this into the physical letter now. It will not be shown again here.");
                apLoadFeed(); apOpenIdRecovery(id);
              });
            }).catch(function (e) { alert(e.message); });
          });
          actions.appendChild(revealBtn);
        }
        if (rq.status !== "sent" && rq.status !== "rejected") {
          var rejectBtn = apEl("button", "qm-btn qm-btn-ghost", "Reject"); rejectBtn.type = "button";
          rejectBtn.addEventListener("click", function () {
            apApi("/api/admin/recover-id/" + id + "/decide", { status: "rejected" })
              .then(function () { apLoadFeed(); apOpenIdRecovery(id); }).catch(function (e) { alert(e.message); });
          });
          actions.appendChild(rejectBtn);
        }
        apDetail.appendChild(actions);
      }).catch(function (e) { apDetail.innerHTML = ""; apDetail.appendChild(apEl("p", "qm-dash-empty", e.message)); });
    }

    function apOpenQuery(id) {
      fetch("/api/admin/queries/" + id).then(function (r) { return r.json(); }).then(function (q) {
        apDetail.innerHTML = "";
        apDetail.appendChild(apEl("h3", "ap-detail-title", q.subject));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "Category: " + q.category + " · status: " + q.status));
        apDetail.appendChild(apEl("p", "ap-detail-body", q.body));
        var repliesBox = apEl("div", "ap-updates");
        (q.replies || []).forEach(function (r) {
          var row = apEl("div", "ap-update-row");
          if (window.QMAvatar) row.appendChild(window.QMAvatar.render({ name: r.author_name, gender: r.author_gender, profile_picture_url: r.author_profile_picture_url }, 22));
          row.appendChild(apEl("b", "", r.author_name + " "));
          row.appendChild(apEl("span", "", r.message + " · " + apAgo(r.created_at)));
          repliesBox.appendChild(row);
        });
        apDetail.appendChild(repliesBox);

        var actions = apEl("div", "ap-actions");
        var replyInput = document.createElement("input");
        replyInput.type = "text"; replyInput.placeholder = "Write a reply…"; replyInput.className = "ap-reply-input";
        actions.appendChild(replyInput);
        var replyBtn = apEl("button", "qm-btn qm-btn-primary", "Reply"); replyBtn.type = "button";
        replyBtn.addEventListener("click", function () {
          if (!replyInput.value.trim()) return;
          apApi("/api/admin/queries/" + id + "/reply", { message: replyInput.value })
            .then(function () { apLoadFeed(); apOpenQuery(id); }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(replyBtn);
        var closeBtn = apEl("button", "qm-btn qm-btn-ghost", "Close ticket"); closeBtn.type = "button";
        closeBtn.addEventListener("click", function () {
          apApi("/api/admin/queries/" + id + "/close", {}).then(function () { apLoadFeed(); apDetail.innerHTML = ""; }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(closeBtn);
        apDetail.appendChild(actions);
      }).catch(function (e) { apDetail.innerHTML = ""; apDetail.appendChild(apEl("p", "qm-dash-empty", e.message)); });
    }

    function apOpenAccountRecovery(id) {
      // Detail fetch, reply and close all reuse the EXISTING /api/admin/queries/* routes
      // unchanged -- they already operate generically on any admin_queries row (its own
      // admin_queries_core.get() is a plain SELECT *, so the account_recovery-only columns come
      // back for free) and are already gated the equivalent way. Only the three account-recovery-
      // specific actions below (verify/reveal/generate-pin) call new routes.
      fetch("/api/admin/queries/" + id).then(function (r) { return r.json(); }).then(function (q) {
        apDetail.innerHTML = "";
        var loc = {};
        try { loc = q.present_location_json ? JSON.parse(q.present_location_json) : {}; } catch (e) { loc = {}; }
        var locLabel = ["village", "tehsil", "district", "state", "country", "continent"]
          .map(function (lvl) { return loc[lvl] && loc[lvl].name; }).filter(Boolean).join(", ") || "—";
        var contactLabel = { phone: "Phone", email: "Email", member_private_id: "Member Private ID" }[q.contact_method] || (q.contact_method || "—");

        apDetail.appendChild(apEl("h3", "ap-detail-title", "Account Recovery — " + (q.guest_name || "Unknown")));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "DOB " + (q.date_of_birth || "—") + " · status: " + q.status + " · verification: " + (q.verification_status || "pending")));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "Present location: " + locLabel));
        apDetail.appendChild(apEl("p", "ap-detail-meta", "Contact method: " + contactLabel + " · value: " + (q.guest_contact || "—")));
        if (q.verification_notes) {
          var notesBox = apEl("div", "ap-detail-body");
          notesBox.appendChild(apEl("b", "", "Internal verification notes (never shown to the requester):"));
          q.verification_notes.split("\n").forEach(function (line) { notesBox.appendChild(apEl("div", "", line)); });
          apDetail.appendChild(notesBox);
        }

        var repliesBox = apEl("div", "ap-updates");
        (q.replies || []).forEach(function (r) {
          var row = apEl("div", "ap-update-row");
          row.appendChild(apEl("b", "", r.author_name + " "));
          row.appendChild(apEl("span", "", r.message + " · " + apAgo(r.created_at)));
          repliesBox.appendChild(row);
        });
        apDetail.appendChild(repliesBox);

        var actions = apEl("div", "ap-actions");

        // Step 1: verification (Part 5.1) -- required before either recovery action is allowed.
        var notesInput = document.createElement("input");
        notesInput.type = "text"; notesInput.placeholder = "Internal verification notes (not shown to requester)…"; notesInput.className = "ap-reply-input";
        actions.appendChild(notesInput);
        var verifyBtn = apEl("button", "qm-btn qm-btn-primary", "Mark Verified"); verifyBtn.type = "button";
        verifyBtn.addEventListener("click", function () {
          apApi("/api/admin/account-recovery/" + id + "/verify", { status: "verified", notes: notesInput.value })
            .then(function () { apLoadFeed(); apOpenAccountRecovery(id); }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(verifyBtn);
        var rejectVerifyBtn = apEl("button", "qm-btn qm-btn-ghost", "Mark Rejected"); rejectVerifyBtn.type = "button";
        rejectVerifyBtn.addEventListener("click", function () {
          apApi("/api/admin/account-recovery/" + id + "/verify", { status: "rejected", notes: notesInput.value })
            .then(function () { apLoadFeed(); apOpenAccountRecovery(id); }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(rejectVerifyBtn);
        apDetail.appendChild(actions);

        // Step 2: the two recovery actions -- only ever shown once verification_status is
        // 'verified'; the backend enforces this too (Part 6: never rely on hiding a button alone).
        if (q.verification_status === "verified" && q.status !== "closed") {
          var resolveBox = apEl("div", "ap-actions");
          var candidateInput = document.createElement("input");
          candidateInput.type = "text"; candidateInput.placeholder = "Verified account's 9-digit Private ID…"; candidateInput.className = "ap-reply-input";
          resolveBox.appendChild(candidateInput);

          var revealBtn = apEl("button", "qm-btn qm-btn-primary", "Reveal Private ID"); revealBtn.type = "button";
          revealBtn.addEventListener("click", function () {
            if (!window.confirm("Reveal this member's real Private ID? This is logged.")) return;
            apApi("/api/admin/account-recovery/" + id + "/reveal-private-id", { candidate_private_id: candidateInput.value })
              .then(function (res) {
                alert("Private ID: " + res.private_code + "\n\nTell the verified person now. It will not be shown again here.");
                apLoadFeed(); apOpenAccountRecovery(id);
              }).catch(function (e) { alert(e.message); });
          });
          resolveBox.appendChild(revealBtn);

          var pinBtn = apEl("button", "qm-btn qm-btn-primary", "Generate Temporary PIN"); pinBtn.type = "button";
          pinBtn.addEventListener("click", function () {
            if (!window.confirm("Generate a new temporary PIN for this account? This replaces their current PIN immediately and is logged.")) return;
            apApi("/api/admin/account-recovery/" + id + "/generate-pin", { candidate_private_id: candidateInput.value })
              .then(function (res) {
                alert("Temporary PIN: " + res.temporary_pin + "\n\nTell the verified person now. It will not be shown again here.");
                apLoadFeed(); apOpenAccountRecovery(id);
              }).catch(function (e) { alert(e.message); });
          });
          resolveBox.appendChild(pinBtn);
          apDetail.appendChild(resolveBox);
        }

        // Reply/close reuse the EXISTING query reply/close routes unchanged.
        var replyActions = apEl("div", "ap-actions");
        var replyInput = document.createElement("input");
        replyInput.type = "text"; replyInput.placeholder = "Write a reply…"; replyInput.className = "ap-reply-input";
        replyActions.appendChild(replyInput);
        var replyBtn = apEl("button", "qm-btn qm-btn-ghost", "Reply"); replyBtn.type = "button";
        replyBtn.addEventListener("click", function () {
          if (!replyInput.value.trim()) return;
          apApi("/api/admin/queries/" + id + "/reply", { message: replyInput.value })
            .then(function () { apLoadFeed(); apOpenAccountRecovery(id); }).catch(function (e) { alert(e.message); });
        });
        replyActions.appendChild(replyBtn);
        var closeBtn = apEl("button", "qm-btn qm-btn-ghost", "Close ticket"); closeBtn.type = "button";
        closeBtn.addEventListener("click", function () {
          apApi("/api/admin/queries/" + id + "/close", {}).then(function () { apLoadFeed(); apDetail.innerHTML = ""; }).catch(function (e) { alert(e.message); });
        });
        replyActions.appendChild(closeBtn);
        apDetail.appendChild(replyActions);
      }).catch(function (e) { apDetail.innerHTML = ""; apDetail.appendChild(apEl("p", "qm-dash-empty", e.message)); });
    }

    function apOpenCouncil(id) {
      fetch("/api/admin/panel/council/" + id).then(function (r) { return r.json(); }).then(function (m) {
        apDetail.innerHTML = "";
        apDetail.appendChild(apEl("h3", "ap-detail-title", m.subject || "(no subject)"));
        apDetail.appendChild(apEl("p", "ap-detail-meta", m.level.charAt(0).toUpperCase() + m.level.slice(1) +
          " " + m.location_id + " · status: " + m.status));
        var bodyP = document.createElement("p"); bodyP.className = "ap-detail-body";
        bodyP.appendChild(window.qmRenderFormattedText(m.body));
        apDetail.appendChild(bodyP);

        (m.attachments || []).forEach(function (att) {
          var link = document.createElement("a");
          link.href = "/api/qmail/attachments/" + att.id; link.target = "_blank"; link.rel = "noopener noreferrer";
          link.className = "ap-attachment-link";
          link.textContent = "📎 " + att.filename + " (" + Math.round(att.byte_size / 1024) + " KB)";
          apDetail.appendChild(link);
        });

        var repliesBox = apEl("div", "ap-updates");
        (m.actions || []).filter(function (a) { return a.action === "replied"; }).forEach(function (a) {
          var row = apEl("div", "ap-update-row");
          row.appendChild(apEl("b", "", a.actor_name + " "));
          var span = document.createElement("span");
          span.appendChild(window.qmRenderFormattedText(a.detail));
          span.appendChild(document.createTextNode(" · " + apAgo(a.created_at)));
          row.appendChild(span);
          repliesBox.appendChild(row);
        });
        apDetail.appendChild(repliesBox);

        if (m.status !== "closed") {
          var actions2 = apEl("div", "ap-actions");
          var replyInput = document.createElement("input");
          replyInput.type = "text"; replyInput.placeholder = "Write a reply…"; replyInput.className = "ap-reply-input";
          actions2.appendChild(replyInput);
          var replyBtn = apEl("button", "qm-btn qm-btn-primary", "Reply"); replyBtn.type = "button";
          replyBtn.addEventListener("click", function () {
            if (!replyInput.value.trim()) return;
            apApi("/api/admin/panel/council/" + id + "/reply", { message: replyInput.value })
              .then(function () { apLoadFeed(); apOpenCouncil(id); }).catch(function (e) { alert(e.message); });
          });
          actions2.appendChild(replyBtn);
          var closeBtn2 = apEl("button", "qm-btn qm-btn-ghost", "Close"); closeBtn2.type = "button";
          closeBtn2.addEventListener("click", function () {
            apApi("/api/admin/panel/council/" + id + "/close", {}).then(function () { apLoadFeed(); apOpenCouncil(id); }).catch(function (e) { alert(e.message); });
          });
          actions2.appendChild(closeBtn2);
          apDetail.appendChild(actions2);
        }
      }).catch(function (e) { apDetail.innerHTML = ""; apDetail.appendChild(apEl("p", "qm-dash-empty", e.message)); });
    }

    apRefreshFeed = apLoadFeed;
  }

  function loadAdminPanel() {
    if (apRefreshFeed) apRefreshFeed();
  }
  // 2026-10-28 (Hierarchical Explorer redesign): the Admin Queue moved from its own top-level tab
  // into the explorer modal's second sub-tab -- multiview.js calls this the first time that
  // sub-tab opens, same lazy-load-once pattern the old "admin" tab click used.
  window.QMLoadAdminPanel = loadAdminPanel;
})();
