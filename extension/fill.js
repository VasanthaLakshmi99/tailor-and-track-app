// Tailor&Track form filler. Injected by the J button into the application page (all frames).
// Defines window.__ttFill(info, resume): fills empty fields it recognises, attaches the resume,
// highlights what it filled. It never clicks Submit: the user checks the form and submits.
(() => {
  if (window.__ttFill) return;

  // [key in info, regex on the field's label/name/placeholder]; first match wins, order matters
  const RULES = [
    ["first_name", /\b(first|given|fore)[\s_-]*name\b|^fname$|firstname/],
    ["last_name", /\b(last|family|sur)[\s_-]*name\b|^lname$|lastname|surname/],
    ["email", /e-?mail/],
    ["phone", /phone|mobile|cell|telephone|contact number/],
    ["linkedin", /linked\s*in/],
    ["github", /git\s*hub/],
    ["website", /website|portfolio|personal (site|url)|blog/],
    ["sponsorship", /sponsor/],
    ["work_auth", /authori[sz]ed to work|legally (authori[sz]ed|eligible|able)|work authori[sz]ation|right to work|eligible to work/],
    ["relocate", /relocat/],
    ["visa", /visa (status|type)|immigration status|citizenship status/],
    ["salary", /salary|compensation|pay (expectation|requirement)|expected ctc|desired pay/],
    ["notice", /notice period|start date|available to start|earliest start|availability/],
    ["years", /years of (professional |relevant |total )?(experience|exp)|total experience|how many years/],
    ["current_company", /current (company|employer)|most recent (company|employer)|present employer/],
    ["current_title", /current (job )?(title|role|position|designation)|most recent (title|role)/],
    ["zip", /\bzip\b|postal|post code|postcode|pin ?code/],
    ["city", /\bcity\b|\btown\b/],
    ["state", /\bstate\b|province|region/],
    ["country", /\bcountry\b/],
    ["address", /street|address line|^address$|mailing address/],
    ["location", /location|where (do )?you (live|reside)|current(ly)? (based|residing)/],
    ["full_name", /full[\s_-]*name|legal name|^name$|your name|candidate name/],
  ];
  const SKIP = /gender|race|ethnic|veteran|disab|pronoun|date of birth|\bdob\b|social security|ssn|password|captcha|search|referr|cover letter|message to|comments?$/;

  const clean = (s) => (s || "").replace(/\s+/g, " ").trim().toLowerCase();

  function labelOf(el) {
    const parts = [];
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) parts.push(l.innerText);
    }
    const by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(n.innerText); });
    parts.push(el.getAttribute("aria-label"), el.getAttribute("placeholder"), el.closest("label")?.innerText);
    if (!parts.filter(Boolean).length || parts.filter(Boolean).join("").length < 3) {
      // the question text usually sits just above the field
      let box = el.parentElement;
      for (let i = 0; i < 3 && box; i++, box = box.parentElement) {
        const t = clean(box.innerText);
        if (t && t.length < 220) { parts.push(t); break; }
      }
    }
    parts.push(el.name, el.id, el.getAttribute("data-automation-id"), el.getAttribute("autocomplete"));
    return clean(parts.filter(Boolean).join(" | "));
  }

  function questionOf(group) {   // radio group: the fieldset legend or the text above the options
    const fs = group[0].closest("fieldset");
    if (fs) {
      const lg = fs.querySelector("legend");
      if (lg) return clean(lg.innerText);
      return clean(fs.innerText).slice(0, 300);
    }
    let box = group[0].parentElement;
    for (let i = 0; i < 5 && box; i++, box = box.parentElement) {
      if (group.every((r) => box.contains(r))) {
        const t = clean(box.innerText);
        if (t.length > 8) return t.slice(0, 300);
      }
    }
    return clean(group[0].name);
  }

  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) &&
    getComputedStyle(el).visibility !== "hidden";

  function keyFor(text) {
    if (!text || SKIP.test(text)) return null;
    for (const [k, re] of RULES) if (re.test(text)) return k;
    return null;
  }

  function setValue(el, value) {   // works with React / Angular forms too
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype :
      el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    el.focus();
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
  }

  const mark = (el) => { el.style.outline = "2px solid #2F5BEA"; el.style.backgroundColor = "#EEF3FF"; };

  function pickOption(options, value) {   // options: [{text, node}]
    const v = clean(value);
    if (!v) return null;
    const yes = /^(y|yes|true)$/.test(v), no = /^(n|no|false)$/.test(v);
    return options.find((o) => clean(o.text) === v) ||
      (yes && options.find((o) => /^yes\b/.test(clean(o.text)))) ||
      (no && options.find((o) => /^no\b/.test(clean(o.text)))) ||
      options.find((o) => clean(o.text).startsWith(v)) ||
      (v.length > 2 && options.find((o) => clean(o.text).includes(v))) || null;
  }

  function attach(input, resume) {
    const bytes = Uint8Array.from(atob(resume.b64), (c) => c.charCodeAt(0));
    const type = resume.name.toLowerCase().endsWith(".pdf") ? "application/pdf" :
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], resume.name, { type }));
    input.files = dt.files;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  window.__ttFill = (info, resume) => {
    const filled = [];
    const fields = [...document.querySelectorAll("input, textarea, select")].filter((el) =>
      !el.disabled && !el.readOnly && visible(el) &&
      !/^(hidden|submit|button|checkbox|radio|file|password|image|reset|search)$/i.test(el.type || ""));
    const used = new Set();
    for (const el of fields) {
      const key = keyFor(labelOf(el));
      const value = key && info[key];
      if (!value) continue;
      if (el.tagName === "SELECT") {
        if (el.selectedIndex > 0 && el.value) continue;            // already chosen
        const opt = pickOption([...el.options].map((o) => ({ text: o.text, node: o })), value);
        if (!opt) continue;
        setValue(el, opt.node.value);
      } else {
        if ((el.value || "").trim()) continue;                      // never overwrite what's there
        if (key === "full_name" && used.has("first_name")) continue;
        setValue(el, String(value));
      }
      used.add(key);
      mark(el);
      filled.push(key);
    }
    // Yes / No questions shown as radio buttons
    const groups = {};
    document.querySelectorAll('input[type="radio"]').forEach((r) => {
      if (!r.disabled && r.name) (groups[r.name] = groups[r.name] || []).push(r);
    });
    for (const group of Object.values(groups)) {
      if (group.some((r) => r.checked) || !group.some(visible)) continue;
      const key = keyFor(questionOf(group));
      if (!key || !info[key]) continue;
      const opts = group.map((r) => ({ text: labelOf(r).split(" | ")[0], node: r }));
      const opt = pickOption(opts, info[key]);
      if (!opt) continue;
      opt.node.click();
      mark(opt.node.parentElement || opt.node);
      filled.push(key);
    }
    // resume upload
    let attached = false;
    if (resume && resume.b64) {
      const files = [...document.querySelectorAll('input[type="file"]')].filter((f) => !f.disabled && !(f.files && f.files.length));
      const target = files.find((f) => /resume|cv\b|curriculum/.test(labelOf(f))) ||
        (files.length === 1 ? files[0] : null);
      if (target) {
        try { attach(target, resume); attached = true; mark(target.parentElement || target); } catch (e) { /* site blocks it */ }
      }
    }
    return { filled, attached, fields: fields.length };
  };
})();