// On job search pages (LinkedIn, Dice, ZipRecruiter, Indeed, Glassdoor, Naukri) this marks each
// job card that Tailor&Track already knows for the profile selected in the app:
//   red   "J · Applied 22 Oct"      – don't apply again
//   blue  "J · Saved" / "J · Saved from Dice" – already in Tailor&Track (maybe from another site)
//   amber "J · Similar role applied …" – same company, similar title, applied in the last 30 days
(() => {
  if (window.__jobpilotBadges) return;
  window.__jobpilotBadges = true;

  const clean = (s) => (s || "").replace(/ /g, " ").replace(/\s+/g, " ").trim();
  const JOB_LINK = /(\/job-detail\/|\/jobs\/view\/|\/viewjob|[?&](jk|vjk|lk|jid|jl)=|\/c\/[^/]+\/job\/|\/job-listing|\/rc\/clk)/i;
  const SKIP = /^(viewed|applied|saved|new|promoted|easy apply|featured|urgent|hot|today|just posted|be an early applicant|actively recruiting|medical|life|dental|vision|retirement|full[- ]time|part[- ]time|contract(or)?|on-?site|remote|hybrid)$/i;
  const PLACE = /(,|\bremote\b|\bhybrid\b|on-?site|united states|india|\barea\b)/i;
  const COLORS = { applied: ["#FDECEC", "#A11D1D"], saved: ["#EAF0FF", "#1F45C9"], similar: ["#FFF6DB", "#6B4700"] };
  const done = new WeakSet();
  const cache = new Map();

  // the job card around a title
  const cardOf = (el) => {
    let box = el;
    for (let i = 0; i < 7 && box.parentElement; i++) {
      box = box.parentElement;
      const len = clean(box.innerText).length;
      if (len > 25 && len < 700) return box;
      if (len >= 700) break;
    }
    return el.parentElement || el;
  };
  // company = the short line just below (or above) the title in the card
  const companyIn = (card, title) => {
    const lines = (card.innerText || "").split("\n").map(clean).filter(Boolean);
    const i = lines.findIndex((l) => l.startsWith(title));
    if (i < 0) return "";
    for (const l of lines.slice(i + 1, i + 4).concat(lines.slice(Math.max(0, i - 2), i).reverse())) {
      if (l.length > 1 && l.length < 70 && !SKIP.test(l) && !PLACE.test(l) && !/\d/.test(l) && !l.includes("·")) return l;
    }
    return "";
  };

  const collect = () => {
    const items = [];
    const add = (el, title, url) => {
      if (done.has(el) || title.length < 3 || title.length > 140) return;
      done.add(el);
      items.push({ el, title, url: url || "", company: companyIn(cardOf(el), title) });
    };
    for (const a of document.querySelectorAll("a[href]")) {
      if (!JOB_LINK.test(a.href)) continue;
      const t = clean(a.innerText).split(" with verification")[0];
      add(a, t, a.href);
    }
    // cards without a link (e.g. ZipRecruiter): title headings inside clickable cards
    for (const h of document.querySelectorAll('[role="button"] h2, [role="button"] h3, article h2, article h3, li h2, li h3')) {
      if (h.querySelector("a[href]") || h.closest("a[href]")) continue;
      add(h, clean(h.innerText), "");
    }
    return items;
  };

  const badge = (el, r) => {
    const next = el.nextElementSibling;
    if (next && next.classList && next.classList.contains("jobpilot-badge")) next.remove();
    const [bg, fg] = COLORS[r.status];
    const b = document.createElement("span");
    b.className = "jobpilot-badge";
    b.textContent = "J · " + r.label;
    b.title = "From Tailor&Track";
    b.style.cssText = `display:inline-block;margin:2px 0 2px 6px;padding:1px 8px;border-radius:10px;` +
      `font:600 11px/18px system-ui,sans-serif;background:${bg};color:${fg};border:1px solid ${fg}33;vertical-align:middle;`;
    el.insertAdjacentElement("afterend", b);
  };

  const ask = (items) => {
    const todo = items.filter((it) => !cache.has(it.url + "|" + it.title + "|" + it.company));
    items.filter((it) => cache.has(it.url + "|" + it.title + "|" + it.company)).forEach((it) => {
      const r = cache.get(it.url + "|" + it.title + "|" + it.company);
      if (r && r.status) badge(it.el, r);
    });
    for (let i = 0; i < todo.length; i += 60) {
      const chunk = todo.slice(i, i + 60);
      try {
        chrome.runtime.sendMessage({ type: "lookup", items: chunk.map(({ url, title, company }) => ({ url, title, company })) },
          (res) => {
            if (chrome.runtime.lastError || !res || !res.results) return;   // app not running
            res.results.forEach((r, k) => {
              const it = chunk[k];
              cache.set(it.url + "|" + it.title + "|" + it.company, r);
              if (r && r.status) badge(it.el, r);
            });
          });
      } catch (e) { /* extension was reloaded: refresh the page */ }
    }
  };

  let timer = null;
  const scan = () => { clearTimeout(timer); timer = setTimeout(() => { const it = collect(); if (it.length) ask(it); }, 700); };
  scan();
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
})();