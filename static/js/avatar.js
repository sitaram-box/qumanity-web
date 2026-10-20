/**
 * avatar.js (2026-10-20): one reusable `window.QMAvatar.render(user, size)` for every surface
 * that shows a person's picture -- the Private account header, Family Tree nodes, Group Chat
 * bubbles, Qmail inbox/sent, Collective Board posts, and the Admin Panel. Replaces the several
 * ad-hoc "letter in a colored circle" implementations each of those grew independently.
 *
 * `user` is {name, gender, profile_picture_url, hide_identity?, account_id?} -- callers pass
 * whatever subset they have; every field is optional and degrades gracefully. Returns a real
 * HTMLElement (<img> or <div>), so it works both appended directly into normal DOM (chat bubbles,
 * board posts, etc.) and inside an SVG <foreignObject> (the Family Tree's own use, since SVG has
 * no <img>/<div> of its own).
 *
 * hide_identity (2026-10-20): when `user.hide_identity` is true, the real name/photo are never
 * used -- a neutral icon renders with the Account ID's own initials instead, mirroring
 * social_core.display_identity()'s "Account ID is the name" rule. Most of today's call sites
 * (Collective Board, Group Chat, Qmail) don't yet pass hide_identity-aware data at all --
 * social_core.py's own docstring documents board posts as "unaffected by design" -- so this
 * branch is here for any caller that does carry it (today: nowhere forces it), not retrofitted
 * onto contexts that have never masked identity.
 */
(function () {
  "use strict";

  var GENDER_COLOR = { male: "#2f6fed", female: "#e0458c", both: "#6b7280" };
  var HIDDEN_COLOR = "#6b7280";

  function initials(name) {
    var parts = (name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    var first = parts[0].charAt(0);
    var last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : "";
    return (first + last).toUpperCase();
  }

  function fallbackDiv(text, color, size, title) {
    var div = document.createElement("div");
    div.className = "qm-avatar qm-avatar-fallback";
    div.style.width = div.style.height = size + "px";
    div.style.fontSize = Math.max(10, Math.round(size * 0.4)) + "px";
    div.style.background = color;
    div.textContent = text;
    if (title) div.title = title;
    return div;
  }

  function render(user, size) {
    size = size || 40;
    user = user || {};

    if (user.hide_identity) {
      var idInitials = (user.account_id || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "ID";
      return fallbackDiv(idInitials, HIDDEN_COLOR, size, "Identity hidden");
    }

    if (user.profile_picture_url) {
      var img = document.createElement("img");
      img.className = "qm-avatar qm-avatar-img";
      img.src = user.profile_picture_url;
      img.alt = user.name || "";
      img.width = size;
      img.height = size;
      img.style.width = img.style.height = size + "px";
      img.onerror = function () {
        var replacement = fallbackDiv(initials(user.name), GENDER_COLOR[user.gender] || GENDER_COLOR.both, size, user.name || "");
        if (img.parentNode) img.parentNode.replaceChild(replacement, img);
      };
      return img;
    }

    return fallbackDiv(initials(user.name), GENDER_COLOR[user.gender] || GENDER_COLOR.both, size, user.name || "");
  }

  window.QMAvatar = { render: render };
})();
