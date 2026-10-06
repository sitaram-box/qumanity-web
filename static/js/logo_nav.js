/**
 * logo_nav.js — Item 12: consistent logo click behavior sitewide.
 *
 * Default ("noop"): never navigates away. Scrolls to top instead. Covers
 * Homepage, About, Sign In, Dashboard (set no data-logo-nav attribute, or
 * "noop" explicitly).
 *
 * Registration ("confirm-exit", set via <body data-logo-nav="confirm-exit">
 * on register.html): clicking the logo opens a confirm popup before
 * leaving, since the wizard holds in-progress, not-yet-saved data.
 */
(function () {
  "use strict";
  var mode = document.body.getAttribute("data-logo-nav") || "noop";

  function scrollTop() {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function buildConfirmPopup() {
    var backdrop = document.createElement("div");
    backdrop.className = "qm-confirm-backdrop";
    backdrop.hidden = true;

    var box = document.createElement("div");
    box.className = "qm-confirm-box";

    var p = document.createElement("p");
    p.textContent = "Do you really want to exit and cancel the registration process?";

    var actions = document.createElement("div");
    actions.className = "qm-confirm-actions";

    var cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "qm-btn qm-btn-ghost";
    cancelBtn.textContent = "Cancel & Continue";

    var exitBtn = document.createElement("button");
    exitBtn.type = "button";
    exitBtn.className = "qm-btn qm-btn-primary";
    exitBtn.textContent = "Yes, Exit";

    actions.appendChild(cancelBtn);
    actions.appendChild(exitBtn);
    box.appendChild(p);
    box.appendChild(actions);
    backdrop.appendChild(box);
    document.body.appendChild(backdrop);

    function close() { backdrop.hidden = true; }
    cancelBtn.addEventListener("click", close);
    backdrop.addEventListener("click", function (e) { if (e.target === backdrop) close(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !backdrop.hidden) close(); });
    exitBtn.addEventListener("click", function () {
      try { sessionStorage.removeItem("qm_reg_draft"); } catch (e) {}
      window.location.href = "/";
    });

    return backdrop;
  }

  var confirmPopup = mode === "confirm-exit" ? buildConfirmPopup() : null;

  function wireLogo(el) {
    if (!el) return;
    el.addEventListener("click", function (e) {
      if (mode === "confirm-exit") {
        e.preventDefault();
        confirmPopup.hidden = false;
        return;
      }
      e.preventDefault();
      scrollTop();
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll(".qm-logo, .hm-brand"), wireLogo);
})();
