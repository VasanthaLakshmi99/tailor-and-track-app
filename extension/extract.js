// Runs inside the job page when you click the J button.
// Reads company, role title, location and JD from the page you are viewing.
//
// It tries several ways, best first, and each one only fills fields that are still empty:
//   1. hidden JobPosting data that most job sites include for Google (JSON-LD / microdata)
//   2. known layouts: LinkedIn, Dice, ZipRecruiter, Indeed, Glassdoor, Naukri, Monster, SimplyHired,
//      and company career systems: Greenhouse, Lever, Workday, Ashby, SmartRecruiters, Workable,
//      iCIMS, Taleo, Jobvite, BambooHR ...
//   3. any other site: the "Job description" heading, the biggest job-like text block,
//      the page title, the company name in the web address
(() => {
  // hide Tailor&Track's own badges while reading, so "J · Saved" is never taken as company or title
  const badges = [...document.querySelectorAll(".jobpilot-badge")];
  badges.forEach((b) => { b.dataset.jpText = b.textContent; b.textContent = ""; });
  const restore = () => badges.forEach((b) => { b.textContent = b.dataset.jpText || ""; });
  const clean = (s) => (s || "").replace(/ /g, " ").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
  // "selector" -> text, "selector@attr" -> attribute value; first one found wins
  const text = (sel) => {
    for (const s of [].concat(sel)) {
      const [css, attr] = s.split("@");
      let el = null;
      try { el = document.querySelector(css); } catch (e) { continue; }
      if (!el) continue;
      const v = clean(attr ? el.getAttribute(attr) : (el.innerText || el.textContent));
      if (v) return v;
    }
    return "";
  };
  const meta = (name) => text([`meta[property="${name}"]@content`, `meta[name="${name}"]@content`]);
  const htmlToText = (html) => {
    const d = document.createElement("div");
    d.innerHTML = (html || "").replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|li|div|h\d)>/gi, "\n").replace(/<li>/gi, "- ");
    return clean(d.textContent);
  };
  const titleCase = (s) => s.replace(/[-_.]+/g, " ").replace(/\s+/g, " ").trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());

  // ---------------------------------------------------------------- JD finders
  const JD_HEAD = /^(about the job|job description|description|about the role|about this role|job details|role description|full job description|job summary|position summary|position description|job overview|role overview|about the position|the opportunity|the role|overview)$/i;
  const jdByHeading = () => {
    for (const h of document.querySelectorAll("h1,h2,h3,h4,strong,b,span,div,p")) {
      const t = clean(h.textContent);
      if (t.length > 40 || !JD_HEAD.test(t.replace(/:$/, ""))) continue;
      let box = h;
      while (box.parentElement && clean(box.innerText).length < t.length + 150) box = box.parentElement;
      const body = clean(box.innerText);
      if (body.length > t.length + 150 && body.length < 40000) return clean(body.slice(body.indexOf(t) + t.length));
    }
    return "";
  };
  // the smallest block that reads like a job description (responsibilities, requirements, skills ...)
  const JD_WORDS = ["responsibilit", "requirement", "qualification", "experience", "skills", "you will", "you'll",
                    "what we", "about you", "benefits", "nice to have", "must have", "preferred", "years"];
  const jdByWords = () => {
    let best = null;
    for (const el of document.querySelectorAll("article,section,main,div,td")) {
      const t = el.textContent || "";
      if (t.length < 300 || t.length > 25000) continue;
      const low = t.toLowerCase();
      const hits = JD_WORDS.filter((w) => low.includes(w)).length;
      if (hits < 4) continue;
      if (!best || hits > best[0] || (hits === best[0] && t.length < best[1])) best = [hits, t.length, el];
    }
    return best ? clean(best[2].innerText) : "";
  };

  // the job title is usually the biggest text on the page (outside the menu and footer)
  const biggestText = () => {
    let best = null;
    for (const el of document.querySelectorAll("h1,h2,h3,div,span,p,strong")) {
      if (el.children.length > 1 || el.closest("header,nav,footer")) continue;
      const t = clean(el.textContent);
      if (t.length < 4 || t.length > 100 || JD_HEAD.test(t)) continue;
      const size = parseFloat(getComputedStyle(el).fontSize) || 0;
      if (size >= 18 && (!best || size > best[0])) best = [size, t];
    }
    return best ? best[1] : "";
  };

  // ---------------------------------------------------------------- location helpers
  // from a line like "CodeVyasa • Greater Bloomington Area" or "Bengaluru, India · 4 months ago · 100 applicants"
  const SEP = /\s*[·•]\s*/;
  const NOT_PLACE = /(viewed|promoted|applied|saved|easy apply|early applicant|actively|ago\b|applicant|clicked|people|reposted|benefit|401\(k\)|over \d|employees|\$|\/hr|\/yr)/i;
  const PLACE = /(,|\barea\b|remote|on-?site|hybrid|united states|india|\busa?\b|\buk\b|canada)/i;
  const placeOk = (s) => s && s.length >= 2 && s.length <= 80 && !NOT_PLACE.test(s);
  const locationLine = (company) => {
    let afterCompany = null, beforeTime = null;
    for (const el of document.querySelectorAll("div,span,p")) {
      const raw = el.textContent || "";
      if (raw.length < 4 || raw.length > 300 || !/[·•]/.test(raw)) continue;
      for (const line of (el.innerText || "").split("\n").map(clean)) {   // line by line: never glue boxes together
        const segs = line.split(SEP).map(clean).filter(Boolean);
        if (segs.length < 2) continue;
        if (company && segs[0].toLowerCase() === company.toLowerCase() && placeOk(segs[1])) {
          if (!afterCompany || line.length < afterCompany[0]) afterCompany = [line.length, segs[1]];
        }
        if (/(ago|applicant|clicked|people)/i.test(line) && placeOk(segs[0]) && PLACE.test(segs[0])) {
          if (!beforeTime || line.length < beforeTime[0]) beforeTime = [line.length, segs[0]];
        }
      }
    }
    return (afterCompany || beforeTime || [0, ""])[1];  // blank is better than wrong
  };

  // ---------------------------------------------------------------- search pages (list left, details right)
  const SEARCHY = /(^\d[\d,]*\+?\s.*\bjobs?\b|\bjobs?\s+in\b|^search\b|^jobs?$|jobs? near|^careers?$|^job search$|^open positions$|^current openings$)/i;
  const jdHeading = () => [...document.querySelectorAll("h1,h2,h3,h4,strong,b,span,div,p")]
    .find((h) => { const t = clean(h.textContent); return t.length <= 40 && JD_HEAD.test(t.replace(/:$/, "")); }) || null;
  // a link to ONE job looks like this; a search page link does not
  const JOB_LINK = /(\/job-detail\/|\/jobs\/view\/|\/viewjob|[?&](jk|vjk|lk|jid|jl|gh_jid)=|\/c\/[^/]+\/job\/|\/jobs\/[^/?]*\d{5,}|\/job\/[^/?]+|job-listing)/i;
  const BADGE = /^(viewed|applied|saved|new|promoted|easy apply|featured|urgent|hot|today|just posted)$/i;
  const titleHeading = (title) => {
    const all = [...document.querySelectorAll("h1,h2,h3")].filter((e) => clean(e.textContent) === title);
    const jdh = jdHeading();
    const before = jdh ? all.filter((e) => e.compareDocumentPosition(jdh) & Node.DOCUMENT_POSITION_FOLLOWING) : [];
    return before.length ? before[before.length - 1] : (all[0] || null);
  };
  const cardLinks = (title) =>
    [...document.querySelectorAll("a[href]")].filter((a) => JOB_LINK.test(a.href) && clean(a.textContent) === title);
  const ownJobLink = (title) => {
    const h = titleHeading(title);
    if (h) {
      const a = h.closest("a[href]") || h.querySelector("a[href]");
      if (a && JOB_LINK.test(a.href)) return a.href;
      let box = h;
      for (let i = 0; i < 6 && box.parentElement; i++) {
        box = box.parentElement;
        const found = [...box.querySelectorAll("a[href]")].filter((x) => JOB_LINK.test(x.href));
        const bases = new Set(found.map((x) => x.href.split("?")[0]));
        if (bases.size === 1) return found[0].href;
        if (bases.size > 1) break;
      }
    }
    const cards = cardLinks(title);
    const unique = [...new Set(cards.map((a) => a.href.split("?")[0]))];
    if (unique.length === 1) return cards[0].href;
    const picked = cards.find((a) => a.closest('[aria-selected="true"],[aria-current="true"],[aria-current="page"],[class*="selected" i],[class*="active" i]'));
    return picked ? picked.href : "";  // several jobs with the same title and none highlighted: don't guess
  };
  const titleBeforeJd = () => {
    const jdh = jdHeading();
    if (!jdh) return "";
    let best = "";
    for (const h of document.querySelectorAll("h1,h2,h3")) {
      if (h === jdh || h.contains(jdh) || jdh.contains(h)) continue;
      if (!(h.compareDocumentPosition(jdh) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      const t = clean(h.textContent);
      if (t.length < 3 || t.length > 120 || SEARCHY.test(t) || JD_HEAD.test(t)) continue;
      best = t;
    }
    return best;
  };
  const detailLines = (title) => {
    const h = titleHeading(title);
    if (!h) return [];
    let box = h;
    for (let i = 0; i < 5 && box.parentElement && clean(box.innerText).length < title.length + 120; i++) box = box.parentElement;
    const lines = (box.innerText || "").split("\n").map(clean).filter(Boolean);
    const i = lines.findIndex((l) => l.startsWith(title));
    return i < 0 ? [] : lines.slice(i + 1, i + 9);
  };
  const companyFromLines = (lines) => {
    for (const l of lines) {
      let m = l.match(/^(?:learn more about|see (?:more|all) jobs (?:at|from)|more jobs (?:at|from)|view (?:all )?jobs (?:at|from)|about the company:?|company:)\s+(.+?)\.?$/i);
      if (m) return clean(m[1]);
      m = l.match(/^(.+?)\s*[•·|]\s*[\d,]+\+?\s*(?:[-–]\s*[\d,]+\+?\s*)?employees/i);
      if (m) return clean(m[1]);
    }
    return "";
  };
  const locationFromLines = (lines) => {
    for (const l of lines) {
      const first = clean(l.split(SEP)[0]);
      if (PLACE.test(first) && placeOk(first) && !/employees|\$|\/hr|\/yr/i.test(l)) return first;
    }
    return "";
  };
  const companyNear = (title) => {
    const fromDetail = companyFromLines(detailLines(title));
    if (fromDetail) return fromDetail;
    const h = titleHeading(title);
    let box = h;
    for (let i = 0; h && i < 5 && box.parentElement; i++) {
      box = box.parentElement;
      const a = [...box.querySelectorAll("a[href]")].find((x) => /compan|employer|organi[sz]ation/i.test(x.href)
        && clean(x.textContent).length > 1 && clean(x.textContent).length < 80);
      if (a) return clean(a.textContent);
    }
    for (const a of cardLinks(title)) {
      let card = a;
      while (card.parentElement && clean(card.innerText).length < title.length + 15) card = card.parentElement;
      const lines = (card.innerText || "").split("\n").map(clean).filter(Boolean);
      const i = lines.findIndex((l) => l.startsWith(title));
      if (i < 0) continue;
      for (const line of lines.slice(i + 1, i + 4).concat(lines.slice(Math.max(0, i - 1), i))) {   // below, then above the title
        if (!BADGE.test(line) && !PLACE.test(line) && !/\d/.test(line) && line.length < 80
            && !/(medical|dental|vision|life|retirement|pto|full[- ]time|part[- ]time|contract|on-?site|remote|hybrid|apply)/i.test(line)) return line;
      }
    }
    return "";
  };

  // ---------------------------------------------------------------- which site is this?
  const host = location.hostname.toLowerCase();
  const path = location.pathname;
  const SOURCES = [
    ["linkedin.", "LinkedIn"], ["dice.", "Dice"], ["ziprecruiter.", "ZipRecruiter"], ["indeed.", "Indeed"],
    ["glassdoor.", "Glassdoor"], ["naukri.", "Naukri"], ["foundit.", "foundit"], ["monster.", "Monster"],
    ["simplyhired.", "SimplyHired"], ["careerbuilder.", "CareerBuilder"], ["wellfound.", "Wellfound"],
    ["builtin.", "Built In"], ["instahyre.", "Instahyre"], ["hirist.", "Hirist"], ["shine.", "Shine"],
    ["timesjobs.", "TimesJobs"], ["cutshort.", "Cutshort"], ["jobright.", "Jobright"], ["otta.", "Welcome to the Jungle"],
    ["welcometothejungle.", "Welcome to the Jungle"], ["remoteok.", "Remote OK"], ["weworkremotely.", "We Work Remotely"],
    ["greenhouse.io", "Greenhouse"], ["lever.co", "Lever"], ["myworkdayjobs.", "Workday"], ["workday.", "Workday"],
    ["ashbyhq.", "Ashby"], ["smartrecruiters.", "SmartRecruiters"], ["workable.", "Workable"], ["icims.", "iCIMS"],
    ["taleo.", "Taleo"], ["jobvite.", "Jobvite"], ["bamboohr.", "BambooHR"], ["recruitee.", "Recruitee"],
    ["breezy.hr", "Breezy"], ["teamtailor.", "Teamtailor"], ["applytojob.", "JazzHR"], ["successfactors.", "SuccessFactors"],
    ["oraclecloud.", "Oracle Cloud"], ["paylocity.", "Paylocity"], ["ultipro.", "UKG"], ["ukg.", "UKG"],
    ["adp.", "ADP"], ["zohorecruit.", "Zoho Recruit"], ["freshteam.", "Freshteam"], ["rippling", "Rippling"],
    ["pinpointhq.", "Pinpoint"], ["personio.", "Personio"],
  ];
  const BOARD_HOSTS = /(linkedin|dice|ziprecruiter|indeed|glassdoor|naukri|foundit|monster|simplyhired|careerbuilder|wellfound|builtin|instahyre|hirist|shine|timesjobs|cutshort|jobright|otta|welcometothejungle|remoteok|weworkremotely|google)\./;
  const sourceName = () => {
    const hit = SOURCES.find(([k]) => host.includes(k));
    return hit ? hit[1] : "Company site";
  };

  // company name hidden in the web address of company career systems
  const companyFromUrl = () => {
    const seg = (i) => (path.split("/").filter(Boolean)[i] || "");
    let m;
    if (/greenhouse\.io|lever\.co|ashbyhq\.com|workable\.com|smartrecruiters\.com|jobvite\.com|breezy\.hr|pinpointhq/.test(host)) {
      const s = seg(0);
      if (s && !/^(embed|jobs?|apply|careers?|j|o|v1)$/i.test(s)) return titleCase(decodeURIComponent(s));
    }
    if ((m = host.match(/^([a-z0-9-]+)\.(wd\d+\.)?myworkdayjobs\.com/))) return titleCase(m[1]);
    if ((m = host.match(/^(?:careers?-|jobs-)?([a-z0-9-]+)\.(icims|bamboohr|recruitee|teamtailor|applytojob|zohorecruit|freshteam|taleo|breezy|pinpointhq|personio)\./)))
      return titleCase(m[1].replace(/^(careers?|jobs)-/, ""));
    // careers.acme.com / jobs.acme.com / acme.com/careers
    if (!BOARD_HOSTS.test(host) && sourceName() === "Company site") {
      const parts = host.replace(/^www\./, "").split(".");
      const name = /^(careers?|jobs|apply|talent|work|join|hiring)$/.test(parts[0]) ? parts[1] : parts[0];
      if (name && name.length > 1) return titleCase(name);
    }
    return "";
  };
  // "Senior DevOps Engineer at Acme | Lever", "Job Application for X at Acme", "Acme - DevOps Engineer"
  const NOT_COMPANY = /^(careers?|jobs?|job board|job details|job application|apply|home|lever|greenhouse|workday|ashby|smartrecruiters|workable|icims|taleo|jobvite|bamboohr|linkedin|indeed|glassdoor|naukri|dice|ziprecruiter|monster|built in|wellfound)$/i;
  const companyFromTabTitle = (title) => {
    const t = clean(document.title).replace(/^\(\d+\)\s*/, "");
    let m = t.match(/\bat\s+(.+?)(?:\s+[|\-–—]\s+.*)?$/i);
    if (m && m[1].length < 60 && !NOT_COMPANY.test(m[1])) return clean(m[1]);
    const parts = t.split(/\s+[|\-–—]\s+/).map(clean).filter(Boolean);
    if (title && parts.length >= 2 && parts.some((p) => p.toLowerCase() === title.toLowerCase())) {
      const rest = parts.filter((p) => p.toLowerCase() !== title.toLowerCase() && !NOT_COMPANY.test(p) && p.length < 60);
      if (rest.length) return rest[0].replace(/\s+(careers?|jobs)$/i, "").replace(/^careers?\s+at\s+/i, "");
    }
    return "";
  };
  const companyFromSiteName = () => {
    const s = meta("og:site_name").replace(/\s+(careers?|jobs)$/i, "").replace(/^careers?\s+at\s+/i, "");
    return s && !NOT_COMPANY.test(s) && !BOARD_HOSTS.test(s.toLowerCase() + ".") ? s : "";
  };

  // ---------------------------------------------------------------- start reading
  const out = { company: "", title: "", location: "", jd: "", source: sourceName(), url: location.href };
  const fill = (key, value) => { if (!out[key] && value) out[key] = clean(value); };

  // 1a. JSON-LD JobPosting (most job sites have it)
  const findPosting = (node) => {
    if (!node || typeof node !== "object") return null;
    if (Array.isArray(node)) { for (const n of node) { const r = findPosting(n); if (r) return r; } return null; }
    const t = node["@type"];
    if (t === "JobPosting" || (Array.isArray(t) && t.includes("JobPosting"))) return node;
    return findPosting(node["@graph"]);
  };
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    let p = null;
    try { p = findPosting(JSON.parse(s.textContent)); } catch (e) { /* ignore broken data */ }
    if (!p) continue;
    const org = p.hiringOrganization;
    fill("title", p.title);
    fill("company", typeof org === "string" ? org : org && org.name);
    fill("jd", htmlToText(p.description));
    const loc = [].concat(p.jobLocation || [])[0];
    const a = loc && loc.address;
    if (a) fill("location", [a.addressLocality, a.addressRegion, a.addressCountry && (a.addressCountry.name || a.addressCountry)]
      .filter((x) => typeof x === "string" && x).join(", "));
    if (/TELECOMMUTE/i.test(p.jobLocationType || "")) out.location = out.location ? out.location + " (Remote)" : "Remote";
    break;
  }
  // 1b. microdata JobPosting
  const md = document.querySelector('[itemtype*="JobPosting" i]');
  if (md) {
    const g = (sel) => { const e = md.querySelector(sel); return e ? clean(e.getAttribute("content") || e.innerText || e.textContent) : ""; };
    fill("title", g('[itemprop="title"]'));
    fill("company", g('[itemprop="hiringOrganization"] [itemprop="name"]') || g('[itemprop="hiringOrganization"]'));
    fill("location", [g('[itemprop="addressLocality"]'), g('[itemprop="addressRegion"]')].filter(Boolean).join(", "));
    fill("jd", g('[itemprop="description"]'));
  }

  // 2. known layouts
  const SITES = [
    { m: /dice\./, title: ['h1[data-cy="jobTitle"]', "h1"], company: ['a[data-cy="companyNameLink"]', '[data-cy="companyNameNoLink"]', '[data-testid="job-detail-header-card"] a'],
      loc: ['[data-cy="location"]', 'li[data-cy="location"]'], jd: ['[data-testid="jobDescriptionHtml"]', "#jobDescription", '[data-cy="jobDescription"]'] },
    { m: /ziprecruiter\./, title: ["h1.job_title"], company: [".hiring_company_text", ".hiring_company a", "a.hiring_company", '[data-testid="job-card-company"]'],
      loc: [".location_text", ".hiring_location"], jd: [".job_description", ".jobDescriptionSection", '[class*="job_description"]'] },
    { m: /indeed\./, title: ['h1[data-testid="jobsearch-JobInfoHeader-title"]', '[data-testid="jobsearch-JobInfoHeader-title"]', "h1"],
      company: ['[data-testid="inlineHeader-companyName"]', '[data-company-name="true"]'],
      loc: ['[data-testid="inlineHeader-companyLocation"]', '[data-testid="job-location"]'], jd: ["#jobDescriptionText"] },
    { m: /glassdoor\./, title: ['[data-test="job-title"]', '[data-test="jobTitle"]', '[class*="JobDetails_jobTitle"]'],
      company: ['[data-test="employer-name"]', '[data-test="employerName"]', '[class*="EmployerProfile_employerName"]'],
      loc: ['[data-test="location"]', '[class*="JobDetails_location"]'], jd: ['[class*="JobDetails_jobDescription"]', ".jobDescriptionContent", '[data-test="jobDescriptionContent"]'] },
    { m: /naukri\./, title: ['[class*="jd-header-title"]', "h1"], company: ['[class*="jd-header-comp-name"] a', '[class*="jd-header-comp-name"]'],
      loc: ['[class*="jhc__location"] a', '[class*="location"] a'], jd: ['[class*="job-desc"]', '[class*="dang-inner-html"]'] },
    { m: /simplyhired\./, title: ['[data-testid="viewJobTitle"]'], company: ['[data-testid="viewJobCompanyName"]'],
      loc: ['[data-testid="viewJobCompanyLocation"]'], jd: ['[data-testid="viewJobBodyJobFullDescriptionContent"]'] },
    { m: /monster\.|foundit\./, title: ['h1[data-testid="jobTitle"]', '[class*="jobTitle"] h1', "h1"], company: ['[data-testid="company"]', '[class*="companyName"]'],
      loc: ['[data-testid="jobDetailLocation"]', '[class*="location"]'], jd: ['[data-testid="svx-description-container-inner"]', '[class*="jobDescription"]', '[class*="job-description"]'] },
    { m: /greenhouse\.io/, title: ["h1.app-title", ".job__title h1", "h1"], company: [".company-name"],
      loc: [".location", ".job__location"], jd: [".job__description", "#content", "#app_body"] },
    { m: /lever\.co/, title: [".posting-headline h2", "h2"], company: [".main-header-logo img@alt", 'meta[property="og:title"]@content'],
      loc: [".posting-categories .location", ".posting-category.location"], jd: ['[data-qa="job-description"]', ".section-wrapper.page-full-width", ".posting-page .content"] },
    { m: /myworkdayjobs\.|workday\./, title: ['[data-automation-id="jobPostingHeader"]', "h2"], company: [],
      loc: ['[data-automation-id="locations"] dd', '[data-automation-id="locations"]'], jd: ['[data-automation-id="jobPostingDescription"]'] },
    { m: /ashbyhq\./, title: ['h1[class*="_title"]', "h1"], company: [],
      loc: ['[class*="_section"] [class*="_location"]'], jd: ['[class*="_descriptionText"]', '[class*="description"]'] },
    { m: /smartrecruiters\./, title: ["h1.job-title", "h1"], company: ['[itemprop="hiringOrganization"] [itemprop="name"]', ".company-name"],
      loc: ['[itemprop="address"]', ".job-detail .location"], jd: ['[itemprop="description"]', ".job-sections"] },
    { m: /workable\./, title: ['h1[data-ui="job-title"]', "h1"], company: ['[data-ui="company-name"]'],
      loc: ['[data-ui="job-location"]'], jd: ['[data-ui="job-description"]', '[data-ui="job-requirements"]'] },
    { m: /icims\./, title: [".iCIMS_Header", "h1"], company: [], loc: [".iCIMS_JobHeaderTag dd", '[class*="iCIMS_JobHeaderField"]'],
      jd: [".iCIMS_JobContent", ".iCIMS_InfoMsg_Job"] },
    { m: /taleo\./, title: [".titlepage", '[id*="reqTitle"]'], company: [], loc: ['[id*="reqlocation"]'],
      jd: ['[id*="requisitionDescriptionInterface.ID"]', ".editablesection"] },
    { m: /jobvite\./, title: [".jv-header", "h2.jv-header"], company: [], loc: [".jv-job-detail-meta"], jd: [".jv-job-detail-description"] },
    { m: /bamboohr\./, title: ["h2", "h1"], company: [], loc: ['[class*="location"]'], jd: [".BambooRich", '[class*="jobDescription"]'] },
    { m: /builtin\./, title: ["h1"], company: ['[data-id="company-title"]', 'a[href*="/company/"]'], loc: [], jd: ['[class*="job-description"]', "#job-post-body"] },
    { m: /wellfound\./, title: ["h1"], company: ['a[href*="/company/"]'], loc: [], jd: ['[class*="description"]'] },
  ];

  if (host.includes("linkedin.")) {
    // search page shows the job on the right side: build the clean job link
    const id = new URLSearchParams(location.search).get("currentJobId") || (path.match(/\/jobs\/view\/(?:[^/]*-)?(\d+)/) || [])[1];
    if (id) out.url = `https://www.linkedin.com/jobs/view/${id}/`;
    // tab title is "Role | Company | LinkedIn" - works even when LinkedIn changes its layout
    const parts = document.title.replace(/^\(\d+\)\s*/, "").split(" | ").map(clean);
    if (parts.length >= 3 && /linkedin/i.test(parts[parts.length - 1])) {
      fill("title", parts[0]);
      fill("company", parts[1]);
    }
    fill("location", locationLine(out.company));
    fill("jd", jdByHeading());
    fill("title", text([".job-details-jobs-unified-top-card__job-title h1", ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title", ".top-card-layout__title", "h1.t-24", "h1"]));
    fill("company", text([".job-details-jobs-unified-top-card__company-name a", ".job-details-jobs-unified-top-card__company-name",
      ".jobs-unified-top-card__company-name", ".topcard__org-name-link", ".topcard__flavor"]));
    fill("location", text([".job-details-jobs-unified-top-card__primary-description-container .tvm__text",
      ".job-details-jobs-unified-top-card__bullet", ".topcard__flavor--bullet"]));
    fill("jd", text(["#job-details", ".jobs-description__content", ".jobs-description-content__text", ".show-more-less-html__markup", ".description__text"]));
  } else {
    const site = SITES.find((s) => s.m.test(host));
    if (site) {
      const t = text(site.title);
      fill("title", SEARCHY.test(t) ? "" : t);
      fill("company", text(site.company));
      fill("location", text(site.loc));
      fill("jd", text(site.jd));
    }
  }

  // 3. any website
  if (SEARCHY.test(out.title)) out.title = "";              // a search heading, not the job
  fill("title", titleBeforeJd());
  const h1 = text("h1"), ogTitle = meta("og:title"), tabTitle = clean(document.title.split(/\s+[|\-–—]\s+/)[0]);
  for (const t of [h1, ogTitle, biggestText(), tabTitle]) fill("title", SEARCHY.test(t) || t.length > 120 ? "" : t);
  out.title = out.title.split("\n")[0].replace(/^job application for\s+/i, "").replace(/\s+at\s+[^,]+$/i, (m) => (out.company ? "" : m));

  if (out.jd.length < 300) {                                // too short: look harder
    const better = [jdByHeading(), jdByWords()].sort((a, b) => b.length - a.length)[0];
    if (better.length > out.jd.length) out.jd = better;
  }

  fill("company", companyNear(out.title));
  fill("company", companyFromTabTitle(out.title));
  fill("company", companyFromSiteName());
  fill("company", companyFromUrl());
  out.company = out.company.split("\n")[0].replace(/^at\s+/i, "").replace(/\s+logo$/i, "").replace(/\s+\d\.\d\s*★?$|\s*★$/, "").trim();  // "at Acme", "Acme 4.1★"

  fill("location", locationLine(out.company));
  fill("location", locationFromLines(detailLines(out.title)));
  out.location = out.location.split("\n")[0].replace(/^(job\s+)?location\s*:?\s*/i, "");

  // 4. on a search page the address bar is the SEARCH, not the job: find the job's own link
  const SEARCH_URL = /(search|srch|\/jobs\/?$|[?&](q|keywords|search|query|k)=|\/q-)/i;
  if (!JOB_LINK.test(out.url) && BOARD_HOSTS.test(host) && SEARCH_URL.test(path + location.search)) {
    const own = ownJobLink(out.title);
    if (own) out.url = own;
    else {
      out.url = "";
      out.problem = "Couldn't find this job's own link. Click the job title to open it in its own tab, then click J again.";
    }
  }
  restore();
  return out;
})();