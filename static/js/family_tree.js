/**
 * family_tree.js — Phase 2: the D3 visual Family Tree. Fetches GET /api/family-groups/<id>/tree
 * (flat nodes + parent_links + spouse_links, unchanged from Phase 1 -- see family_core.py), merges
 * each active spouse pair into one "composite" layout node (the only sane way to map a DAG where a
 * child has two parents onto d3.tree()'s strict one-parent-per-node hierarchy), lays it out with
 * d3.tree(), and renders plain SVG rects/text (not foreignObject -- simpler, and fully compatible
 * with d3-zoom's transform-based panning, which some browsers handle inconsistently for embedded
 * HTML). Exposes window.QMFamilyTree.showTree(groupId) for family.js's group list to call into.
 */
(function () {
  "use strict";
  var container = document.getElementById("family-tree-container");
  if (!container || typeof d3 === "undefined") return;

  var summaryEl = document.getElementById("family-activated-summary");
  var svgEl = document.getElementById("ft-svg");
  var backBtn = document.getElementById("ft-back-btn");

  var NODE_W = 120, NODE_H = 56, NODE_GAP = 10, COL_W = 200, ROW_H = 150;

  function api(url, body) {
    var opt = body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }

  var state = { currentGroupId: null, editingNodeId: null };

  // ---- Composite-couple merge: pair every ACTIVE spouse link into one layout node, so a child's
  // two parent_links (father + mother) both resolve to the SAME composite, satisfying
  // d3.hierarchy()'s one-parent-per-node rule without dropping either parent. ----
  function buildHierarchy(tree) {
    var byId = {};
    tree.nodes.forEach(function (n) { byId[n.id] = n; });

    var compositeOf = {};
    var composites = [];
    function compositeFor(nodeId) {
      if (compositeOf[nodeId]) return compositeOf[nodeId];
      var c = { key: "c" + nodeId, people: [byId[nodeId]] };
      compositeOf[nodeId] = c;
      composites.push(c);
      return c;
    }
    tree.nodes.forEach(function (n) { compositeFor(n.id); });

    function mergeComposites(a, b) {
      if (a === b) return a;
      a.people = a.people.concat(b.people);
      b.people.forEach(function (p) { compositeOf[p.id] = a; });
      composites = composites.filter(function (c) { return c !== b; });
      return a;
    }

    (tree.spouse_links || []).forEach(function (link) {
      if (link.status !== "active") return;
      var cLo = compositeOf[link.node_lo_id], cHi = compositeOf[link.node_hi_id];
      if (cLo && cHi) mergeComposites(cLo, cHi);
    });

    // Co-parents with NO recorded spouse link (e.g. a lineage group's father + mother -- Phase 1
    // never creates a spouse_link between them) still need pairing: if two distinct composites
    // point at the exact same child composite(s), they're acting as joint parents and must be
    // merged into one layout node -- otherwise d3.hierarchy() would visit that shared child once
    // per parent branch, silently duplicating it in the render. Repeats to a fixed point since a
    // merge can itself create a new shared-child-set match.
    var changed = true;
    while (changed) {
      changed = false;
      var childSetOf = {};
      composites.forEach(function (c) { childSetOf[c.key] = []; });
      (tree.parent_links || []).forEach(function (link) {
        var parentC = compositeOf[link.parent_node_id], childC = compositeOf[link.child_node_id];
        if (!parentC || !childC || parentC === childC) return;
        if (childSetOf[parentC.key].indexOf(childC.key) === -1) childSetOf[parentC.key].push(childC.key);
      });
      var bySignature = {};
      composites.forEach(function (c) {
        var sig = childSetOf[c.key].slice().sort().join(",");
        if (!sig) return;
        bySignature[sig] = bySignature[sig] || [];
        bySignature[sig].push(c);
      });
      Object.keys(bySignature).forEach(function (sig) {
        var group = bySignature[sig];
        if (group.length > 1) {
          for (var i = 1; i < group.length; i++) mergeComposites(group[0], group[i]);
          changed = true;
        }
      });
    }

    var childrenOf = {}, hasParent = {};
    (tree.parent_links || []).forEach(function (link) {
      var parentC = compositeOf[link.parent_node_id], childC = compositeOf[link.child_node_id];
      if (!parentC || !childC || parentC === childC) return;
      childrenOf[parentC.key] = childrenOf[parentC.key] || [];
      if (childrenOf[parentC.key].indexOf(childC) === -1) childrenOf[parentC.key].push(childC);
      hasParent[childC.key] = true;
    });
    composites.forEach(function (c) { c.children = childrenOf[c.key]; });

    var roots = composites.filter(function (c) { return !hasParent[c.key]; });
    if (roots.length === 1) return roots[0];
    if (roots.length === 0) return composites[0] || { key: "empty", people: [] };
    return { key: "synthetic-root", people: [], children: roots, synthetic: true };
  }

  // ---- Rendering ----
  function nodeLabel(person) {
    return person.name + (person.is_deceased ? " 🕊️" : "");
  }

  function nodeClasses(person) {
    var cls = "ft-node";
    if (!person.claimed) cls += " is-empty";
    if (person.is_deceased) cls += " is-deceased";
    if (person.is_viewer) cls += " is-viewer";
    return cls;
  }

  function renderTree(tree) {
    var root = d3.hierarchy(buildHierarchy(tree));
    var layout = d3.tree().nodeSize([COL_W, ROW_H]);
    layout(root);

    var svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    var g = svg.append("g").attr("class", "ft-zoom-layer");

    var zoomBehavior = d3.zoom().scaleExtent([0.4, 2]).on("zoom", function (event) {
      g.attr("transform", event.transform);
    });
    svg.call(zoomBehavior);

    // Parent links: from each composite's bottom-center to each child composite's top-center.
    var linkGen = d3.linkVertical().x(function (d) { return d.x; }).y(function (d) { return d.y; });
    g.append("g").attr("class", "ft-links-parent")
      .selectAll("path")
      .data(root.links())
      .enter().append("path")
      .attr("class", "ft-link-parent")
      .attr("d", function (d) {
        return linkGen({
          source: { x: d.source.x, y: d.source.y + NODE_H / 2 },
          target: { x: d.target.x, y: d.target.y - NODE_H / 2 },
        });
      });

    // Spouse links: a short horizontal connector between the two cards of a 2-person composite.
    g.append("g").attr("class", "ft-links-spouse")
      .selectAll("line")
      .data(root.descendants().filter(function (d) { return d.data.people.length === 2; }))
      .enter().append("line")
      .attr("class", "ft-link-spouse")
      .attr("x1", function (d) { return d.x - NODE_GAP / 2; })
      .attr("x2", function (d) { return d.x + NODE_GAP / 2; })
      .attr("y1", function (d) { return d.y; })
      .attr("y2", function (d) { return d.y; });

    // Node cards: 1 or 2 person-cards per composite, centered on the composite's (x, y).
    var cardGroups = g.append("g").attr("class", "ft-nodes")
      .selectAll("g.ft-composite")
      .data(root.descendants())
      .enter().append("g")
      .attr("class", "ft-composite")
      .attr("transform", function (d) { return "translate(" + d.x + "," + d.y + ")"; });

    cardGroups.each(function (d) {
      var group = d3.select(this);
      var people = d.data.people || [];
      var count = people.length;
      people.forEach(function (person, i) {
        var offsetX = count === 2 ? (i === 0 ? -(NODE_W + NODE_GAP) / 2 : (NODE_W + NODE_GAP) / 2) : 0;
        var card = group.append("g")
          .attr("class", nodeClasses(person))
          .attr("transform", "translate(" + offsetX + ",0)");
        card.append("rect")
          .attr("x", -NODE_W / 2).attr("y", -NODE_H / 2)
          .attr("width", NODE_W).attr("height", NODE_H)
          .attr("rx", 10);
        card.append("text")
          .attr("y", 5)
          .text(nodeLabel(person));
        if (!person.claimed) {
          card.style("cursor", "pointer").on("click", function () { openEditModal(person); });
        }
      });
    });

    // Center the initial view on the viewer's own node.
    var viewerDescendant = root.descendants().filter(function (d) {
      return (d.data.people || []).some(function (p) { return p.is_viewer; });
    })[0];
    var wrapRect = svgEl.getBoundingClientRect();
    var cx = viewerDescendant ? viewerDescendant.x : 0;
    var cy = viewerDescendant ? viewerDescendant.y : 0;
    var initialTransform = d3.zoomIdentity
      .translate(wrapRect.width / 2 - cx, wrapRect.height / 2 - cy);
    svg.call(zoomBehavior.transform, initialTransform);
  }

  // ---- Entry point ----
  function showTree(groupId) {
    state.currentGroupId = groupId;
    api("/api/family-groups/" + groupId + "/tree").then(function (tree) {
      summaryEl.hidden = true;
      container.hidden = false;
      renderTree(tree);
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
