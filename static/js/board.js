/**
 * board.js — Collective Board (group-chat style feed of posts that are voted up from Village to Earth)
 * and the Q-Punch council popup. Global and Public tabs each get a board that follows the level tab chosen above it.
 */
(function () {
  "use strict";

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function api(url, body) {
    var opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(url, opt).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); });
  }
  function ago(iso) {
    var s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "just now"; if (s < 3600) return Math.floor(s / 60) + " min ago";
    if (s < 86400) return Math.floor(s / 3600) + " h ago"; return Math.floor(s / 86400) + " d ago";
  }
  function left(iso) {
    var s = (new Date(iso).getTime() - Date.now()) / 1000;
    if (s <= 0) return "closing now";
    var d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    return d ? d + "d " + h + "h left" : h ? h + "h " + m + "m left" : m + "m left";
  }
  function fmt(n) { return (n > 0 ? "+" : "") + n.toLocaleString(); }

  var REACTION_ICON = { agree: "\uD83D\uDC4D", disagree: "\uD83D\uDC4E", read: "\uD83D\uDC41\uFE0F" };
  function reactionBar(m, scope, memberCount, onChange) {
    var bar = el("div", "bd-reactions");
    ["agree", "disagree", "read"].forEach(function (kind) {
      var mine = m.reactions.mine === kind;
      var btn = el("button", "bd-react" + (mine ? " is-on" : ""), REACTION_ICON[kind] + " " + m.reactions[kind]); btn.type = "button";
      btn.addEventListener("click", function () {
        api("/api/reactions/" + scope + "/" + m.id, { reaction: mine ? null : kind }).then(onChange).catch(function (e) { alert(e.message); });
      });
      bar.appendChild(btn);
    });
    bar.appendChild(el("small", "bd-react-total", "out of " + memberCount + " member" + (memberCount === 1 ? "" : "s")));
    return bar;
  }

  // ---- Q-Punch popup ----
  var qpModal = document.getElementById("qp-modal"), qpBody = document.getElementById("qp-body");
  function openQp(level) {
    qpModal.hidden = false; qpBody.innerHTML = ""; qpBody.appendChild(el("p", "qm-dash-empty", "Loading…"));
    api("/api/qpunch/" + level).then(function (d) {
      qpBody.innerHTML = "";
      qpBody.appendChild(el("p", "tb-place", d.label + " · " + d.group));
      var c = d.cycle;
      qpBody.appendChild(el("p", "qp-lead", d.level === "village"
        ? "Now: " + c.sign + " month — the " + c.sign + " leaders serve. Next month the " + "leaders of the next sign take over."
        : "Now: " + c.element + " leaders (" + c.sign + " month). Leaders of each element take the months of their signs."));
      if (d.election) qpBody.appendChild(electionBlock(d.election, d.guide, level));
      d.seats.forEach(function (s) {
        var row = el("div", "qp-seat" + (s.filled ? " is-filled" : ""));
        row.appendChild(el("span", "qp-no", s.seat));
        var t = el("div", "qp-text");
        t.appendChild(el("b", "", s.title));
        t.appendChild(el("p", "", s.text));
        if (s.seat === 1) t.appendChild(el("small", "", "Founder · Admin"));
        if ((s.seat === 2 || s.seat === 3) && d.election) {
          var who = d.election.winners && d.election.winners[s.seat === 2 ? "male" : "female"];
          t.appendChild(el("small", "", who ? "🏆 " + who + " · term " + d.election.winners.term_start + " to " + d.election.winners.term_end
            : "Elected by " + d.election.sign + " members this month — results in week 4 (" + d.election.weeks[3].start + ")"));
        } else if (s.seat === 2 || s.seat === 3) t.appendChild(el("small", "", "Not elected yet — elections open at " + d.election_min.toLocaleString() + " residents"));
        if (s.seat === 5) {
          t.appendChild(el("div", "qp-counts", d.volunteers + " volunteer" + (d.volunteers === 1 ? "" : "s") + " · " + d.agents + " agent" + (d.agents === 1 ? "" : "s")));
          if (d.can_volunteer) {
            var f = el("form", "qp-vol"), i = el("input"); i.placeholder = "What do you do? e.g. vegetable seller"; i.maxLength = 80; i.required = true;
            var go = el("button", "sg-btn", "Register as volunteer"); go.type = "submit"; f.appendChild(i); f.appendChild(go);
            f.addEventListener("submit", function (e) { e.preventDefault(); api("/api/qpunch/volunteer", { skill: i.value }).then(function () { openQp(level); }).catch(function (er) { alert(er.message); }); });
            t.appendChild(f);
          } else if (d.is_volunteer) t.appendChild(el("small", "", "✓ You are registered as a volunteer here"));
          t.appendChild(referrerBlock(d.is_admin));
        }
        row.appendChild(t); qpBody.appendChild(row);
      });
      var pct = Math.min(100, Math.round(100 * d.residents / d.election_min));
      var prog = el("div", "qp-progress");
      prog.appendChild(el("small", "", "Council elections open at " + d.election_min.toLocaleString() + " residents · " + d.residents.toLocaleString() + " now"));
      var bar = el("div", "qp-bar"); var fill = el("i"); fill.style.width = Math.max(2, pct) + "%"; bar.appendChild(fill); prog.appendChild(bar);
      qpBody.appendChild(prog);

      var histBtn = el("button", "sg-btn", "💰 Group wallet — weekly history"); histBtn.type = "button"; histBtn.style.marginTop = "10px";
      var histBox = el("div", "qp-history"); histBox.hidden = true;
      histBtn.addEventListener("click", function () {
        histBox.hidden = !histBox.hidden;
        if (histBox.hidden || histBox.dataset.loaded) return;
        histBox.dataset.loaded = "1";
        api("/api/wallet/history/" + level + "/" + encodeURIComponent(d.group_id)).then(function (h) {
          histBox.innerHTML = "";
          histBox.appendChild(el("p", "tb-place", "Balance: " + h.balance_qoins + " Qoins"));
          if (!h.is_council) histBox.appendChild(el("p", "qm-dash-empty", "Full history is for council members; you see the last 3 months."));
          else if (h.older_weeks_hidden) histBox.appendChild(el("p", "qm-dash-empty", h.older_weeks_hidden + " older week(s) available to council members."));
          if (!h.weeks.length) histBox.appendChild(el("p", "qm-dash-empty", "No transactions yet."));
          h.weeks.forEach(function (wk) {
            var box = el("div", "wh-week");
            box.appendChild(el("b", "", wk.start + " – " + wk.end + " · " + (wk.change >= 0 ? "+" : "") + wk.change + " Qoins"));
            wk.rows.forEach(function (r) { box.appendChild(el("small", "", (r.amount >= 0 ? "+" : "") + r.amount + " · " + r.reason)); });
            histBox.appendChild(box);
          });
        }).catch(function (e) { histBox.innerHTML = ""; histBox.appendChild(el("p", "qm-dash-empty", e.message)); });
      });
      qpBody.appendChild(histBtn); qpBody.appendChild(histBox);
    }).catch(function (e) { qpBody.innerHTML = ""; qpBody.appendChild(el("p", "qm-dash-empty", e.message)); });
  }

  // The monthly sign election (election_core.py) -- same card as the phone app's Q-Punch:
  // 4-week timeline, what this member should do, candidates, and the winners' 1-year term.
  function shortDate(iso) { return new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" }); }
  function electionBlock(e, g, level) {
    var box = el("div", "qp-elec qp-elec-" + (e.element || "").toLowerCase());
    var head = el("div", "qp-elec-head");
    head.appendChild(el("b", "", e.sign + " election · " + e.year));
    head.appendChild(el("small", "", "Week " + e.week + " of 4"));
    box.appendChild(head);
    var tl = el("div", "qp-elec-weeks");
    e.weeks.forEach(function (w) {
      var s = el("div", "qp-elec-week" + (w.week === e.week ? " is-now" : w.week < e.week ? " is-done" : ""));
      s.appendChild(el("b", "", w.week < e.week ? "✓" : String(w.week)));
      s.appendChild(el("span", "", w.title));
      s.appendChild(el("small", "", shortDate(w.start) + "–" + shortDate(w.end)));
      tl.appendChild(s);
    });
    box.appendChild(tl);
    var now = e.weeks.filter(function (w) { return w.week === e.week; })[0];
    if (now) box.appendChild(el("p", "qp-elec-text", now.text));
    if (g) box.appendChild(el("p", "qp-elec-guide" + (g.action ? " is-action" : ""), (g.action ? "📣 " : "ℹ️ ") + g.text));
    if (g && g.can_stand) {
      var f = el("form", "qp-vol qp-elec-form"), qs = {};
      [["reason", "Why are you standing?"], ["why_vote", "Why should members vote for you?"], ["changes", "What will you change?"]].forEach(function (q) {
        var i = el("input"); i.placeholder = q[1]; i.maxLength = 300; i.required = true; qs[q[0]] = i; f.appendChild(i);
      });
      var go = el("button", "sg-btn", "Stand as a candidate"); go.type = "submit"; f.appendChild(go);
      f.addEventListener("submit", function (ev) {
        ev.preventDefault();
        api("/api/election/nominate", { reason: qs.reason.value, why_vote: qs.why_vote.value, changes: qs.changes.value })
          .then(function () { openQp(level); }).catch(function (er) { alert(er.message); });
      });
      box.appendChild(f);
    }
    if (e.winners) {
      var w = el("div", "qp-elec-winners");
      w.appendChild(el("b", "", "New " + e.sign + " leaders"));
      if (e.winners.male) w.appendChild(el("p", "", "🏆 " + e.winners.male + " · Male Leader · " + e.winners.male_votes + " votes"));
      if (e.winners.female) w.appendChild(el("p", "", "🏆 " + e.winners.female + " · Female Leader · " + e.winners.female_votes + " votes"));
      w.appendChild(el("small", "", "Term of work: " + e.winners.term_start + " to " + e.winners.term_end + " (1 year)"));
      box.appendChild(w);
    }
    ["male", "female"].forEach(function (gender) {
      var list = e.candidates[gender] || [];
      box.appendChild(el("b", "qp-elec-sec", (gender === "male" ? "Male" : "Female") + " candidates" + (list.length ? " (" + list.length + ")" : "")));
      if (!list.length) box.appendChild(el("small", "", e.status === "nomination" ? "Candidates are coming forward this week." : "No candidates."));
      var canVote = g && g.can_vote && g.my_gender === gender && g.voted_genders.indexOf(gender) < 0;
      list.forEach(function (c) {
        var row = el("div", "qp-elec-cand" + (e.winners && e.winners[gender] === c.name ? " is-winner" : ""));
        var t = el("div", "");
        t.appendChild(el("b", "", c.name + (c.votes !== null ? " · " + c.votes + " votes" : "")));
        if (c.reason) t.appendChild(el("p", "", "“" + c.reason + "”"));
        if (c.changes) t.appendChild(el("small", "", "Plan: " + c.changes));
        row.appendChild(t);
        if (canVote) {
          var v = el("button", "sg-btn", "Vote"); v.type = "button";
          v.addEventListener("click", function () {
            if (!confirm("Vote for " + c.name + "? You can vote only once.")) return;
            api("/api/election/vote", { candidate_user_id: c.user_id, gender: gender }).then(function () { openQp(level); }).catch(function (er) { alert(er.message); });
          });
          row.appendChild(v);
        }
        box.appendChild(row);
      });
    });
    box.appendChild(el("small", "qp-elec-turnout", e.turnout + " of " + e.eligible_voters + " " + e.sign + " members have voted."));
    return box;
  }

  function referrerBlock(isAdmin) {
    var wrap = el("div", "qp-ref");
    api("/api/referrer/me").then(function (r) {
      if (r.code) {
        wrap.appendChild(el("small", "", "✓ Referral code: " + r.code.code + " · used " + r.code.uses + " time" + (r.code.uses === 1 ? "" : "s")));
      } else if (r.pending) {
        wrap.appendChild(el("small", "", "Application pending council review"));
      } else {
        var f = el("form", "qp-vol"), i = el("input"); i.placeholder = "Why do you want to be a referrer?"; i.maxLength = 300;
        var go = el("button", "sg-btn", "Apply to be a referrer"); go.type = "submit"; f.appendChild(i); f.appendChild(go);
        f.addEventListener("submit", function (e) {
          e.preventDefault();
          api("/api/referrer/apply", { note: i.value }).then(function () { wrap.innerHTML = ""; wrap.appendChild(el("small", "", "Application sent — waiting for council review")); }).catch(function (er) { alert(er.message); });
        });
        wrap.appendChild(f);
      }
      if (isAdmin) {
        api("/api/referrer/applications").then(function (a) {
          if (!a.applications.length) return;
          var box = el("div", "qp-pending");
          box.appendChild(el("small", "", a.applications.length + " referrer application" + (a.applications.length === 1 ? "" : "s") + " waiting"));
          a.applications.forEach(function (app_) {
            var row = el("div", "sg-row"); row.appendChild(el("span", "", app_.name + (app_.note ? " — " + app_.note : "")));
            var ok = el("button", "sg-btn", "Approve"), no = el("button", "sg-btn", "Decline"); ok.type = no.type = "button";
            ok.addEventListener("click", function () { api("/api/referrer/applications/" + app_.id + "/decide", { approve: true }).then(function (res) { alert("Approved — code " + res.code); openQp(level); }); });
            no.addEventListener("click", function () { api("/api/referrer/applications/" + app_.id + "/decide", { approve: false }).then(function () { openQp(level); }); });
            row.appendChild(ok); row.appendChild(no); box.appendChild(row);
          });
          wrap.appendChild(box);
        }).catch(function () {});
      }
    }).catch(function () {});
    return wrap;
  }

  // ---- one board ----
  function Board(root) {
    var level = root.getAttribute("data-level");
    var titleEl = root.querySelector(".bd-title"), subEl = root.querySelector(".bd-sub"), feed = root.querySelector(".bd-feed");
    var form = root.querySelector(".bd-compose"), ta = form.querySelector("textarea"), note = root.querySelector(".bd-note");
    // Admin-only "Mark as test" toggle (2026-10-17) -- the markup lives in dashboard.html
    // (file 6); guarded with `if` everywhere below so this file works unchanged whether or not
    // that markup has landed yet.
    var testToggleBox = form.querySelector(".bd-test-toggle");
    var testToggle = testToggleBox ? testToggleBox.querySelector("input") : null;
    var chat = null;                       // {id, name} while a village sub-group chat is open
    var view = "live";                     // "live" (default) or "frozen" — each fills the whole board
    var toggle = root.querySelector(".bd-toggle"), foot = root.querySelector(".bd-foot"), lastView = null;
    var self = { setChat: null };
    var announceBanner = root.querySelector(".bd-announce-banner");
    var announceBannerText = announceBanner.querySelector(".bd-announce-banner-text");
    var announceBannerFull = announceBanner.querySelector(".bd-announce-banner-full");
    var announceRotateTimer = null, announceIndex = 0, announceItems = [];
    announceBanner.addEventListener("click", function () {
      if (!announceItems.length) return;
      var expanded = !announceBannerFull.hidden;
      announceBannerFull.hidden = expanded;
      if (!expanded) announceBannerFull.textContent = announceItems[announceIndex].body;
    });
    root.querySelector(".bd-qp").addEventListener("click", function () { openQp(level); });
    var reportBtn = root.querySelector(".bd-report-btn");
    reportBtn.addEventListener("click", function (e) { e.preventDefault(); openPostOrReportChoice(); });

    function section(text, small) { var h = el("div", "bd-sec", text); if (small) h.appendChild(el("small", "", small)); return h; }

    // A paid post's price is shown as "<currency symbol><amount> | <n> Qoin(s)" (2026-09-28) --
    // the currency value on the left, a "|" separator, then the real number of Qoins that make it
    // up (qoin_core.to_qoins: e.g. ₹1000 = two 500-value Qoins). No sentence.
    function priceLine(v) {
      var n = v.post_price_qoins.length;
      return v.currency_symbol + v.post_price.toLocaleString() + " | " + n + " Qoin" + (n === 1 ? "" : "s");
    }

    function render(v) {
      titleEl.textContent = v.group + " Lok";
      subEl.innerHTML = "";
      subEl.appendChild(el("span", "bd-count", "\uD83D\uDC65 " + v.members.toLocaleString() + " member" + (v.members === 1 ? "" : "s")));
      subEl.appendChild(el("span", "bd-count", "\uD83D\uDD37 " + v.qoins.toLocaleString() + " Qoins"));
      if (level === "country" || level === "state") loadSentiment(level, v.group_id); else if (sentimentBox) sentimentBox.hidden = true;
      form.hidden = !(v.can_post || v.can_pay_post);
      reportBtn.hidden = !v.can_post;
      if (testToggleBox) testToggleBox.hidden = !v.is_admin;
      if (v.can_post) {
        ta.placeholder = "Post to your village — it is voted on for 7 days…";
        form.querySelector("button").textContent = "Post";
      } else if (v.can_pay_post) {
        ta.placeholder = "Write your post…";
        form.querySelector("button").textContent = "Post · " + priceLine(v);
      }
      note.hidden = v.can_post || v.can_pay_post;
      note.textContent = "Posts are made in your Village and rise here through votes. You can read, vote and — after voting ends — comment.";
      feed.innerHTML = "";
      lastView = v;
      var live = v.posts.filter(function (p) { return p.status === "active"; });
      var done = v.posts.filter(function (p) { return p.status !== "active"; }).sort(function (a, b) { return b.score - a.score; });
      foot.hidden = false;
      if (view === "live") {
        toggle.querySelector("span").textContent = "Frozen posts (" + done.length + ")";
        feed.appendChild(section("🗳️ Open for live voting", live.length + " post" + (live.length === 1 ? "" : "s")));
        if (!live.length) feed.appendChild(el("p", "bd-empty", v.can_post ? "Nothing is being voted on — start the conversation below." : "Nothing is open for voting at this level."));
        live.forEach(function (p) { feed.appendChild(bubble(p, v)); });
      } else {
        toggle.querySelector("span").textContent = "← Back to live voting";
        feed.appendChild(section("❄️ Frozen & elevated posts", "best scores first · comments open"));
        if (!done.length) feed.appendChild(el("p", "bd-empty", "No closed posts yet."));
        done.forEach(function (p, i) { feed.appendChild(bubble(p, v, i)); });
      }
      renderAnnouncements(v);
      renderReportInbox(v);
      renderStars(v);
    }

    // ---- Recognition stars (2026-10-17): a permanent, independent record of every positively-
    // recognised post at this location -- written once at freeze/elevate time, so it keeps
    // showing here even after the lunar pipeline eventually archives the post itself. No reward
    // flows from a star; it is recognition only, separate from the author's own Qoin credit. ----
    var starsBox = root.querySelector(".bd-stars");
    function renderStars(v) {
      if (!starsBox) return;
      var stars = v.stars || [];
      starsBox.innerHTML = "";
      if (!stars.length) { starsBox.hidden = true; return; }
      starsBox.hidden = false;
      starsBox.appendChild(section("⭐ Recognised", stars.length + " star" + (stars.length === 1 ? "" : "s")));
      var list = el("div", "bd-stars-list");
      stars.forEach(function (s) {
        var row = el("div", "bd-star-row");
        row.appendChild(el("span", "bd-star-ico", "⭐"));
        row.appendChild(el("b", "", s.author));
        row.appendChild(el("small", "", "score " + fmt(s.score) + " · " + ago(s.at)));
        list.appendChild(row);
      });
      starsBox.appendChild(list);
    }

    // ---- Item 8: Announcements -- pinned banner (this panel) + right-sidebar card ----
    function showBannerItem() {
      if (!announceItems.length) { announceBanner.hidden = true; return; }
      announceBanner.hidden = false;
      announceBannerFull.hidden = true;
      var a = announceItems[announceIndex];
      announceBannerText.textContent = (a.title ? a.title + " — " : "") + a.body.slice(0, 80) + (a.body.length > 80 ? "…" : "");
    }

    function renderAnnouncements(v) {
      announceItems = v.announcements || [];
      announceIndex = 0;
      showBannerItem();
      clearInterval(announceRotateTimer);
      if (announceItems.length > 1) {
        announceRotateTimer = setInterval(function () {
          announceIndex = (announceIndex + 1) % announceItems.length;
          showBannerItem();
        }, 5000);
      }

      var sidebarPrefix = (v.level === "continent" || v.level === "country" || v.level === "earth") ? "qm-dg-stats" : "qm-dp-stats";
      var listEl = document.getElementById(sidebarPrefix + "-announce-list");
      var emptyEl = document.getElementById(sidebarPrefix + "-announce-empty");
      var viewAllBtn = document.getElementById(sidebarPrefix + "-announce-viewall");
      var newBtn = document.getElementById(sidebarPrefix + "-announce-new");
      if (!listEl) return;
      listEl.innerHTML = "";
      announceItems.slice(0, 5).forEach(function (a) {
        var li = el("li", "qm-announce-item");
        if (a.title) li.appendChild(el("b", "", a.title));
        li.appendChild(el("p", "", a.body.slice(0, 120) + (a.body.length > 120 ? "…" : "")));
        li.appendChild(el("small", "", (a.author_name || "Council") + " · " + ago(a.created_at)));
        listEl.appendChild(li);
      });
      emptyEl.hidden = announceItems.length > 0;
      viewAllBtn.hidden = announceItems.length === 0;
      viewAllBtn.onclick = function () { openAnnounceViewAll(v.level, v.group_id); };
      newBtn.hidden = !v.can_publish_announcement;
      newBtn.onclick = function () { openAnnounceNew(v.level, v.group_id); };
    }

    // ---- Item 9: Report Inbox -- same sidebar, visible only to the council/admin holding
    // this exact location (reuses v.can_view_report_inbox, computed identically to
    // v.can_publish_announcement on the server; see docs/reports_design.md §2) ----
    function renderReportInbox(v) {
      var sidebarPrefix = (v.level === "continent" || v.level === "country" || v.level === "earth") ? "qm-dg-stats" : "qm-dp-stats";
      var section = document.getElementById(sidebarPrefix + "-reportinbox-section");
      if (!section) return;
      section.hidden = !v.can_view_report_inbox;
      if (!v.can_view_report_inbox) return;
      var listEl = document.getElementById(sidebarPrefix + "-reportinbox-list");
      var emptyEl = document.getElementById(sidebarPrefix + "-reportinbox-empty");
      api("/api/reports/inbox?location_level=" + v.level + "&location_id=" + encodeURIComponent(v.group_id)).then(function (d) {
        listEl.innerHTML = "";
        emptyEl.hidden = d.reports.length > 0;
        d.reports.forEach(function (r) {
          var li = el("li", "qm-announce-item");
          li.style.cursor = "pointer";
          li.appendChild(el("p", "", r.body_preview));
          li.appendChild(el("small", "", (r.author_name || "Citizen") + " · SLA " + left(r.sla_deadline)));
          li.addEventListener("click", function () { openReportDetail(r.id); });
          listEl.appendChild(li);
        });
      }).catch(function () {});
    }

    var sentimentBox = el("div", "bd-sentiment"); sentimentBox.hidden = true;
    function loadSentiment(lvl, groupId) {
      if (!groupId) { sentimentBox.hidden = true; return; }
      api("/api/election-sentiment/" + lvl + "/" + encodeURIComponent(groupId)).then(function (s) {
        sentimentBox.hidden = false; sentimentBox.innerHTML = "";
        if (!s.visible) {
          sentimentBox.appendChild(el("b", "", "📊 Election sentiment is not shown yet — " + s.reason));
        } else {
          sentimentBox.appendChild(el("b", "", "📊 " + s.label + " sentiment · based on " + s.total_responses + " response" + (s.total_responses === 1 ? "" : "s")));
          s.parties.forEach(function (p) {
            var row = el("div", "bd-sentiment-row");
            row.appendChild(el("span", "", p.label));
            var bar = el("div", "bd-sentiment-bar"), fill = el("i"); fill.style.width = p.pct + "%"; bar.appendChild(fill);
            row.appendChild(bar); row.appendChild(el("b", "", p.pct + "%"));
            sentimentBox.appendChild(row);
          });
        }
        if (!sentimentBox.parentNode) root.querySelector(".bd-head").insertAdjacentElement("afterend", sentimentBox);
      }).catch(function () { sentimentBox.hidden = true; });
    }

    // post_kind badge text (2026-10-17) -- exact strings per the four combinations; 'member'
    // posts get no badge at all (function returns null, caller skips appending anything).
    function postBadge(p) {
      if (p.post_kind === "council_update") return "Council Update";
      if (p.post_kind === "test") return p.is_demo_post ? "Demo · Test" : "Admin · Test";
      return null;
    }

    // The frozen test record (design doc Section 3/8): only ever rendered once a test post has
    // actually settled (p.test_record is only present on the payload for frozen/elevated test
    // posts -- board_core.py never attaches it to an active one). "Frozen" uses voting_end as the
    // settle moment, since there is no separate frozen_at column -- settle() runs lazily (any
    // board read, plus the weekly cron), usually very soon after voting_end, but not pinned to
    // the exact instant; this is an approximation, not a precise timestamp.
    function testRecordBlock(tr) {
      var box = el("div", "bd-test-record");
      box.appendChild(el("div", "bd-test-record-row", "Voting window: " + ago(tr.voting_start) + " → " + ago(tr.voting_end)));
      box.appendChild(el("div", "bd-test-record-row", "Final score " + fmt(tr.final_score)));
      box.appendChild(el("div", "bd-test-record-row", tr.reward_inr != null
        ? ("Reward: ₹" + tr.reward_inr.toLocaleString() + " (test — not credited)")
        : "No reward earned"));
      box.appendChild(el("div", "bd-test-record-row",
        "Voted by " + tr.demo_voter_count + " demo user" + (tr.demo_voter_count === 1 ? "" : "s") + " for testing purposes"));
      box.appendChild(el("div", "bd-test-record-row", "Frozen " + ago(tr.voting_end)));
      return box;
    }

    function bubble(p, v, rank) {
      var b = el("article", "bd-post" + (p.mine ? " is-mine" : "") + " is-" + p.status);
      var head = el("div", "bd-post-head");
      if (rank === 0 && p.score > 0) head.appendChild(el("span", "bd-crown", "🏆"));
      head.appendChild(el("span", "bd-avatar", (p.author || "?").charAt(0)));
      head.appendChild(el("b", "", p.author));
      var badge = postBadge(p);
      if (badge) head.appendChild(el("span", "bd-badge bd-badge-" + p.post_kind, badge));
      head.appendChild(el("small", "", ago(p.created_at)));
      b.appendChild(head);
      if (p.origin) b.appendChild(el("div", "bd-origin", "⬆️ Elevated from " + p.origin.level + " · final score " + fmt(p.origin.score)));
      b.appendChild(el("p", "bd-text", p.content));

      if (p.post_kind === "council_update") {
        // No vote buttons, no score/countdown line -- a council update is never a proposal.
        // Thumbs up/down + counts instead, via the existing generic reaction route (scope=
        // "board_post"); clicking the already-selected one clears the reaction (same toggle
        // behaviour as reactions_core.set_reaction's own None-clears contract).
        var reactBar = el("div", "bd-reactions");
        [["agree", "👍"], ["disagree", "👎"]].forEach(function (x) {
          var count = (p.reactions && p.reactions[x[0]]) || 0;
          var mine = p.reactions && p.reactions.mine === x[0];
          var btn = el("button", "bd-react" + (mine ? " is-on" : ""), x[1] + " " + count);
          btn.type = "button";
          btn.addEventListener("click", function () {
            api("/api/reactions/board_post/" + p.id, { reaction: mine ? null : x[0] }).then(load).catch(function (e) { alert(e.message); });
          });
          reactBar.appendChild(btn);
        });
        b.appendChild(reactBar);
        return b;
      }

      var meta = el("div", "bd-meta");
      var status = p.status === "active" ? "🗳️ Voting · " + left(p.voting_end)
        : p.status === "elevated" ? "⬆️ Elevated to " + p.elevated_to : "❄️ Frozen · voting closed " + ago(p.voting_end);
      meta.appendChild(el("span", "bd-status", status));
      meta.appendChild(el("span", "bd-score", "Final score " + fmt(p.score)));
      if (p.status === "active") meta.lastChild.textContent = "Score " + fmt(p.score);
      b.appendChild(meta);
      var bar = el("div", "bd-bar"), fill = el("i"); fill.style.width = Math.max(0, Math.min(100, Math.round(100 * p.score / p.threshold))) + "%";
      bar.appendChild(fill); b.appendChild(bar);

      if (p.test_record) b.appendChild(testRecordBlock(p.test_record));

      if (p.can_vote) {
        var votes = el("div", "bd-votes");
        [[1, "👍 +1"], [0, "➖ 0"], [-1, "👎 −1"]].forEach(function (x) {
          var btn = el("button", "bd-vote" + (p.my_vote === x[0] ? " is-on" : ""), x[1]); btn.type = "button";
          btn.addEventListener("click", function () {
            api("/api/board/vote", { post_id: p.id, value: x[0] }).then(load).catch(function (e) { alert(e.message); load(); });
          });
          votes.appendChild(btn);
        });
        b.appendChild(votes);
      } else {
        var cm = el("div", "bd-comments");
        cm.appendChild(el("small", "", p.comments.length ? p.comments.length + " comment" + (p.comments.length === 1 ? "" : "s") : "No comments yet"));
        p.comments.forEach(function (c) { var r = el("div", "bd-comment"); r.appendChild(el("b", "", c.who)); r.appendChild(el("span", "", " " + c.text)); cm.appendChild(r); });
        var f = el("form", "bd-cform"), i = el("input"); i.type = "text"; i.maxLength = 500; i.placeholder = "Write a comment…"; i.required = true;
        var go = el("button", "", "Send"); go.type = "submit"; f.appendChild(i); f.appendChild(go);
        f.addEventListener("submit", function (e) { e.preventDefault(); api("/api/board/comment", { post_id: p.id, text: i.value }).then(load).catch(function (er) { alert(er.message); }); });
        cm.appendChild(f); b.appendChild(cm);
      }
      return b;
    }

    function renderChat(d) {
      titleEl.textContent = d.name;
      subEl.innerHTML = "";
      subEl.appendChild(el("span", "bd-count", "👥 " + d.members + " member" + (d.members === 1 ? "" : "s")));
      subEl.appendChild(el("span", "bd-count", "Admin: " + d.admin_label));
      var back = el("button", "bd-back", "← Village board"); back.type = "button"; back.addEventListener("click", function () { self.setChat(null); });
      subEl.appendChild(back);
      form.hidden = false; note.hidden = true; foot.hidden = true; ta.placeholder = "Message " + d.name + "…";
      feed.innerHTML = "";
      if (!d.messages.length) feed.appendChild(el("p", "bd-empty", "No messages yet — say hello."));
      d.messages.forEach(function (m) { feed.appendChild(subgroupBubble(m, d.members)); });
      feed.scrollTop = feed.scrollHeight;
    }

    function subgroupBubble(m, memberCount) {
      var b = el("div", "bd-msg bd-msg-full" + (m.mine ? " is-mine" : ""));
      var head = el("div", "bd-msg-head"); head.appendChild(el("b", "", m.who)); head.appendChild(el("small", "", m.account_id || "")); b.appendChild(head);
      b.appendChild(el("p", "bd-msg-text", m.text));
      b.appendChild(el("small", "bd-msg-time", ago(m.at)));
      b.appendChild(reactionBar(m, "subgroup", memberCount, function () { load(); }));
      return b;
    }

    function load() {
      if (chat) return api("/api/chat/" + chat.id).then(renderChat).catch(function (e) { feed.innerHTML = ""; feed.appendChild(el("p", "bd-empty", e.message)); });
      return api("/api/board/" + level).then(render).catch(function (e) {
        titleEl.textContent = "Collective Board"; subEl.textContent = ""; feed.innerHTML = ""; feed.appendChild(el("p", "bd-empty", e.message)); form.hidden = true;
      });
    }
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!chat && lastView && lastView.can_pay_post && !window.confirm(priceLine(lastView) + " — from your wallet. Continue?")) return;
      var postBody = { content: ta.value, level: level };
      if (!chat && testToggle && testToggle.checked) postBody.is_test = true;
      var req = chat ? api("/api/chat/" + chat.id, { text: ta.value }) : api("/api/board/post", postBody);
      req.then(function () { ta.value = ""; if (testToggle) testToggle.checked = false; load(); }).catch(function (er) { alert(er.message); });
    });
    toggle.addEventListener("click", function () { view = view === "live" ? "frozen" : "live"; if (lastView) render(lastView); feed.scrollTop = 0; });
    self.setChat = function (c) { chat = c; return load(); };
    self.setLevel = function (l) { chat = null; view = "live"; level = l; root.setAttribute("data-level", l); return load(); };
    self.load = load;
    return self;
  }

  // ---- Item 8: shared "+ New Announcement" / "View all" modals (one pair, reused by
  // whichever panel's sidebar card opened them -- the target location travels with the call) ----
  var announceNewModal = document.getElementById("announce-new-modal");
  var announceNewForm = document.getElementById("announce-new-form");
  var announceNewError = document.getElementById("announce-new-error");
  var announceNewTarget = null; // {level, groupId}
  if (announceNewModal) {
    announceNewForm.addEventListener("submit", function (e) {
      e.preventDefault();
      announceNewError.hidden = true;
      if (!announceNewTarget) return;
      api("/api/announcements", {
        location_id: announceNewTarget.groupId, location_level: announceNewTarget.level,
        title: document.getElementById("announce-new-title-input").value.trim(),
        body: document.getElementById("announce-new-body").value.trim(),
        image_url: document.getElementById("announce-new-image").value.trim(),
      }).then(function () {
        announceNewForm.reset();
        announceNewModal.hidden = true;
        boardInstances.forEach(function (inst) { inst.load(); });
      }).catch(function (er) { announceNewError.textContent = er.message; announceNewError.hidden = false; });
    });
  }
  function openAnnounceNew(level, groupId) {
    announceNewTarget = { level: level, groupId: groupId };
    announceNewError.hidden = true;
    announceNewForm.reset();
    announceNewModal.hidden = false;
  }

  var announceViewAllModal = document.getElementById("announce-viewall-modal");
  function openAnnounceViewAll(level, groupId) {
    var listEl = document.getElementById("announce-viewall-list"), emptyEl = document.getElementById("announce-viewall-empty");
    listEl.innerHTML = ""; emptyEl.hidden = true;
    announceViewAllModal.hidden = false;
    api("/api/announcements/" + level + "/" + encodeURIComponent(groupId) + "?limit=20").then(function (d) {
      emptyEl.hidden = d.announcements.length > 0;
      d.announcements.forEach(function (a) {
        var li = el("li", "qm-announce-item");
        if (a.title) li.appendChild(el("b", "", a.title));
        li.appendChild(el("p", "", a.body));
        li.appendChild(el("small", "", (a.author_name || "Council") + " · " + ago(a.created_at)));
        listEl.appendChild(li);
      });
    }).catch(function () { emptyEl.hidden = false; emptyEl.textContent = "Could not load announcements right now."; });
  }

  // ---- Item 9: Citizen Report (FIR) -- choice popup, submit modal, shared detail/reply modal ----
  var postOrReportModal = document.getElementById("post-or-report-modal");
  if (postOrReportModal) {
    document.getElementById("choose-make-post").addEventListener("click", function () { postOrReportModal.hidden = true; });
    document.getElementById("choose-submit-report").addEventListener("click", function () { postOrReportModal.hidden = true; openReportSubmit(); });
  }
  function openPostOrReportChoice() { postOrReportModal.hidden = false; }

  var reportNewModal = document.getElementById("report-new-modal");
  var reportNewForm = document.getElementById("report-new-form");
  var reportNewError = document.getElementById("report-new-error");
  var reportNewSuccess = document.getElementById("report-new-success");
  function openReportSubmit() {
    reportNewForm.hidden = false; reportNewError.hidden = true; reportNewSuccess.hidden = true;
    reportNewForm.reset();
    reportNewModal.hidden = false;
  }
  if (reportNewForm) {
    reportNewForm.addEventListener("submit", function (e) {
      e.preventDefault();
      reportNewError.hidden = true;
      api("/api/reports", {
        body: document.getElementById("report-new-body").value.trim(),
        anonymous: document.getElementById("report-new-anonymous").checked,
      }).then(function () {
        reportNewForm.hidden = true;
        reportNewSuccess.hidden = false;
      }).catch(function (er) { reportNewError.textContent = er.message; reportNewError.hidden = false; });
    });
  }

  var reportDetailModal = document.getElementById("report-detail-modal");
  var reportDetailMeta = document.getElementById("report-detail-meta");
  var reportDetailBody = document.getElementById("report-detail-body");
  var reportDetailTimeline = document.getElementById("report-detail-timeline");
  var reportDetailReply = document.getElementById("report-detail-reply");
  var reportReplyForm = document.getElementById("report-reply-form");
  var reportReplyType = document.getElementById("report-reply-type");
  var reportReplyDeadlineField = document.getElementById("report-reply-deadline-field");
  var reportReplyError = document.getElementById("report-reply-error");
  var reportEscalateBtn = document.getElementById("report-escalate-btn");
  var currentReportId = null;

  function openReportDetail(reportId) {
    currentReportId = reportId;
    reportDetailModal.hidden = false;
    reportDetailMeta.textContent = "Loading…";
    reportDetailBody.textContent = "";
    reportDetailTimeline.innerHTML = "";
    reportDetailReply.hidden = true;
    api("/api/reports/" + reportId).then(renderReportDetail).catch(function (er) {
      reportDetailMeta.textContent = "Could not load this report: " + er.message;
    });
  }

  function renderReportDetail(d) {
    reportDetailMeta.textContent = (d.anonymous ? "Anonymous Citizen" : d.author_name) + " · " + d.status + " · holder: " + d.current_holder_level + " · SLA " + left(d.sla_deadline);
    reportDetailBody.textContent = d.body;
    reportDetailTimeline.innerHTML = "";
    d.updates.forEach(function (u) {
      var li = el("li", "qm-report-update");
      li.appendChild(el("b", "", u.update_type + (u.author_name ? " — " + u.author_name : "")));
      if (u.message) li.appendChild(el("p", "", u.message));
      li.appendChild(el("small", "", ago(u.created_at)));
      reportDetailTimeline.appendChild(li);
    });
    reportDetailReply.hidden = !d.is_holder;
    reportEscalateBtn.hidden = !d.is_holder || d.current_holder_level === "earth" || d.status === "resolved" || d.status === "denied";
  }

  if (reportReplyType) {
    reportReplyType.addEventListener("change", function () {
      reportReplyDeadlineField.hidden = reportReplyType.value !== "needs_time";
    });
    reportReplyForm.addEventListener("submit", function (e) {
      e.preventDefault();
      reportReplyError.hidden = true;
      var type = reportReplyType.value;
      var newDeadline = document.getElementById("report-reply-deadline").value;
      if (type === "needs_time" && !newDeadline) {
        reportReplyError.textContent = "Please choose a new deadline"; reportReplyError.hidden = false; return;
      }
      api("/api/reports/" + currentReportId + "/update", {
        update_type: type, message: document.getElementById("report-reply-message").value.trim(),
        new_deadline: type === "needs_time" ? newDeadline : undefined,
      }).then(function () {
        reportReplyForm.reset(); reportReplyDeadlineField.hidden = true;
        openReportDetail(currentReportId);
      }).catch(function (er) { reportReplyError.textContent = er.message; reportReplyError.hidden = false; });
    });
    reportEscalateBtn.addEventListener("click", function () {
      api("/api/reports/" + currentReportId + "/escalate", {}).then(function () { openReportDetail(currentReportId); })
        .catch(function (er) { reportReplyError.textContent = er.message; reportReplyError.hidden = false; });
    });
  }
  window.qmOpenReportDetail = openReportDetail;

  var boardInstances = [];
  var boards = [["bd-global", "global-root-tabs", "qm-dash-global"], ["bd-public", "public-root-tabs", "qm-dash-public"]];
  boards.forEach(function (cfg) {
    var root = document.getElementById(cfg[0] + "-board"); if (!root) return;
    var b = Board(root), tabs = document.getElementById(cfg[1]), panel = document.getElementById(cfg[2]);
    boardInstances.push(b);
    var CHILD = { earth: "Continents", continent: "Countries", country: "Zones", zone: "States", state: "Districts", district: "Tehsils", tehsil: "Villages" };
    var heading = document.getElementById(cfg[0] === "bd-public" ? "public-places-h" : "global-places-h"), tree = panel.querySelector(".qm-explorer-tree");
    var sgBox = document.getElementById("subgroups-box");
    function applyLevel(l) {
      var village = l === "village";
      if (heading) { heading.textContent = CHILD[l] || ""; heading.hidden = village; }
      tree.hidden = village;
      Array.prototype.forEach.call(panel.querySelectorAll(".qm-explorer-note"), function (n) { n.hidden = village; });
      if (sgBox && cfg[0] === "bd-public") sgBox.hidden = !village;
    }
    applyLevel(root.getAttribute("data-level"));
    if (tabs) tabs.addEventListener("click", function (e) {
      var t = e.target.closest("[data-root]"); if (t && !t.disabled) { applyLevel(t.getAttribute("data-root")); b.setLevel(t.getAttribute("data-root")); }
    });
    document.querySelector('.qm-dash-tab[data-tab="' + cfg[2].replace("qm-dash-", "") + '"]').addEventListener("click", function () { b.load(); });

    // left drawer: places tree + (public) village groups
    var drawer = panel.querySelector(".dr"), back = panel.querySelector(".dr-backdrop");
    function setDrawer(open) { drawer.classList.toggle("is-open", open); back.hidden = !open; if (open && cfg[0] === "bd-public") loadSubgroups(); }
    root.querySelector(".bd-groups").addEventListener("click", function () { setDrawer(!drawer.classList.contains("is-open")); });
    // Stats lives in its own always-rendered column beside the board (qm-stats-col) -- on a
    // narrow/stacked layout that column ends up far down the page, so this button's whole job is
    // just making it easy to find: scroll straight to it (the data itself is already loading there).
    var statsBtn = root.querySelector(".bd-stats");
    if (statsBtn) statsBtn.addEventListener("click", function () {
      var statsCol = panel.querySelector(".qm-stats-col");
      if (statsCol) statsCol.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    panel.querySelector(".dr-close").addEventListener("click", function () { setDrawer(false); });
    back.addEventListener("click", function () { setDrawer(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") setDrawer(false); });

    if (cfg[0] !== "bd-public") return;
    var box = document.getElementById("subgroups-box"), list = document.getElementById("subgroups-list"), empty = document.getElementById("subgroups-empty");
    var createForm = document.getElementById("subgroup-create");
    function loadSubgroups() {
      api("/api/subgroups").then(function (d) {
        box.hidden = root.getAttribute("data-level") !== "village"; list.innerHTML = ""; empty.hidden = d.groups.length > 0; createForm.hidden = !d.is_admin;
        d.groups.forEach(function (g) {
          var li = el("li", "sg-item"), row = el("div", "sg-row"), left_ = el("div");
          left_.appendChild(el("b", "", g.name)); left_.appendChild(el("small", "", g.members + " member" + (g.members === 1 ? "" : "s") + (g.description ? " · " + g.description : "")));
          row.appendChild(left_);
          var btn = el("button", "sg-btn"); btn.type = "button";
          if (g.my_status === "approved" || d.is_admin) { btn.textContent = "Open chat"; btn.addEventListener("click", function () { setDrawer(false); b.setChat({ id: g.id, name: g.name }); }); }
          else if (g.my_status === "pending") { btn.textContent = "Requested"; btn.disabled = true; }
          else { btn.textContent = "Ask to join"; btn.addEventListener("click", function () { api("/api/subgroups/" + g.id + "/join", {}).then(loadSubgroups).catch(function (e) { alert(e.message); }); }); }
          row.appendChild(btn); li.appendChild(row);
          (g.pending || []).forEach(function (p) {
            var pr = el("div", "sg-pending"), r = el("div", "sg-row"); r.appendChild(el("span", "", p.name + " wants to join"));
            var ok = el("button", "sg-btn", "Approve"), no = el("button", "sg-btn", "Decline"); ok.type = no.type = "button";
            ok.addEventListener("click", function () { api("/api/subgroups/" + g.id + "/decide", { user_id: p.user_id, approve: true }).then(loadSubgroups); });
            no.addEventListener("click", function () { api("/api/subgroups/" + g.id + "/decide", { user_id: p.user_id, approve: false }).then(loadSubgroups); });
            r.appendChild(ok); r.appendChild(no); pr.appendChild(r); li.appendChild(pr);
          });
          list.appendChild(li);
        });
      }).catch(function () {});
    }
    createForm.addEventListener("submit", function (e) {
      e.preventDefault();
      api("/api/subgroups", { name: document.getElementById("subgroup-name").value, admin_label: document.getElementById("subgroup-admin-label").value }).then(function () { document.getElementById("subgroup-name").value = ""; document.getElementById("subgroup-admin-label").value = ""; loadSubgroups(); }).catch(function (er) { alert(er.message); });
    });
  });

  // ---- removed posts, kept in the author's Private timeline ----
  var rl = document.getElementById("removed-list");
  if (rl) api("/api/board/removed").then(function (d) {
    if (!d.posts.length) return;
    document.getElementById("removed-card").hidden = false;
    d.posts.forEach(function (p) {
      var li = el("li"); li.appendChild(el("b", "", p.level + " · " + p.group + " · score " + fmt(p.score))); li.appendChild(el("span", "", p.content)); rl.appendChild(li);
    });
  }).catch(function () {});
})();
