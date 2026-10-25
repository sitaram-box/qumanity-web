/**
 * family_tree.js — the Nuclear Family Node neighborhood view (2026-10-20). A unit IS a couple, so
 * there is no DAG to flatten here the way the old per-person tree needed (Phase 2's composite-
 * couple merge is gone): GET /api/family/node/<group_id>/neighborhood already returns exactly
 * three fixed rows -- up to 2 parent units above, the current unit in the middle, its unmarried
 * children and child units below -- so this just places them directly, no d3.hierarchy()/d3.tree()
 * layout algorithm needed. Clicking a parent OR child unit re-centers the view by fetching ITS
 * neighborhood; the current (middle) unit is never clickable to navigate. Exposes
 * window.QMFamilyTree.showTree(groupId) for family.js's group list to call into (name kept for
 * compatibility with the existing call site).
 *
 * Explicit tree growth (2026-10-20): the top row always shows exactly 2 slots (husband/wife side)
 * -- a real unit card if neighborhood_for_group() found one, else a dashed "+ Add Father's/
 * Mother's Family" button. The bottom row always appends a trailing dashed "+ Add Child" button
 * after any real children. A dashed "+ Add Sibling" button sits beside the SPOUSE's parents' card
 * specifically (only once that card is real) -- an in-law is structurally a child of the spouse's
 * parents' unit, not a peer of the viewer, so it is never placed beside the self card.
 */
