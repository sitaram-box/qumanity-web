/**
 * family.js — Family Timeline activation: the 6-step Activation Wizard (Parents, Your Status,
 * Spouse, Children, Discover or Create, Review) that gates the Personal → Family Tree panel until
 * a user activates. The wizard asks its own relationship-status question directly (Step 2) rather
 * than trusting users.relationship_status, which may be stale or never set if the user reaches
 * this wizard before ever visiting their profile page (2026-10-20 restructure -- the previous
 * version's isMarried() read that field and silently skipped the Spouse/Children steps if it
 * happened to be unset). Drives family_core.py's activate_timeline()/marry_timeline() (two
 * separate calls -- see Step 6) and search_suggestions() (Step 5).
 */
(function () {
  "use strict";
  var panel = document.getElementById("pt-family-panel");
  if (!panel) return;

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function api(url, body) {
    var opt = body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }

  var gateEl = document.getElementById("family-activation-gate");
  var summaryEl = document.getElementById("family-activated-summary");
  var groupsListEl = document.getElementById("family-groups-list");
  var wizardEl = document.getElementById("family-wizard");

  var STEP_ORDER = ["parents", "status", "spouse", "children", "discover", "review"];
  var stepEls = Array.prototype.slice.call(document.querySelectorAll("#fw-steps .qm-step"));
  var screenEls = {
    parents: document.getElementById("fw-screen-parents"),
    status: document.getElementById("fw-screen-status"),
    spouse: document.getElementById("fw-screen-spouse"),
    children: document.getElementById("fw-screen-children"),
    discover: document.getElementById("fw-screen-discover"),
    review: document.getElementById("fw-screen-review"),
  };

  // Single/married/separated/divorced/widowed -> family_core.py's own
  // _RELATIONSHIP_TO_PROFILE_STATUS keys, exactly. marriage_status is a SEPARATE mapping (the
  // richer, family_groups-only enum) -- the same wizard answer feeds two different destination
  // columns with two different vocabularies, never one value reused for both.
  var MARRIAGE_STATUS_MAP = { married: "active", separated: "separated", divorced: "dissolved", widowed: "active" };
  var SPOUSE_HEADINGS = { married: "💍 Spouse", separated: "🤝 Former Spouse", divorced: "📄 Former Spouse", widowed: "🕊️ Late Spouse" };
  var STATUS_LABELS = { single: "Single / Never Married", married: "Married", separated: "Separated", divorced: "Divorced", widowed: "Widowed" };
  // Same 3 values registration offers (templates/register.html's male/female/both) -- the label
  // here is just a different, relationship-appropriate framing of the identical underlying value,
  // never a 4th option of its own. Keeping the value set consistent everywhere matters in practice:
  // a claimed child's gender resolves live from their own real users.gender once claimed (see
  // family_core.py's _person_summary()), so the placeholder's gender must speak the same vocabulary.
  var GENDER_LABELS = { male: "Son", female: "Daughter", both: "Third Gender" };

  // state.slots is the single source of truth by Step 5 -- each entry already carries the exact
  // shape activate_timeline()/marry_timeline() expect ({name, action, gender?, group_id?,
  // matched_node_id?, user_id?, is_deceased?}), so Step 6's submit is just picking slots out by
  // key, no translation.
  var state = {
    status: null, // last GET /api/family/status response
    father: { name: "", is_deceased: false },
    mother: { name: "", is_deceased: false },
    grandparentsKnown: null, // true | false | null (not yet answered)
    fatherFather: { name: "", is_deceased: false },
    fatherMother: { name: "", is_deceased: false },
    motherFather: { name: "", is_deceased: false },
    motherMother: { name: "", is_deceased: false },
    relationship: null, // single | married | separated | divorced | widowed -- the wizard's OWN answer
    hasChildren: null, // true | false | null (not yet answered)
    spouse: null, // null if single; else {name, viaExactId, resolvedUserId, resolvedAccountId, is_deceased?}
    spouseParentsKnown: null, // true | false | null (not yet answered)
    spouseFather: { name: "", is_deceased: false },
    spouseMother: { name: "", is_deceased: false },
    children: [], // [{name, gender}]
    slots: [],
  };

  function goToFwStep(name) {
    var idx = STEP_ORDER.indexOf(name);
    STEP_ORDER.forEach(function (s) { screenEls[s].classList.toggle("is-active", s === name); });
    stepEls.forEach(function (stepEl) {
      var s = stepEl.getAttribute("data-fstep");
      var i = STEP_ORDER.indexOf(s);
      stepEl.classList.toggle("is-active", s === name);
      stepEl.classList.toggle("is-done", i < idx);
    });
  }

  // ---- Panel refresh: gate vs activated-summary. Never yanks the wizard away mid-flow. ----
  function refreshFamilyPanel() {
    api("/api/family/status").then(function (status) {
      state.status = status;
      if (!wizardEl.hidden) return;
      gateEl.hidden = status.activated;
      summaryEl.hidden = !status.activated;
      if (status.activated) {
        renderGroupsList(status.groups);
        // 2026-10-27: jump straight into the D3 tree for the obvious unit, instead of making
        // every visit start on this flat "pick a group" screen -- the viewer's own founded unit
        // if they have exactly one, or their one-and-only unit if there's nothing else to choose
        // from. This screen stays reachable (its own "← Back to groups" button, inside the tree
        // view) for genuine ambiguity -- e.g. remarried, with more than one active founded unit.
        var founded = status.groups.filter(function (g) { return g.is_founder; });
        var primary = founded.length === 1 ? founded[0] : (status.groups.length === 1 ? status.groups[0] : null);
        if (primary && window.QMFamilyTree) {
          summaryEl.hidden = true;
          window.QMFamilyTree.showTree(primary.id);
        }
      }
    }).catch(function () {});
  }

  // "My Family" (a unit the viewer themself founded) always sorts above "Joined Family" (a unit
  // they were approved into, e.g. their parents') -- is_founder/is_admin come straight from
  // family_core.my_family_groups(), which also excludes dormant units (both founders deceased)
  // entirely from this list, though they still render, faded, in the D3 tree. See that function's
  // own docstring for why is_founder and is_admin are two independent signals, not one.
  function renderGroupsList(groups) {
    groupsListEl.innerHTML = "";
    if (!groups.length) { groupsListEl.appendChild(el("li", "pt-empty-row", "No groups yet.")); return; }
    var sorted = groups.slice().sort(function (a, b) { return (b.is_founder ? 1 : 0) - (a.is_founder ? 1 : 0); });
    sorted.forEach(function (g) {
      var li = el("li", "pt-group-row");
      var btn = el("button", "qm-member-row ft-group-btn" + (g.is_founder ? " is-my-family" : " is-joined-family"));
      btn.type = "button";
      if (g.is_founder) btn.appendChild(el("span", "ft-group-dot"));
      btn.appendChild(el("span", "ft-group-name", g.name));
      var badgeText = g.is_founder ? "My Family" : (g.role === "admin" ? "Joined Family · Admin" : "Joined Family · Member");
      btn.appendChild(el("span", "ft-group-badge", badgeText));
      btn.appendChild(el("span", "ft-group-meta", g.members + " member" + (g.members === 1 ? "" : "s") + "  🌳"));
      btn.addEventListener("click", function () {
        if (window.QMFamilyTree) window.QMFamilyTree.showTree(g.id);
      });
      li.appendChild(btn);
      groupsListEl.appendChild(li);
    });
  }

  // ---- Find a relative: name + location search for already-activated members, distinct from the
  // Activation wizard's own father/mother/spouse/child slot-matching (same /api/family/suggest
  // route, a third result "type": "real_user" family_core.search_suggestions() now also returns). ----
  var familySearchInput = document.getElementById("family-search-input");
  var familySearchBtn = document.getElementById("family-search-btn");
  var familySearchResult = document.getElementById("family-search-result");
  if (familySearchBtn) {
    familySearchBtn.addEventListener("click", function () {
      var q = familySearchInput.value.trim();
      if (q.length < 2) return;
      familySearchResult.innerHTML = "";
      familySearchResult.appendChild(el("p", "qm-dash-empty", "Searching…"));
      api("/api/family/suggest?name=" + encodeURIComponent(q)).then(function (d) {
        renderFamilySearchResults((d.results || []).filter(function (r) { return r.type === "real_user"; }));
      }).catch(function () {
        familySearchResult.innerHTML = "";
        familySearchResult.appendChild(el("p", "qm-dash-empty", "Couldn't search right now."));
      });
    });
    familySearchInput.addEventListener("keydown", function (e) { if (e.key === "Enter") familySearchBtn.click(); });
  }

  // A 40px avatar for a suggestion row -- the uploaded profile picture if there is one, else a
  // colored circle with the name's first letter (same fallback idiom as the Private account's
  // own .pv-avatar).
  function suggestionAvatar(name, pictureUrl) {
    var div = el("div", "fw-suggestion-avatar");
    if (pictureUrl) { div.style.backgroundImage = "url('" + pictureUrl + "')"; }
    else { div.textContent = (name || "?").charAt(0).toUpperCase(); }
    return div;
  }
  function genderLabel(gender) {
    return gender === "male" ? "Male" : gender === "female" ? "Female" : gender === "both" ? "Third Gender" : "";
  }

  function renderFamilySearchResults(rows) {
    familySearchResult.innerHTML = "";
    if (!rows.length) { familySearchResult.appendChild(el("p", "qm-dash-empty", "No matches nearby.")); return; }
    rows.forEach(function (r) {
      var row = el("div", "fw-suggestion-row");
      var top = el("div", "fw-suggestion-top");
      top.appendChild(suggestionAvatar(r.name, r.profile_picture_url));
      var textWrap = el("div", "fw-suggestion-text");
      var detail = r.name + (r.gender ? " · " + genderLabel(r.gender) : "") +
        (r.location ? " — " + r.location : "") + (r.mutual_group_name ? " · shares " + r.mutual_group_name : "");
      textWrap.appendChild(el("p", "", detail));
      top.appendChild(textWrap);
      row.appendChild(top);
      var joinBtn = el("button", "qm-btn qm-btn-primary", "Request to Join " + r.group_name);
      joinBtn.type = "button";
      joinBtn.addEventListener("click", function () {
        joinBtn.disabled = true; joinBtn.textContent = "Requesting…";
        api("/api/family-groups/" + r.group_id + "/join-request", {}).then(function () {
          joinBtn.textContent = "✓ Requested";
        }).catch(function (e) {
          joinBtn.disabled = false; joinBtn.textContent = "Request to Join " + r.group_name;
          alert(e.message);
        });
      });
      row.appendChild(joinBtn);
      familySearchResult.appendChild(row);
    });
  }

  // Piggyback on the Personal tab's existing top-tab switcher (social.js owns show/hide) --
  // just refresh our own gate/summary state whenever the Family Tree tab is opened.
  var topTabs = document.getElementById("personal-top-tabs");
  if (topTabs) {
    topTabs.addEventListener("click", function (e) {
      if (e.target.closest('[data-ptab="family"]')) refreshFamilyPanel();
    });
  }

  // ---- Start / reset the wizard ----
  document.getElementById("family-activate-start-btn").addEventListener("click", function () {
    state.father = { name: "", is_deceased: false };
    state.mother = { name: "", is_deceased: false };
    state.grandparentsKnown = null;
    state.fatherFather = { name: "", is_deceased: false };
    state.fatherMother = { name: "", is_deceased: false };
    state.motherFather = { name: "", is_deceased: false };
    state.motherMother = { name: "", is_deceased: false };
    state.relationship = null;
    state.hasChildren = null;
    state.spouse = null;
    state.spouseParentsKnown = null;
    state.spouseFather = { name: "", is_deceased: false };
    state.spouseMother = { name: "", is_deceased: false };
    state.children = [];
    state.slots = [];

    document.getElementById("fw-father-name").value = "";
    document.getElementById("fw-father-deceased").checked = false;
    document.getElementById("fw-mother-name").value = "";
    document.getElementById("fw-mother-deceased").checked = false;

    Array.prototype.forEach.call(document.querySelectorAll("#fw-grandparents-group .qm-gender-btn"), function (b) { b.classList.remove("is-active"); });
    document.getElementById("fw-grandparents-wrap").hidden = true;
    ["ff", "fm", "mf", "mm"].forEach(function (p) {
      document.getElementById("fw-" + p + "-name").value = "";
      document.getElementById("fw-" + p + "-deceased").checked = false;
    });

    document.getElementById("fw-status-error").hidden = true;
    Array.prototype.forEach.call(document.querySelectorAll("#fw-status-group .qm-gender-btn"), function (b) { b.classList.remove("is-active"); });
    document.getElementById("fw-spouse-heading").textContent = "💍 Spouse";

    document.getElementById("fw-spouse-name").value = "";
    document.getElementById("fw-spouse-onapp").checked = false;
    document.getElementById("fw-spouse-search-row").hidden = true;
    document.getElementById("fw-spouse-search-input").value = "";
    document.getElementById("fw-spouse-search-result").innerHTML = "";
    document.getElementById("fw-marital-error").hidden = true;
    Array.prototype.forEach.call(document.querySelectorAll("#fw-spouse-grandparents-group .qm-gender-btn"), function (b) { b.classList.remove("is-active"); });
    document.getElementById("fw-spouse-parents-wrap").hidden = true;
    ["sf", "sm"].forEach(function (p) {
      document.getElementById("fw-" + p + "-name").value = "";
      document.getElementById("fw-" + p + "-deceased").checked = false;
    });

    document.getElementById("fw-children-error").hidden = true;
    Array.prototype.forEach.call(document.querySelectorAll("#fw-has-children-group .qm-gender-btn"), function (b) { b.classList.remove("is-active"); });
    document.getElementById("fw-children-rows").innerHTML = "";
    document.getElementById("fw-children-rows-wrap").hidden = true;
    childRowCount = 0;

    // Continuity with whatever the profile page already recorded (sons_count/daughters_count) --
    // pre-fills that many rows (by aggregate count only, not per-child identity) and auto-answers
    // "Yes" to the children question, rather than silently dropping this existing signal.
    var sons = (state.status && state.status.sons_count) || 0;
    var daughters = (state.status && state.status.daughters_count) || 0;
    for (var i = 0; i < sons; i++) addChildRow("male");
    for (var i = 0; i < daughters; i++) addChildRow("female");
    if (sons + daughters > 0) {
      state.hasChildren = true;
      document.getElementById("fw-children-rows-wrap").hidden = false;
      document.querySelector('#fw-has-children-group [data-haschildren="yes"]').classList.add("is-active");
    }

    gateEl.hidden = true;
    wizardEl.hidden = false;
    goToFwStep("parents");
  });

  // ---- Step 1: Parents (+ optional Grandparents) ----
  var grandparentsButtons = Array.prototype.slice.call(document.querySelectorAll("#fw-grandparents-group .qm-gender-btn"));
  grandparentsButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var yes = btn.getAttribute("data-grandparents") === "yes";
      state.grandparentsKnown = yes;
      grandparentsButtons.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
      document.getElementById("fw-grandparents-wrap").hidden = !yes;
    });
  });

  function readGrandparentField(prefix) {
    var name = document.getElementById("fw-" + prefix + "-name").value.trim();
    if (!name) return { name: "", is_deceased: false };
    return { name: name, is_deceased: document.getElementById("fw-" + prefix + "-deceased").checked };
  }

  document.getElementById("fw-parents-next-btn").addEventListener("click", function () {
    var fatherName = document.getElementById("fw-father-name").value.trim();
    var motherName = document.getElementById("fw-mother-name").value.trim();
    var errEl = document.getElementById("fw-parents-error");
    if (!fatherName || !motherName) {
      errEl.textContent = "Both parents' names are required.";
      errEl.hidden = false;
      return;
    }
    errEl.hidden = true;
    state.father = { name: fatherName, is_deceased: document.getElementById("fw-father-deceased").checked };
    state.mother = { name: motherName, is_deceased: document.getElementById("fw-mother-deceased").checked };
    if (state.grandparentsKnown) {
      state.fatherFather = readGrandparentField("ff");
      state.fatherMother = readGrandparentField("fm");
      state.motherFather = readGrandparentField("mf");
      state.motherMother = readGrandparentField("mm");
    } else {
      state.fatherFather = state.fatherMother = state.motherFather = state.motherMother = { name: "", is_deceased: false };
    }
    goToFwStep("status");
  });

  // ---- Step 2: Your Status (the branching point) ----
  var statusButtons = Array.prototype.slice.call(document.querySelectorAll("#fw-status-group .qm-gender-btn"));
  statusButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      state.relationship = btn.getAttribute("data-relationship");
      statusButtons.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
    });
  });

  document.getElementById("fw-status-back-btn").addEventListener("click", function () { goToFwStep("parents"); });

  document.getElementById("fw-status-next-btn").addEventListener("click", function () {
    var errEl = document.getElementById("fw-status-error");
    if (!state.relationship) {
      errEl.textContent = "Please choose your relationship status.";
      errEl.hidden = false;
      return;
    }
    errEl.hidden = true;
    if (state.relationship === "single") {
      // Single users do not have a spouse or children in this form's context -- both steps are
      // skipped entirely, not shown-then-left-empty.
      state.spouse = null;
      state.children = [];
      buildSlotsAndEnterDiscover();
      return;
    }
    document.getElementById("fw-spouse-heading").textContent = SPOUSE_HEADINGS[state.relationship];
    goToFwStep("spouse");
  });

  // ---- Step 3: Spouse (only reached for married/separated/divorced/widowed) ----
  document.getElementById("fw-marital-back-btn").addEventListener("click", function () { goToFwStep("status"); });

  document.getElementById("fw-spouse-onapp").addEventListener("change", function (e) {
    document.getElementById("fw-spouse-search-row").hidden = !e.target.checked;
  });

  document.getElementById("fw-spouse-search-btn").addEventListener("click", function () {
    var q = document.getElementById("fw-spouse-search-input").value.trim();
    var resultEl = document.getElementById("fw-spouse-search-result");
    if (!q) return;
    resultEl.innerHTML = "";
    resultEl.appendChild(el("p", "qm-dash-empty", "Searching…"));
    api("/api/people/search?q=" + encodeURIComponent(q)).then(function (person) {
      state.spouse = { name: person.name, viaExactId: true, resolvedUserId: person.user_id, resolvedAccountId: person.account_id };
      resultEl.innerHTML = "";
      // Never show an ID (2026-10-26): a hidden member's "name" here IS their Account ID.
      var who = person.hidden ? "Private until you are family" : person.name;
      var details = [genderLabel(person.gender), person.age_group, person.location].filter(Boolean).join(" · ");
      resultEl.appendChild(el("p", "qm-dash-empty", "✅ Found: " + who + (details ? " — " + details : "")));
    }).catch(function (e) {
      resultEl.innerHTML = "";
      resultEl.appendChild(el("p", "qm-summary-error", e.message));
    });
  });
  var spouseGrandparentsButtons = Array.prototype.slice.call(document.querySelectorAll("#fw-spouse-grandparents-group .qm-gender-btn"));
  spouseGrandparentsButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var yes = btn.getAttribute("data-spouseparents") === "yes";
      state.spouseParentsKnown = yes;
      spouseGrandparentsButtons.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
      document.getElementById("fw-spouse-parents-wrap").hidden = !yes;
    });
  });

  function readSpouseParentField(prefix) {
    var name = document.getElementById("fw-" + prefix + "-name").value.trim();
    if (!name) return { name: "", is_deceased: false };
    return { name: name, is_deceased: document.getElementById("fw-" + prefix + "-deceased").checked };
  }

  document.getElementById("fw-marital-next-btn").addEventListener("click", function () {
    var errEl = document.getElementById("fw-marital-error");
    var name = document.getElementById("fw-spouse-name").value.trim();
    var onApp = document.getElementById("fw-spouse-onapp").checked;
    if (!name) { errEl.textContent = "Spouse's name is required."; errEl.hidden = false; return; }
    if (onApp && !(state.spouse && state.spouse.viaExactId)) {
      errEl.textContent = "Find your spouse's exact Public ID above, or uncheck the box.";
      errEl.hidden = false;
      return;
    }
    errEl.hidden = true;
    if (!onApp) state.spouse = { name: name, viaExactId: false };
    else state.spouse.name = name; // keep resolvedUserId/resolvedAccountId from the search
    // Widowed marks the spouse deceased automatically -- no separate checkbox needed. Only takes
    // effect for a freshly-created node (viaExactId resolves to an existing node that this wizard
    // doesn't mutate the is_deceased flag of; a known, narrow limitation -- see mark_deceased()
    // for that separately, if it's ever needed for an already-claimed spouse).
    if (state.relationship === "widowed" && !onApp) state.spouse.is_deceased = true;
    if (state.spouseParentsKnown) {
      state.spouseFather = readSpouseParentField("sf");
      state.spouseMother = readSpouseParentField("sm");
    } else {
      state.spouseFather = state.spouseMother = { name: "", is_deceased: false };
    }
    goToFwStep("children");
  });

  // ---- Step 4: Children (conditional: skipped entirely for Single) ----
  var childRowCount = 0;
  function addChildRow(presetGender) {
    childRowCount++;
    var idx = childRowCount;
    var row = el("div", "fw-child-row");
    row.dataset.gender = presetGender || "";
    var input = document.createElement("input");
    input.type = "text"; input.maxLength = 80; input.placeholder = "Child " + idx + " name";
    input.className = "fw-child-input";

    var genderGroup = el("div", "qm-gender-group fw-child-gender-group");
    [
      { gender: "male", icon: "👦", label: "Son" },
      { gender: "female", icon: "👧", label: "Daughter" },
      { gender: "both", icon: "⚧️", label: "Third Gender" },
    ].forEach(function (g) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "qm-gender-btn fw-child-gender-btn";
      btn.setAttribute("data-gender", g.gender);
      btn.innerHTML = g.icon + "<span>" + g.label + "</span>";
      if (g.gender === presetGender) btn.classList.add("is-active");
      btn.addEventListener("click", function () {
        row.dataset.gender = g.gender;
        Array.prototype.forEach.call(genderGroup.children, function (b) { b.classList.toggle("is-active", b === btn); });
      });
      genderGroup.appendChild(btn);
    });

    var removeBtn = el("button", "qm-btn qm-btn-ghost fw-child-remove", "✕");
    removeBtn.type = "button";
    removeBtn.setAttribute("aria-label", "Remove this child");
    removeBtn.addEventListener("click", function () { row.remove(); });

    row.appendChild(input);
    row.appendChild(genderGroup);
    row.appendChild(removeBtn);
    document.getElementById("fw-children-rows").appendChild(row);
  }
  document.getElementById("fw-add-child-btn").addEventListener("click", function () { addChildRow(); });

  var hasChildrenButtons = Array.prototype.slice.call(document.querySelectorAll("#fw-has-children-group .qm-gender-btn"));
  hasChildrenButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var yes = btn.getAttribute("data-haschildren") === "yes";
      state.hasChildren = yes;
      hasChildrenButtons.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
      document.getElementById("fw-children-rows-wrap").hidden = !yes;
      if (yes && !document.querySelector("#fw-children-rows .fw-child-row")) addChildRow();
    });
  });

  document.getElementById("fw-children-back-btn").addEventListener("click", function () { goToFwStep("spouse"); });

  document.getElementById("fw-children-next-btn").addEventListener("click", function () {
    var errEl = document.getElementById("fw-children-error");
    errEl.hidden = true;
    if (state.hasChildren === null) {
      errEl.textContent = "Please choose Yes or No.";
      errEl.hidden = false;
      return;
    }
    if (state.hasChildren === false) {
      state.children = [];
      buildSlotsAndEnterDiscover();
      return;
    }
    var rows = Array.prototype.slice.call(document.querySelectorAll("#fw-children-rows .fw-child-row"));
    var children = [];
    for (var i = 0; i < rows.length; i++) {
      var name = rows[i].querySelector(".fw-child-input").value.trim();
      if (!name) continue;
      var gender = rows[i].dataset.gender;
      if (!gender) {
        errEl.textContent = "Please choose Son, Daughter or Child for " + name + ".";
        errEl.hidden = false;
        return;
      }
      children.push({ name: name, gender: gender });
    }
    if (!children.length) {
      errEl.textContent = "Add at least one child, or go back and choose No.";
      errEl.hidden = false;
      return;
    }
    state.children = children;
    buildSlotsAndEnterDiscover();
  });

  // ---- Step 5: Discover or Create ----
  function buildSlotsAndEnterDiscover() {
    state.slots = [
      { key: "father", label: "Father", name: state.father.name, is_deceased: state.father.is_deceased, action: "create" },
      { key: "mother", label: "Mother", name: state.mother.name, is_deceased: state.mother.is_deceased, action: "create" },
    ];
    // Grandparents (and the spouse's parents, below) are always "create" -- not run through the
    // Discover step's existing-group matching, a deliberate scoped simplification -- but still
    // shown in Discover/Review for transparency before Activate, reusing the same slot pipeline.
    [
      ["fatherFather", "father_father", "Father's Father"], ["fatherMother", "father_mother", "Father's Mother"],
      ["motherFather", "mother_father", "Mother's Father"], ["motherMother", "mother_mother", "Mother's Mother"],
    ].forEach(function (g) {
      var v = state[g[0]];
      if (v && v.name) state.slots.push({ key: g[1], label: g[2], name: v.name, is_deceased: v.is_deceased, action: "create", skipDiscover: true });
    });
    if (state.spouse) {
      if (state.spouse.viaExactId) {
        state.slots.push({ key: "spouse", label: "Spouse", name: state.spouse.name, action: "notify", user_id: state.spouse.resolvedUserId, resolved: true });
      } else {
        state.slots.push({ key: "spouse", label: "Spouse", name: state.spouse.name, is_deceased: !!state.spouse.is_deceased, action: "create" });
      }
    }
    [["spouseFather", "spouse_father", "Spouse's Father"], ["spouseMother", "spouse_mother", "Spouse's Mother"]].forEach(function (g) {
      var v = state[g[0]];
      if (v && v.name) state.slots.push({ key: g[1], label: g[2], name: v.name, is_deceased: v.is_deceased, action: "create", skipDiscover: true });
    });
    state.children.forEach(function (c, i) {
      state.slots.push({ key: "child_" + (i + 1), label: "Child " + (i + 1), name: c.name, gender: c.gender, action: "create" });
    });
    goToFwStep("discover");
    renderDiscoverList();
  }

  function markSlotResolved(card, text) {
    var body = card.querySelector(".fw-discover-body");
    body.innerHTML = "";
    body.appendChild(el("p", "qm-dash-empty", "✓ " + text));
  }

  function renderDiscoverList() {
    var listEl = document.getElementById("fw-discover-list");
    listEl.innerHTML = "";
    state.slots.forEach(function (slot, i) {
      var card = el("div", "qm-private-col fw-discover-card");
      card.appendChild(el("h3", "qm-form-section-title", slot.label + ": " + slot.name));
      var body = el("div", "fw-discover-body");
      card.appendChild(body);
      listEl.appendChild(card);

      if (slot.resolved) {
        markSlotResolved(card, "Linked to an existing Qumanity member — we'll notify them.");
        return;
      }
      if (slot.skipDiscover) {
        markSlotResolved(card, "Will create a new profile for " + slot.name + ".");
        return;
      }
      body.appendChild(el("p", "qm-dash-empty", "Checking…"));
      api("/api/family/suggest?name=" + encodeURIComponent(slot.name)).then(function (d) {
        renderSlotSuggestions(card, body, slot, i, d.results);
      }).catch(function () {
        body.innerHTML = "";
        body.appendChild(el("p", "qm-dash-empty", "Couldn't check — will create a new profile."));
      });
    });
  }

  function renderSlotSuggestions(card, body, slot, slotIndex, results) {
    body.innerHTML = "";
    var groupMatches = results.filter(function (r) { return r.type === "group"; });
    var userMatches = results.filter(function (r) { return r.type === "unactivated_user"; });

    if (!groupMatches.length && !userMatches.length) {
      body.appendChild(el("p", "qm-dash-empty", "No existing match — we'll create a new profile."));
      return;
    }

    // A marriage is a declared mutual fact (2026-10-26 ruling) -- joining a SPOUSE's unit is
    // instant, no approval needed, unlike every other "join" here (a parent/grandparent match
    // still queues a request the unit's creator must accept). Same button, same slot pipeline,
    // different copy so the user isn't told to expect a wait that will never happen.
    var isSpouseSlot = slot.key === "spouse";
    groupMatches.forEach(function (m) {
      var row = el("div", "fw-suggestion-row");
      row.appendChild(el("p", "", "We found " + m.group_name + " (" + m.member_count +
        " member" + (m.member_count === 1 ? "" : "s") + ") — matched via " + m.matched_name + "."));
      var joinBtn = el("button", "qm-btn qm-btn-primary", isSpouseSlot ? "Join Instantly" : "Request to Join");
      joinBtn.type = "button";
      joinBtn.addEventListener("click", function () {
        state.slots[slotIndex].action = "join";
        state.slots[slotIndex].group_id = m.group_id;
        state.slots[slotIndex].matched_node_id = m.matched_node_id;
        markSlotResolved(card, isSpouseSlot
          ? "You'll join " + m.group_name + " immediately as their spouse — no approval needed. They'll be notified."
          : "Will request to join " + m.group_name + ".");
      });
      row.appendChild(joinBtn);
      body.appendChild(row);
    });

    userMatches.forEach(function (m) {
      var row = el("div", "fw-suggestion-row");
      var top = el("div", "fw-suggestion-top");
      top.appendChild(suggestionAvatar(m.name, m.profile_picture_url));
      var textWrap = el("div", "fw-suggestion-text");
      textWrap.appendChild(el("p", "", m.name + (m.gender ? " · " + genderLabel(m.gender) : "") +
        " is already on Qumanity but hasn't activated their Family Timeline."));
      top.appendChild(textWrap);
      row.appendChild(top);
      var notifyBtn = el("button", "qm-btn qm-btn-ghost", "Notify Them");
      notifyBtn.type = "button";
      notifyBtn.addEventListener("click", function () {
        state.slots[slotIndex].action = "notify";
        state.slots[slotIndex].user_id = m.user_id;
        markSlotResolved(card, "Will notify " + m.name + " to activate.");
      });
      row.appendChild(notifyBtn);
      body.appendChild(row);
    });

    var createBtn = el("button", "qm-btn qm-btn-ghost", "Not them — create new instead");
    createBtn.type = "button";
    createBtn.addEventListener("click", function () {
      var s = state.slots[slotIndex];
      s.action = "create"; delete s.group_id; delete s.matched_node_id; delete s.user_id;
      markSlotResolved(card, "Will create a new profile for " + slot.name + ".");
    });
    body.appendChild(createBtn);
  }

  document.getElementById("fw-discover-back-btn").addEventListener("click", function () {
    goToFwStep(state.relationship === "single" ? "status" : "children");
  });
  document.getElementById("fw-discover-next-btn").addEventListener("click", function () {
    goToFwStep("review");
    renderReview();
  });

  // ---- Step 6: Review ----
  function slotPayload(key) {
    var s = state.slots.filter(function (x) { return x.key === key; })[0];
    if (!s) return null;
    var out = { name: s.name, action: s.action };
    if (s.is_deceased) out.is_deceased = true;
    if (s.gender) out.gender = s.gender;
    if (s.group_id) out.group_id = s.group_id;
    if (s.matched_node_id) out.matched_node_id = s.matched_node_id;
    if (s.user_id) out.user_id = s.user_id;
    return out;
  }

  function actionLabel(action, slotKey) {
    if (action === "join") return slotKey === "spouse" ? "Join instantly — no approval needed" : "Request to join an existing group";
    return action === "notify" ? "Notify an existing member" : "Create a new profile";
  }

  function renderReview() {
    var listEl = document.getElementById("fw-review-list");
    listEl.innerHTML = "";

    var statusRow = document.createElement("div");
    statusRow.appendChild(el("dt", "", "Your Status"));
    statusRow.appendChild(el("dd", "", STATUS_LABELS[state.relationship] || state.relationship));
    listEl.appendChild(statusRow);

    state.slots.forEach(function (slot) {
      var row = document.createElement("div");
      row.appendChild(el("dt", "", slot.label));
      var detail = slot.name
        + (slot.gender ? " (" + GENDER_LABELS[slot.gender] + ")" : "")
        + (slot.is_deceased ? " (deceased)" : "")
        + " — " + actionLabel(slot.action, slot.key);
      row.appendChild(el("dd", "", detail));
      listEl.appendChild(row);
    });
    document.getElementById("fw-review-error").hidden = true;
    document.getElementById("fw-review-partial-note").hidden = true;
  }

  document.getElementById("fw-review-back-btn").addEventListener("click", function () { goToFwStep("discover"); });

  document.getElementById("fw-review-activate-btn").addEventListener("click", function () {
    var btn = document.getElementById("fw-review-activate-btn");
    var errEl = document.getElementById("fw-review-error");
    var noteEl = document.getElementById("fw-review-partial-note");
    errEl.hidden = true; noteEl.hidden = true;
    btn.disabled = true; btn.textContent = "Activating…";

    var activatePayload = {
      father: slotPayload("father"), mother: slotPayload("mother"), relationship: state.relationship,
      father_father: slotPayload("father_father"), father_mother: slotPayload("father_mother"),
      mother_father: slotPayload("mother_father"), mother_mother: slotPayload("mother_mother"),
    };

    api("/api/family/activate", activatePayload).then(function () {
      if (state.relationship === "single" || !state.spouse) { finishWizard(); return; }
      var childPayloads = state.slots
        .filter(function (s) { return s.key.indexOf("child_") === 0; })
        .map(function (s) { return slotPayload(s.key); });
      var spousePayload = state.spouse.viaExactId
        ? { name: state.spouse.name, action: "notify", user_id: state.spouse.resolvedUserId }
        : slotPayload("spouse");
      return api("/api/family/marry", {
        spouse: spousePayload, children: childPayloads,
        marriage_status: MARRIAGE_STATUS_MAP[state.relationship],
        spouse_father: slotPayload("spouse_father"), spouse_mother: slotPayload("spouse_mother"),
      }).then(function () {
        finishWizard();
      }).catch(function (e) {
        noteEl.textContent = "Your Family Timeline is active. Adding your spouse ran into a problem: " +
          e.message + " — you can retry this from your Personal tab.";
        noteEl.hidden = false;
        finishWizard();
      });
    }).catch(function (e) {
      errEl.textContent = e.message;
      errEl.hidden = false;
      btn.disabled = false; btn.textContent = "✅ Activate";
    });
  });

  function finishWizard() {
    wizardEl.hidden = true;
    refreshFamilyPanel();
  }

  // Exposed so family_tree.js can refresh the groups list after a successful "Leave this unit".
  window.QMFamilyRefresh = refreshFamilyPanel;
})();
