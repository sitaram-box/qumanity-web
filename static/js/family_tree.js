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
 */
(function () {
  "use strict";
  var container = document.getElementById("family-tree-container");
  if (!container || typeof d3 === "undefined") return;

  var summaryEl = document.getElementById("family-activated-summary");
  var svgEl = document.getElementById("ft-svg");
  var backBtn = document.getElementById("ft-back-btn");

  var UNIT_W = 230, UNIT_H = 60, SINGLE_W = 130, CARD_GAP = 50, ROW_H = 180;

  function api(url, body) {
    var opt = body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }

  var state = { currentGroupId: null, editingNodeId: null };

  function personLabel(person) {
    return person.name + (person.is_deceased ? " 🕊️" : "");
  }

  function unitTitle(unit, role) {
    if (role === "self") return "My Family";
    if (role === "husband") return "Father's Family";
    if (role === "wife") return "Mother's Family";
    return unit.name; // a child unit -- shown by its own group name, no fixed relation label
  }

  // ---- Layout: fixed 3 rows, centered on x=0. No hierarchy algorithm needed -- row and width are
  // already known from the neighborhood response's own shape. ----
  function layoutUniform(items, y, width) {
    var n = items.length;
    if (!n) return [];
    var totalW = n * width + (n - 1) * CARD_GAP;
    var x = -totalW / 2;
    return items.map(function (item) {
      var cx = x + width / 2;
      x += width + CARD_GAP;
      return { x: cx, y: y, width: width, kind: "unit", data: item };
    });
  }

  function layoutChildren(childGroups, unmarriedChildren, y) {
    var items = (childGroups || []).map(function (g) { return { kind: "unit", data: g, width: UNIT_W }; })
      .concat((unmarriedChildren || []).map(function (p) { return { kind: "person", data: p, width: SINGLE_W }; }));
    if (!items.length) return [];
    var totalW = items.reduce(function (sum, it) { return sum + it.width; }, 0) + (items.length - 1) * CARD_GAP;
    var x = -totalW / 2;
    return items.map(function (it) {
      var cx = x + it.width / 2;
      x += it.width + CARD_GAP;
      return { x: cx, y: y, width: it.width, kind: it.kind, data: it.data };
    });
  }

  // ---- Rendering ----
  function renderUnitCard(group, unit, width, isSelf, role) {
    var rectCls = "ft-unit-rect" + (unit.is_dormant ? " is-dormant" : "") + (isSelf ? " is-current" : "");
    group.append("rect").attr("class", rectCls)
      .attr("x", -width / 2).attr("y", -UNIT_H / 2).attr("width", width).attr("height", UNIT_H).attr("rx", 12);
    group.append("text").attr("class", "ft-unit-title").attr("y", -UNIT_H / 2 - 10).text(unitTitle(unit, role));

    renderPersonHalf(group, unit.husband, -width / 4);
    renderPersonHalf(group, unit.wife, width / 4);
    group.append("line").attr("class", "ft-unit-divider").attr("x1", 0).attr("x2", 0)
      .attr("y1", -UNIT_H / 2 + 8).attr("y2", UNIT_H / 2 - 8);
  }

  function renderPersonHalf(group, person, offsetX) {
    var cls = "ft-person" + (!person || !person.claimed ? " is-empty" : "")
      + (person && person.is_deceased ? " is-deceased" : "") + (person && person.is_viewer ? " is-viewer" : "");
    var p = group.append("g").attr("class", cls).attr("transform", "translate(" + offsetX + ",0)");
    p.append("text").attr("y", 5).text(person ? personLabel(person) : "+ Add");
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
    group.append("text").attr("y", 5).text(person ? personLabel(person) : "+ Add");
    if (!person.claimed) {
      group.style("cursor", "pointer").on("click", function (event) {
        event.stopPropagation();
        openEditModal(person);
      });
    }
  }

  function renderNeighborhood(nbh) {
    var parentCards = layoutUniform(nbh.parent_groups, -ROW_H, UNIT_W).map(function (c, i) {
      c.role = nbh.parent_groups[i].side;
      return c;
    });
    var selfCard = { x: 0, y: 0, width: UNIT_W, kind: "unit", data: nbh, role: "self" };
    var childCards = layoutChildren(nbh.child_groups, nbh.unmarried_children, ROW_H);

    var svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    var g = svg.append("g").attr("class", "ft-zoom-layer");
    var zoomBehavior = d3.zoom().scaleExtent([0.4, 2]).on("zoom", function (event) { g.attr("transform", event.transform); });
    svg.call(zoomBehavior);

    // Connecting lines, drawn first so cards sit visually on top of them.
    var linkGen = d3.linkVertical().x(function (d) { return d.x; }).y(function (d) { return d.y; });
    var linksLayer = g.append("g").attr("class", "ft-links-layer");
    parentCards.forEach(function (p) {
      linksLayer.append("path").attr("class", "ft-link").attr("d", linkGen({
        source: { x: p.x, y: p.y + UNIT_H / 2 },
        target: { x: selfCard.x, y: selfCard.y - UNIT_H / 2 },
      }));
    });
    childCards.forEach(function (c) {
      var targetHalfH = c.kind === "person" ? UNIT_H * 0.35 : UNIT_H / 2;
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
      if (d.kind === "person") {
        renderPersonCard(group, d.data, d.width);
      } else {
        renderUnitCard(group, d.data, d.width, d === selfCard, d.role);
      }
    });

    // Click-to-navigate: any unit card except the current (self) one. A click on an empty person
    // slot is stopped from bubbling here (see renderPersonHalf), so it opens the edit modal only.
    cardGroups.filter(function (d) { return d.kind === "unit" && d !== selfCard; })
      .style("cursor", "pointer")
      .on("click", function (event, d) { showTree(d.data.group_id); });

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

  // ---- Click-an-empty-node modal ----
  var editModal = document.getElementById("ft-edit-modal");
  var nameInput = document.getElementById("ft-edit-name-input");
  var linkInput = document.getElementById("ft-edit-link-input");
  var errorEl = document.getElementById("ft-edit-error");

  editModal.addEventListener("click", function (e) {
    if (e.target === editModal || e.target.hasAttribute("data-close")) editModal.hidden = true;
  });

  function openEditModal(person) {
    state.editingNodeId = person.id;
    document.getElementById("ft-edit-modal-title").textContent = "Add: " + person.name;
    nameInput.value = "";
    linkInput.value = "";
    errorEl.hidden = true;
    editModal.hidden = false;
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
    if (!val) { errorEl.textContent = "Enter a Public ID or Account ID."; errorEl.hidden = false; return; }
    api("/api/family/node/" + state.editingNodeId + "/link", { user_id: val })
      .then(reloadAfterEdit)
      .catch(function (e) { errorEl.textContent = e.message; errorEl.hidden = false; });
  });

  window.QMFamilyTree = { showTree: showTree };
})();
