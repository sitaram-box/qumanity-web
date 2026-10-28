/**
 * tutorial.js — a real spotlight walkthrough over the live dashboard (not a separate slideshow):
 * each step dims the page, cuts a highlighted hole around one real element, switches tabs for
 * it if needed, and shows a title/description popup with Step X of Y + Next/Skip/Exit.
 *
 * Shown once after first sign-in (review_core.py's tour status, shared with the phone app's own
 * tour — GET/POST /api/onboarding[/tour]); replayable any time from the Private tab's "🎓 Tutorial"
 * button. A step whose target isn't on screen right now (e.g. the election card, or the Post
 * button when posting isn't open at this level) is skipped automatically, never blocking the tour.
 */
(function () {
  "use strict";

  function $(sel, root) { return (root || document).querySelector(sel); }

  // 2026-10-28 ("purpose tour" upgrade): bodies now name what CHANGES because of the action, not
  // just the rule that governs it -- "a post that climbs reaches Earth" instead of "posts are
  // voted on for seven days." `stat`, where present, is a function (not a static string) called
  // fresh at render() time, reading data another part of the page already loaded (board.js's own
  // window.QMBoardLastView, set every time its board panel renders) -- no fetch of its own, and it
  // genuinely varies: an empty village gets the Founder's own empty_prompt CTA instead of a count.
  var STEPS = [
    {
      key: "tabs", tab: null, selector: ".qm-dash-tabs",
      title: "This is where it starts.",
      body: "Four timelines of your life, side by side: Global, Public, Personal, Private. Everything else in Qumanity happens inside one of these four.",
    },
    {
      key: "board", tab: "public", selector: "#bd-public-board .bd-feed",
      title: "Your village has a voice. This is it.",
      body: "A post that holds up for seven days doesn't stay a village matter — it climbs to the Tehsil, then higher, carrying your name with it the whole way.",
      stat: function () {
        var v = window.QMBoardLastView && window.QMBoardLastView["bd-public-board"];
        if (!v) return null;
        if (v.empty_prompt) return "🌱 " + v.empty_prompt.cta + " — right now, it would be the very first.";
        var live = (v.posts || []).filter(function (p) { return p.status === "active"; }).length;
        if (!live) return null;
        return "📊 Right now: " + live + " post" + (live === 1 ? " is" : "s are") + " being voted on in " + v.group + ".";
      },
    },
    {
      key: "reports", tab: "private", selector: "#qm-myreports-card",
      title: "When something needs fixing, say so.",
      body: "A Citizen Report isn't a suggestion box nobody reads — the council has ten days to answer, and you watch that answer land right here, not somewhere you have to go looking for it.",
    },
    {
      key: "wallet", tab: "private", selector: "#qm-wallet-card",
      title: "What you give, kept.",
      body: "Every Qoin you earn and every point of Karma your village gives you lands in this same ledger — permanent, visible to you alone, and never quietly rewritten by anyone, including the people who run this place.",
    },
    {
      key: "next", tab: "public", selector: "#bd-public-board",
      title: "Now make it real.",
      body: "A post, a vote, a report — any one of them is a real mark your village will carry forward. Nothing here happens without you making it happen first.",
      nextLabel: "Let's go →",
    },
  ];

  var overlay, spotlight, popup, state = null;

  function build() {
    overlay = document.createElement("div");
    overlay.className = "qm-tour-overlay";
    spotlight = document.createElement("div");
    spotlight.className = "qm-tour-spotlight";
    popup = document.createElement("div");
    popup.className = "qm-tour-popup";
    popup.setAttribute("role", "dialog");
    popup.setAttribute("aria-modal", "true");
    document.body.appendChild(overlay);
    document.body.appendChild(spotlight);
    document.body.appendChild(popup);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
  }

  function activateTab(tabName) {
    if (!tabName) return;
    var btn = document.querySelector('.qm-dash-tab[data-tab="' + tabName + '"]');
    if (btn && !btn.classList.contains("is-active")) btn.click();
  }

  function isVisible(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && el.offsetParent !== null;
  }

  function reposition() {
    if (!state || state.index >= STEPS.length) return;
    var step = STEPS[state.index];
    var el = $(step.selector);
    if (!isVisible(el)) { advance(); return; }
    var r = el.getBoundingClientRect();
    var pad = 8;
    spotlight.style.top = (r.top - pad) + "px";
    spotlight.style.left = (r.left - pad) + "px";
    spotlight.style.width = (r.width + pad * 2) + "px";
    spotlight.style.height = (r.height + pad * 2) + "px";

    var popupW = Math.min(360, window.innerWidth - 32);
    var popupH = popup.getBoundingClientRect().height || 180;
    var margin = 12;
    var popupTop = r.bottom + 16;
    if (popupTop + popupH > window.innerHeight - margin) popupTop = r.top - 16 - popupH;
    popupTop = Math.max(margin, Math.min(popupTop, window.innerHeight - popupH - margin));
    var popupLeft = Math.min(Math.max(margin, r.left), window.innerWidth - popupW - margin);
    popup.style.top = popupTop + "px";
    popup.style.left = popupLeft + "px";
    popup.style.width = popupW + "px";
  }

  function render() {
    var step = STEPS[state.index];
    popup.innerHTML = "";

    var head = document.createElement("div");
    head.className = "qm-tour-head";
    var stepNum = document.createElement("span");
    stepNum.className = "qm-tour-stepnum";
    stepNum.textContent = "Step " + (state.index + 1) + " of " + STEPS.length;
    head.appendChild(stepNum);
    var exitBtn = document.createElement("button");
    exitBtn.type = "button"; exitBtn.className = "qm-tour-exit"; exitBtn.setAttribute("aria-label", "Exit tutorial");
    exitBtn.textContent = "×";
    exitBtn.addEventListener("click", function () { endTour("skipped"); });
    head.appendChild(exitBtn);
    popup.appendChild(head);

    var title = document.createElement("h4");
    title.textContent = step.title;
    popup.appendChild(title);
    var body = document.createElement("p");
    body.textContent = step.body;
    popup.appendChild(body);

    // 2026-10-28: the live stat line, when step.stat() has something to say right now -- omitted
    // entirely (not shown empty) when there's no board data loaded yet or nothing to report, so
    // this never shows a stale or placeholder number.
    if (typeof step.stat === "function") {
      var statText = step.stat();
      if (statText) {
        var stat = document.createElement("p");
        stat.className = "qm-tour-stat";
        stat.textContent = statText;
        popup.appendChild(stat);
      }
    }

    var actions = document.createElement("div");
    actions.className = "qm-tour-actions";
    var skip = document.createElement("button");
    skip.type = "button"; skip.className = "qm-btn qm-btn-ghost"; skip.textContent = "Skip";
    skip.addEventListener("click", function () { endTour("skipped"); });
    actions.appendChild(skip);
    var next = document.createElement("button");
    next.type = "button"; next.className = "qm-btn qm-btn-primary"; next.textContent = step.nextLabel || "Next →";
    next.addEventListener("click", function () { advance(); });
    actions.appendChild(next);
    popup.appendChild(actions);

    activateTab(step.tab);
    requestAnimationFrame(function () {
      var el = $(step.selector);
      if (el) el.scrollIntoView({ block: "center", behavior: "auto" });
      requestAnimationFrame(reposition);
    });
  }

  function showCompletion() {
    spotlight.style.width = spotlight.style.height = "0px";
    popup.className = "qm-tour-popup qm-tour-popup--done";
    popup.innerHTML = "";
    var title = document.createElement("h4");
    title.textContent = "🎉 You're ready to use Qumanity!";
    popup.appendChild(title);
    var body = document.createElement("p");
    body.textContent = "You can replay this tutorial any time from the Private tab.";
    popup.appendChild(body);
    var label = document.createElement("label");
    label.className = "qm-tour-dontshow";
    var cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = true; cb.id = "qm-tour-dontshow-cb";
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" Don't show this tutorial again"));
    popup.appendChild(label);
    var actions = document.createElement("div");
    actions.className = "qm-tour-actions";
    var done = document.createElement("button");
    done.type = "button"; done.className = "qm-btn qm-btn-primary"; done.textContent = "Start using Qumanity →";
    done.addEventListener("click", function () { endTour(cb.checked ? "done" : "skipped"); });
    actions.appendChild(done);
    popup.appendChild(actions);
    popup.style.position = "fixed";
    popup.style.top = "50%"; popup.style.left = "50%";
    popup.style.transform = "translate(-50%, -50%)";
    popup.style.width = Math.min(360, window.innerWidth - 32) + "px";
  }

  function advance() {
    var next = state.index + 1;
    while (next < STEPS.length) {
      activateTab(STEPS[next].tab);
      if (isVisible($(STEPS[next].selector))) { state.index = next; popup.style.position = ""; popup.className = "qm-tour-popup"; render(); return; }
      next += 1;
    }
    state.index = STEPS.length;
    showCompletion();
  }

  function endTour(status) {
    if (overlay) overlay.remove();
    if (spotlight) spotlight.remove();
    if (popup) popup.remove();
    overlay = spotlight = popup = null;
    var wasTour = !!state;
    state = null;
    if (wasTour) {
      fetch("/api/onboarding/tour", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: status }),
      }).catch(function () {});
    }
  }

  function start() {
    if (state) return;
    build();
    state = { index: -1 };
    advance();
  }

  window.QumanityTutorial = { start: start };

  var replayBtn = document.getElementById("tutorial-replay-btn");
  if (replayBtn) replayBtn.addEventListener("click", start);

  if (document.getElementById("qm-dash-private")) {
    fetch("/api/onboarding").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.tour) start();
    }).catch(function () {});
  }
})();
