/**
 * mobile_keyboard.js — keeps a chat's text box (and its Send button) visible above the on-screen
 * keyboard on a phone, for every chat surface on the dashboard (village/tehsil boards, personal
 * groups, private chats). The poems marquee never hides — it stays pinned to the bottom of the
 * VISIBLE area (just above the keyboard when one is open, at the very bottom otherwise), always
 * running. Delegated, so it works for chat panels built after this script loads.
 */
(function () {
  "use strict";
  var marquee = document.getElementById("pm-bar");

  function isComposeField(el) {
    return el && el.tagName === "TEXTAREA" && el.closest(".bd-compose, .bd-cform, .qp-vol, .sg-create");
  }

  // Keep the marquee pinned just above the on-screen keyboard (never hidden, never under it).
  // With the keyboard closed, visualViewport covers the whole layout viewport, so this settles
  // back to its normal `bottom: 0`.
  function repositionMarquee() {
    if (!marquee || !window.visualViewport) return;
    var vv = window.visualViewport;
    var gap = window.innerHeight - (vv.height + vv.offsetTop);
    marquee.style.bottom = Math.max(0, Math.round(gap)) + "px";
  }

  document.addEventListener("focusin", function (e) {
    if (!isComposeField(e.target)) return;
    setTimeout(function () { e.target.scrollIntoView({ block: "end", behavior: "smooth" }); }, 250);
  });

  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", function () {
      repositionMarquee();
      var active = document.activeElement;
      if (isComposeField(active)) active.scrollIntoView({ block: "end" });
    });
    window.visualViewport.addEventListener("scroll", repositionMarquee);
  }
})();
