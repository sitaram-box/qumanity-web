/**
 * qmail.js — the standalone /qmail page (2026-10-18): folder switching (inbox/sent/drafts), the
 * message list with a scaffolded-but-inert checkbox column, the reading pane, and the compose
 * overlay (smart-To autocomplete, a markup toolbar, an optional attachment, save-on-close
 * autosave to Drafts, send). Reuses the existing backend routes as-is
 * (/api/qmail/inbox|sent|drafts|compose|resolve-username|attachments) plus the new draft routes
 * built alongside this page. No bulk-action logic behind the checkboxes -- they render and do
 * nothing, on purpose.
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
  function snippet(text, n) {
    var s = (text || "").replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  var shell = document.querySelector(".qmail-shell");
  var listEl = $("qmail-list"), listEmpty = $("qmail-list-empty");
  var readingContent = $("qmail-reading-content");
  var backBtn = $("qmail-back-btn");
  var folderBtns = Array.prototype.slice.call(document.querySelectorAll(".qmail-folder"));
  var currentFolder = "inbox";
  var itemsCache = [];

  // ---- Folder loading ----
  function loadFolder(folder) {
    currentFolder = folder;
    var url = folder === "drafts" ? "/api/qmail/drafts" : "/api/qmail/" + folder;
    api(url).then(function (d) {
      var rows = folder === "drafts" ? (d.drafts || []) : (d.messages || []);
      itemsCache = rows.map(function (r) { return normalizeItem(r, folder); });
      renderList();
    }).catch(function (e) {
      listEl.innerHTML = "";
      listEl.appendChild(el("p", "qm-dash-empty", e.message));
    });
  }

  function normalizeItem(r, folder) {
    if (folder === "inbox") {
      return { id: r.id, folder: folder, who: r.from_name || r.from_address || "Unknown",
        gender: r.from_gender, profile_picture_url: r.from_profile_picture_url, subject: r.subject,
        body: r.body, date: r.created_at, unread: !r.read_at, attachments: r.attachments || [], raw: r };
    }
    if (folder === "sent") {
      // kind tells a member message from a council one -- their ids come from two tables and can
      // be the same number. A council "recipient" isn't a person, so it has no avatar data at all.
      return { id: r.id, folder: folder, kind: r.kind || "member", who: r.to_name || r.to_address || "Unknown",
        gender: r.to_gender, profile_picture_url: r.to_profile_picture_url, subject: r.subject,
        body: r.body, date: r.created_at, unread: false, attachments: r.attachments || [], raw: r };
    }
    // drafts -- to_address is unresolved/unvalidated by design (qmail_core.save_draft's own docstring)
    return { id: r.id, folder: folder, who: r.to_address ? r.to_address : "(no recipient yet)", subject: r.subject,
      body: r.body, date: r.updated_at, unread: false, attachments: [], raw: r };
  }

  function renderList() {
    listEl.innerHTML = "";
    listEmpty.hidden = itemsCache.length !== 0;
    itemsCache.forEach(function (item) {
      var row = el("button", "qmail-row");
      row.type = "button";
      if (item.unread) row.classList.add("is-unread");

      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "qmail-row-checkbox";
      cb.addEventListener("click", function (e) { e.stopPropagation(); }); // scaffolded only -- no bulk action
      row.appendChild(cb);

      if (window.QMAvatar) row.appendChild(window.QMAvatar.render({ name: item.who, gender: item.gender, profile_picture_url: item.profile_picture_url }, 36));

      var main = el("div", "qmail-row-main");
      main.appendChild(el("div", "qmail-row-who", item.who));
      main.appendChild(el("div", "qmail-row-subject", item.subject || "(no subject)"));
      main.appendChild(el("div", "qmail-row-snippet", snippet(item.body, 80)));
      row.appendChild(main);

      row.appendChild(el("div", "qmail-row-date", ago(item.date)));

      row.addEventListener("click", function () {
        if (item.folder === "drafts") openDraftForEdit(item);
        else openMessage(item);
      });
      listEl.appendChild(row);
    });
  }

  function openMessage(item) {
    if (item.folder === "sent" && item.kind === "council") { openThread("council", item.id); return; }
    readingContent.innerHTML = "";
    readingContent.appendChild(el("h2", "", item.subject || "(no subject)"));
    var metaLabel = item.folder === "inbox" ? "From " : "To ";
    readingContent.appendChild(el("p", "qmail-reading-meta", metaLabel + item.who + " · " + new Date(item.date).toLocaleString()));
    var bodyP = el("div", "qmail-reading-body");
    bodyP.appendChild(window.qmRenderFormattedText(item.body));
    readingContent.appendChild(bodyP);
    item.attachments.forEach(function (att) {
      var a = document.createElement("a");
      a.href = "/api/qmail/attachments/" + att.id;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "qmail-attachment-link";
      a.textContent = "📎 " + att.filename + " (" + Math.round(att.byte_size / 1024) + " KB)";
      readingContent.appendChild(a);
    });
    if (shell) shell.classList.add("is-reading"); // only visually relevant at <=760px

    if (item.folder === "inbox" && item.unread) {
      api("/api/qmail/messages/" + item.id + "/read", {}).then(function () {
        item.unread = false;
        item.raw.read_at = new Date().toISOString();
        renderList();
      }).catch(function () {});
    }
  }

  // ---- A message the member sent to a council, or a query they sent the Admin, with the
  // replies to it. Opening it marks the reply notification read (server side, in the same GET).
  // Shows the reply text and when it arrived, never who on the council replied or the log.
  function openThread(kind, id) {
    var url = kind === "council" ? "/api/qmail/sent/council/" + id : "/api/queries/mine/" + id;
    var replyFrom = kind === "council" ? "the council" : "the Admin";
    readingContent.innerHTML = "";
    api(url).then(function (t) {
      readingContent.innerHTML = "";
      readingContent.appendChild(el("h2", "", t.subject || "(no subject)"));
      var to = kind === "council" ? (t.to_name || t.to_address || "Council") : "the Admin";
      readingContent.appendChild(el("p", "qmail-reading-meta", "To " + to + " · " + new Date(t.created_at).toLocaleString()));
      var bodyP = el("div", "qmail-reading-body");
      bodyP.appendChild(window.qmRenderFormattedText(t.body));
      readingContent.appendChild(bodyP);
      (t.attachments || []).forEach(function (att) {
        var a = document.createElement("a");
        a.href = "/api/qmail/attachments/" + att.id;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.className = "qmail-attachment-link";
        a.textContent = "📎 " + att.filename + " (" + Math.round(att.byte_size / 1024) + " KB)";
        readingContent.appendChild(a);
      });
      var replies = t.replies || [];
      if (!replies.length) {
        readingContent.appendChild(el("p", "qmail-reading-meta", "No reply yet."));
      }
      replies.forEach(function (r) {
        readingContent.appendChild(el("p", "qmail-reading-meta", "Reply from " + replyFrom + " · " + new Date(r.created_at).toLocaleString()));
        var replyBody = el("div", "qmail-reading-body");
        replyBody.appendChild(window.qmRenderFormattedText(r.message));
        readingContent.appendChild(replyBody);
      });
      if (shell) shell.classList.add("is-reading");
    }).catch(function (e) {
      readingContent.innerHTML = "";
      readingContent.appendChild(el("p", "qm-dash-empty", e.message));
    });
  }

  if (backBtn) backBtn.addEventListener("click", function () { if (shell) shell.classList.remove("is-reading"); });

  folderBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      folderBtns.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
      if (shell) shell.classList.remove("is-reading");
      readingContent.innerHTML = "";
      readingContent.appendChild(el("p", "qm-dash-empty", "Select a message from the list."));
      loadFolder(btn.getAttribute("data-folder"));
    });
  });

  // ---- Compose overlay ----
  var overlay = $("qmail-compose-overlay");
  var composeBtn = $("qmail-compose-btn");
  var closeBtn = $("qmail-compose-close");
  var titleEl = $("qmail-compose-title");
  var toInput = $("qmail-to-input"), suggestionsEl = $("qmail-to-suggestions");
  var subjectInput = $("qmail-subject-input"), bodyInput = $("qmail-body-input");
  var attachmentInput = $("qmail-attachment-input"), attachNameEl = $("qmail-attach-name");
  var sendBtn = $("qmail-send-btn"), errorEl = $("qmail-compose-error");

  var currentDraftId = null;
  var selectedAddress = null;

  function resetCompose() {
    toInput.value = ""; subjectInput.value = ""; bodyInput.value = "";
    attachmentInput.value = ""; attachNameEl.textContent = "";
    suggestionsEl.hidden = true; errorEl.hidden = true;
    selectedAddress = null; currentDraftId = null;
    titleEl.textContent = "New Message";
  }

  function openComposeBlank() {
    resetCompose();
    overlay.hidden = false;
    toInput.focus();
  }
  composeBtn.addEventListener("click", openComposeBlank);

  function openDraftForEdit(item) {
    resetCompose();
    currentDraftId = item.id;
    toInput.value = item.raw.to_address || "";
    selectedAddress = item.raw.to_address || null; // best effort -- re-validated server-side at send either way
    subjectInput.value = item.subject || "";
    bodyInput.value = item.body || "";
    titleEl.textContent = "Edit Draft";
    overlay.hidden = false;
  }

  function closeCompose() {
    // Save the resolved address if one was actually picked from the smart-To suggestions, not
    // the input's own display text ("Name (address)") -- saving the display string here was a
    // real bug, found by reopening a saved draft and trying to send it: the draft's to_address
    // ended up holding "Page Target (pagetargetqm-...)" instead of the bare address, which
    // resolve_address()'s exact-string lookup (by design, qmail_core.py) could never match. A
    // draft with no address picked yet still saves the raw typed text -- "a draft is allowed to
    // have a garbage or incomplete recipient while being edited" (docs/QMAIL.md's drafts section).
    var to = (selectedAddress || toInput.value).trim(), subject = subjectInput.value.trim(), body = bodyInput.value.trim();
    overlay.hidden = true;
    if (to || subject || body) {
      // Silent autosave, no dialog -- matches what Gmail actually does, not a confirm prompt.
      var url = currentDraftId ? "/api/qmail/drafts/" + currentDraftId : "/api/qmail/drafts";
      api(url, { to: to, subject: subject, body: body }).then(function () {
        if (currentFolder === "drafts") loadFolder("drafts");
      }).catch(function () {});
    }
    resetCompose();
  }
  closeBtn.addEventListener("click", closeCompose);

  // Smart-To autocomplete -- the same connected_user_ids()-scoped route the dashboard's own
  // (now-removed) compose form used.
  toInput.addEventListener("input", function () {
    selectedAddress = null;
    var q = toInput.value.trim();
    if (q.length < 2) { suggestionsEl.hidden = true; return; }
    api("/api/qmail/resolve-username?q=" + encodeURIComponent(q)).then(function (d) {
      suggestionsEl.innerHTML = "";
      var matches = d.matches || [];
      if (!matches.length) { suggestionsEl.hidden = true; return; }
      matches.forEach(function (m) {
        var row = el("button", "qmail-to-suggestion", m.name + " (" + m.full_address + ")");
        row.type = "button";
        row.addEventListener("click", function () {
          selectedAddress = m.full_address;
          toInput.value = m.name + " (" + m.full_address + ")";
          suggestionsEl.hidden = true;
        });
        suggestionsEl.appendChild(row);
      });
      suggestionsEl.hidden = false;
    }).catch(function () { suggestionsEl.hidden = true; });
  });

  // Format toolbar -- wraps the textarea's current selection; a link prompts for the URL.
  function wrapSelection(before, after) {
    var start = bodyInput.selectionStart, end = bodyInput.selectionEnd;
    var value = bodyInput.value;
    var selected = value.slice(start, end);
    bodyInput.value = value.slice(0, start) + before + selected + after + value.slice(end);
    bodyInput.focus();
    bodyInput.selectionStart = start + before.length;
    bodyInput.selectionEnd = start + before.length + selected.length;
  }
  Array.prototype.slice.call(document.querySelectorAll(".qmail-fmt-btn")).forEach(function (btn) {
    btn.addEventListener("click", function () {
      var kind = btn.getAttribute("data-fmt");
      if (kind === "bold") wrapSelection("**", "**");
      else if (kind === "italic") wrapSelection("_", "_");
      else if (kind === "link") {
        var url = window.prompt("Link URL (http:// or https://):", "https://");
        if (!url) return;
        var start = bodyInput.selectionStart, end = bodyInput.selectionEnd;
        if (start === end) {
          // No selection -- insert a placeholder label rather than an empty [](url).
          var value = bodyInput.value;
          var placeholder = "link";
          bodyInput.value = value.slice(0, start) + "[" + placeholder + "](" + url + ")" + value.slice(end);
          bodyInput.focus();
          bodyInput.selectionStart = start + 1;
          bodyInput.selectionEnd = start + 1 + placeholder.length;
        } else {
          wrapSelection("[", "](" + url + ")");
        }
      }
    });
  });

  attachmentInput.addEventListener("change", function () {
    var f = attachmentInput.files[0];
    attachNameEl.textContent = f ? f.name + " (" + Math.round(f.size / 1024) + " KB)" : "";
  });

  sendBtn.addEventListener("click", function () {
    errorEl.hidden = true;
    if (!selectedAddress) {
      errorEl.textContent = "Choose a recipient from the suggestions.";
      errorEl.hidden = false;
      return;
    }
    if (!bodyInput.value.trim()) {
      errorEl.textContent = "A message body is required.";
      errorEl.hidden = false;
      return;
    }
    var form = new FormData();
    form.append("to", selectedAddress);
    form.append("subject", subjectInput.value);
    form.append("body", bodyInput.value);
    if (currentDraftId) form.append("draft_id", currentDraftId);
    if (attachmentInput.files[0]) form.append("attachment", attachmentInput.files[0]);
    fetch("/api/qmail/compose", { method: "POST", body: form })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); })
      .then(function () {
        overlay.hidden = true;
        resetCompose();
        if (currentFolder === "sent" || currentFolder === "drafts") loadFolder(currentFolder);
      })
      .catch(function (e) {
        errorEl.textContent = e.message;
        errorEl.hidden = false;
      });
  });

  // A reply notification links here as /qmail#council-<id> or /qmail#query-<id>.
  var hashMatch = /^#(council|query)-(\d+)$/.exec(window.location.hash || "");
  if (hashMatch) {
    if (hashMatch[1] === "council") {
      folderBtns.forEach(function (b) { b.classList.toggle("is-active", b.getAttribute("data-folder") === "sent"); });
      loadFolder("sent");
    } else {
      loadFolder("inbox");
    }
    openThread(hashMatch[1], parseInt(hashMatch[2], 10));
  } else {
    loadFolder("inbox");
  }
})();
