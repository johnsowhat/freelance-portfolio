// Embeddable AI chat. Add to any site: <script src="https://YOUR-SERVER/widget.js" defer></script>
// Lives in a Shadow DOM, so the host site's CSS can't break it and it can't break the site.
(function () {
  if (window.__aiChatLoaded) return;
  window.__aiChatLoaded = true;
  var API = new URL(document.currentScript.src).origin + "/api/chat";
  var GREETING = __GREETING__, BUSINESS = __BUSINESS__;

  function sessionId() {
    var id;
    try { id = localStorage.getItem("ai-chat-session"); } catch (e) {}
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()).replace(/[^A-Za-z0-9_-]/g, "");
      try { localStorage.setItem("ai-chat-session", id); } catch (e) {}
    }
    return id;
  }

  var host = document.createElement("div");
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML = '<style>' +
    ':host{--accent:#1f7a5a;--bg:#fff;--ink:#17201c;--muted:#5f6b66;--line:#dde3e0;--bot:#eef3f1;all:initial}' +
    '@media (prefers-color-scheme:dark){:host{--accent:#3fb388;--bg:#1a211e;--ink:#e9efec;--muted:#9aa8a2;--line:#2c3632;--bot:#232c28}}' +
    '*{box-sizing:border-box;font-family:system-ui,-apple-system,sans-serif}' +
    '.btn{position:fixed;right:20px;bottom:20px;width:60px;height:60px;border-radius:50%;border:0;background:var(--accent);color:#fff;' +
    'cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.25);font-size:26px;z-index:2147483646}' +
    '.panel{position:fixed;right:20px;bottom:92px;width:370px;max-width:calc(100vw - 32px);height:540px;max-height:calc(100vh - 120px);' +
    'background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:16px;box-shadow:0 12px 40px rgba(0,0,0,.25);' +
    'display:none;flex-direction:column;overflow:hidden;z-index:2147483647}' +
    '.panel.open{display:flex}' +
    '.head{background:var(--accent);color:#fff;padding:14px 16px;font-weight:600;font-size:15px;display:flex;justify-content:space-between;align-items:center}' +
    '.head small{display:block;font-weight:400;opacity:.85;font-size:12px}' +
    '.close{background:none;border:0;color:#fff;font-size:22px;cursor:pointer;line-height:1}' +
    '.log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px}' +
    '.m{max-width:85%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word}' +
    '.bot{background:var(--bot);align-self:flex-start;border-bottom-left-radius:4px}' +
    '.me{background:var(--accent);color:#fff;align-self:flex-end;border-bottom-right-radius:4px}' +
    '.typing{color:var(--muted);font-size:13px;padding:0 14px 6px;min-height:20px}' +
    'form{display:flex;gap:8px;padding:10px;border-top:1px solid var(--line)}' +
    'input{flex:1;padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:14px;background:var(--bg);color:var(--ink)}' +
    'input:focus{outline:2px solid var(--accent);outline-offset:-1px}' +
    'form button{border:0;background:var(--accent);color:#fff;border-radius:10px;padding:0 14px;font-weight:600;cursor:pointer}' +
    'form button:disabled{opacity:.5;cursor:default}' +
    '@media (max-width:480px){.panel{right:16px;bottom:88px;height:calc(100vh - 110px)}}' +
    '</style>' +
    '<div class="panel" role="dialog" aria-label="Chat"><div class="head"><div><span class="title"></span><small>Usually replies instantly</small></div>' +
    '<button class="close" aria-label="Close chat">×</button></div>' +
    '<div class="log" aria-live="polite"></div><div class="typing"></div>' +
    '<form><input maxlength="1000" placeholder="Type your question…" aria-label="Your message"><button type="submit">Send</button></form></div>' +
    '<button class="btn" aria-label="Open chat">💬</button>';

  var $ = function (s) { return root.querySelector(s); };
  var panel = $(".panel"), log = $(".log"), input = $("input"), send = $("form button"), typing = $(".typing");
  $(".title").textContent = BUSINESS;

  function add(text, who) {
    var el = document.createElement("div");
    el.className = "m " + who;
    el.textContent = text;  // textContent: never render HTML from the server
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
  }

  function toggle(open) {
    panel.classList.toggle("open", open);
    if (open) {
      if (!log.children.length) add(GREETING, "bot");
      input.focus();
    }
  }
  $(".btn").addEventListener("click", function () { toggle(!panel.classList.contains("open")); });
  $(".close").addEventListener("click", function () { toggle(false); });

  $("form").addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || send.disabled) return;
    add(text, "me");
    input.value = "";
    send.disabled = true;
    typing.textContent = "Typing…";
    fetch(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session: sessionId(), message: text }) })
      .then(function (r) { return r.json(); })
      .then(function (d) { add(d.reply || "Sorry, something went wrong. Please try again.", "bot"); })
      .catch(function () { add("Connection problem. Please try again in a moment.", "bot"); })
      .finally(function () { send.disabled = false; typing.textContent = ""; input.focus(); });
  });
})();
