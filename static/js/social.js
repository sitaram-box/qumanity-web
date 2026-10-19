/**
 * social.js — Personal timeline: Private / Family / Friend / Business groups + Create New,
 * search-by-ID, message & group-invite requests, and private one-to-one chats.
 */
(function () {
  "use strict";
  var panel = document.getElementById("qm-dash-personal");
  if (!panel) return;

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function api(url, body) {
    var opt = body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }
  function ago(iso) {
    var s = Math.max(0, (Date.now() - new Date(iso.replace(" ", "T") + (iso.endsWith("Z") ? "" : "Z")).getTime()) / 1000);
    if (s < 60) return "just now"; if (s < 3600) return Math.floor(s / 60) + " min ago";
    if (s < 86400) return Math.floor(s / 3600) + " h ago"; return Math.floor(s / 86400) + " d ago";
  }

  var REACTION_ICON = { agree: "👍", disagree: "👎", read: "👁️" };
  function reactionBar(m, memberCount, onChange) {
    var bar = el("div", "bd-reactions");
    ["agree", "disagree", "read"].forEach(function (kind) {
      var mine = m.reactions.mine === kind;
      var btn = el("button", "bd-react" + (mine ? " is-on" : ""), REACTION_ICON[kind] + " " + m.reactions[kind]); btn.type = "button";
      btn.addEventListener("click", function () {
        api("/api/reactions/personal/" + m.id, { reaction: mine ? null : kind }).then(onChange).catch(function (e) { alert(e.message); });
      });
      bar.appendChild(btn);
    });
    bar.appendChild(el("small", "bd-react-total", "out of " + memberCount + " member" + (memberCount === 1 ? "" : "s")));
    return bar;
  }

  function renderChatShell(root, opts) {
    root.innerHTML = "";
    var head = el("div", "bd-head");
    var ht = el("div", "bd-headtext"); ht.appendChild(el("b", "bd-title", opts.title)); ht.appendChild(el("small", "bd-sub", opts.sub || ""));
    head.appendChild(ht);
    if (opts.headExtra) head.appendChild(opts.headExtra);
    root.appendChild(head);
    var feed = el("div", "bd-feed"); feed.setAttribute("aria-live", "polite"); root.appendChild(feed);
    var form = el("form", "bd-compose"), ta = document.createElement("textarea"); ta.rows = 2; ta.maxLength = 1000; ta.placeholder = opts.placeholder || "Message…"; ta.required = true;
    var send = el("button", "", "Send"); send.type = "submit"; form.appendChild(ta); form.appendChild(send);
    root.appendChild(form);
    return { feed: feed, form: form, ta: ta };
  }

  function renderMessages(feed, messages, emptyText, memberCount, onReact) {
    feed.innerHTML = "";
    if (!messages.length) { feed.appendChild(el("p", "bd-empty", emptyText)); return; }
    messages.forEach(function (m) {
      if (m.reactions && memberCount) {
        var b = el("div", "bd-msg bd-msg-full" + (m.mine ? " is-mine" : ""));
        var head = el("div", "bd-msg-head"); head.appendChild(el("b", "", m.who)); head.appendChild(el("small", "", m.account_id || "")); b.appendChild(head);
        b.appendChild(el("p", "bd-msg-text", m.text));
        b.appendChild(el("small", "bd-msg-time", ago(m.at)));
        b.appendChild(reactionBar(m, memberCount, onReact));
        feed.appendChild(b);
      } else {
        var plain = el("div", "bd-msg" + (m.mine ? " is-mine" : "")); if (!m.mine && m.who) plain.appendChild(el("b", "", m.who)); plain.appendChild(document.createTextNode(m.text));
        feed.appendChild(plain);
      }
    });
    feed.scrollTop = feed.scrollHeight;
  }

  // ---- top tabs ----
  var topTabs = document.getElementById("personal-top-tabs");
  var panels = {
    private: document.getElementById("pt-private-panel"), family: document.getElementById("pt-family-panel"),
    friends: document.getElementById("pt-friends-panel"), business: document.getElementById("pt-business-panel"),
    custom: document.getElementById("pt-custom-panel"),
  };
  function showTab(tab) {
    Object.keys(panels).forEach(function (k) { panels[k].hidden = k !== tab; });
    if (tab === "private") loadChats(); else if (tab !== "custom" || true) loadGroups();
  }
  topTabs.addEventListener("click", function (e) {
    var b = e.target.closest("[data-ptab]"); if (!b) return;
    Array.prototype.forEach.call(topTabs.querySelectorAll(".qm-ptab"), function (x) { x.classList.toggle("is-active", x === b); });
    showTab(b.getAttribute("data-ptab"));
  });

  // ---- group lists (Friends / Business / Custom -- Family moved to family.js's Activation
  // wizard, 2026-10-20: #pt-family-list no longer exists, the old Paternal/Maternal personal_groups
  // data is untouched but this panel no longer renders it) ----
  var LIST_EL = { friends: document.getElementById("pt-friends-list"),
                  business: document.getElementById("pt-business-list"), custom: document.getElementById("pt-custom-list") };
  var groupsCache = null;

  function loadGroups() {
    return api("/api/people/groups").then(function (d) {
      groupsCache = d;
      Object.keys(LIST_EL).forEach(function (cat) { renderGroupList(cat, d[cat]); });
    }).catch(function () {});
  }

  function renderGroupList(cat, data) {
    var list = LIST_EL[cat]; list.innerHTML = "";
    var rows = data.owned.concat(data.joined);
    if (!rows.length) { list.appendChild(el("li", "pt-empty-row", "No groups yet.")); return; }
    rows.forEach(function (g) {
      var li = el("li", "pt-group-row");
      var btn = el("button", "qm-member-row", g.name + " · " + g.members + " member" + (g.members === 1 ? "" : "s") + (g.mine ? "" : " · " + g.owner_name + "'s group"));
      btn.type = "button";
      btn.addEventListener("click", function () { openGroupChat(g.id, cat); });
      li.appendChild(btn);
      list.appendChild(li);
    });
  }

  // New groups are always created as Custom (2026-09-28: Family/Friends/Business are pre-defined
  // or auto-created only, never created directly -- see social_core.create_group). A category box's
  // own "+ New"/"+ Create" still works from the user's point of view: it creates as Custom, then
  // immediately moves the new group into that box's category.
  Array.prototype.forEach.call(document.querySelectorAll(".pt-new-group-inline"), function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = form.querySelector("input"), cat = form.getAttribute("data-category");
      api("/api/people/groups/create", { category: "custom", name: input.value }).then(function (r) {
        return cat === "custom" ? r : api("/api/people/groups/" + r.id + "/move", { category: cat });
      }).then(function () { input.value = ""; loadGroups(); }).catch(function (er) { alert(er.message); });
    });
  });

  var groupModal = document.getElementById("pt-group-modal"), groupRoot = document.getElementById("pt-group-chat");
  groupModal.addEventListener("click", function (e) { if (e.target === groupModal || e.target.hasAttribute("data-close")) groupModal.hidden = true; });

  function openGroupChat(groupId, cat) {
    groupModal.hidden = false;
    api("/api/people/groups/" + groupId + "/messages").then(function (d) {
      var extra = null;
      if (cat === "business") {
        extra = el("button", "sg-btn", "✏️ Business details"); extra.type = "button";
        extra.addEventListener("click", function () { openBusinessEditor(groupId, d.business); });
      } else if (d.is_owner) {
        extra = el("button", "sg-btn", "✏️ Rename"); extra.type = "button";
        extra.addEventListener("click", function () {
          var name = window.prompt("Rename this group", d.name); if (!name) return;
          api("/api/people/groups/" + groupId + "/rename", { name: name }).then(function () { openGroupChat(groupId, cat); loadGroups(); }).catch(function (e) { alert(e.message); });
        });
      }
      if (d.is_owner) {
        var inviteBtn = el("button", "sg-btn", "➕ Add member"); inviteBtn.type = "button";
        inviteBtn.addEventListener("click", function () {
          var code = window.prompt("Their 12-digit search ID or Account ID:"); if (!code) return;
          api("/api/people/search?q=" + encodeURIComponent(code)).then(function (p) {
            return api("/api/people/invite", { group_id: groupId, user_id: p.user_id });
          }).then(function () { alert("Invitation sent."); }).catch(function (e) { alert(e.message); });
        });
        var wrap = el("span"); wrap.appendChild(inviteBtn); if (extra) wrap.appendChild(extra); extra = wrap;
      }
      var sub = d.members.length + " member" + (d.members.length === 1 ? "" : "s") + ": " + d.members.map(function (m) { return m.you ? "You" : m.name; }).join(", ");
      var bizNote = d.business && d.business.name ? d.business.name + (d.business.sector ? " · " + d.business.sector : "") : "";
      var ui = renderChatShell(groupRoot, { title: d.name, sub: bizNote ? sub + " · " + bizNote : sub, headExtra: extra, placeholder: "Message " + d.name + "…" });
      renderMessages(ui.feed, d.messages, "No messages yet — say hello.", d.members.length, function () { openGroupChat(groupId, cat); });
      ui.form.addEventListener("submit", function (e) {
        e.preventDefault();
        api("/api/people/groups/" + groupId + "/messages", { text: ui.ta.value }).then(function () { ui.ta.value = ""; openGroupChat(groupId, cat); }).catch(function (er) { alert(er.message); });
      });
    }).catch(function (e) { groupRoot.innerHTML = ""; groupRoot.appendChild(el("p", "bd-empty", e.message)); });
  }

  function openBusinessEditor(groupId, biz) {
    var name = window.prompt("Business name", (biz && biz.name) || ""); if (name === null) return;
    var sector = window.prompt("Work sector (e.g. Retail, Services, Manufacturing)", (biz && biz.sector) || "");
    var services = window.prompt("Services you provide", (biz && biz.services) || "");
    api("/api/people/groups/" + groupId + "/business", { name: name, sector: sector, services: services }).then(function () { openGroupChat(groupId, "business"); loadGroups(); }).catch(function (e) { alert(e.message); });
  }

  // ---- search ----
  var searchInput = document.getElementById("pt-search-input"), searchBtn = document.getElementById("pt-search-btn"), searchResult = document.getElementById("pt-search-result");
  function runSearch() {
    var q = searchInput.value.trim(); if (!q) return;
    searchResult.innerHTML = ""; searchResult.appendChild(el("p", "qm-dash-empty", "Searching…"));
    api("/api/people/search?q=" + encodeURIComponent(q)).then(function (p) {
      searchResult.innerHTML = "";
      var card = el("div", "pt-person");
      card.appendChild(el("b", "", p.name)); card.appendChild(el("small", "", " " + p.gender + " · " + (p.place || "")));
      var actions = el("div", "pt-person-actions");
      var msgBtn = el("button", "sg-btn", "✉️ Message"); msgBtn.type = "button";
      msgBtn.addEventListener("click", function () {
        var text = window.prompt("Your one-time message to " + p.name + ":"); if (!text) return;
        api("/api/people/message", { user_id: p.user_id, text: text }).then(function () { alert("Sent — waiting for them to accept."); }).catch(function (e) { alert(e.message); });
      });
      actions.appendChild(msgBtn);
      card.appendChild(actions);
      card.appendChild(el("p", "qm-dash-empty", "To add them to a group, open the group (Family/Friends/Business/Custom) and use “➕ Add member” with this same ID."));
      searchResult.appendChild(card);
    }).catch(function (e) { searchResult.innerHTML = ""; searchResult.appendChild(el("p", "qm-dash-empty", e.message)); });
  }
  searchBtn.addEventListener("click", runSearch);
  searchInput.addEventListener("keydown", function (e) { if (e.key === "Enter") runSearch(); });

  // ---- inbox ----
  var inboxList = document.getElementById("pt-inbox-list"), inboxEmpty = document.getElementById("pt-inbox-empty");
  function loadInbox() {
    api("/api/people/inbox").then(function (d) {
      inboxList.innerHTML = ""; inboxEmpty.hidden = d.requests.length > 0;
      d.requests.forEach(function (r) {
        var li = el("li", "pt-inbox-item");
        var text = r.kind === "message" ? r.from_name + ": “" + r.first_message + "”" : r.from_name + " invites you to " + r.group_name;
        li.appendChild(el("div", "", text)); li.appendChild(el("small", "", ago(r.created_at)));
        var row = el("div", "pt-person-actions");
        [["accept", "✓ Accept"], ["decline", "✕ Decline"], ["waiting", "… Later"]].forEach(function (a) {
          var b = el("button", "sg-btn", a[1]); b.type = "button";
          b.addEventListener("click", function () { api("/api/people/inbox/" + r.id + "/decide", { decision: a[0] }).then(function () { loadInbox(); loadChats(); loadGroups(); }).catch(function (e) { alert(e.message); }); });
          row.appendChild(b);
        });
        li.appendChild(row); inboxList.appendChild(li);
      });
    }).catch(function () {});
  }
  loadInbox();

  // ---- private chats ----
  var chatList = document.getElementById("pt-chat-list"), chatEmpty = document.getElementById("pt-chat-empty");
  var chatModal = document.getElementById("pt-chat-modal"), chatRoot = document.getElementById("pt-private-chat");
  chatModal.addEventListener("click", function (e) { if (e.target === chatModal || e.target.hasAttribute("data-close")) chatModal.hidden = true; });

  function loadChats() {
    api("/api/people/chats").then(function (d) {
      chatList.innerHTML = ""; chatEmpty.hidden = d.chats.length > 0;
      d.chats.forEach(function (c) {
        var li = el("li", "pt-inbox-item"); var b = el("button", "qm-member-row", c.with + (c.last ? " — " + c.last : "")); b.type = "button";
        b.addEventListener("click", function () { openChat(c.chat_id); });
        li.appendChild(b); chatList.appendChild(li);
      });
    }).catch(function () {});
  }
  function openChat(chatId) {
    chatModal.hidden = false;
    api("/api/people/chats/" + chatId).then(function (d) {
      var ui = renderChatShell(chatRoot, { title: d.with, sub: "Private chat", placeholder: "Message " + d.with + "…" });
      renderMessages(ui.feed, d.messages, "No messages yet.");
      ui.form.addEventListener("submit", function (e) {
        e.preventDefault();
        api("/api/people/chats/" + chatId, { text: ui.ta.value }).then(function () { ui.ta.value = ""; openChat(chatId); }).catch(function (er) { alert(er.message); });
      });
    }).catch(function (e) { chatRoot.innerHTML = ""; chatRoot.appendChild(el("p", "bd-empty", e.message)); });
  }
  loadChats();

  document.querySelector('.qm-dash-tab[data-tab="personal"]').addEventListener("click", function () { loadInbox(); loadChats(); });
})();
