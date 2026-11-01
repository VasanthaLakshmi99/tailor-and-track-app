// J button popup: read the page, check duplicates with Tailor&Track, save.
const API = "http://127.0.0.1:8765";
const $ = (id) => document.getElementById(id);
const FIELDS = ["company", "title", "location", "url", "jd"];
let tabId = null;
let source = "";
let problem = "";

function setStatus(level, msg) {
  const s = $("status");
  s.className = level;
  s.textContent = msg;
  $("save").disabled = level === "blocked" || level === "error" || level === "saved" || level === "";
}

async function call(path, body) {
  const r = await fetch(API + path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-JobPilot": "1" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
}

function job() {
  const j = { source, profile_id: Number($("profile").value) || null };
  FIELDS.forEach((k) => (j[k] = $(k).value.trim()));
  return j;
}

const LABELS = {
  new: "🟢 New job, you can save it",
  warning: "🟡 Careful: ",
  blocked: "🔴 Don't apply: ",
};

// match % against your master resume, shown before you save
function showMatch(r) {
  const box = $("match");
  box.textContent = "";
  if (!("match" in r)) {  // old app version is still running
    box.style.display = "block";
    box.textContent = "To see the match %, restart Tailor&Track: Ctrl+C in VS Code, then streamlit run app.py";
    return;
  }
  const who = $("profile").selectedOptions[0] ? $("profile").selectedOptions[0].textContent : "this profile";
  if (r.match == null) {
    box.style.display = $("jd").value.trim() ? "block" : "none";
    box.textContent = r.has_resume === false
      ? `Upload ${who}'s resume in Tailor&Track to see the match %`
      : "Add the job description to see the match %";
    return;
  }
  box.style.display = "block";
  const pct = document.createElement("span");
  pct.className = "pct " + (r.match >= 75 ? "hi" : r.match >= 50 ? "mid" : "lo");
  pct.textContent = r.match + "%";
  box.append(pct, `skills match for ${who}`);
  if (r.has_roles) {                       // does the job title fit this profile's target roles?
    const fit = document.createElement("div");
    fit.className = r.fit ? "fit ok" : "fit no";
    fit.textContent = r.fit ? `✓ Role fits: ${r.fit}` : "⚠ Job title doesn't match this profile's target roles";
    box.append(fit);
  }
  if (r.missing && r.missing.length) {
    const miss = document.createElement("div");
    miss.className = "miss";
    miss.append("Missing: ");
    r.missing.forEach((k) => {
      const s = document.createElement("span");
      s.className = "kw";
      s.textContent = k;
      miss.append(s);
    });
    box.append(miss);
  }
}

async function check() {
  const j = job();
  try {
    const r = await call("/check", j);   // always ask: the match % shows even if a field is missing
    showMatch(r);
    if (!j.company || !j.title) return setStatus("error", "Fill in company name and role title");
    if (!j.url) return setStatus("error", problem || "Add the job's own link (not the search page link)");
    if (r.level === "new") setStatus("new", LABELS.new);
    else setStatus(r.level, (LABELS[r.level] || "") + r.message);
  } catch (e) {
    setStatus("error", "Tailor&Track app is not running. Start it: streamlit run app.py");
  }
}

let timer = null;
["company", "title", "url", "jd"].forEach((k) =>
  $(k).addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(check, 500); }));
$("jd").addEventListener("input", () => ($("jdcount").textContent = `${$("jd").value.length} characters`));

$("sel").addEventListener("click", async () => {
  const [res] = await chrome.scripting.executeScript({ target: { tabId }, func: () => String(window.getSelection()) });
  if (res && res.result.trim()) {
    $("jd").value = res.result.trim();
    $("jd").dispatchEvent(new Event("input"));
  } else {
    setStatus("error", "First select the JD text on the page, then click this button.");
  }
});

$("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("save").disabled = true;
  try {
    const r = await call("/save", job());
    if (r.level === "new" || r.level === "warning") {
      setStatus("saved", `✓ Saved to Tailor&Track` + (r.match != null ? ` · match ${r.match}%` : ""));
    } else {
      setStatus(r.level === "blocked" ? "blocked" : "error", (LABELS[r.level] || "") + r.message);
    }
  } catch (err) {
    setStatus("error", "Tailor&Track app is not running. Start it: streamlit run app.py");
  }
});

