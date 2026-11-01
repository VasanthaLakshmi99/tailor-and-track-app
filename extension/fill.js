// Tailor&Track form filler. Injected by the J button into the application page (all frames).
// Defines window.__ttFill(info, resume) -> Promise<{filled, attached, empty, fields}>.
// Fills EMPTY fields it recognises (text boxes, dropdowns, custom dropdowns, Yes/No buttons),
// attaches the resume and highlights what it filled. It never clicks Submit / Next.
(() => {
  if (window.__ttFill) return;

  // [key in info, regex on the field's question/label/name]; first match wins, so order matters
  const RULES = [
    ["phone_type", /phone (device )?type|type of phone/],
    ["sponsorship", /sponsor/],
    ["work_auth", /authori[sz]ed to work|legally (authori[sz]ed|eligible|able|permitted)|work authori[sz]ation|right to work|eligible to work|permitted to work/],
    ["relocate", /relocat/],
    ["visa", /visa (status|type)|immigration status|citizenship status|current status in the us/],
    ["salary", /salary|compensation|pay (expectation|requirement)|expected ctc|desired pay|pay range/],
    ["notice", /notice period|start date|available to start|earliest start|when can you start|availability to start/],
    ["years", /years of (professional |relevant |total |work )?(experience|exp)|total experience|how many years/],
    ["first_name", /\b(first|given|fore|preferred first) ?name\b|\bfname\b/],
    ["last_name", /\b(last|family|sur) ?name\b|\blname\b|\bsurname\b/],
    ["email", /e ?mail/],
    ["phone", /phone|mobile|cell|telephone|contact number/],
    ["linkedin", /linked ?in/],
    ["github", /git ?hub/],
    ["website", /website|portfolio|personal (site|url)|\bblog\b/],
    ["current_company", /current (company|employer)|most recent (company|employer)|present employer|^company$|employer name/],
    ["current_title", /current (job )?(title|role|position|designation)|most recent (job )?(title|role)/],
    ["zip", /\bzip\b|postal|post ?code|pin ?code/],
    ["city", /\bcity\b|\btown\b/],
    ["state", /\bstate\b|province|\bregion\b/],
    ["country", /\bcountry\b/],
    ["address", /street|address line|^address\b|mailing address|home address/],
    ["location", /\blocation\b|where (do )?you (live|reside)|current(ly)? (based|residing)|city, state/],
    ["full_name", /full ?name|legal name|^name\b|your name|candidate name/],
  ];
  // never touch these (voluntary / sensitive / not ours to answer)
  const SKIP = /gender|race|ethnic|veteran|disab|pronoun|sexual|date of birth|\bdob\b|birth|social security|\bssn\b|password|captcha|search jobs|keyword|referr|referred|how did you hear|cover letter|message to|middle name|extension|\bext\b|country (phone )?code|dial code|signature|i agree|acknowledge|terms|consent|salary history/;

  // every element, also inside open shadow roots (SmartRecruiters, some Oracle / SAP sites)
  function all(selector, root = document) {
    const out = [...root.querySelectorAll(selector)];
    root.querySelectorAll("*").forEach((n) => { if (n.shadowRoot) out.push(...all(selector, n.shadowRoot)); });
    return out;
  }
  const words = (s) => (s || "").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_\-.:]+/g, " ")
    .replace(/[*?]/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) &&
    getComputedStyle(el).visibility !== "hidden";
  const short = (s) => (s || "").split(" | ")[0].slice(0, 50);

  function labelOf(el) {
    const root = el.getRootNode ? el.getRootNode() : document;
    const parts = [];
    if (el.id && root.querySelector) {
      const l = root.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) parts.push(l.innerText || l.textContent);
    }
    const by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach((id) => { const n = (root.getElementById ? root : document).getElementById(id); if (n) parts.push(n.innerText || n.textContent); });
    parts.push(el.getAttribute("aria-label"), el.getAttribute("placeholder"), el.getAttribute("title"));
    const wrap = el.closest("label");
    if (wrap) parts.push(wrap.innerText);
    if (parts.filter(Boolean).join("").trim().length < 3) {
      // the question usually sits just above the field
      let box = el.parentElement;
      for (let i = 0; i < 4 && box; i++, box = box.parentElement) {
        const t = (box.innerText || "").trim();
        if (t && t.length < 250) { parts.push(t); break; }
      }
    }
    parts.push(el.name, el.id, el.getAttribute("data-automation-id"), el.getAttribute("data-qa"), el.getAttribute("autocomplete"));
    return parts.filter(Boolean).map(words).join(" | ");
  }

  function questionOf(nodes) {   // a group of radio / Yes-No buttons: the fieldset legend or the text above
    const fs = nodes[0].closest("fieldset");
    if (fs) {
      const lg = fs.querySelector("legend");
      return words(lg ? lg.innerText : fs.innerText).slice(0, 300);
    }
    let box = nodes[0].parentElement;
    for (let i = 0; i < 6 && box; i++, box = box.parentElement) {
      if (nodes.every((r) => box.contains(r))) {
        const t = words(box.innerText);
        if (t.length > 12) return t.slice(0, 300);
      }
    }
    return words(nodes[0].name);
  }

  function keyFor(text) {
    if (!text) return null;
    const first = text.split(" | ")[0];
    if (SKIP.test(first) || (!first && SKIP.test(text))) return null;
    for (const [k, re] of RULES) if (re.test(first)) return k;      // the visible label first
    if (SKIP.test(text)) return null;
    for (const [k, re] of RULES) if (re.test(text)) return k;       // then name / id / automation id
    return null;
  }

  function setValue(el, value) {   // works with React / Angular / Vue forms too
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype :
      el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  const mark = (el) => { if (el && el.style) { el.style.outline = "2px solid #2F5BEA"; el.style.backgroundColor = "#EEF3FF"; } };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const press = (el, key) => ["keydown", "keyup"].forEach((t) =>
    el.dispatchEvent(new KeyboardEvent(t, { key, code: key, bubbles: true })));
  const realClick = (el) => {
    ["pointerdown", "mousedown", "pointerup", "mouseup"].forEach((t) =>
      el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window })));
    el.click();
  };

  function pickOption(options, value, loose) {   // options: [{text, node}]
    const v = words(value);
    if (!v) return null;
    const yes = /^(y|yes|true)$/.test(v), no = /^(n|no|false)$/.test(v);
    const t = (o) => words(o.text);
    return options.find((o) => t(o) === v) ||
      (yes && options.find((o) => /^yes\b/.test(t(o)))) ||
      (no && options.find((o) => /^no\b/.test(t(o)))) ||
      options.find((o) => t(o).startsWith(v)) ||
      (v.length > 2 && options.find((o) => t(o).includes(v))) ||
      (loose && v.length > 2 && options.find((o) => v.includes(t(o)) && t(o).length > 2)) || null;
  }

  // what to type / choose for a field
  function valueFor(key, info) {
    if (key === "phone_type") return "Mobile";
    if (key === "country" && /^(us|usa|u s a)$/i.test(words(info.country))) return "United States";
    return info[key];
  }

  // custom dropdowns: Workday buttons, React-Select (Greenhouse new boards, Lever), Ashby, LinkedIn
  async function chooseFromList(trigger, key, info, typeInto) {
    const value = valueFor(key, info);
    const typed = (key === "location" || key === "city") ? (info.city || value) : value;
    if (typeInto) {
      typeInto.focus();
      setValue(typeInto, String(typed));
      press(typeInto, "ArrowDown");
    } else {
      realClick(trigger);
    }
    let opt = null;
    for (let i = 0; i < 12 && !opt; i++) {                    // the list can take a moment (or a search) to appear
      await sleep(i < 4 ? 150 : 300);
      const opts = all('[role="option"], [data-automation-id="promptOption"], li[role="menuitem"]')
        .filter(visible).map((n) => ({ text: n.innerText || n.textContent || "", node: n }));
      if (!opts.length) continue;
      opt = pickOption(opts, value, true) || (typeInto && typed !== value ? pickOption(opts, typed, true) : null);
      if (!opt && opts.length && i >= 6) break;
    }
    if (opt) {
      realClick(opt.node);
      await sleep(150);
      return true;
    }
    if (typeInto) setValue(typeInto, "");                     // don't leave half-typed text behind
    press(typeInto || trigger, "Escape");
    document.body.click();
    await sleep(100);
    return false;
  }

  function attach(input, resume) {
    const bytes = Uint8Array.from(atob(resume.b64), (c) => c.charCodeAt(0));
    const type = resume.name.toLowerCase().endsWith(".pdf") ? "application/pdf" :
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    const file = new File([bytes], resume.name, { type });
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return dt;
  }

  const isEmptyChoice = (t) => !t || /^(select|choose|please select|--|—|none selected|select one|select\.\.\.)/i.test(t.trim());

  window.__ttFill = async (info, resume) => {
    const filled = [], used = new Set();
    const done = (key, el) => { used.add(key); filled.push(key); mark(el); };

    // 1. text boxes and normal dropdowns
    const fields = all("input, textarea, select").filter((el) =>
      !el.disabled && !el.readOnly && visible(el) &&
      !/^(hidden|submit|button|checkbox|radio|file|password|image|reset|search)$/i.test(el.type || ""));
    for (const el of fields) {
      const key = keyFor(labelOf(el));
      const value = key && valueFor(key, info);
      if (!value) continue;
      if (key === "full_name" && used.has("first_name")) continue;
      const combo = el.getAttribute("role") === "combobox" || el.getAttribute("aria-autocomplete") === "list" ||
        !!el.closest('[class*="select__control"], [class*="Select-control"]');
      if (el.tagName === "SELECT") {
        if (el.selectedIndex > 0 && el.value) continue;               // already chosen
        const opt = pickOption([...el.options].map((o) => ({ text: o.text, node: o })), value, true);
        if (!opt) continue;
        setValue(el, opt.node.value);
        done(key, el);
      } else if (combo) {
        const box = el.closest('[class*="select__control"], [class*="Select-control"]');
        const shown = box ? (box.innerText || "") : el.value;
        if (!isEmptyChoice(shown) && shown.trim()) continue;
        if (await chooseFromList(el, key, info, el)) done(key, box || el);
      } else {
        if ((el.value || "").trim()) continue;                        // never overwrite what's there
        el.focus();
        setValue(el, String(value));
        el.blur();
        done(key, el);
      }
    }

    // 2. custom dropdown buttons (Workday "Select One", Oracle, SAP)
    const buttons = all('button[aria-haspopup="listbox"], [role="combobox"]:not(input), [data-automation-id="selectWidget"] button')
      .filter((b) => visible(b) && !b.disabled && !b.querySelector("input"));
    for (const b of buttons) {
      if (!isEmptyChoice(b.innerText || b.getAttribute("aria-label") || "")) continue;
      const key = keyFor(labelOf(b));
      if (!key || !valueFor(key, info)) continue;
      if (await chooseFromList(b, key, info, null)) done(key, b);
    }

    // 3. Yes / No questions as radio buttons
    const groups = {};
    all('input[type="radio"]').forEach((r) => { if (!r.disabled && r.name) (groups[r.name] = groups[r.name] || []).push(r); });
    for (const group of Object.values(groups)) {
      if (group.some((r) => r.checked)) continue;
      const shown = group.filter(visible).length ? group :
        group.filter((r) => r.closest("label") && visible(r.closest("label")));   // styled radios hide the dot
      if (!shown.length) continue;
      const key = keyFor(questionOf(group));
      if (!key || !valueFor(key, info)) continue;
      const opts = group.map((r) => ({ text: (r.closest("label") || {}).innerText || labelOf(r).split(" | ")[0] || r.value, node: r }));
      const opt = pickOption(opts, valueFor(key, info));
      if (!opt) continue;
      (opt.node.closest("label") || opt.node).click();
      if (!opt.node.checked) opt.node.click();
      done(key, opt.node.closest("label") || opt.node.parentElement);
    }

    // 4. Yes / No questions as toggle buttons (Ashby, some Greenhouse boards)
    const btnGroups = new Map();
    all("button, [role='radio']").filter((b) => visible(b) && /^(yes|no)$/i.test((b.innerText || "").trim()))
      .forEach((b) => { const g = b.parentElement; if (!btnGroups.has(g)) btnGroups.set(g, []); btnGroups.get(g).push(b); });
    for (const [, btns] of btnGroups) {
      if (btns.length < 2 || btns.some((b) => b.getAttribute("aria-pressed") === "true" || b.getAttribute("aria-checked") === "true")) continue;
      const key = keyFor(questionOf(btns));
      if (!key || !valueFor(key, info)) continue;
      const opt = pickOption(btns.map((b) => ({ text: b.innerText, node: b })), valueFor(key, info));
      if (!opt) continue;
      realClick(opt.node);
      done(key, opt.node);
    }

    // 5. resume upload (also drop zones)
    let attached = false;
    if (resume && resume.b64) {
      const files = all('input[type="file"]').filter((f) => !f.disabled && !(f.files && f.files.length));
      const target = files.find((f) => /resume|\bcv\b|curriculum/.test(labelOf(f) + " " + words((f.closest("div,section,fieldset") || {}).innerText || "").slice(0, 200))) ||
        files.find((f) => !/cover|letter|transcript|photo|portfolio/.test(labelOf(f))) || null;
      if (target) {
        try {
          const dt = attach(target, resume);
          attached = true;
          const zone = target.closest("[class*='drop'], [data-automation-id*='file'], div") || target.parentElement;
          if (zone && /drop|drag/i.test(zone.innerText || "")) {          // some sites only listen for a drop
            ["dragenter", "dragover", "drop"].forEach((t) => zone.dispatchEvent(new DragEvent(t, { bubbles: true, dataTransfer: dt })));
          }
          mark(target.parentElement || target);
        } catch (e) { /* the site blocks it: the user attaches it */ }
      }
    }

    // 6. required questions still empty, so the user knows what to answer
    const empty = [];
    all("input, textarea, select").filter((el) => visible(el) && !el.disabled &&
      !/^(hidden|submit|button|checkbox|radio|file|image|reset)$/i.test(el.type || "") &&
      (el.required || el.getAttribute("aria-required") === "true" || /\*/.test(((el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) || {}).innerText || "")) &&
      !(el.value || "").trim() &&
      !(() => { const c = el.closest('[class*="select__control"], [class*="Select-control"]'); return c && !isEmptyChoice(c.innerText); })()).forEach((el) => { const l = short(labelOf(el)); if (l && !empty.includes(l)) empty.push(l); });

    return { filled, attached, empty: empty.slice(0, 8), fields: fields.length };
  };
})();