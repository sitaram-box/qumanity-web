/**
 * qmail_format.js — the Qmail formatted-text renderer (2026-10-18), extracted out of
 * dashboard.js rather than kept as a second copy. Shared by three consumers: dashboard.js (the
 * Admin Panel's council detail view, apOpenCouncil), dash_extras.js (the dashboard's member
 * mailbox card), and the standalone /qmail page's own script once it exists. One function, one
 * definition -- the same reason social_core.regenerate_account_id() is this codebase's one place
 * account_id changes, not two that could drift apart.
 *
 * There is no HTML string anywhere in this function, on purpose: every piece of user text reaches
 * the page only through textContent or an element property, never innerHTML, so a <script> typed
 * into a message body is inert text in every case, not something that needs sanitising -- see
 * docs/QMAIL.md's note on why no sanitiser library is installed. Only three constructs are
 * recognised (**bold**, _italic_, [text](url)); everything else, including any literal angle
 * bracket, is plain text. A link whose url is not http(s) renders as its label only, never as an
 * <a> -- this is what keeps a javascript: URL from ever becoming clickable.
 *
 * Must load BEFORE dashboard.js and dash_extras.js in templates/dashboard.html (and before the
 * /qmail page's own script, once it exists) -- each calls window.qmRenderFormattedText at
 * render time, and it must already be defined when they run.
 */
(function () {
  "use strict";

  function qmRenderFormattedText(text) {
    var frag = document.createDocumentFragment();
    String(text || "").split("\n").forEach(function (line, i) {
      if (i > 0) frag.appendChild(document.createElement("br"));
      qmRenderLineInto(frag, line);
    });
    return frag;
  }

  function qmRenderLineInto(frag, line) {
    var re = /\*\*([^*]+)\*\*|_([^_]+)_|\[([^\]]+)\]\(([^)]+)\)/g;
    var last = 0, m;
    while ((m = re.exec(line)) !== null) {
      if (m.index > last) frag.appendChild(document.createTextNode(line.slice(last, m.index)));
      if (m[1] !== undefined) {
        var b = document.createElement("b");
        b.textContent = m[1];
        frag.appendChild(b);
      } else if (m[2] !== undefined) {
        var it = document.createElement("i");
        it.textContent = m[2];
        frag.appendChild(it);
      } else if (/^https?:\/\//i.test(m[4])) {
        var a = document.createElement("a");
        a.href = m[4];
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = m[3];
        frag.appendChild(a);
      } else {
        frag.appendChild(document.createTextNode(m[3]));
      }
      last = re.lastIndex;
    }
    if (last < line.length) frag.appendChild(document.createTextNode(line.slice(last)));
  }

  window.qmRenderFormattedText = qmRenderFormattedText;
})();
