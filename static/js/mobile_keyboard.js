/**
 * mobile_keyboard.js — keeps a chat's text box (and its Send button) visible above the on-screen
 * keyboard on a phone, for every chat surface on the dashboard (village/tehsil boards, personal
 * groups, private chats). Delegated, so it works for chat panels built after this script loads.
 *
 * 2026-11-08: this file used to also reposition the (now removed) poems marquee bar above the
 * keyboard -- that marquee-specific piece (a `marquee`/#pm-bar lookup and a
 * repositionMarquee() helper) was deleted along with the rest of the Marquee feature; the
 * compose-field behavior below is unrelated to it and is unchanged.
 */
(function () {
  "use strict";

  function isComposeField(el) {
    return el && el.tagName === "TEXTAREA" && el.closest(".bd-compose, .bd-cform, .qp-vol, .sg-create");
  }

  document.addEventListener("focusin", function (e) {
    if (!isComposeField(e.target)) return;
    setTimeout(function () { e.target.scrollIntoView({ block: "end", behavior: "smooth" }); }, 250);
  });

  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", function () {
      var active = document.activeElement;
      if (isComposeField(active)) active.scrollIntoView({ block: "end" });
    });
  }
})();
