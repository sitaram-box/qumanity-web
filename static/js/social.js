/**
 * social.js — Personal timeline: Private / Family / Friend / Business groups + Create New,
 * search-by-ID, message & group-invite requests, and private one-to-one chats.
 */
(function () {
  "use strict";
  var panel = document.getElementById("qm-dash-personal");
  if (!panel) return;

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  var GENDER_LABEL = { male: "Male", female: "Female", both: "Third Gender" };
  // Personal groups have no founder concept, so this only ever shows admin/member -- but reading
  // the same `role` field family groups use (2026-10-27) keeps both renderers in sync.
  var ROLE_LABEL = { founder: "Founder", admin: "Admin", member: "Member" };
  function api(url, body) {
    var opt = body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }
  function ago(iso) {
    var s = Math.max(0, (Date.now() - new Date(iso.replace(" ", "T") + (iso.endsWith("Z") ? "" : "Z")).getTime()) / 1000);
    if (s < 60) return "just now"; if (s < 3600) return Math.floor(s / 60) + " min ago";
    if (s < 86400) return Math.floor(s / 3600) + " h ago"; return Math.floor(s / 86400) + " d ago";
  }

  // reactionBar()/renderChatShell()/renderMessages() (the local chat-feed renderers this panel
  // used before the Universal Inbox pass, 2026-11-25) are removed along with their only two
  // callers, openGroupChat() and openChat() -- this panel no longer renders any chat feed of its
  // own, see renderGroupList()'s own comment.

  // ---- top tabs ----
  var topTabs = document.getElementById("personal-top-tabs");
  var panels = {
    private: document.getElementById("pt-private-panel"), family: document.getElementById("pt-family-panel"),
    friends: document.getElementById("pt-friends-panel"), business: document.getElementById("pt-business-panel"),
    custom: document.getElementById("pt-custom-panel"),
  };
  var sideEl = document.querySelector(".pt-side");
  var layoutEl = document.querySelector(".pt-layout");
  function showTab(tab) {
    Object.keys(panels).forEach(function (k) { panels[k].hidden = k !== tab; });
    // Family Tree's own slide-in chat panel (2026-10-28) is retired as of 2026-11-25 -- a node's
    // chat now opens on the dashboard's Home tab instead (family_tree.js's goToFamilyChat()), so
    // .pt-side is simply hidden for Family Tree now, no is-chat-mode exception left to check.
    // Find & connect / Requests are shared across Friends/Business/Custom (and Self) -- hidden for
    // Family Tree, which has its own dedicated search (family.js) and whose D3 view wants the full
    // panel width. The grid's second column track doesn't collapse just because its content is
    // `hidden` -- .pt-layout--full (CSS) drops it to one column.
    if (sideEl) sideEl.hidden = tab === "family";
    if (layoutEl) layoutEl.classList.toggle("pt-layout--full", tab === "family");
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

  // Universal Inbox pass (2026-11-25): a row's own click now goes straight to the dashboard's
  // Home tab and opens this exact group's REAL conversation there (window.QMOpenHomeChat,
  // dashboard.js) -- this panel no longer renders a chat feed of its own at all (the old
  // openGroupChat()/renderChatShell()-based modal is gone, not just rerouted). Members/Rename/
  // Business details are MANAGEMENT actions, not the conversation itself, so they stay here as
  // small per-row icon buttons instead of moving with the chat.
  function renderGroupList(cat, data) {
    var list = LIST_EL[cat]; list.innerHTML = "";
    var rows = data.owned.concat(data.joined);
    if (!rows.length) { list.appendChild(el("li", "pt-empty-row", "No groups yet.")); return; }
    rows.forEach(function (g) {
      var li = el("li", "pt-group-row");
      var btn = el("button", "qm-member-row", g.name + " · " + g.members + " member" + (g.members === 1 ? "" : "s") + (g.mine ? "" : " · " + g.owner_name + "'s group"));
      btn.type = "button";
      btn.addEventListener("click", function () { window.QMOpenHomeChat("group", g.id); });
      li.appendChild(btn);

      var membersBtn = el("button", "pt-group-row-icon-btn", "👥"); membersBtn.type = "button";
      membersBtn.title = "Members"; membersBtn.setAttribute("aria-label", "Members");
      membersBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        currentGroup = { id: g.id, cat: cat, isOwner: g.mine };
        openMembersModal();
      });
      li.appendChild(membersBtn);

      // Rename/Business details are owner-only server-side (social_core.rename_group()/
      // set_business_profile()) -- g.mine (this list's own "is this my group" flag) matches
      // that exactly, so the button is simply never shown otherwise rather than shown-then-403'd.
      if (g.mine) {
        var manageLabel = cat === "business" ? "Business details" : "Rename";
        var manageBtn = el("button", "pt-group-row-icon-btn", "✏️"); manageBtn.type = "button";
        manageBtn.title = manageLabel; manageBtn.setAttribute("aria-label", manageLabel);
        manageBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          if (cat === "business") {
            openBusinessEditor(g.id, { name: g.business_name, sector: g.business_sector, services: g.business_services });
          } else {
            var name = window.prompt("Rename this group", g.name); if (!name) return;
            api("/api/people/groups/" + g.id + "/rename", { name: name }).then(loadGroups).catch(function (e2) { alert(e2.message); });
          }
        });
        li.appendChild(manageBtn);
      }
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

  var currentGroup = { id: null, cat: null, isOwner: false };

  // ---- Members modal (2026-10-25): avatar + name + role for every approved member, plus an
  // "Add Member by Public ID" box (owner only) -- replaces the old window.prompt()-based
  // "➕ Add member" flow and the plain comma-joined name list in the chat subtitle. ----
  var membersModal = document.getElementById("pt-members-modal");
  var membersList = document.getElementById("pt-members-list");
  var membersAddSection = document.getElementById("pt-members-add-section");
  var membersSearchInput = document.getElementById("pt-members-search-input");
  var membersSearchResult = document.getElementById("pt-members-search-result");
  var membersErrorEl = document.getElementById("pt-members-error");

  membersModal.addEventListener("click", function (e) {
    if (e.target === membersModal || e.target.hasAttribute("data-close")) membersModal.hidden = true;
  });

  function openMembersModal() {
    if (!currentGroup.id) return;
    membersErrorEl.hidden = true;
    membersSearchInput.value = "";
    membersSearchResult.innerHTML = "";
    membersAddSection.hidden = !currentGroup.isOwner;
    membersModal.hidden = false;
    api("/api/people/groups/" + currentGroup.id + "/messages").then(function (d) {
      membersList.innerHTML = "";
      d.members.forEach(function (m) {
        var li = el("li", "ft-member-row");
        if (window.QMAvatar) li.appendChild(QMAvatar.render(m, 40));
        var textWrap = el("div", "ft-member-text");
        textWrap.appendChild(el("b", "", m.name + (m.you ? " (You)" : "")));
        var meta = [GENDER_LABEL[m.gender] || m.gender, m.age_group, m.present_location].filter(Boolean).join(" · ");
        textWrap.appendChild(el("span", "ft-member-meta", meta));
        li.appendChild(textWrap);
        li.appendChild(el("span", "ft-member-role" + (m.role !== "member" ? " is-admin" : ""), ROLE_LABEL[m.role] || "Member"));
        membersList.appendChild(li);
      });
    }).catch(function (e) { membersErrorEl.textContent = e.message; membersErrorEl.hidden = false; });
  }

  document.getElementById("pt-members-search-btn").addEventListener("click", function () {
    var code = membersSearchInput.value.trim();
    membersErrorEl.hidden = true;
    membersSearchResult.innerHTML = "";
    if (!code) { membersErrorEl.textContent = "Enter a 12-digit Public ID."; membersErrorEl.hidden = false; return; }
    api("/api/people/search?q=" + encodeURIComponent(code)).then(function (p) {
      var card = el("div", "fw-suggestion-row");
      var top = el("div", "fw-suggestion-top");
      if (window.QMAvatar) top.appendChild(QMAvatar.render(p, 40));
      var textWrap = el("div", "fw-suggestion-text");
      textWrap.appendChild(el("p", "", p.name + " · " + p.gender));
      top.appendChild(textWrap);
      card.appendChild(top);
      var inviteBtn = el("button", "qm-btn qm-btn-primary", "Send Invite"); inviteBtn.type = "button";
      inviteBtn.addEventListener("click", function () {
        inviteBtn.disabled = true; inviteBtn.textContent = "Inviting…";
        api("/api/people/invite", { group_id: currentGroup.id, user_id: p.user_id }).then(function () {
          inviteBtn.textContent = "✓ Invited"; membersSearchInput.value = "";
        }).catch(function (e) {
          inviteBtn.disabled = false; inviteBtn.textContent = "Send Invite";
          membersErrorEl.textContent = e.message; membersErrorEl.hidden = false;
        });
      });
      card.appendChild(inviteBtn);
      membersSearchResult.appendChild(card);
    }).catch(function (e) { membersErrorEl.textContent = e.message; membersErrorEl.hidden = false; });
  });

  function openBusinessEditor(groupId, biz) {
    var name = window.prompt("Business name", (biz && biz.name) || ""); if (name === null) return;
    var sector = window.prompt("Work sector (e.g. Retail, Services, Manufacturing)", (biz && biz.sector) || "");
    var services = window.prompt("Services you provide", (biz && biz.services) || "");
    api("/api/people/groups/" + groupId + "/business", { name: name, sector: sector, services: services }).then(loadGroups).catch(function (e) { alert(e.message); });
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
      // 2026-10-27: already mutually connected (shares an approved group) -> skip the
      // message-request-and-wait step entirely and open a real chat immediately. 2026-11-25:
      // "immediately" now means the Home tab's own Unified Chat feed, not a panel in here.
      if (p.can_open_chat) {
        var openBtn = el("button", "sg-btn", "💬 Open Chat"); openBtn.type = "button";
        openBtn.addEventListener("click", function () {
          api("/api/people/open-chat", { user_id: p.user_id }).then(function (d) { window.QMOpenHomeChat("private", d.chat_id); loadChats(); }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(openBtn);
      } else {
        var msgBtn = el("button", "sg-btn", "✉️ Message"); msgBtn.type = "button";
        msgBtn.addEventListener("click", function () {
          var text = window.prompt("Your one-time message to " + p.name + ":"); if (!text) return;
          api("/api/people/message", { user_id: p.user_id, text: text }).then(function () { alert("Sent — waiting for them to accept."); }).catch(function (e) { alert(e.message); });
        });
        actions.appendChild(msgBtn);
      }
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
        var text;
        if (r.kind === "message") text = r.from_name + ": “" + r.first_message + "”";
        else if (r.kind === "rejoin") text = r.from_name + " wants back into " + r.chat_name;
        else if (r.kind === "family_group_join") text = r.from_name + " wants to join " + r.family_group_name;
        else if (r.kind === "family_group_invite") text = r.from_name + " invites you to join " + r.family_group_name;
        else text = r.from_name + " invites you to " + r.group_name;  // kind === "group"
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
  // Universal Inbox pass (2026-11-25): a row's click now goes straight to the dashboard's Home
  // tab and opens this exact 1:1 conversation there -- a private chat has no management action of
  // its own (no Rename/Business details/Members to keep here), so the old pt-chat-modal and its
  // openChat() are removed outright, not just rerouted.
  var chatList = document.getElementById("pt-chat-list"), chatEmpty = document.getElementById("pt-chat-empty");

  function loadChats() {
    api("/api/people/chats").then(function (d) {
      chatList.innerHTML = ""; chatEmpty.hidden = d.chats.length > 0;
      d.chats.forEach(function (c) {
        var li = el("li", "pt-inbox-item"); var b = el("button", "qm-member-row"); b.type = "button";
        if (window.QMAvatar) b.appendChild(window.QMAvatar.render({ name: c.with, gender: c.with_gender, profile_picture_url: c.with_profile_picture_url }, 28));
        b.appendChild(document.createTextNode(c.with + (c.last ? " — " + c.last : "")));
        b.addEventListener("click", function () { window.QMOpenHomeChat("private", c.chat_id); });
        li.appendChild(b); chatList.appendChild(li);
      });
    }).catch(function () {});
  }
  loadChats();

  document.querySelector('.qm-dash-tab[data-tab="personal"]').addEventListener("click", function () { loadInbox(); loadChats(); });
})();
