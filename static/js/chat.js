/**
 * chat.js — the standalone /chat page (Unified Chat Architecture, Phase 2 Step 2, 2026-11-24):
 * the Teams-style middle conversation list (All/Unread/Mentions filter tabs, Private vs. Channels,
 * channels grouped by their own location), the right-hand feed (messages + composer), presence
 * dots, the Members panel, and the Governance-pane-only Karma badge.
 *
 * Backend: GET /api/chat/conversations (chat_core.list_my_conversations() -- the read-side
 * aggregator across all six existing messaging systems). Loading/sending a conversation's own
 * messages still goes straight to each system's OWN existing route -- this page does not
 * introduce a seventh, unified message store; see chat_core.py's own module docstring for why.
 * The per-kind route map below mirrors the Phone App's identical dispatch table
 * (Qumanity_App/mobile/src/api/qumanity.ts's chatLoad()/chatSend()) so the two clients can never
 * silently drift onto different endpoints for the same kind.
 *
 * No "Favorites" section is rendered here: no pinning mechanism exists anywhere in this codebase
 * today (confirmed by grep -- no pinned_conversations table, no pin/favorite column on any
 * messaging table). Building fake pinning UI with nothing behind it would be worse than leaving
 * it out; see renderList()'s own comment for where it plugs in once that schema work is done.
 *
 * "Unread" and "Mentions" are real, wired-up filter tabs, but both are honestly empty today:
 * chat_core.list_my_conversations() returns unread_count=0 for every row (no per-user "last read"
 * timestamp exists anywhere yet -- that function's own docstring says so), and no @mention parser
 * exists anywhere in this codebase either. Switching to either tab filters correctly; there's just
 * nothing to show until that backend work happens.
 */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function api(url, body) {
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
  function ago(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    var sameDay = d.toDateString() === new Date().toDateString();
    return sameDay ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : d.toLocaleDateString();
  }

  // ---- Per-kind message routes -- mirrors Qumanity_App/mobile/src/api/qumanity.ts exactly ----
  var ROUTE = {
    sub: function (id) { return "/api/chat/" + id; },
    local: function (id) { return "/api/local-areas/" + id + "/chat"; },
    family: function (id) { return "/api/family-groups/" + id + "/messages"; },
    group: function (id) { return "/api/people/groups/" + id + "/messages"; },
    private: function (id) { return "/api/people/chats/" + id; },
  };

  var PRESENCE_COLOR = { green: "#3DBE6B", yellow: "#F2B705", grey: "#8A97A3", red: "#E0483E" };
  var PRESENCE_LABEL = { green: "Active now", yellow: "Away", grey: "Offline", red: "Busy" };

  var state = {
    conversations: [],
    filter: "all",
    active: null,       // the open conversation's own row from state.conversations
    activeMembers: [],  // [{user_id, name}], refreshed each time a conversation opens
  };

  // ---- Conversation list ----

  function loadConversations() {
    return api("/api/chat/conversations").then(function (r) {
      state.conversations = r.conversations;
      renderList();
      refreshPrivatePresence();
    });
  }

  function matchesFilter(c) {
    if (state.filter === "unread") return c.unread_count > 0;
    if (state.filter === "mentions") return false; // no @mention detection exists yet -- see module docstring
    return true;
  }

  function renderList() {
    var list = $("qm-chat-list");
    list.innerHTML = "";
    var visible = state.conversations.filter(matchesFilter);
    if (!visible.length) {
      var emptyText = state.filter === "unread" ? "No unread conversations."
        : state.filter === "mentions" ? "No mentions yet."
        : "Nothing here yet.";
      list.appendChild(el("p", "qm-chat-empty", emptyText));
      return;
    }

    // Favorites (pinned items) deliberately has nothing to render -- see this file's own module
    // docstring. The hook for it, once a pinning table exists, is here: filter `visible` for
    // c.pinned before splitting into the two sections below, and render it as a third, first
    // section the same way.

    var privateItems = visible.filter(function (c) { return c.pane === "private"; });
    var channelItems = visible.filter(function (c) { return c.pane === "channel"; });

    if (privateItems.length) {
      list.appendChild(el("div", "qm-chat-list-section-title", "Private"));
      privateItems.forEach(function (c) { list.appendChild(buildRow(c)); });
    }

    if (channelItems.length) {
      list.appendChild(el("div", "qm-chat-list-section-title", "Channels"));
      // Grouped by location -- a Village's channels separate from a Tehsil's, etc. (the one
      // structural signal the whole Teams redesign exists to add -- see the Phase 1 proposal).
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
        group.forEach(function (c) { list.appendChild(buildRow(c)); });
      });
    }
  }

  function buildRow(c) {
    var row = el("button", "qm-chat-row" + (state.active && state.active.kind === c.kind && state.active.id === c.id ? " is-active" : ""));
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
    titleRow.appendChild(el("span", "qm-chat-row-time", ago(c.last_message_at)));
    body.appendChild(titleRow);
    var sub = el("div", "qm-chat-row-sub", c.pane === "channel" ? (c.location_level ? c.location_level.charAt(0).toUpperCase() + c.location_level.slice(1) + " Channel" : "Channel") : "Private chat");
    body.appendChild(sub);
    row.appendChild(body);

    if (c.unread_count > 0) row.appendChild(el("span", "qm-chat-row-badge", String(c.unread_count)));

    row.addEventListener("click", function () { openConversation(c); });
    return row;
  }

  function refreshPrivatePresence() {
    var ids = state.conversations.filter(function (c) { return c.pane === "private" && c.other_user_id; }).map(function (c) { return c.other_user_id; });
    if (!ids.length) return;
    api("/api/presence/batch?user_ids=" + ids.join(",")).then(function (r) {
      Object.keys(r.statuses).forEach(function (uid) {
        document.querySelectorAll('[data-presence-for="' + uid + '"]').forEach(function (dot) {
          dot.className = "qm-presence-dot qm-presence-dot--" + r.statuses[uid];
          dot.title = PRESENCE_LABEL[r.statuses[uid]] || "";
        });
      });
    }).catch(function () { /* presence is advisory; a failed fetch just leaves the grey default */ });
  }

  // ---- Filter tabs ----

  document.querySelectorAll(".qm-chat-filter-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".qm-chat-filter-tab").forEach(function (t) {
        t.classList.toggle("is-active", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      state.filter = tab.getAttribute("data-filter");
      renderList();
    });
  });

  // ---- The feed ----

  function openConversation(c) {
    state.active = c;
    renderList();
    $("qm-chat-feed-empty").hidden = true;
    $("qm-chat-feed-active").hidden = false;
    $("qm-chat-feed-name").textContent = c.title;
    $("qm-chat-feed-desc").textContent = c.pane === "channel"
      ? (c.location_level ? c.location_level.charAt(0).toUpperCase() + c.location_level.slice(1) + " · " + c.location_id : "")
      : "";
    $("qm-chat-messages").innerHTML = "<p class=\"qm-chat-empty\">Loading…</p>";

    api(ROUTE[c.kind](c.id)).then(function (r) {
      state.activeMembers = (r.extra && r.extra.members) || [];
      $("qm-chat-members-count").textContent = state.activeMembers.length ? String(state.activeMembers.length) : "";
      renderMessages(r.messages || [], c.pane === "channel");
    }).catch(function (e) {
      $("qm-chat-messages").innerHTML = "";
      $("qm-chat-messages").appendChild(el("p", "qm-chat-empty", e.message));
    });
  }

  function renderMessages(messages, isChannel) {
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
      row.appendChild(el("div", "qm-chat-message-at", ago(m.at)));
      box.appendChild(row);
    });
    box.scrollTop = box.scrollHeight;
    if (isChannel) applyKarmaBadges(messages);
  }

  function applyKarmaBadges(messages) {
    var ids = Array.from(new Set(messages.map(function (m) { return m.user_id; }).filter(Boolean)));
    if (!ids.length) return;
    var since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    api("/api/karma/recent?user_ids=" + ids.join(",") + "&since=" + encodeURIComponent(since)).then(function (r) {
      Object.keys(r.karma).forEach(function (uid) {
        var entry = r.karma[uid];
        document.querySelectorAll('[data-karma-for="' + uid + '"]').forEach(function (badge) {
          badge.hidden = false;
          badge.textContent = "✦ +" + entry.points + " Karma";
          badge.title = entry.reason + " · " + ago(entry.at);
        });
      });
    }).catch(function () { /* the badge is a bonus; a failed lookup just means no badge shows */ });
  }

  $("qm-chat-composer").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!state.active) return;
    var input = $("qm-chat-input");
    var text = input.value.trim();
    if (!text) return;
    input.disabled = true;
    api(ROUTE[state.active.kind](state.active.id), { text: text }).then(function () {
      input.value = "";
      input.disabled = false;
      openConversation(state.active); // reload so the new message (and anyone else's since) shows
    }).catch(function (err) {
      input.disabled = false;
      window.alert(err.message);
    });
  });

  // ---- Members panel ----

  $("qm-chat-members-btn").addEventListener("click", function () {
    if (!state.active) return;
    var overlay = $("qm-chat-members-overlay");
    var listEl = $("qm-chat-members-list");
    listEl.innerHTML = "<p class=\"qm-chat-empty\">Loading…</p>";
    overlay.hidden = false;

    membersFor(state.active).then(function (members) {
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
      api("/api/presence/batch?user_ids=" + ids.join(",")).then(function (r) {
        Object.keys(r.statuses).forEach(function (uid) {
          listEl.querySelectorAll('[data-presence-for="' + uid + '"]').forEach(function (dot) {
            dot.className = "qm-presence-dot qm-presence-dot--" + r.statuses[uid];
            dot.title = PRESENCE_LABEL[r.statuses[uid]] || "";
          });
        });
      }).catch(function () { /* advisory only */ });
    });
  });

  function membersFor(c) {
    // family/group already embed their member list in the SAME response chatLoad() fetches
    // (state.activeMembers, cached by openConversation()) -- no second request needed.
    if (c.kind === "family" || c.kind === "group") return Promise.resolve(state.activeMembers);
    if (c.kind === "private") return Promise.resolve(c.other_user_id ? [{ user_id: c.other_user_id, name: c.title }] : []);
    if (c.kind === "local") return api("/api/local-areas/" + c.id + "/members").then(function (r) { return r.members; });
    return api("/api/subgroups/" + c.id + "/members").then(function (r) { return r.members; }); // kind === 'sub'
  }

  $("qm-chat-members-close").addEventListener("click", function () { $("qm-chat-members-overlay").hidden = true; });

  // ---- Rail (Activity/Chat/Channels/Karma are placeholder tabs for now -- this page IS "Chat";
  // the others route to their own existing pages once built, same icon-rail shell either way) ----
  document.querySelectorAll(".qm-chat-rail-btn[data-rail]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".qm-chat-rail-btn[data-rail]").forEach(function (b) { b.classList.toggle("is-active", b === btn); });
    });
  });

  loadConversations();
  // Presence/unread refresh -- same 30-second cadence dash_extras.js's own notification poll
  // already uses elsewhere on the site, not a new, more aggressive loop.
  setInterval(loadConversations, 30000);
})();
