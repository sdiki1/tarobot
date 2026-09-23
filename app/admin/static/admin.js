/* Админ-панель: редактор текстов с форматированием Telegram, поиск по текстам,
   предупреждение о несохранённых изменениях. */
(() => {
  "use strict";

  // Теги Telegram, в которые превращается форматирование редактора
  const TAGS = {
    B: "b", STRONG: "b", I: "i", EM: "i", U: "u", INS: "u", S: "s", STRIKE: "s", DEL: "s",
    CODE: "code", PRE: "pre", BLOCKQUOTE: "blockquote", "TG-SPOILER": "tg-spoiler",
  };
  const BLOCKS = new Set(["DIV", "P", "LI", "H1", "H2", "H3", "H4", "H5", "H6"]);
  const SAFE_LINK = /^(https?:\/\/|tg:\/\/|mailto:)/i;
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const escAttr = (s) => esc(s).replace(/"/g, "&quot;");

  /** DOM -> HTML Telegram: только поддерживаемые теги, весь текст экранирован. */
  function toTelegram(root) {
    let out = "";
    const walk = (node) => {
      for (const ch of node.childNodes) {
        if (ch.nodeType === Node.TEXT_NODE) {
          out += esc(ch.nodeValue.replace(/\u00a0/g, " "));
          continue;
        }
        if (ch.nodeType !== Node.ELEMENT_NODE) continue;
        const name = ch.nodeName;
        if (name === "BR") { out += "\n"; continue; }
        const block = BLOCKS.has(name);
        if (block && out && !out.endsWith("\n")) out += "\n";
        let open = "";
        let close = "";
        const tag = TAGS[name] || (name === "SPAN" && ch.classList.contains("tg-spoiler") ? "tg-spoiler" : "");
        if (name === "A") {
          const href = (ch.getAttribute("href") || "").trim();
          if (SAFE_LINK.test(href)) { open = `<a href="${escAttr(href)}">`; close = "</a>"; }
        } else if (tag) {
          open = `<${tag}>`;
          close = `</${tag}>`;
        }
        const start = out.length;
        out += open;
        const inner = out.length;
        walk(ch);
        if (open) {
          if (out.length === inner) out = out.slice(0, start); // пустой тег не нужен
          else out += close;
        }
        if (block && !out.endsWith("\n")) out += "\n";
      }
    };
    walk(root);
    return out.replace(/\s+$/, "");
  }

  /** Любой HTML -> безопасный HTML Telegram (для загрузки в редактор). */
  function normalize(html) {
    const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
    return toTelegram(doc.body);
  }

  function visibleText(html) {
    return new DOMParser().parseFromString(`<body>${html}</body>`, "text/html").body.textContent;
  }

  function setupEditor(box) {
    const area = box.querySelector(".rte-area");
    const source = box.querySelector(".rte-source");
    const counter = box.querySelector(".rte-count");
    const toolbar = box.querySelector(".rte-toolbar");
    const limit = Number(box.dataset.limit || 0);
    let sourceMode = false;

    const range = () => {
      const sel = window.getSelection();
      if (!sel.rangeCount) return null;
      const r = sel.getRangeAt(0);
      return area.contains(r.commonAncestorContainer) ? r : null;
    };
    const select = (r) => {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
    };
    const ensureFocus = () => {
      if (range()) return;
      area.focus();
      const r = document.createRange();
      r.selectNodeContents(area);
      r.collapse(false);
      select(r);
    };
    const ancestor = (node, names) => {
      for (let n = node; n && n !== area; n = n.parentNode) {
        if (n.nodeType === Node.ELEMENT_NODE && names.includes(n.nodeName)) return n;
      }
      return null;
    };
    const unwrap = (el) => {
      const parent = el.parentNode;
      while (el.firstChild) parent.insertBefore(el.firstChild, el);
      parent.removeChild(el);
      parent.normalize();
    };

    function updateCounter() {
      const len = (sourceMode ? visibleText(source.value) : area.innerText.replace(/\n$/, "")).length;
      counter.textContent = limit ? `${len} / ${limit}` : `${len} симв.`;
      counter.classList.toggle("over", Boolean(limit) && len > limit);
    }
    function changed() {
      if (!sourceMode) source.value = toTelegram(area);
      updateCounter();
      box.dispatchEvent(new Event("input", { bubbles: true }));
    }
    function load(html) {
      area.innerHTML = normalize(html);
      source.value = toTelegram(area);
      updateCounter();
    }

    function toggleWrap(tag) {
      const r = range();
      if (!r) return;
      const name = tag.toUpperCase();
      const existing = ancestor(r.startContainer, [name]) || ancestor(r.endContainer, [name]);
      if (existing) { unwrap(existing); changed(); return; }
      if (r.collapsed) return;
      const el = document.createElement(tag);
      el.appendChild(r.extractContents());
      r.insertNode(el);
      const nr = document.createRange();
      nr.selectNodeContents(el);
      select(nr);
      changed();
    }

    function link() {
      ensureFocus();
      const r = range();
      const existing = r && ancestor(r.startContainer, ["A"]);
      if (existing) { unwrap(existing); changed(); return; }
      const saved = r.cloneRange();
      let url = (window.prompt("Адрес ссылки", "https://") || "").trim();
      if (!url || url === "https://") return;
      if (!/^[a-z]+:/i.test(url)) url = `https://${url}`;
      if (!SAFE_LINK.test(url)) { window.alert("Ссылка должна начинаться с https://"); return; }
      area.focus();
      select(saved);
      if (saved.collapsed) {
        document.execCommand("insertHTML", false, `<a href="${escAttr(url)}">${esc(url)}</a>`);
      } else {
        document.execCommand("createLink", false, url);
      }
      changed();
    }

    function clearFormat() {
      const r = range();
      if (!r || r.collapsed) return;
      document.execCommand("removeFormat"); // жирный, курсив, подчёркнутый, зачёркнутый
      const cur = range() || r;
      area.querySelectorAll("tg-spoiler, code, pre, blockquote, a").forEach((el) => {
        if (cur.intersectsNode(el)) unwrap(el);
      });
      changed();
    }

    function insert(text) {
      if (sourceMode) {
        source.setRangeText(text, source.selectionStart, source.selectionEnd, "end");
        source.focus();
        changed();
        return;
      }
      ensureFocus();
      document.execCommand("insertText", false, text);
      changed();
    }

    function toggleSource(btn) {
      if (sourceMode) {
        load(source.value);
        source.hidden = true;
        area.hidden = false;
      } else {
        source.value = toTelegram(area);
        area.hidden = true;
        source.hidden = false;
      }
      sourceMode = !sourceMode;
      btn.classList.toggle("active", sourceMode);
      toolbar.querySelectorAll("[data-cmd]:not([data-cmd=source]), [data-wrap]").forEach((b) => { b.disabled = sourceMode; });
      (sourceMode ? source : area).focus();
      updateCounter();
    }

    // Кнопки панели не забирают фокус — выделение в тексте сохраняется
    toolbar.addEventListener("mousedown", (e) => {
      if (e.target.closest("button") && !sourceMode) e.preventDefault();
    });
    toolbar.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn || btn.disabled) return;
      const { cmd, wrap, insert: text } = btn.dataset;
      if (text) insert(text);
      else if (wrap) { ensureFocus(); toggleWrap(wrap); }
      else if (cmd === "link") link();
      else if (cmd === "clear") clearFormat();
      else if (cmd === "source") toggleSource(btn);
      else if (cmd) { ensureFocus(); document.execCommand(cmd); changed(); }
      refreshState();
    });

    area.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing && document.queryCommandSupported("insertLineBreak")) {
        e.preventDefault();
        document.execCommand("insertLineBreak");
      }
    });
    area.addEventListener("paste", (e) => {
      e.preventDefault();
      document.execCommand("insertText", false, (e.clipboardData || window.clipboardData).getData("text/plain"));
    });
    area.addEventListener("drop", (e) => e.preventDefault());
    area.addEventListener("input", () => { source.value = toTelegram(area); updateCounter(); });
    source.addEventListener("input", updateCounter);

    const stateButtons = toolbar.querySelectorAll("[data-cmd=bold], [data-cmd=italic], [data-cmd=underline], [data-cmd=strikeThrough], [data-cmd=link], [data-wrap]");
    function refreshState() {
      const r = range();
      stateButtons.forEach((b) => {
        let on = false;
        if (r && !sourceMode) {
          if (b.dataset.wrap) on = Boolean(ancestor(r.startContainer, [b.dataset.wrap.toUpperCase()]));
          else if (b.dataset.cmd === "link") on = Boolean(ancestor(r.startContainer, ["A"]));
          else {
            try { on = document.queryCommandState(b.dataset.cmd); } catch (err) { on = false; }
          }
        }
        b.classList.toggle("active", on);
      });
    }
    document.addEventListener("selectionchange", () => {
      if (range() || toolbar.querySelector(".active:not([data-cmd=source])")) refreshState();
    });

    box.rte = {
      load,
      sync: () => { if (!sourceMode) source.value = toTelegram(area); },
    };
    if ("showSource" in box.dataset) {
      // В разметке ошибка — показываем код как есть, без автоисправлений
      const raw = source.value;
      toggleSource(toolbar.querySelector("[data-cmd=source]"));
      source.value = raw;
      updateCounter();
    } else {
      load(source.value);
    }
  }

  document.execCommand("styleWithCSS", false, false);
  document.querySelectorAll(".rte").forEach(setupEditor);

  // ---------- Возврат к стандартному тексту ----------
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-reset]");
    if (!btn) return;
    const item = btn.closest(".text-item");
    const def = item.querySelector(".default-value").value;
    const box = item.querySelector(".rte");
    const check = item.querySelector("input[type=checkbox]");
    const input = item.querySelector("input:not([type=hidden]):not([type=checkbox]), textarea:not(.rte-source):not(.default-value)");
    if (box) box.rte.load(def);
    else if (check) check.checked = def === "true";
    else if (input) input.value = def;
    item.dispatchEvent(new Event("input", { bubbles: true }));
  });

  // ---------- Несохранённые изменения ----------
  let dirty = false;
  let submitting = false;
  const saveBar = document.querySelector("[data-dirty-note]");
  const markDirty = (e) => {
    if (!e.target.closest || !e.target.closest("form[data-guard]")) return;
    dirty = true;
    if (saveBar) saveBar.hidden = false;
  };
  document.addEventListener("input", markDirty);
  document.addEventListener("change", markDirty);
  document.addEventListener("submit", (e) => {
    e.target.querySelectorAll(".rte").forEach((box) => box.rte && box.rte.sync());
  }, true);
  document.addEventListener("submit", (e) => { if (!e.defaultPrevented) submitting = true; });
  window.addEventListener("beforeunload", (e) => {
    if (dirty && !submitting) { e.preventDefault(); e.returnValue = ""; }
  });

  // ---------- Поиск по текстам ----------
  const search = document.querySelector("[data-text-search]");
  if (search) {
    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();
      document.querySelectorAll(".group-card").forEach((group) => {
        let shown = 0;
        group.querySelectorAll(".text-item").forEach((item) => {
          const hit = !q || item.dataset.search.includes(q);
          item.hidden = !hit;
          if (hit) shown += 1;
        });
        group.hidden = shown === 0;
      });
    });
  }

  // Прокрутка к первой ошибке и автоскрытие уведомления
  const firstError = document.querySelector(".field-error");
  if (firstError) firstError.closest(".text-item, .field")?.scrollIntoView({ block: "center" });
  const toast = document.querySelector(".toast");
  if (toast) setTimeout(() => { toast.hidden = true; }, 3500);
})();