(function () {
  "use strict";
  var container = document.getElementById("family-tree-container");
  if (!container || typeof d3 === "undefined") return;

  var summaryEl = document.getElementById("family-activated-summary");
  var svgEl = document.getElementById("ft-svg");
  var backBtn = document.getElementById("ft-back-btn");

  var UNIT_W = 230, UNIT_H = 60, SINGLE_W = 130, CARD_GAP = 50, ROW_H = 180, AVATAR_R = 11;

  function api(url, body) {
    var opt = body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }

  var state = { currentGroupId: null, editingNodeId: null };

  function personLabel(person) {
    return person.name + (person.is_deceased ? " 🕊️" : "");
  }

  function unitSubtitle(unit) {
    var n = unit.members || 0;
    return n + " member" + (n === 1 ? "" : "s");
  }

  // ---- Avatars: window.QMAvatar.render() (static/js/avatar.js), the SAME function every other
  // surface (chat, Qmail, board, admin) uses -- embedded via <foreignObject>, since SVG has no
  // <img>/<div> of its own to render QMAvatar's real HTMLElement output directly. ----
  function renderAvatar(parent, person, cx, cy, r) {
    if (!person || !window.QMAvatar) return;
    var size = r * 2;
    var fo = parent.append("foreignObject").attr("class", "ft-avatar")
      .attr("x", cx - r).attr("y", cy - r).attr("width", size).attr("height", size);
    var body = fo.append("xhtml:div").style("width", size + "px").style("height", size + "px");
    body.node().appendChild(QMAvatar.render(person, size));
  }

  // ---- Layout: fixed 3 rows, centered on x=0. A single generic row-layout function (mixed
  // widths, centered) now covers all three rows -- the top row needs mixed widths too, once a
  // narrower "+ Add Sibling" button can sit beside a full-width parent-unit card. ----
  function layoutRow(items, y) {
    if (!items.length) return [];
    var totalW = items.reduce(function (sum, it) { return sum + it.width; }, 0) + (items.length - 1) * CARD_GAP;
    var x = -totalW / 2;
    return items.map(function (it) {
      var cx = x + it.width / 2;
      x += it.width + CARD_GAP;
      var out = { x: cx, y: y, width: it.width, kind: it.kind, data: it.data };
      if (it.role) out.role = it.role;
      if (it.side) out.side = it.side;
      if (it.targetGroupId !== undefined) out.targetGroupId = it.targetGroupId;
      return out;
    });
  }

  function buildTopRowItems(nbh) {
    var bySide = {};
    (nbh.parent_groups || []).forEach(function (g) { bySide[g.side] = g; });
    var husbandItem = bySide.husband
      ? { kind: "unit", data: bySide.husband, role: "husband", width: UNIT_W }
      : { kind: "add-parents", side: "husband", width: UNIT_W };
    var wifeItem = bySide.wife
      ? { kind: "unit", data: bySide.wife, role: "wife", width: UNIT_W }
      : { kind: "add-parents", side: "wife", width: UNIT_W };
    var items = [husbandItem, wifeItem];

    // The spouse is whichever founder of the CURRENT unit the viewer is NOT -- "Add Sibling"
    // only makes sense once we know which side is the spouse's, and only once that side's
    // parents' unit is real (there's nothing to attach an in-law to otherwise).
    var spouseSide = (nbh.husband && nbh.husband.is_viewer) ? "wife" : ((nbh.wife && nbh.wife.is_viewer) ? "husband" : null);
    if (spouseSide && bySide[spouseSide]) {
      var siblingItem = { kind: "add-sibling", targetGroupId: bySide[spouseSide].group_id, width: SINGLE_W };
      if (spouseSide === "husband") items.unshift(siblingItem); else items.push(siblingItem);
    }
    return items;
  }

  function buildBottomRowItems(nbh) {
    var items = (nbh.child_groups || []).map(function (g) { return { kind: "unit", data: g, width: UNIT_W }; })
      .concat((nbh.unmarried_children || []).map(function (p) { return { kind: "person", data: p, width: SINGLE_W }; }));
    items.push({ kind: "add-child", targetGroupId: nbh.group_id, width: SINGLE_W });
    return items;
  }

  // ---- Rendering ----
  // Color encodes the relation this card has to the CURRENT unit (role: 'self' | 'husband' |
  // 'wife' | undefined for a child unit): self = navy, husband's ascending line = saffron, wife's
  // ascending line = gold -- replaces the old text labels ("Father's Family" etc.), which the
  // group-name header (below) now occupies instead.
  function roleClass(role) {
    if (role === "self") return "is-self";
    if (role === "husband") return "is-husband-side";
    if (role === "wife") return "is-wife-side";
    return "";
  }

  function renderUnitCard(group, unit, width, isSelf, role) {
    var rectCls = "ft-unit-rect" + (unit.is_dormant ? " is-dormant" : "") + (" " + roleClass(role)).trimEnd();
    group.append("rect").attr("class", rectCls)
      .attr("x", -width / 2).attr("y", -UNIT_H / 2).attr("width", width).attr("height", UNIT_H).attr("rx", 12);
    group.append("text").attr("class", "ft-unit-title").attr("y", -UNIT_H / 2 - 10).text(unit.name);
    group.append("text").attr("class", "ft-unit-subtitle").attr("y", UNIT_H / 2 + 16).text(unitSubtitle(unit));

    renderPersonHalf(group, unit.husband, -width / 4);
    renderPersonHalf(group, unit.wife, width / 4);
    group.append("line").attr("class", "ft-unit-divider").attr("x1", 0).attr("x2", 0)
      .attr("y1", -UNIT_H / 2 + 8).attr("y2", UNIT_H / 2 - 8);
  }

  function renderPersonHalf(group, person, offsetX) {
    var cls = "ft-person" + (!person || !person.claimed ? " is-empty" : "")
      + (person && person.is_deceased ? " is-deceased" : "") + (person && person.is_viewer ? " is-viewer" : "");
    var p = group.append("g").attr("class", cls).attr("transform", "translate(" + offsetX + ",0)");
    renderAvatar(p, person, 0, -12, AVATAR_R);
    p.append("text").attr("y", 18).text(person ? personLabel(person) : "+ Add");
    if (person && !person.claimed) {
      p.style("cursor", "pointer").on("click", function (event) {
        event.stopPropagation();
        openEditModal(person);
      });
    }
  }

  function renderPersonCard(group, person, width) {
    var cls = "ft-single-rect" + (person.is_deceased ? " is-deceased" : "") + (!person.claimed ? " is-empty" : "") + (person.is_viewer ? " is-viewer" : "");
    group.append("rect").attr("class", cls)
      .attr("x", -width / 2).attr("y", -UNIT_H * 0.35).attr("width", width).attr("height", UNIT_H * 0.7).attr("rx", 10);
    renderAvatar(group, person, 0, -9, AVATAR_R * 0.8);
    group.append("text").attr("class", person.claimed ? null : "ft-empty-label").attr("y", 13).text(person ? personLabel(person) : "+ Add");
    if (!person.claimed) {
      group.style("cursor", "pointer").on("click", function (event) {
        event.stopPropagation();
        openEditModal(person);
      });
    }
  }

  function renderAddUnitCard(group, width, label) {
    group.append("rect").attr("class", "ft-unit-rect ft-add-rect")
      .attr("x", -width / 2).attr("y", -UNIT_H / 2).attr("width", width).attr("height", UNIT_H).attr("rx", 12);
    group.append("text").text(label);
  }

  function renderAddPersonCard(group, width, label) {
    group.append("rect").attr("class", "ft-single-rect is-empty")
      .attr("x", -width / 2).attr("y", -UNIT_H * 0.35).attr("width", width).attr("height", UNIT_H * 0.7).attr("rx", 10);
    group.append("text").attr("y", 5).text(label);
  }

  function renderNeighborhood(nbh) {
    var topItems = buildTopRowItems(nbh);
    var parentCards = layoutRow(topItems, -ROW_H);
    var selfCard = { x: 0, y: 0, width: UNIT_W, kind: "unit", data: nbh, role: "self" };
    var bottomItems = buildBottomRowItems(nbh);
    var childCards = layoutRow(bottomItems, ROW_H);

    var svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    var g = svg.append("g").attr("class", "ft-zoom-layer");
    var zoomBehavior = d3.zoom().scaleExtent([0.4, 2]).on("zoom", function (event) { g.attr("transform", event.transform); });
    svg.call(zoomBehavior);

    // Connecting lines, drawn first so cards sit visually on top of them. The "+ Add Sibling"
    // button is never linked to self -- it isn't a child of this unit, it would belong to the
    // spouse's parents' unit above, which already has its own card.
    var linkGen = d3.linkVertical().x(function (d) { return d.x; }).y(function (d) { return d.y; });
    var linksLayer = g.append("g").attr("class", "ft-links-layer");
    parentCards.forEach(function (p) {
      if (p.kind === "add-sibling") return;
      var sourceHalfH = p.kind === "add-parents" ? UNIT_H / 2 : UNIT_H / 2;
      linksLayer.append("path").attr("class", "ft-link").attr("d", linkGen({
        source: { x: p.x, y: p.y + sourceHalfH },
        target: { x: selfCard.x, y: selfCard.y - UNIT_H / 2 },
      }));
    });
    childCards.forEach(function (c) {
      var targetHalfH = c.kind === "unit" ? UNIT_H / 2 : UNIT_H * 0.35;
      linksLayer.append("path").attr("class", "ft-link").attr("d", linkGen({
        source: { x: selfCard.x, y: selfCard.y + UNIT_H / 2 },
        target: { x: c.x, y: c.y - targetHalfH },
      }));
    });

    // Cards.
    var allCards = parentCards.concat([selfCard], childCards);
    var cardGroups = g.append("g").attr("class", "ft-cards")
      .selectAll("g.ft-card")
      .data(allCards)
      .enter().append("g")
      .attr("class", function (d) { return "ft-card " + (d.kind === "unit" ? "ft-card-unit" : "ft-card-person"); })
      .attr("transform", function (d) { return "translate(" + d.x + "," + d.y + ")"; });

    cardGroups.each(function (d) {
      var group = d3.select(this);
      switch (d.kind) {
        case "person":
          renderPersonCard(group, d.data, d.width);
          break;
        case "add-parents":
          renderAddUnitCard(group, d.width, d.side === "husband" ? "+ Add Father's Family" : "+ Add Mother's Family");
          break;
        case "add-sibling":
          renderAddPersonCard(group, d.width, "+ Add Sibling");
          break;
        case "add-child":
          renderAddPersonCard(group, d.width, "+ Add Child");
          break;
        default:
          renderUnitCard(group, d.data, d.width, d === selfCard, d.role);
      }
    });

    // Click-to-navigate: any real unit card except the current (self) one. A click on an empty
    // person slot is stopped from bubbling here (see renderPersonHalf), so it opens the edit
    // modal only.
    cardGroups.filter(function (d) { return d.kind === "unit" && d !== selfCard; })
      .style("cursor", "pointer")
      .on("click", function (event, d) { showTree(d.data.group_id); });

    // Click-to-grow: the dashed "+Add" buttons each open ft-add-modal in the right mode.
    cardGroups.filter(function (d) { return d.kind === "add-parents"; })
      .style("cursor", "pointer")
      .on("click", function (event, d) { openAddModal("parents", { groupId: nbh.group_id, side: d.side }); });
    cardGroups.filter(function (d) { return d.kind === "add-sibling"; })
      .style("cursor", "pointer")
      .on("click", function (event, d) { openAddModal("child", { groupId: d.targetGroupId, title: "Add Sibling" }); });
    cardGroups.filter(function (d) { return d.kind === "add-child"; })
      .style("cursor", "pointer")
      .on("click", function (event, d) { openAddModal("child", { groupId: d.targetGroupId, title: "Add Child" }); });

    // Center the initial view on the current unit.
    var wrapRect = svgEl.getBoundingClientRect();
    svg.call(zoomBehavior.transform, d3.zoomIdentity.translate(wrapRect.width / 2, wrapRect.height / 2));
  }

  // ---- Entry point ----
  function showTree(groupId) {
    state.currentGroupId = groupId;
    api("/api/family/node/" + groupId + "/neighborhood").then(function (nbh) {
      summaryEl.hidden = true;
      container.hidden = false;
      renderNeighborhood(nbh);
    }).catch(function (e) { alert(e.message); });
  }

  backBtn.addEventListener("click", function () {
    container.hidden = true;
    summaryEl.hidden = false;
  });

  var leaveBtn = document.getElementById("ft-leave-btn");
  var leaveErrorEl = document.getElementById("ft-leave-error");
  if (leaveBtn) {
    leaveBtn.addEventListener("click", function () {
      if (!state.currentGroupId) return;
      leaveErrorEl.hidden = true;
      if (!window.confirm("Leave this Family Group? You can rejoin later by requesting again.")) return;
      api("/api/family-groups/" + state.currentGroupId + "/leave", {}).then(function () {
        container.hidden = true;
        summaryEl.hidden = false;
        if (window.QMFamilyRefresh) window.QMFamilyRefresh();
      }).catch(function (e) {
        leaveErrorEl.textContent = e.message;
        leaveErrorEl.hidden = false;
      });
    });
  }

  // ---- Click-an-empty-node modal (2026-10-20 redesign): a clicked node already HAS a typed
  // name (e.g. "Pardeep Sharma") -- the modal's default, primary action is linking it to a real
  // Qumanity member by their 12-digit Public ID, not re-typing a name that's already there. The
  // Name field stays tucked behind an "Edit Name" toggle, pre-filled with the current name so
  // editing it is a correction, not starting from blank. ----
  var editModal = document.getElementById("ft-edit-modal");
  var nameSection = document.getElementById("ft-edit-name-section");
  var nameInput = document.getElementById("ft-edit-name-input");
  var linkInput = document.getElementById("ft-edit-link-input");
  var errorEl = document.getElementById("ft-edit-error");
  var toggleNameBtn = document.getElementById("ft-edit-toggle-name-btn");

  editModal.addEventListener("click", function (e) {
    if (e.target === editModal || e.target.hasAttribute("data-close")) editModal.hidden = true;
  });

  toggleNameBtn.addEventListener("click", function () {
    nameSection.hidden = !nameSection.hidden;
  });

  function openEditModal(person) {
    state.editingNodeId = person.id;
    document.getElementById("ft-edit-modal-title").textContent = person.name;
    nameInput.value = person.name;
    linkInput.value = "";
    nameSection.hidden = true; // defaults to the Link view -- see the redesign note above
    errorEl.hidden = true;
    editModal.hidden = false;
    linkInput.focus();
  }

  function reloadAfterEdit() {
    editModal.hidden = true;
    if (state.currentGroupId) showTree(state.currentGroupId);
  }

  document.getElementById("ft-edit-save-name-btn").addEventListener("click", function () {
    var name = nameInput.value.trim();
    if (!name) { errorEl.textContent = "A name is required."; errorEl.hidden = false; return; }
    api("/api/family/node/" + state.editingNodeId + "/name", { name: name })
      .then(reloadAfterEdit)
      .catch(function (e) { errorEl.textContent = e.message; errorEl.hidden = false; });
  });

  document.getElementById("ft-edit-link-btn").addEventListener("click", function () {
    var val = linkInput.value.trim();
    if (!val) { errorEl.textContent = "Enter a 12-digit Public ID."; errorEl.hidden = false; return; }
    api("/api/family/node/" + state.editingNodeId + "/link", { user_id: val })
      .then(reloadAfterEdit)
      .catch(function (e) { errorEl.textContent = e.message; errorEl.hidden = false; });
  });

  // ---- "+Add" modal (2026-10-20): grows the tree by hand. 'parents' mode fills a missing
  // husband-/wife-side parents' unit (POST .../add-parents); 'child' mode covers BOTH "+ Add
  // Child" and "+ Add Sibling" (POST .../add-child) -- same route, the opener just picks which
  // unit's group_id to target. ----
  var addModal = document.getElementById("ft-add-modal");
  var addModalTitle = document.getElementById("ft-add-modal-title");
  var addParentsFields = document.getElementById("ft-add-parents-fields");
  var addChildFields = document.getElementById("ft-add-child-fields");
  var addFatherInput = document.getElementById("ft-add-father-name");
  var addMotherInput = document.getElementById("ft-add-mother-name");
  var addChildNameInput = document.getElementById("ft-add-child-name");
  var addChildGenderBtns = Array.prototype.slice.call(document.querySelectorAll("#ft-add-child-gender-group .qm-gender-btn"));
  var addErrorEl = document.getElementById("ft-add-error");
  var addState = { mode: null, groupId: null, side: null, gender: null };

  addModal.addEventListener("click", function (e) {
    if (e.target === addModal || e.target.hasAttribute("data-close")) addModal.hidden = true;
  });

  addChildGenderBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      addState.gender = btn.getAttribute("data-gender");
      addChildGenderBtns.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
    });
  });

  function openAddModal(mode, opts) {
    addState.mode = mode;
    addState.groupId = opts.groupId;
    addState.side = opts.side || null;
    addState.gender = null;
    addErrorEl.hidden = true;
    addFatherInput.value = ""; addMotherInput.value = ""; addChildNameInput.value = "";
    addChildGenderBtns.forEach(function (b) { b.classList.remove("is-active"); });

    if (mode === "parents") {
      addModalTitle.textContent = opts.side === "husband" ? "Add Father's Family" : "Add Mother's Family";
      addParentsFields.hidden = false;
      addChildFields.hidden = true;
    } else {
      addModalTitle.textContent = opts.title || "Add Child";
      addParentsFields.hidden = true;
      addChildFields.hidden = false;
    }
    addModal.hidden = false;
  }

  function reloadAfterAdd() {
    addModal.hidden = true;
    if (state.currentGroupId) showTree(state.currentGroupId);
  }

  document.getElementById("ft-add-save-btn").addEventListener("click", function () {
    addErrorEl.hidden = true;
    if (addState.mode === "parents") {
      var father = addFatherInput.value.trim(), mother = addMotherInput.value.trim();
      if (!father && !mother) { addErrorEl.textContent = "Enter at least one parent's name."; addErrorEl.hidden = false; return; }
      api("/api/family/node/" + addState.groupId + "/add-parents", {
        side: addState.side,
        father: father ? { name: father } : null,
        mother: mother ? { name: mother } : null,
      }).then(reloadAfterAdd).catch(function (e) { addErrorEl.textContent = e.message; addErrorEl.hidden = false; });
    } else {
      var name = addChildNameInput.value.trim();
      if (!name) { addErrorEl.textContent = "A name is required."; addErrorEl.hidden = false; return; }
      api("/api/family/node/" + addState.groupId + "/add-child", { name: name, gender: addState.gender })
        .then(reloadAfterAdd).catch(function (e) { addErrorEl.textContent = e.message; addErrorEl.hidden = false; });
    }
  });

  // ---- Members modal (2026-10-25): who's actually in this unit, with their role, plus an
  // "Add Member by Public ID" box -- previously the only way to see a unit's membership was the
  // D3 cards themselves, and there was no admin-initiated invite at all for Family Groups (only
  // the self-service "request to join" flow). ----
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  var GENDER_LABEL = { male: "Male", female: "Female", both: "Third Gender" };

  var membersModal = document.getElementById("ft-members-modal");
  var membersList = document.getElementById("ft-members-list");
  var membersSearchInput = document.getElementById("ft-members-search-input");
  var membersSearchResult = document.getElementById("ft-members-search-result");
  var membersErrorEl = document.getElementById("ft-members-error");

  membersModal.addEventListener("click", function (e) {
    if (e.target === membersModal || e.target.hasAttribute("data-close")) membersModal.hidden = true;
  });

  function renderMembersList(members) {
    membersList.innerHTML = "";
    members.forEach(function (m) {
      var li = el("li", "ft-member-row");
      if (window.QMAvatar) li.appendChild(QMAvatar.render(m, 40));
      var textWrap = el("div", "ft-member-text");
      textWrap.appendChild(el("b", "", m.name + (m.you ? " (You)" : "")));
      var meta = [GENDER_LABEL[m.gender] || m.gender, m.age_group, m.present_location].filter(Boolean).join(" · ");
      textWrap.appendChild(el("span", "ft-member-meta", meta));
      li.appendChild(textWrap);
      li.appendChild(el("span", "ft-member-role" + (m.is_admin ? " is-admin" : ""), m.is_admin ? "Admin" : "Member"));
      membersList.appendChild(li);
    });
  }

  function openMembersModal() {
    if (!state.currentGroupId) return;
    membersErrorEl.hidden = true;
    membersSearchInput.value = "";
    membersSearchResult.innerHTML = "";
    membersModal.hidden = false;
    api("/api/family-groups/" + state.currentGroupId + "/members").then(function (d) {
      renderMembersList(d.members);
    }).catch(function (e) {
      membersErrorEl.textContent = e.message;
      membersErrorEl.hidden = false;
    });
  }

  var membersBtn = document.getElementById("ft-members-btn");
  if (membersBtn) membersBtn.addEventListener("click", openMembersModal);

  document.getElementById("ft-members-search-btn").addEventListener("click", function () {
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
        api("/api/family-groups/" + state.currentGroupId + "/invite", { user_id: p.user_id }).then(function () {
          inviteBtn.textContent = "✓ Invited"; membersSearchInput.value = "";
        }).catch(function (e) {
          inviteBtn.disabled = false; inviteBtn.textContent = "Send Invite";
          membersErrorEl.textContent = e.message; membersErrorEl.hidden = false;
        });
      });
      card.appendChild(inviteBtn);
      membersSearchResult.appendChild(card);
    }).catch(function (e) {
      membersErrorEl.textContent = e.message;
      membersErrorEl.hidden = false;
    });
  });

  window.QMFamilyTree = { showTree: showTree };
})();
