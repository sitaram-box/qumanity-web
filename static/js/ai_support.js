/**
 * ai_support.js — the "AI Support" chat widget (2026-10-28). A scripted (not LLM-backed) 3/4-step
 * flow: category -> [name, if logged out] -> [contact, optional] -> message -> POST
 * /api/support/ticket. window.QM_LOGGED_IN (set inline in home.html from the Flask session) skips
 * the name/contact steps entirely for a logged-in visitor -- the route auto-links their ticket to
 * their own account instead.
 */
(function () {
  "use strict";

  var fab = document.getElementById("hm-action-support");
  var modal = document.getElementById("hm-support-modal");
  var chat = document.getElementById("hm-support-chat");
  var form = document.getElementById("hm-support-form");
  var input = document.getElementById("hm-support-input");
  if (!fab || !modal || !chat || !form || !input) return;

  var CATEGORIES = [["query", "A question"], ["complaint", "A complaint"], ["proposal", "A proposal"]];
  var state = null; // null until the modal opens; see resetConversation()

  function botMsg(text) {
    var el = document.createElement("div");
    el.className = "hm-support-msg is-bot";
    el.textContent = text;
    chat.appendChild(el);
    chat.scrollTop = chat.scrollHeight;
  }
  function userMsg(text) {
    var el = document.createElement("div");
    el.className = "hm-support-msg is-user";
    el.textContent = text;
    chat.appendChild(el);
    chat.scrollTop = chat.scrollHeight;
  }
  function botQuickReplies(options) {
    var wrap = document.createElement("div");
    wrap.className = "hm-support-msg is-bot";
    options.forEach(function (opt, i) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "qm-btn qm-btn-ghost";
      btn.style.marginRight = "6px";
      btn.style.marginTop = i ? "6px" : "0";
      btn.textContent = opt[1];
      btn.addEventListener("click", function () { userMsg(opt[1]); advance(opt[0]); });
      wrap.appendChild(btn);
    });
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
  }

  function resetConversation() {
    chat.innerHTML = "";
    state = { step: "category", category: null, name: null, contact: null, body: null };
    botMsg("Hi! I'm Qumanity's support assistant. What's this about?");
    botQuickReplies(CATEGORIES);
    input.placeholder = "Pick an option above…";
    input.disabled = true;
  }

  function nextStepAfterCategory() {
    if (!window.QM_LOGGED_IN) { state.step = "name"; botMsg("What's your name?"); input.disabled = false; input.placeholder = "Your name…"; input.focus(); return; }
    state.step = "body";
    botMsg("What would you like to tell us?");
    input.disabled = false; input.placeholder = "Type your message…"; input.focus();
  }

  function advance(value) {
    if (state.step === "category") {
      state.category = value;
      nextStepAfterCategory();
    } else if (state.step === "name") {
      state.name = value;
      state.step = "contact";
      botMsg("Thanks, " + value + ". An email or your Private ID, if you'd like a reply (optional — just hit Send to skip).");
      input.placeholder = "Email or Private ID (optional)…";
    } else if (state.step === "contact") {
      state.contact = value || null;
      state.step = "body";
      botMsg("What would you like to tell us?");
      input.placeholder = "Type your message…";
    } else if (state.step === "body") {
      state.body = value;
      submitTicket();
    }
  }

  function submitTicket() {
    state.step = "submitting";
    input.disabled = true;
    botMsg("One moment…");
    fetch("/api/support/ticket", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: state.category, subject: state.category, body: state.body, name: state.name, contact: state.contact }),
    })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Something went wrong"); return j; }); })
      .then(function (data) {
        botMsg(data.message + " We'll get back to you" + (state.contact ? " at " + state.contact : window.QM_LOGGED_IN ? " — check My Tickets in your Private account." : "."));
        state.step = "done";
      })
      .catch(function (e) {
        botMsg("Sorry — that didn't go through (" + e.message + "). You can try again.");
        state.step = "body";
        input.disabled = false;
      });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var value = input.value.trim();
    input.value = "";
    if (state.step === "category" || state.step === "submitting" || state.step === "done") return;
    if (state.step !== "contact" && !value) return; // contact is the one optional free-text step
    if (value) userMsg(value);
    advance(value);
  });

  fab.addEventListener("click", function () {
    modal.hidden = false;
    resetConversation();
  });
  modal.addEventListener("click", function (e) {
    if (e.target === modal || e.target.hasAttribute("data-close")) modal.hidden = true;
  });
})();
