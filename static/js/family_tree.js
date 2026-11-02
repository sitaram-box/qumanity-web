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

  // UNIT_W/SINGLE_W below are the MINIMUM/default widths, not fixed ones any more (Phase 2,
  // 2026-11-01, dynamic node sizing -- see sizeUnitCard()/sizeSingleCard()). UNIT_H/CARD_GAP stay
  // truly fixed: UNIT_H is every card's TOP edge offset from its own center (never moves -- a
  // card only ever grows DOWNWARD to fit extra wrapped lines, see renderUnitCard()/
  // renderPersonCard()'s own notes), and CARD_GAP is the fixed horizontal gap within a row.
  var UNIT_W = 230, UNIT_H = 60, SINGLE_W = 130, CARD_GAP = 50, ROW_GAP = 70, AVATAR_R = 11;
  var MAX_UNIT_HALF_W = 160, MAX_SINGLE_W = 190, PERSON_PAD = 16, LINE_H = 14;

  function api(url, body) {
    var opt = body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }

  var state = { currentGroupId: null };

  function personLabel(person) {
    return person.name + (person.is_deceased ? " 🕊️" : "");
  }

  function unitSubtitle(unit) {
    var n = unit.members || 0;
    return n + " member" + (n === 1 ? "" : "s");
  }

  // ---- Dynamic node sizing (Phase 2, 2026-11-01): real browser text measurement (Canvas
  // measureText(), the work order's own suggestion) against the SAME font every .ft-card text
  // element actually renders with (read live off <body>, not a hardcoded guess) -- never a fixed
  // pixels-per-character estimate. A name that still doesn't fit at MAX_UNIT_HALF_W/MAX_SINGLE_W
  // wraps onto additional lines (never truncated, never has a middle name/surname silently
  // dropped) and the card grows DOWNWARD to fit them; a short name never forces a wide card. ----
  var _measureCtx = document.createElement("canvas").getContext("2d");
  var _BASE_FONT_FAMILY = (window.getComputedStyle(document.body).fontFamily) || "Inter, system-ui, sans-serif";

  function fontSpec(px, weight) { return (weight || 400) + " " + px + "px " + _BASE_FONT_FAMILY; }
  function textWidth(text, font) { _measureCtx.font = font; return _measureCtx.measureText(text || "").width; }

  function wrapText(text, font, maxWidth) {
    var words = (text || "").split(/\s+/).filter(Boolean);
    if (!words.length) return [""];
    var lines = [], current = words[0];
    for (var i = 1; i < words.length; i++) {
      var attempt = current + " " + words[i];
      if (textWidth(attempt, font) <= maxWidth) { current = attempt; } else { lines.push(current); current = words[i]; }
    }
    lines.push(current);
    return lines;
  }

  // One line if it already fits maxWidth, else wrapped across as many as it needs.
  function personLines(person, maxWidth, font) {
    var label = person ? personLabel(person) : "+ Add";
    if (textWidth(label, font) <= maxWidth) return { lines: [label], width: textWidth(label, font) };
    var lines = wrapText(label, font, maxWidth);
    return { lines: lines, width: Math.max.apply(null, lines.map(function (l) { return textWidth(l, font); })) };
  }

  function sizeUnitCard(unit) {
    var font = fontSpec(12, 400);
    var husband = personLines(unit.husband, MAX_UNIT_HALF_W - PERSON_PAD, font);
    var wife = personLines(unit.wife, MAX_UNIT_HALF_W - PERSON_PAD, font);
    var halfW = Math.max(UNIT_W / 2, husband.width + PERSON_PAD, wife.width + PERSON_PAD);
    var extraLines = Math.max(husband.lines.length, wife.lines.length, 1) - 1;
    return { width: halfW * 2, height: UNIT_H + extraLines * LINE_H, husbandLines: husband.lines, wifeLines: wife.lines };
  }

  function sizeSingleCard(person) {
    var font = fontSpec(12, 400);
    var res = personLines(person, MAX_SINGLE_W - PERSON_PAD, font);
    var width = Math.max(SINGLE_W, res.width + PERSON_PAD);
    return { width: width, height: UNIT_H * 0.7 + (res.lines.length - 1) * LINE_H, lines: res.lines };
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
  // widths, centered) now covers all three rows. Every item's height is its own TOP-edge-fixed
  // card growing downward (see sizeUnitCard()/sizeSingleCard()), so only width affects horizontal
  // placement here -- height is carried through for renderNeighborhood()'s own row-to-row and
  // connector math below, never used for x positioning. ----
  function layoutRow(items, y) {
    if (!items.length) return [];
    var totalW = items.reduce(function (sum, it) { return sum + it.width; }, 0) + (items.length - 1) * CARD_GAP;
    var x = -totalW / 2;
    return items.map(function (it) {
      var cx = x + it.width / 2;
      x += it.width + CARD_GAP;
      var out = { x: cx, y: y, width: it.width, height: it.height, kind: it.kind, data: it.data };
      if (it.role) out.role = it.role;
      if (it.side) out.side = it.side;
      if (it.targetGroupId !== undefined) out.targetGroupId = it.targetGroupId;
      if (it.contextGroupId !== undefined) out.contextGroupId = it.contextGroupId;
      if (it.lines) out.lines = it.lines;
      if (it.husbandLines) out.husbandLines = it.husbandLines;
      if (it.wifeLines) out.wifeLines = it.wifeLines;
      return out;
    });
  }

  // 2026-11-01 (Phase 2): the dashed "+ Add Sibling"/"+ Add Child" tree-level buttons are gone --
  // both actions now live on the clicked PERSON's own Profile Card instead (see openProfileCard()
  // below), which is exactly as reachable: click either founder shown here (or anyone in the
  // bottom row) and use the card's own button. "+ Add Father's/Mother's Family" stays -- a
  // structurally different action (filling an EMPTY top-level slot), not tied to any one person.
  function buildTopRowItems(nbh) {
    var bySide = {};
    (nbh.parent_groups || []).forEach(function (g) { bySide[g.side] = g; });
    var husbandItem = bySide.husband
      ? Object.assign({ kind: "unit", data: bySide.husband, role: "husband" }, sizeUnitCard(bySide.husband))
      : { kind: "add-parents", side: "husband", width: UNIT_W, height: UNIT_H };
    var wifeItem = bySide.wife
      ? Object.assign({ kind: "unit", data: bySide.wife, role: "wife" }, sizeUnitCard(bySide.wife))
      : { kind: "add-parents", side: "wife", width: UNIT_W, height: UNIT_H };
    return [husbandItem, wifeItem];
  }

  function buildBottomRowItems(nbh) {
    return (nbh.child_groups || []).map(function (g) { return Object.assign({ kind: "unit", data: g }, sizeUnitCard(g)); })
      .concat((nbh.unmarried_children || []).map(function (p) {
        return Object.assign({ kind: "person", data: p, contextGroupId: nbh.group_id }, sizeSingleCard(p));
      }));
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

  // height/husbandLines/wifeLines come from sizeUnitCard() (buildTopRowItems()/buildBottomRowItems()
  // already computed them once; never re-measured here). The rect's TOP edge is always -UNIT_H/2,
  // same pixel position as the original fixed-UNIT_H design -- a card only ever grows DOWNWARD to
  // fit extra wrapped lines, so title/avatar/first line of text sit exactly where they always did
  // and only the subtitle/divider/bottom edge/chat-icon-row move down to match the real height.
  function renderUnitCard(group, unit, width, height, isSelf, role, husbandLines, wifeLines) {
    var topY = -UNIT_H / 2;
    var rectCls = "ft-unit-rect" + (unit.is_dormant ? " is-dormant" : "") + (" " + roleClass(role)).trimEnd();
    group.append("rect").attr("class", rectCls)
      .attr("x", -width / 2).attr("y", topY).attr("width", width).attr("height", height).attr("rx", 12);
    group.append("text").attr("class", "ft-unit-title").attr("y", topY - 10).text(unit.name);
    group.append("text").attr("class", "ft-unit-subtitle").attr("y", topY + height + 16).text(unitSubtitle(unit));

    renderPersonHalf(group, unit.husband, -width / 4, unit.group_id, husbandLines);
    renderPersonHalf(group, unit.wife, width / 4, unit.group_id, wifeLines);
    group.append("line").attr("class", "ft-unit-divider").attr("x1", 0).attr("x2", 0)
      .attr("y1", topY + 8).attr("y2", topY + height - 8);

    // 2026-10-27: the SELF card's own click opens its chat directly (see the click-wiring below)
    // -- but a neighbor unit card's click still NAVIGATES (re-centers the tree there), since
    // losing that would make a multi-generation tree unusable. This icon is the explicit
    // "open this neighbor's chat without navigating away" escape hatch.
    if (!isSelf) {
      var chatIcon = group.append("g").attr("class", "ft-chat-icon")
        .attr("transform", "translate(" + (width / 2 - 18) + "," + (topY + 18) + ")")
        .on("click", function (event) {
          event.stopPropagation();
          openFamilyChat(unit.group_id);
        });
      chatIcon.append("circle").attr("r", 13);
      chatIcon.append("text").attr("class", "ft-chat-icon-glyph").attr("y", 5).text("💬");
    }
  }

  // 2026-11-01 (Phase 2): every individual person -- claimed or not -- is now clickable, opening
  // the Profile Card (replaces the old unclaimed-only openEditModal()). contextGroupId is whichever
  // unit this person was rendered as part of here -- the Profile Card's own "+ Add Child" passes it
  // straight through as add_child_to_node()'s group_id, so it never has to guess which of a
  // person's own units (if they founded more than one) a new child belongs to. lines (from
  // sizeUnitCard()) is this person's own pre-measured, possibly-wrapped label.
  function renderPersonHalf(group, person, offsetX, contextGroupId, lines) {
    var cls = "ft-person" + (!person || !person.claimed ? " is-empty" : "")
      + (person && person.is_deceased ? " is-deceased" : "") + (person && person.is_viewer ? " is-viewer" : "");
    var p = group.append("g").attr("class", cls).attr("transform", "translate(" + offsetX + ",0)");
    renderAvatar(p, person, 0, -12, AVATAR_R);
    var textEl = p.append("text");
    (lines && lines.length ? lines : [person ? personLabel(person) : "+ Add"]).forEach(function (line, i) {
      textEl.append("tspan").attr("x", 0).attr("y", 18 + i * LINE_H).text(line);
    });
    if (person) {
      p.style("cursor", "pointer").on("click", function (event) {
        event.stopPropagation();
        openProfileCard(person, contextGroupId);
      });
    }
  }

  // Same growth rule as renderUnitCard(): the rect's top edge stays fixed at -UNIT_H*0.35, only
  // the bottom grows to fit wrapped lines.
  function renderPersonCard(group, person, width, height, contextGroupId, lines) {
    var topY = -UNIT_H * 0.35;
    var cls = "ft-single-rect" + (person.is_deceased ? " is-deceased" : "") + (!person.claimed ? " is-empty" : "") + (person.is_viewer ? " is-viewer" : "");
    group.append("rect").attr("class", cls)
      .attr("x", -width / 2).attr("y", topY).attr("width", width).attr("height", height).attr("rx", 10);
    renderAvatar(group, person, 0, topY + 12, AVATAR_R * 0.8);
    var textEl = group.append("text").attr("class", person.claimed ? null : "ft-empty-label");
    (lines && lines.length ? lines : [person ? personLabel(person) : "+ Add"]).forEach(function (line, i) {
      textEl.append("tspan").attr("x", 0).attr("y", topY + 34 + i * LINE_H).text(line);
    });
    group.style("cursor", "pointer").on("click", function (event) {
      event.stopPropagation();
      openProfileCard(person, contextGroupId);
    });
  }

  function renderAddUnitCard(group, width, label) {
    group.append("rect").attr("class", "ft-unit-rect ft-add-rect")
      .attr("x", -width / 2).attr("y", -UNIT_H / 2).attr("width", width).attr("height", UNIT_H).attr("rx", 12);
    group.append("text").text(label);
  }

  function renderNeighborhood(nbh) {
    var selfSize = sizeUnitCard(nbh);
    var selfCard = { x: 0, y: 0, width: selfSize.width, height: selfSize.height, kind: "unit", data: nbh, role: "self",
                      husbandLines: selfSize.husbandLines, wifeLines: selfSize.wifeLines };
    var selfTopOffset = -UNIT_H / 2;
    var selfBottomOffset = -UNIT_H / 2 + selfSize.height;

    // Every card's TOP edge is a fixed constant offset from its own center regardless of height
    // (unit: -UNIT_H/2; person: -UNIT_H*0.35; add-parents: -UNIT_H/2) -- only each card's BOTTOM
    // edge grows with wrapped lines (see sizeUnitCard()/sizeSingleCard() and renderUnitCard()'s own
    // note). So the gap between two rows only ever depends on the EARLIER row's actual (possibly
    // grown) bottom edge and the LATER row's fixed top-edge constant -- never a flat ROW_H guess.
    function bottomOffsetOf(card) { return card.kind === "unit" ? (-UNIT_H / 2 + card.height) : UNIT_H * 0.5; }
    function topOffsetMagnitudeOf(card) { return card.kind === "unit" ? UNIT_H / 2 : UNIT_H * 0.35; }

    var topItems = buildTopRowItems(nbh);
    var topRowMaxBottomOffset = topItems.length ? Math.max.apply(null, topItems.map(bottomOffsetOf)) : 0;
    var topRowY = selfTopOffset - ROW_GAP - topRowMaxBottomOffset;
    var parentCards = layoutRow(topItems, topRowY);

    var bottomItems = buildBottomRowItems(nbh);
    var bottomRowMaxTopOffsetMag = bottomItems.length ? Math.max.apply(null, bottomItems.map(topOffsetMagnitudeOf)) : UNIT_H / 2;
    var bottomRowY = selfBottomOffset + ROW_GAP + bottomRowMaxTopOffsetMag;
    var childCards = layoutRow(bottomItems, bottomRowY);

    var svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    var g = svg.append("g").attr("class", "ft-zoom-layer");
    var zoomBehavior = d3.zoom().scaleExtent([0.4, 2]).on("zoom", function (event) { g.attr("transform", event.transform); });
    svg.call(zoomBehavior);

    // Connecting lines, drawn first so cards sit visually on top of them. Endpoints attach to each
    // card's ACTUAL dimensions (its own bottom/top edge offset), not a shared fixed-height guess.
    var linkGen = d3.linkVertical().x(function (d) { return d.x; }).y(function (d) { return d.y; });
    var linksLayer = g.append("g").attr("class", "ft-links-layer");
    parentCards.forEach(function (p) {
      linksLayer.append("path").attr("class", "ft-link").attr("d", linkGen({
        source: { x: p.x, y: p.y + bottomOffsetOf(p) },
        target: { x: selfCard.x, y: selfCard.y + selfTopOffset },
      }));
    });
    childCards.forEach(function (c) {
      linksLayer.append("path").attr("class", "ft-link").attr("d", linkGen({
        source: { x: selfCard.x, y: selfCard.y + selfBottomOffset },
        target: { x: c.x, y: c.y - topOffsetMagnitudeOf(c) },
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
          renderPersonCard(group, d.data, d.width, d.height, d.contextGroupId, d.lines);
          break;
        case "add-parents":
          renderAddUnitCard(group, d.width, d.side === "husband" ? "+ Add Father's Family" : "+ Add Mother's Family");
          break;
        default:
          renderUnitCard(group, d.data, d.width, d.height, d === selfCard, d.role, d.husbandLines, d.wifeLines);
      }
    });

    // Click-to-navigate: any real unit card except the current (self) one. A click on an
    // individual person (either founder half, or a plain-card single person) is stopped from
    // bubbling here (see renderPersonHalf()/renderPersonCard()), so it opens the Profile Card
    // instead of navigating. A click on the small 💬 icon (see renderUnitCard()) also stops
    // propagation, so it opens that neighbor's chat instead of navigating.
    cardGroups.filter(function (d) { return d.kind === "unit" && d !== selfCard; })
      .style("cursor", "pointer")
      .on("click", function (event, d) { showTree(d.data.group_id); });

    // Click-to-chat: the SELF (center) card opens its own chat directly -- no separate "Chat"
    // button anywhere in the toolbar (2026-10-27).
    cardGroups.filter(function (d) { return d === selfCard; })
      .style("cursor", "pointer")
      .on("click", function () { openFamilyChat(nbh.group_id); });

    // Click-to-grow: the dashed "+ Add Father's/Mother's Family" button still opens ft-add-modal
    // (parents mode) -- "+ Add Sibling"/"+ Add Child" moved to the Profile Card, see above.
    cardGroups.filter(function (d) { return d.kind === "add-parents"; })
      .style("cursor", "pointer")
      .on("click", function (event, d) { openAddModal({ groupId: nbh.group_id, side: d.side }); });

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

  // Dynamic sizing (section 9.4): recalculates after a window resize or a mobile orientation
  // change (both fire the same "resize" event) by simply re-showing the current unit -- the
  // cheapest correct way to redo the whole measure-and-layout pass without a second, parallel
  // code path to keep in sync with renderNeighborhood() above. Debounced so a drag-resize doesn't
  // re-render on every intermediate pixel.
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (state.currentGroupId && !container.hidden) showTree(state.currentGroupId);
    }, 200);
  });

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

  // ---- Group chat (2026-10-27): GET/POST /api/family-groups/<id>/messages already existed as a
  // backend route with no frontend screen to open it from at all -- clicking a unit node is now
  // that screen. Built standalone here (not a shared helper with social.js's personal-group
  // renderChatShell()/renderMessages(), which are module-private to that file) -- reuses the same
  // .bd-*/QMAvatar markup conventions for visual consistency, at the cost of a little duplication. ----
  // 2026-10-28 ("living map" upgrade): slides in over .pt-side (the same column social.js's
  // showTab() hides for the Family Tree tab, since the D3 view wants the full panel width when
  // no chat is open) instead of a centered dq-modal that used to cover the whole tree.
  var chatPanel = document.getElementById("ft-chat-panel");
  var chatBody = document.getElementById("ft-chat-body");
  var ptSide = document.querySelector(".pt-side");
  var ptLayout = document.querySelector(".pt-layout");
  document.getElementById("ft-chat-panel-close").addEventListener("click", closeFamilyChat);

  function closeFamilyChat() {
    chatPanel.classList.remove("is-open");
    chatPanel.hidden = true;
    if (ptSide) { ptSide.hidden = true; ptSide.classList.remove("is-chat-mode"); }
    if (ptLayout) ptLayout.classList.add("pt-layout--full");
  }

  function openFamilyChat(groupId) {
    if (ptSide) { ptSide.hidden = false; ptSide.classList.add("is-chat-mode"); }
    if (ptLayout) ptLayout.classList.remove("pt-layout--full");
    chatPanel.hidden = false;
    // Slide-in: unhidden at opacity 0/translateX first, then .is-open added a frame later so the
    // CSS transition actually has something to animate from (adding the class in the same tick
    // hidden was cleared would just jump straight to the end state).
    chatPanel.classList.remove("is-open");
    requestAnimationFrame(function () { requestAnimationFrame(function () { chatPanel.classList.add("is-open"); }); });
    chatBody.innerHTML = "";
    chatBody.appendChild(el("p", "qm-dash-empty", "Loading…"));
    api("/api/family-groups/" + groupId + "/messages").then(function (d) {
      chatBody.innerHTML = "";
      var head = el("div", "bd-head");
      var ht = el("div", "bd-headtext");
      ht.appendChild(el("b", "bd-title", d.name));
      var memberCount = (d.members || []).length;
      ht.appendChild(el("small", "bd-sub", memberCount + " member" + (memberCount === 1 ? "" : "s")));
      head.appendChild(ht);
      chatBody.appendChild(head);

      var feed = el("div", "bd-feed"); feed.setAttribute("aria-live", "polite"); chatBody.appendChild(feed);
      if (!d.messages.length) {
        feed.appendChild(el("p", "bd-empty", "No messages yet — say hello."));
      } else {
        d.messages.forEach(function (m) {
          var row = el("div", "bd-msg" + (m.mine ? " is-mine" : ""));
          if (!m.mine) {
            var msgHead = el("div", "bd-msg-head");
            if (window.QMAvatar) msgHead.appendChild(QMAvatar.render({ name: m.who, gender: m.gender, profile_picture_url: m.profile_picture_url }, 24));
            msgHead.appendChild(el("b", "", m.who));
            row.appendChild(msgHead);
          }
          row.appendChild(document.createTextNode(m.text));
          feed.appendChild(row);
        });
        feed.scrollTop = feed.scrollHeight;
      }

      var form = el("form", "bd-compose"), ta = document.createElement("textarea");
      ta.rows = 2; ta.maxLength = 1000; ta.placeholder = "Message " + d.name + "…"; ta.required = true;
      var send = el("button", "", "Send"); send.type = "submit";
      form.appendChild(ta); form.appendChild(send);
      chatBody.appendChild(form);
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        api("/api/family-groups/" + groupId + "/messages", { text: ta.value }).then(function () {
          ta.value = ""; openFamilyChat(groupId);
        }).catch(function (er) { alert(er.message); });
      });
    }).catch(function (e) {
      chatBody.innerHTML = "";
      chatBody.appendChild(el("p", "bd-empty", e.message));
    });
  }

  // ---- Shared auto-search (2026-10-27): types a 12-digit Public ID, debounced search fires on
  // its own (no "Find" button anywhere), and the match renders as a profile-card preview with a
  // single action button -- "Link" (the Profile Card's own Connect Existing Member box, see
  // openProfileCard() above) or "Invite" (the Members modal's general "Add Member," no specific
  // node in play). Both call sites share this exact search/preview UI; only what the button DOES
  // differs, via `onAction(person, btn, code)` -- `code` is the raw digits typed, since /link needs
  // the 12-digit Public ID itself, not any field off the resolved profile. ----
  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }

  function wireAutoSearch(inputEl, resultEl, errorEl, actionLabel, onAction) {
    var run = debounce(function () {
      var code = inputEl.value.replace(/\D/g, "");
      resultEl.innerHTML = "";
      if (errorEl) errorEl.hidden = true;
      if (code.length !== 12) return;
      resultEl.appendChild(el("p", "qm-dash-empty", "Searching…"));
      api("/api/people/search?q=" + encodeURIComponent(code)).then(function (p) {
        resultEl.innerHTML = "";
        var card = el("div", "fw-suggestion-row");
        var top = el("div", "fw-suggestion-top");
        if (window.QMAvatar) top.appendChild(QMAvatar.render(p, 40));
        var textWrap = el("div", "fw-suggestion-text");
        textWrap.appendChild(el("p", "", p.name + " · " + (GENDER_LABEL[p.gender] || p.gender)));
        top.appendChild(textWrap);
        card.appendChild(top);
        var btn = el("button", "qm-btn qm-btn-primary", actionLabel); btn.type = "button";
        btn.addEventListener("click", function () { onAction(p, btn, code); });
        card.appendChild(btn);
        resultEl.appendChild(card);
      }).catch(function (e) {
        resultEl.innerHTML = "";
        if (errorEl) { errorEl.textContent = e.message; errorEl.hidden = false; }
      });
    }, 400);
    inputEl.addEventListener("input", run);
  }

  // ---- Profile Card (Phase 2, 2026-11-01): replaces the old click-an-empty-node modal above --
  // EVERY individual person (claimed or not) now opens this. Two bodies share one card shell,
  // toggled by the clicked person's own claimed status: ft-profile-claimed-body (read-only,
  // authorized registered-member data) or ft-profile-unclaimed-body (the placeholder editor --
  // Public ID link, reusing the exact same wireAutoSearch() the Members modal already uses below,
  // or manual First/Middle/Last/Gender/Approximate Age entry). See templates/dashboard.html's
  // #ft-profile-modal for the markup this drives. ----
  var profileModal = document.getElementById("ft-profile-modal");
  var profileAvatarEl = document.getElementById("ft-profile-avatar");
  var profileNameEl = document.getElementById("ft-profile-name");
  var profileRelationshipEl = document.getElementById("ft-profile-relationship");
  var profileBadgeEl = document.getElementById("ft-profile-badge");
  var profileClaimedBodyEl = document.getElementById("ft-profile-claimed-body");
  var profileUnclaimedBodyEl = document.getElementById("ft-profile-unclaimed-body");
  var profileLinkInput = document.getElementById("ft-profile-link-input");
  var profileLinkResultEl = document.getElementById("ft-profile-link-result");
  var profileFirstNameInput = document.getElementById("ft-profile-first-name");
  var profileMiddleNameInput = document.getElementById("ft-profile-middle-name");
  var profileLastNameInput = document.getElementById("ft-profile-last-name");
  var profileGenderBtns = Array.prototype.slice.call(document.querySelectorAll("#ft-profile-gender-group .qm-gender-btn"));
  var profileApproxAgeInput = document.getElementById("ft-profile-approx-age");
  var profileSaveBtn = document.getElementById("ft-profile-save-btn");
  var profileSaveErrorEl = document.getElementById("ft-profile-save-error");
  var profileSaveSuccessEl = document.getElementById("ft-profile-save-success");
  var profileCascadeEl = document.getElementById("ft-profile-cascade");
  var profileInlineFormEl = document.getElementById("ft-profile-inline-form");
  var profileActionErrorEl = document.getElementById("ft-profile-action-error");

  // nodeId/contextGroupId are the only state a reopen needs -- contextGroupId is whichever unit
  // the clicked card was rendered as part of (see renderPersonHalf()/renderPersonCard() above),
  // passed straight through as add_child_to_node()'s own group_id so Add Child never has to guess
  // which of this person's own units (if they founded more than one) a new child belongs to.
  var profile = { nodeId: null, contextGroupId: null, gender: null };

  profileModal.addEventListener("click", function (e) {
    if (e.target === profileModal || e.target.hasAttribute("data-close")) profileModal.hidden = true;
  });

  function genderDisplay(gender) { return GENDER_LABEL[gender] || "Unknown"; }
  function ageDisplay(person) {
    if (person.age_years == null) return "Unknown";
    return person.age_years + (person.age_is_approx ? " (approx.)" : "");
  }

  function renderClaimedBody(person) {
    profileClaimedBodyEl.innerHTML = "";
    [["Full Name", person.name], ["Age", ageDisplay(person)], ["Gender", genderDisplay(person.gender)],
     ["Account ID", person.account_id || "—"]].forEach(function (pair) {
      var row = document.createElement("div");
      row.appendChild(el("dt", "", pair[0]));
      row.appendChild(el("dd", "", pair[1]));
      profileClaimedBodyEl.appendChild(row);
    });
  }

  // First/Middle/Last are never stored as separate columns (family_nodes.display_name is a
  // single field -- see docs/family_tree/PHASE_2_FRONTEND_OVERHAUL_REPORT.md) -- splitting the
  // current name into 3 fields here, and rejoining them on Save, is what satisfies "preserve the
  // separate name components if the existing data model supports them... do not silently discard
  // an existing name when a user edits one field": whichever field the user leaves untouched
  // still carries its own current value through to the rejoined name.
  function splitName(name) {
    var parts = (name || "").trim().split(/\s+/).filter(Boolean);
    if (parts.length <= 1) return { first: parts[0] || "", middle: "", last: "" };
    if (parts.length === 2) return { first: parts[0], middle: "", last: parts[1] };
    return { first: parts[0], middle: parts.slice(1, -1).join(" "), last: parts[parts.length - 1] };
  }

  function renderUnclaimedBody(person) {
    profileLinkInput.value = "";
    profileLinkResultEl.innerHTML = "";
    var parts = splitName(person.name);
    profileFirstNameInput.value = parts.first;
    profileMiddleNameInput.value = parts.middle;
    profileLastNameInput.value = parts.last;
    profile.gender = person.gender || null;
    profileGenderBtns.forEach(function (b) { b.classList.toggle("is-active", b.getAttribute("data-gender") === person.gender); });
    profileApproxAgeInput.value = person.approximate_age != null ? person.approximate_age : "";
    profileSaveErrorEl.hidden = true;
    profileSaveSuccessEl.hidden = true;
  }

  function openProfileCard(person, contextGroupId) {
    profile.nodeId = person.id;
    profile.contextGroupId = contextGroupId || null;

    profileAvatarEl.innerHTML = "";
    if (window.QMAvatar) profileAvatarEl.appendChild(QMAvatar.render(person, 64));
    profileNameEl.textContent = person.name + (person.is_deceased ? " 🕊️" : "");
    profileRelationshipEl.textContent = person.is_viewer ? "You" : (person.relationship_to_viewer || "Family Member");
    profileBadgeEl.textContent = person.claimed ? "✅ Registered Member" : "Placeholder";
    profileBadgeEl.className = "ft-profile-badge" + (person.claimed ? " is-claimed" : " is-unclaimed");

    profileClaimedBodyEl.hidden = !person.claimed;
    profileUnclaimedBodyEl.hidden = !!person.claimed;
    profileCascadeEl.hidden = true; profileCascadeEl.innerHTML = "";
    profileInlineFormEl.hidden = true; profileInlineFormEl.innerHTML = "";
    profileActionErrorEl.hidden = true;

    if (person.claimed) renderClaimedBody(person); else renderUnclaimedBody(person);
    profileModal.hidden = false;
  }

  // ---- Cascading discovery (section 7): after a successful Public ID link, shows whatever the
  // tree already knows about that person's own family -- each row opens either that relative's
  // own Profile Card (a person) or navigates the D3 view there (a unit), so the user can explore
  // it without the card ever trying to merge a second generation onto one SVG canvas (the
  // existing neighborhood model stays a single centered unit at a time, by design). ----
  function cascadePersonRow(label, person) {
    if (!person) return null;
    var row = el("div", "ft-cascade-row");
    row.appendChild(el("span", "ft-cascade-label", label));
    var link = el("button", "qm-btn qm-btn-ghost ft-cascade-link", person.name);
    link.type = "button";
    link.addEventListener("click", function () { openProfileCard(person, null); });
    row.appendChild(link);
    return row;
  }
  function cascadeGroupRow(label, group) {
    if (!group) return null;
    var who = group.husband ? group.husband.name : (group.wife ? group.wife.name : group.name);
    var row = el("div", "ft-cascade-row");
    row.appendChild(el("span", "ft-cascade-label", label));
    var link = el("button", "qm-btn qm-btn-ghost ft-cascade-link", who + " →");
    link.type = "button";
    link.addEventListener("click", function () { profileModal.hidden = true; showTree(group.group_id); });
    row.appendChild(link);
    return row;
  }
  function renderCascadeDiscovery(cascade) {
    profileCascadeEl.innerHTML = "";
    if (!cascade) { profileCascadeEl.hidden = true; return; }
    var rows = [];
    if (cascade.parents) {
      rows.push(cascadePersonRow("Father", cascade.parents.father));
      rows.push(cascadePersonRow("Mother", cascade.parents.mother));
    }
    (cascade.siblings || []).forEach(function (s) { rows.push(cascadePersonRow("Sibling", s)); });
    (cascade.grandparent_groups || []).forEach(function (g) {
      rows.push(cascadeGroupRow(g.side === "paternal" ? "Paternal Grandparents" : "Maternal Grandparents", g));
    });
    rows.push(cascadePersonRow("Spouse", cascade.spouse));
    (cascade.children || []).forEach(function (c) { rows.push(cascadePersonRow("Child", c)); });
    (cascade.child_groups || []).forEach(function (g) { rows.push(cascadeGroupRow("Their own family", g)); });
    rows = rows.filter(Boolean);
    if (!rows.length) { profileCascadeEl.hidden = true; return; }
    profileCascadeEl.appendChild(el("h4", "qm-form-section-title", "🌳 Family Found"));
    rows.forEach(function (r) { profileCascadeEl.appendChild(r); });
    profileCascadeEl.hidden = false;
  }

  wireAutoSearch(profileLinkInput, profileLinkResultEl, null, "Link", function (p, btn, code) {
    btn.disabled = true; btn.textContent = "Linking…";
    var linkedNodeId = profile.nodeId;
    var ctxGroupId = profile.contextGroupId;
    api("/api/family/node/" + linkedNodeId + "/link", { user_id: code }).then(function () {
      if (state.currentGroupId) showTree(state.currentGroupId);
      return api("/api/family/person/" + linkedNodeId + "/cascade");
    }).then(function (cascade) {
      openProfileCard(cascade.node, ctxGroupId);
      renderCascadeDiscovery(cascade);
    }).catch(function (e) {
      btn.disabled = false; btn.textContent = "Link";
      profileLinkResultEl.innerHTML = "";
      profileLinkResultEl.appendChild(el("p", "qm-summary-error", e.message));
    });
  });

  profileGenderBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      profile.gender = btn.getAttribute("data-gender");
      profileGenderBtns.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
    });
  });

  profileSaveBtn.addEventListener("click", function () {
    profileSaveErrorEl.hidden = true; profileSaveSuccessEl.hidden = true;
    var first = profileFirstNameInput.value.trim();
    if (!first) { profileSaveErrorEl.textContent = "First name is required."; profileSaveErrorEl.hidden = false; return; }
    var name = [first, profileMiddleNameInput.value.trim(), profileLastNameInput.value.trim()].filter(Boolean).join(" ");
    var payload = { name: name, gender: profile.gender };
    var approxAge = profileApproxAgeInput.value.trim();
    if (approxAge !== "") payload.approximate_age = parseInt(approxAge, 10);
    profileSaveBtn.disabled = true; profileSaveBtn.textContent = "Saving…";
    api("/api/family/node/" + profile.nodeId + "/details", payload).then(function () {
      profileSaveBtn.disabled = false; profileSaveBtn.textContent = "Save";
      profileSaveSuccessEl.hidden = false;
      if (state.currentGroupId) showTree(state.currentGroupId);
    }).catch(function (e) {
      // Validation failure: the fields above keep exactly what the user typed, nothing is reset.
      profileSaveBtn.disabled = false; profileSaveBtn.textContent = "Save";
      profileSaveErrorEl.textContent = e.message; profileSaveErrorEl.hidden = false;
    });
  });

  // ---- Contextual relationship actions (section 6): + Add Sibling/Child/Spouse, each a small
  // inline form inside the card itself rather than a separate modal -- one shared shell, built
  // fresh per action so there's exactly one place that knows how to build it. ----
  var ADD_ACTION = {
    sibling: { route: "sibling", verb: "Sibling", needsGroupContext: false },
    child: { route: "child", verb: "Child", needsGroupContext: true },
    spouse: { route: "spouse", verb: "Spouse", needsGroupContext: false },
  };

  function openInlineAddForm(kind) {
    var cfg = ADD_ACTION[kind];
    profileActionErrorEl.hidden = true;
    profileInlineFormEl.innerHTML = "";
    profileInlineFormEl.hidden = false;

    var nameLabel = el("label", "qm-field");
    nameLabel.appendChild(el("span", "", cfg.verb + "'s Name"));
    var nameInputEl = document.createElement("input");
    nameInputEl.type = "text"; nameInputEl.maxLength = 80;
    nameLabel.appendChild(nameInputEl);
    profileInlineFormEl.appendChild(nameLabel);

    var genderGroup = el("div", "qm-gender-group");
    var chosenGender = null;
    [["male", "👦", "Male"], ["female", "👧", "Female"], ["both", "⚧️", "Third Gender"]].forEach(function (g) {
      var genderBtn = document.createElement("button");
      genderBtn.type = "button"; genderBtn.className = "qm-gender-btn";
      genderBtn.innerHTML = g[1] + "<span>" + g[2] + "</span>";
      genderBtn.addEventListener("click", function () {
        chosenGender = g[0];
        Array.prototype.forEach.call(genderGroup.children, function (b) { b.classList.toggle("is-active", b === genderBtn); });
      });
      genderGroup.appendChild(genderBtn);
    });
    profileInlineFormEl.appendChild(genderGroup);

    var actionsRow = el("div", "qm-summary-actions");
    var cancelBtn = el("button", "qm-btn qm-btn-ghost", "Cancel");
    cancelBtn.type = "button";
    cancelBtn.addEventListener("click", function () { profileInlineFormEl.hidden = true; profileInlineFormEl.innerHTML = ""; });
    var saveBtn = el("button", "qm-btn qm-btn-primary", "Add " + cfg.verb);
    saveBtn.type = "button";
    saveBtn.addEventListener("click", function () {
      var name = nameInputEl.value.trim();
      if (!name) { profileActionErrorEl.textContent = "A name is required."; profileActionErrorEl.hidden = false; return; }
      var payload = { name: name, gender: chosenGender };
      if (cfg.needsGroupContext && profile.contextGroupId) payload.group_id = profile.contextGroupId;
      var actedNodeId = profile.nodeId;
      saveBtn.disabled = true; saveBtn.textContent = "Adding…";
      api("/api/family/person/" + actedNodeId + "/" + cfg.route, payload).then(function (result) {
        if (state.currentGroupId) showTree(state.currentGroupId);
        profileInlineFormEl.hidden = true; profileInlineFormEl.innerHTML = "";
        return api("/api/family/person/" + result.node_id + "/cascade").then(function (cascade) {
          if (cascade) openProfileCard(cascade.node, result.group_id || profile.contextGroupId);
        });
      }).catch(function (e) {
        saveBtn.disabled = false; saveBtn.textContent = "Add " + cfg.verb;
        profileActionErrorEl.textContent = e.message; profileActionErrorEl.hidden = false;
      });
    });
    actionsRow.appendChild(cancelBtn);
    actionsRow.appendChild(saveBtn);
    profileInlineFormEl.appendChild(actionsRow);
    nameInputEl.focus();
  }

  document.getElementById("ft-profile-add-sibling-btn").addEventListener("click", function () { openInlineAddForm("sibling"); });
  document.getElementById("ft-profile-add-child-btn").addEventListener("click", function () { openInlineAddForm("child"); });
  document.getElementById("ft-profile-add-spouse-btn").addEventListener("click", function () { openInlineAddForm("spouse"); });

  // ---- "+Add" modal (2026-10-20): fills a missing husband-/wife-side parents' unit (POST
  // .../add-parents) -- structurally different from Add Sibling/Child/Spouse (which act on a
  // specific PERSON's own units, see the Profile Card above): this fills an EMPTY top-level slot
  // that isn't tied to any one clickable person yet. 'child' mode is gone (2026-11-01) -- Add
  // Sibling/Add Child moved to the Profile Card. ----
  var addModal = document.getElementById("ft-add-modal");
  var addModalTitle = document.getElementById("ft-add-modal-title");
  var addFatherInput = document.getElementById("ft-add-father-name");
  var addMotherInput = document.getElementById("ft-add-mother-name");
  var addErrorEl = document.getElementById("ft-add-error");
  var addState = { groupId: null, side: null };

  addModal.addEventListener("click", function (e) {
    if (e.target === addModal || e.target.hasAttribute("data-close")) addModal.hidden = true;
  });

  function openAddModal(opts) {
    addState.groupId = opts.groupId;
    addState.side = opts.side || null;
    addErrorEl.hidden = true;
    addFatherInput.value = ""; addMotherInput.value = "";
    addModalTitle.textContent = opts.side === "husband" ? "Add Father's Family" : "Add Mother's Family";
    addModal.hidden = false;
  }

  function reloadAfterAdd() {
    addModal.hidden = true;
    if (state.currentGroupId) showTree(state.currentGroupId);
  }

  document.getElementById("ft-add-save-btn").addEventListener("click", function () {
    addErrorEl.hidden = true;
    var father = addFatherInput.value.trim(), mother = addMotherInput.value.trim();
    if (!father && !mother) { addErrorEl.textContent = "Enter at least one parent's name."; addErrorEl.hidden = false; return; }
    api("/api/family/node/" + addState.groupId + "/add-parents", {
      side: addState.side,
      father: father ? { name: father } : null,
      mother: mother ? { name: mother } : null,
    }).then(reloadAfterAdd).catch(function (e) { addErrorEl.textContent = e.message; addErrorEl.hidden = false; });
  });

  // ---- Members modal (2026-10-25): who's actually in this unit, with their role, plus an
  // "Add Member by Public ID" box -- previously the only way to see a unit's membership was the
  // D3 cards themselves, and there was no admin-initiated invite at all for Family Groups (only
  // the self-service "request to join" flow). ----
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  var GENDER_LABEL = { male: "Male", female: "Female", both: "Third Gender" };
  // 'founder' | 'admin' | 'member' (2026-10-27) -- the honest three-way label. A unit's creator
  // is also always granted admin even when they're just a plain child (create_group()'s own
  // additive grant), so is_admin alone can't tell them apart from an actual husband/wife founder.
  var ROLE_LABEL = { founder: "Founder", admin: "Admin", member: "Member" };

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
      li.appendChild(el("span", "ft-member-role" + (m.role !== "member" ? " is-admin" : ""), ROLE_LABEL[m.role] || "Member"));
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

  // 2026-10-27: no specific placeholder node is in play here (this is the general "Add Member,"
  // not editing a known Father/Mother/Spouse/Child slot) -- so the shared auto-search's action is
  // always "Invite" (POST .../invite), never "Link". See wireAutoSearch()'s own note for why the
  // two call sites share this search/preview UI but differ in what the button does.
  wireAutoSearch(membersSearchInput, membersSearchResult, membersErrorEl, "Send Invite", function (p, btn) {
    btn.disabled = true; btn.textContent = "Inviting…";
    api("/api/family-groups/" + state.currentGroupId + "/invite", { user_id: p.user_id }).then(function () {
      btn.textContent = "✓ Invited"; membersSearchInput.value = "";
    }).catch(function (e) {
      btn.disabled = false; btn.textContent = "Send Invite";
      membersErrorEl.textContent = e.message; membersErrorEl.hidden = false;
    });
  });

  // closeChat (2026-10-28): social.js's showTab() calls this when navigating away from the
  // Family Tree tab, so the slide-in chat panel never stays open (and .pt-side's is-chat-mode
  // never stays set) under a different tab's own content.
  window.QMFamilyTree = { showTree: showTree, closeChat: closeFamilyChat };
})();
