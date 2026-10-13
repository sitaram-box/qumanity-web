/**
 * home_signin.js — the homepage's inline sign-in box (hero right column).
 *
 * This is the only sign-in entry point on the site now (the nav/footer "Login"
 * links are gone) -- reuses /login's own validation and POST /login call
 * almost verbatim, just against this box's own field ids, plus a small
 * expand/collapse for the "Forgot Private ID or PIN?" button.
 */
(function () {
  "use strict";

  var form = document.getElementById("hm-login-form");
  if (!form) return;
  var errorEl = document.getElementById("hm-login-error");
  var PIN_RE = /^(?=.*[A-Za-z0-9])[A-Za-z0-9!@#$%^&*()_+\-=\[\]{}|;:'",.<>/?]{5}$/;

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    errorEl.hidden = true;
    var pin = document.getElementById("hm-field-pin").value;
    if (!PIN_RE.test(pin)) {
      errorEl.textContent = "PIN must be 5 characters. It can include numbers, letters, or special characters — but not all special characters.";
      errorEl.hidden = false;
      return;
    }
    fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        private_id: document.getElementById("hm-field-private-id").value.trim(),
        pin: document.getElementById("hm-field-pin").value.trim(),
      }),
    })
      .then(function (res) {
        return res.json().then(function (body) { return { ok: res.ok, body: body }; });
      })
      .then(function (result) {
        if (!result.ok) throw new Error(result.body.error || "Login failed");
        window.location.href = result.body.redirect;
      })
      .catch(function (err) {
        errorEl.textContent = err.message;
        errorEl.hidden = false;
      });
  });

  var forgotBtn = document.getElementById("hm-forgot-btn");
  var forgotLinks = document.getElementById("hm-forgot-links");
  if (forgotBtn && forgotLinks) {
    forgotBtn.addEventListener("click", function () {
      var opening = forgotLinks.hidden;
      forgotLinks.hidden = !opening;
      forgotBtn.setAttribute("aria-expanded", opening ? "true" : "false");
    });
  }
})();