// fill the application form on this page with the profile's saved answers + resume (never submits)
const NAMES = { first_name: "first name", last_name: "last name", full_name: "name", email: "email", phone: "phone",
  linkedin: "LinkedIn", github: "GitHub", website: "website", city: "city", state: "state", zip: "ZIP", country: "country",
  address: "address", location: "location", current_company: "company", current_title: "title", years: "years",
  work_auth: "work authorization", sponsorship: "sponsorship", relocate: "relocation", salary: "salary",
  notice: "start date", visa: "visa" };
$("fill").addEventListener("click", async () => {
  const msg = $("fillmsg");
  msg.style.display = "block";
  msg.textContent = "Filling…";
  try {
    const j = job();
    const r = await call("/apply_info", j);
    const resume = r.resume_b64 ? { b64: r.resume_b64, name: r.resume_name } : null;
    await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, files: ["fill.js"] });
    const out = await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: (info, res) => (window.__ttFill ? window.__ttFill(info, res) : null),
      args: [r.info || {}, resume],
    });
    const filled = [...new Set(out.flatMap((o) => (o && o.result && o.result.filled) || []))];
    const attached = out.some((o) => o && o.result && o.result.attached);
    if (!filled.length && !attached) {
      msg.textContent = "No empty form fields found here. Open the application form (click Apply on the job page), then try again. " +
        "Add more answers in Tailor&Track → Profiles → ✍️ Application form answers.";
      return;
    }
    msg.textContent = `✓ Filled ${filled.length}: ${filled.map((k) => NAMES[k] || k).join(", ")}` +
      (attached ? ` · attached ${r.resume_kind} resume ${r.resume_name}` : (resume ? " · attach the resume yourself" : "")) +
      ". Blue boxes = filled. Check every answer, then click Submit yourself.";
  } catch (e) {
    msg.textContent = "Can't fill this page (the app is not running, or the site blocks extensions).";
  }
});

// profile picker: which candidate this job is for
async function loadProfiles() {
  const r = await call("/profiles");
  const sel = $("profile");
  sel.textContent = "";
  r.profiles.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = p.name;
    if (p.id === r.active) o.selected = true;
    sel.append(o);
  });
}
$("profile").addEventListener("change", async () => {
  await call("/active", { profile_id: Number($("profile").value) });  // same profile in the app
  check();
});

(async function start() {
  const forced = new URLSearchParams(location.search).get("tabId"); // used only for testing
  if (forced) tabId = Number(forced);
  else tabId = (await chrome.tabs.query({ active: true, currentWindow: true }))[0].id;
  try {
    // read the page and any frames inside it, then keep the best value for each field
    const results = await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, files: ["extract.js"] });
    // trust the main page; frames inside it may only supply a longer JD
    const main = results.find((r) => r.frameId === 0) || results[0];
    const d = Object.assign({}, (main && main.result) || {});
    // some career sites (e.g. iCIMS) show the job inside a frame: use that frame's details
    const inner = results.map((r) => (r && r.result) || {})
      .filter((v) => (v.jd || "").length >= 200)
      .sort((a, b) => b.jd.length - a.jd.length)[0];
    if (inner && inner.jd.length > (d.jd || "").length) {
      const mainIsJob = (d.jd || "").length >= 200;   // if the main page has no JD, the frame IS the job
      d.jd = inner.jd;
      for (const k of ["title", "company", "location"]) if (!d[k] || !mainIsJob) d[k] = inner[k] || d[k] || "";
    }
    source = d.source || "";
    problem = d.problem || "";
    FIELDS.forEach((k) => ($(k).value = d[k] || ""));
    $("jd").dispatchEvent(new Event("input"));
  } catch (e) {
    setStatus("error", "Can't read this page. Open a job page and try again.");
    return;
  }
  try {
    await loadProfiles();
  } catch (e) {
    return setStatus("error", "Tailor&Track app is not running. Start it: streamlit run app.py");
  }
  check();
})();