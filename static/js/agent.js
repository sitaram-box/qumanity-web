/**
 * agent.js — the standalone /agent page (2026-11-25): the Agent Dashboard, an OAP-style command
 * center for Qumanity's salaried Agents (case_core.py's `agents` table -- see
 * docs/economic_engine_phase1_design_2026_11_25.md). Three columns: a rail (Queue/Compass/
 * Directory/History), a middle list, and a right-hand workspace that shows a Case, a Supplier, or
 * a Compass task depending on what's selected.
 *
 * Duplicates a few small label maps (CASE_TYPE_LABEL/CASE_STATUS_LABEL/CASE_ROLE_LABEL/
 * caseDisplayId) that also exist in dashboard.js -- this is a separate page with no shared module
 * system between the two (same reasoning qmail.js stands alone from dashboard.js today).
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

  var CASE_TYPE_LABEL = { commerce: "Commerce", service_request: "Service Request" };
  var CASE_STATUS_LABEL = {
    created: "Pending Agent", agent_assigned: "Agent Assigned", supplier_contacted: "Supplier Contacted",
    pending_supplier: "Awaiting Supplier", pending_payment: "Pending Payment", in_progress: "In Progress",
    resolved: "Resolved", disputed: "Disputed", escalated: "Escalated", cancelled: "Cancelled",
  };
  var CASE_ROLE_LABEL = { member: "Member", agent: "You", supplier: "Supplier", system: "System", council: "Council" };
  var CASE_TERMINAL = { resolved: true, cancelled: true };
  // The manually-selectable next statuses, in the order the brief's own worked chain uses them.
  // Deliberately excludes 'resolved'/'cancelled' (their own dedicated Resolve button / the
  // Member's own flows handle those) and, whenever the Case is 'pending_payment', excludes
  // 'in_progress' too -- that one exact transition is the Member's own "Pay to Escrow" action
  // (it locks THEIR Qoins), not something an Agent should trigger by picking it from a dropdown.
  var SELECTABLE_STATUSES = [
    "agent_assigned", "supplier_contacted", "pending_supplier", "pending_payment",
    "in_progress", "disputed", "escalated",
  ];

  function caseDisplayId(c) {
    return "CASE-" + (c.location_level || "village").slice(0, 3).toUpperCase() + "-" + c.id;
  }

  var agentState = {
    view: "queue",          // 'queue' | 'compass' | 'directory' | 'history'
    cases: [],
    compassTasks: [],
    suppliers: [],
    location: null,         // {location_level, location_id} -- this Agent's own, from /api/agent/me
    selected: null,         // {type: 'case'|'supplier'|'compass', id}
    currentCase: null,      // the full detail of the open Case workspace, if any
    activeCaseId: null,     // the last Case opened this session -- "Message Supplier"'s target
  };

  var VIEW_TITLE = { queue: "Queue", compass: "Compass", directory: "Directory", history: "History" };
  var VIEW_EMPTY = {
    queue: "Nothing in your queue.", compass: "No open Compass tasks.",
    directory: "No Suppliers registered at your location yet.", history: "No closed Cases yet.",
  };

  function isSelected(type, id) {
    return !!(agentState.selected && agentState.selected.type === type && agentState.selected.id === id);
  }

  // ---- The rail ----
  document.querySelectorAll(".ag-rail-btn[data-view]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".ag-rail-btn[data-view]").forEach(function (b) { b.classList.toggle("is-active", b === btn); });
      agentState.view = btn.getAttribute("data-view");
      $("ag-list-title").textContent = VIEW_TITLE[agentState.view];
      if (agentState.view === "queue" || agentState.view === "history") loadCases();
      else if (agentState.view === "compass") loadCompass();
      else loadDirectory();
    });
  });

  // ---- Loading each view's list ----
  function listLoading() { $("ag-list").innerHTML = "<p class=\"ag-empty\">Loading…</p>"; }
  function listError(e) { $("ag-list").innerHTML = ""; $("ag-list").appendChild(el("p", "ag-empty", e.message)); }

  function loadCases() {
    listLoading();
    return api("/api/agent/cases").then(function (r) { agentState.cases = r.cases; renderList(); }).catch(listError);
  }
  function loadCompass() {
    listLoading();
    return api("/api/agent/compass").then(function (r) { agentState.compassTasks = r.tasks; renderList(); }).catch(listError);
  }
  function loadDirectory() {
    listLoading();
    var go = function () {
      var loc = agentState.location;
      api("/api/supplier/list?location_level=" + encodeURIComponent(loc.location_level) + "&location_id=" + encodeURIComponent(loc.location_id))
        .then(function (r) { agentState.suppliers = r.suppliers; renderList(); }).catch(listError);
    };
    if (agentState.location) { go(); return; }
    api("/api/agent/me").then(function (a) {
      agentState.location = { location_level: a.location_level, location_id: a.location_id };
      go();
    }).catch(listError);
  }

  function renderList() {
    var list = $("ag-list");
    list.innerHTML = "";
    var items = agentState.view === "queue" ? agentState.cases.filter(function (c) { return !CASE_TERMINAL[c.status]; })
      : agentState.view === "history" ? agentState.cases.filter(function (c) { return CASE_TERMINAL[c.status]; })
      : agentState.view === "compass" ? agentState.compassTasks
      : agentState.suppliers;
    $("ag-list-count").textContent = items.length ? String(items.length) : "";
    if (!items.length) { list.appendChild(el("p", "ag-empty", VIEW_EMPTY[agentState.view])); return; }
    items.forEach(function (item) {
      if (agentState.view === "queue" || agentState.view === "history") list.appendChild(buildCaseRow(item));
      else if (agentState.view === "compass") list.appendChild(buildCompassRow(item));
      else list.appendChild(buildSupplierRow(item));
    });
  }

  function buildCaseRow(c) {
    var row = el("button", "ag-row" + (isSelected("case", c.id) ? " is-active" : ""));
    row.type = "button";
    row.appendChild(el("div", "ag-row-title", caseDisplayId(c)));
    row.appendChild(el("div", "ag-row-sub", (c.member_name || "Member") + " · " + (CASE_TYPE_LABEL[c.case_type] || c.case_type)));
    row.appendChild(el("span", "ag-row-badge", CASE_STATUS_LABEL[c.status] || c.status));
    row.addEventListener("click", function () { openCase(c.id); });
    return row;
  }
  function buildCompassRow(t) {
    var row = el("button", "ag-row" + (isSelected("compass", t.id) ? " is-active" : ""));
    row.type = "button";
    row.appendChild(el("div", "ag-row-title", t.note));
    row.appendChild(el("div", "ag-row-sub", "Case #" + t.case_id));
    row.appendChild(el("span", "ag-row-badge", t.due_at ? t.due_at : "No due date"));
    row.addEventListener("click", function () { openCompassTask(t); });
    return row;
  }
  function buildSupplierRow(s) {
    var row = el("button", "ag-row" + (isSelected("supplier", s.user_id) ? " is-active" : ""));
    row.type = "button";
    row.appendChild(el("div", "ag-row-title", s.name || ("Supplier #" + s.user_id)));
    row.appendChild(el("div", "ag-row-sub", s.service_category));
    row.appendChild(el("span", "ag-row-badge", "★ " + s.karma.total));
    row.addEventListener("click", function () { openSupplier(s); });
    return row;
  }

  // ---- The workspace ----
  function showWorkspace(kind) {
    $("ag-workspace-empty").hidden = kind != null;
    $("ag-case-workspace").hidden = kind !== "case";
    $("ag-supplier-workspace").hidden = kind !== "supplier";
    $("ag-compass-workspace").hidden = kind !== "compass";
  }

  // ---- Case workspace ----
  function openCase(id) {
    agentState.selected = { type: "case", id: id };
    showWorkspace("case");
    $("ag-add-supplier-panel").hidden = true;
    $("ag-add-compass-form").hidden = true;
    $("ag-case-title").textContent = "Loading…";
    $("ag-case-sub").textContent = "";
    api("/api/agent/cases/" + id).then(function (c) {
      agentState.currentCase = c;
      agentState.activeCaseId = c.id;
      renderCaseHeader(c);
      loadCaseLogs(id);
      loadMemberPanel(c);
      renderList();
    }).catch(function (e) { $("ag-case-title").textContent = "Error"; $("ag-case-sub").textContent = e.message; });
  }

  function renderCaseHeader(c) {
    $("ag-case-title").textContent = caseDisplayId(c) + " — " + (c.member_name || "Member");
    $("ag-case-sub").textContent = (CASE_TYPE_LABEL[c.case_type] || c.case_type) + " · " + (CASE_STATUS_LABEL[c.status] || c.status);
    var sel = $("ag-case-status-select");
    sel.innerHTML = "";
    SELECTABLE_STATUSES.forEach(function (s) {
      if (s === c.status) return;
      if (s === "in_progress" && c.status === "pending_payment") return;
      var opt = document.createElement("option");
      opt.value = s; opt.textContent = CASE_STATUS_LABEL[s] || s;
      sel.appendChild(opt);
    });
    $("ag-case-resolve-btn").disabled = !(c.status === "in_progress" || c.status === "disputed");
  }

  // Both handlers below refresh agentState.cases (loadCases()) whenever the Queue/History list is
  // what's on screen, not just the open Case's own detail -- found live (2026-11-25): without
  // this, a Case's Queue/History row kept showing its OLD status badge after a successful update,
  // since renderList() reads agentState.cases, which openCase()'s own detail fetch never touches.
  $("ag-case-status-apply").addEventListener("click", function () {
    var c = agentState.currentCase;
    var newStatus = $("ag-case-status-select").value;
    if (!c || !newStatus) return;
    api("/api/agent/cases/" + c.id + "/status", { status: newStatus }).then(function () {
      openCase(c.id);
      if (agentState.view === "queue" || agentState.view === "history") loadCases();
    }).catch(function (e) { window.alert(e.message); });
  });

  $("ag-case-resolve-btn").addEventListener("click", function () {
    var c = agentState.currentCase;
    if (!c) return;
    if (!window.confirm("Resolve " + caseDisplayId(c) + "? This releases escrow to the Supplier (commerce) or awards Karma (service request), and cannot be undone.")) return;
    api("/api/agent/cases/" + c.id + "/resolve", {}).then(function () {
      openCase(c.id);
      if (agentState.view === "queue" || agentState.view === "history") loadCases();
    }).catch(function (e) { window.alert(e.message); });
  });

  function loadCaseLogs(id) {
    $("ag-case-logs").innerHTML = "<p class=\"ag-empty\">Loading…</p>";
    api("/api/cases/" + id + "/logs").then(function (r) { renderCaseLogs(r.logs || []); }).catch(function (e) {
      $("ag-case-logs").innerHTML = "";
      $("ag-case-logs").appendChild(el("p", "ag-empty", e.message));
    });
  }

  function renderCaseLogs(logs) {
    var box = $("ag-case-logs");
    box.innerHTML = "";
    if (!logs.length) { box.appendChild(el("p", "ag-empty", "No activity yet.")); return; }
    logs.forEach(function (l) {
      // Every log_type but 'comment' is an automated/internal entry -- rendered as a single
      // centered line, same convention the Member's own Home-tab Case Chat uses (dashboard.js).
      // The Agent (and only the Agent/council -- see case_core.logs_for()) also sees 'internal'
      // visibility entries (e.g. a Compass note); marked (internal) so it's never mistaken for
      // something the Member can also see.
      if (l.log_type !== "comment") {
        var tag = l.visibility === "internal" ? " (internal)" : "";
        box.appendChild(el("div", "ag-system-log", "⚙️ [System] " + (l.message || l.log_type) + tag));
        return;
      }
      var mine = l.author_role === "agent";
      var row = el("div", "ag-message" + (mine ? " ag-message--mine" : ""));
      row.appendChild(el("div", "ag-message-who", CASE_ROLE_LABEL[l.author_role] || l.author_role));
      row.appendChild(el("div", "ag-message-text", l.message));
      row.appendChild(el("div", "ag-message-at", ago(l.created_at)));
      box.appendChild(row);
    });
    box.scrollTop = box.scrollHeight;
  }

  $("ag-case-composer").addEventListener("submit", function (e) {
    e.preventDefault();
    var c = agentState.currentCase;
    var input = $("ag-case-input");
    var text = input.value.trim();
    if (!c || !text) return;
    input.disabled = true;
    // /api/agent/cases/<id>/message, not the Member-facing /api/cases/<id>/message -- see that
    // route's own docstring (app.py) for why this distinction matters.
    api("/api/agent/cases/" + c.id + "/message", { message: text }).then(function () {
      input.value = ""; input.disabled = false;
      loadCaseLogs(c.id);
    }).catch(function (err) { input.disabled = false; window.alert(err.message); });
  });

  function loadMemberPanel(c) {
    $("ag-member-info").textContent = (c.member_name || "Member") + " (member #" + c.member_user_id + ")";
    $("ag-member-karma").textContent = "Loading…";
    api("/api/karma/user/" + c.member_user_id).then(function (r) {
      $("ag-member-karma").textContent = r.score.total + " total (" + r.score.commercial + " commercial, " + r.score.noncommercial + " non-commercial)";
    }).catch(function () { $("ag-member-karma").textContent = "—"; });

    var box = $("ag-member-cases");
    box.innerHTML = "<p class=\"ag-empty\">Loading…</p>";
    api("/api/agent/cases/" + c.id + "/member-cases").then(function (r) {
      box.innerHTML = "";
      if (!r.cases.length) { box.appendChild(el("p", "ag-empty", "No other active Cases at this location.")); return; }
      r.cases.forEach(function (other) {
        var row = el("button", "ag-link-btn");
        row.type = "button";
        row.textContent = caseDisplayId(other) + " · " + (CASE_STATUS_LABEL[other.status] || other.status);
        row.addEventListener("click", function () { openCase(other.id); });
        box.appendChild(row);
      });
    }).catch(function (e) { box.innerHTML = ""; box.appendChild(el("p", "ag-empty", e.message)); });
  }

  // ---- Add Supplier (from a Case's own toolbar) ----
  $("ag-case-add-supplier-btn").addEventListener("click", function () {
    $("ag-add-compass-form").hidden = true;
    $("ag-add-supplier-panel").hidden = !$("ag-add-supplier-panel").hidden;
    if (!$("ag-add-supplier-panel").hidden) searchSuppliersForCase();
  });
  function searchSuppliersForCase() {
    var c = agentState.currentCase;
    if (!c) return;
    var category = $("ag-add-supplier-category").value.trim();
    var url = "/api/supplier/list?location_level=" + encodeURIComponent(c.location_level) + "&location_id=" + encodeURIComponent(c.location_id);
    if (category) url += "&service_category=" + encodeURIComponent(category);
    var box = $("ag-add-supplier-results");
    box.innerHTML = "<p class=\"ag-empty\">Searching…</p>";
    api(url).then(function (r) {
      box.innerHTML = "";
      if (!r.suppliers.length) { box.appendChild(el("p", "ag-empty", "No Suppliers found for this location/category.")); return; }
      r.suppliers.forEach(function (s) {
        var row = el("div", "ag-inline-result-row");
        row.appendChild(el("span", "", (s.name || "Supplier") + " — " + s.service_category + " (★" + s.karma.total + ")"));
        var btn = el("button", "qm-btn qm-btn-ghost", "Select"); btn.type = "button";
        btn.addEventListener("click", function () {
          api("/api/agent/cases/" + c.id + "/add-supplier", { supplier_user_id: s.user_id }).then(function () {
            $("ag-add-supplier-panel").hidden = true;
            openCase(c.id);
          }).catch(function (e) { window.alert(e.message); });
        });
        row.appendChild(btn);
        box.appendChild(row);
      });
    }).catch(function (e) { box.innerHTML = ""; box.appendChild(el("p", "ag-empty", e.message)); });
  }
  $("ag-add-supplier-search").addEventListener("click", searchSuppliersForCase);

  // ---- Add Compass Task (from a Case's own toolbar) ----
  $("ag-case-add-compass-btn").addEventListener("click", function () {
    $("ag-add-supplier-panel").hidden = true;
    $("ag-add-compass-form").hidden = !$("ag-add-compass-form").hidden;
  });
  $("ag-add-compass-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var c = agentState.currentCase;
    var note = $("ag-add-compass-note").value.trim();
    var due = $("ag-add-compass-due").value || null;
    if (!c || !note) return;
    api("/api/agent/cases/" + c.id + "/compass", { note: note, due_at: due }).then(function () {
      $("ag-add-compass-note").value = ""; $("ag-add-compass-due").value = "";
      $("ag-add-compass-form").hidden = true;
      loadCaseLogs(c.id);
    }).catch(function (e) { window.alert(e.message); });
  });

  // ---- Supplier workspace ----
  function openSupplier(s) {
    agentState.selected = { type: "supplier", id: s.user_id };
    showWorkspace("supplier");
    $("ag-supplier-name").textContent = s.name || ("Supplier #" + s.user_id);
    $("ag-supplier-sub").textContent = s.service_category + " · ★ " + s.karma.total + " Karma";
    $("ag-supplier-description").textContent = s.description || "No description provided.";
    $("ag-supplier-pricelist").textContent = s.price_list ? ("Price list: " + s.price_list) : "No price list provided.";
    renderList();
  }

  // "Message Supplier" (brief's own wording): there's no separate Supplier-chat surface -- a
  // Supplier is "messaged" by being added to a Case's own Case Chat (Decision 4, no telephony,
  // Case Chat only), same action as "Add Supplier" above, just entered from the Directory side.
  // Needs a target Case -- uses the last one opened this session; with none open yet, there's
  // nothing to attach the Supplier to, so this asks the Agent to open one first rather than
  // guessing which Case they meant.
  $("ag-supplier-message-btn").addEventListener("click", function () {
    var sel = agentState.selected;
    if (!sel || sel.type !== "supplier") return;
    if (!agentState.activeCaseId) {
      window.alert("Open a Case from the Queue first, then come back here to add this Supplier to it.");
      return;
    }
    if (!window.confirm("Add this Supplier to your currently open Case and start the conversation there?")) return;
    api("/api/agent/cases/" + agentState.activeCaseId + "/add-supplier", { supplier_user_id: sel.id }).then(function () {
      document.querySelector('.ag-rail-btn[data-view="queue"]').click();
      openCase(agentState.activeCaseId);
    }).catch(function (e) { window.alert(e.message); });
  });

  // ---- Compass task workspace ----
  function openCompassTask(t) {
    agentState.selected = { type: "compass", id: t.id };
    showWorkspace("compass");
    var link = $("ag-compass-case-link");
    link.textContent = "Go to Case #" + t.case_id;
    link.onclick = function () {
      document.querySelector('.ag-rail-btn[data-view="queue"]').click();
      openCase(t.case_id);
    };
    $("ag-compass-note").textContent = t.note;
    $("ag-compass-due").textContent = t.due_at ? ("Due: " + t.due_at) : "No due date set.";
    var doneBtn = $("ag-compass-done-btn");
    doneBtn.disabled = t.status === "done";
    doneBtn.textContent = t.status === "done" ? "✓ Done" : "✓ Mark as Done";
    renderList();
  }
  $("ag-compass-done-btn").addEventListener("click", function () {
    var sel = agentState.selected;
    if (!sel || sel.type !== "compass") return;
    api("/api/agent/compass/" + sel.id + "/done", {}).then(function () {
      showWorkspace(null);
      agentState.selected = null;
      loadCompass();
    }).catch(function (e) { window.alert(e.message); });
  });

  loadCases();
})();
