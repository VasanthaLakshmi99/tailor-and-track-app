"""Automatic resume tailoring (free, offline, no AI).

For one job it builds a new resume PDF from the master resume:
  - a headline with the job's title
  - the summary's first sentence rewritten with the JD's top skills the candidate has
  - "Core skills for this role": every JD keyword the candidate has, spelled the way the JD spells it
  - work-experience bullets reordered so the ones using the JD's skills come first
  - JD skills the candidate confirmed (ticked) are added to Skills and to the work experience
    of the job where they were used
  - education, certifications and everything else kept as they are
It never adds a skill that is not in the resume or ticked by you.
"""
VERSION = "2026-11-02a"   # all Tailor&Track files must have the same version
import re
from pathlib import Path

import matching

MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATES = re.compile(rf"({MONTH}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})\s*[–—-]+\s*({MONTH}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}}|present|current|now|till date)",
                   re.I)
BULLET = re.compile("^\\s*[•●▪◦‣\\-\\*\x7f\uf0b7\uf0a7\uf076\uf0d8\uf0fc\uf0a8➢►✓❖■□➤→]\\s*")
BULLET_ONLY = re.compile("^\\s*[•●▪◦‣\\-\\*\x7f\uf0b7\uf0a7\uf076\uf0d8\uf0fc\uf0a8➢►✓❖■□➤→o]\\s*$")
HEADINGS = {
    "summary": ["summary", "professional summary", "profile", "career summary", "objective", "about me",
                "professional profile", "executive summary", "career objective", "personal statement"],
    "experience": ["work experience", "experience", "professional experience", "employment history",
                   "work history", "relevant experience", "career history", "employment"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "core competencies", "skills & tools",
               "areas of expertise", "key competencies", "competencies", "technical expertise", "skills and tools"],
    "education": ["education", "academic background", "education & certifications", "education and certifications",
                  "education & training", "qualifications", "academic qualifications"],
    "certifications": ["certifications", "certification", "licenses & certifications", "certificates",
                       "certifications & awards", "awards & certifications"],
    "projects": ["projects", "key projects"],
}
_HEAD = {name.lower(): key for key, names in HEADINGS.items() for name in names}
_HEAD_WORDS = [("education", "education"), ("qualification", "education"), ("certif", "certifications"),
               ("experience", "experience"), ("employment", "experience"), ("skill", "skills"),
               ("competenc", "skills"), ("expertise", "skills"), ("summary", "summary"), ("profile", "summary"),
               ("objective", "summary"), ("project", "projects")]


def _heading(line, allow_extra=True):
    """Section key for a heading line, 'extra:<words>' for other headings (Awards, Languages ...), or None."""
    s = re.sub(r"[:\s]+$", "", line.strip())
    low = s.lower()
    if low in _HEAD:
        return _HEAD[low]
    letters = re.sub(r"[^A-Za-z]", "", s)
    if 3 <= len(s) <= 40 and letters and letters.isupper() and not DATES.search(s) and "@" not in s \
            and len(s.split()) <= 5 and not re.search(r"\d", s):
        for word, key in _HEAD_WORDS:                       # "EDUCATION & CERTIFICATIONS", "KEY SKILLS"
            if word in low:
                return key
        return "extra:" + s if allow_extra else None        # "AWARDS", "LANGUAGES", "VOLUNTEERING"
    return None


def _date_only(s):
    m = DATES.search(s)
    return bool(m) and len(re.sub(r"[\s|,–—-]", "", s[:m.start()] + s[m.end():])) <= 2


# ---------------------------------------------------------------- read the master resume
def parse(text):
    """Master resume text -> dict(name, headline, contact, summary, experience[], skills[], other{})."""
    raw = [ln.rstrip() for ln in (text or "").splitlines()]
    lines = []
    for ln in raw:                                          # a bullet sign alone on its line belongs to the next line
        if BULLET_ONLY.match(ln):
            lines.append("\x00")
        elif lines and lines[-1] == "\x00":
            lines[-1] = "• " + ln.strip()
        else:
            lines.append(ln)
    lines = [ln for ln in lines if ln != "\x00"]

    # name, headline and contact: everything before the first section heading
    first_head = next((i for i, ln in enumerate(lines) if _heading(ln, allow_extra=False)), len(lines))
    top = [ln.strip() for ln in lines[:first_head] if ln.strip()]
    contact_i = next((i for i, ln in enumerate(top) if "@" in ln or re.search(r"\+?\d[\d\s().-]{8,}\d", ln)), None)
    contact = top[contact_i] if contact_i is not None else ""
    rest_top = [ln for i, ln in enumerate(top) if i != contact_i]
    name = rest_top[0] if rest_top and len(rest_top[0]) < 60 and not re.search(r"\d", rest_top[0]) else ""
    headline = " ".join(ln for ln in rest_top if ln != name)

    sections, cur, order, titles = {}, None, [], {}
    for ln in lines[first_head:]:
        key = _heading(ln)
        if key:
            cur = key
            sections.setdefault(cur, [])
            if key not in order:
                order.append(key)
                titles[key] = re.sub(r"[:\s]+$", "", ln.strip())     # the master's own heading words
            continue
        if cur:
            sections[cur].append(ln)

    summary = " ".join(x.strip() for x in sections.get("summary", []) if x.strip())

    # experience: header line(s) + dates, an optional intro paragraph, bullets
    jobs, job = [], None
    exp = [ln.strip() for ln in sections.get("experience", []) if ln.strip()]
    for i, s in enumerate(exp):
        nxt = exp[i + 1] if i + 1 < len(exp) else ""
        if _date_only(s):
            if job is not None and not job["dates"] and not job["bullets"] and not job["intro"]:
                job["dates"] = DATES.search(s).group(0).strip()
            else:
                job = {"header": "", "dates": DATES.search(s).group(0).strip(), "intro": "", "bullets": []}
                jobs.append(job)
        elif DATES.search(s) and not BULLET.match(s):
            m = DATES.search(s)
            job = {"header": s[:m.start()].strip(" ,|–-"), "dates": m.group(0).strip(), "intro": "", "bullets": []}
            jobs.append(job)
        elif BULLET.match(s):
            if job is None:
                job = {"header": "", "dates": "", "intro": "", "bullets": []}
                jobs.append(job)
            job["bullets"].append(BULLET.sub("", s))
        elif _date_only(nxt) or job is None:                    # a job header whose dates are on the next line
            job = {"header": s, "dates": "", "intro": "", "bullets": []}
            jobs.append(job)
        elif job["bullets"]:
            job["bullets"][-1] += " " + s                       # wrapped line of the same bullet
        elif job["dates"]:
            job["intro"] = (job["intro"] + " " + s).strip()     # a paragraph under the job title
        else:
            job["header"] = (job["header"] + " " + s).strip()   # second header line (e.g. location)

    # skills: "Category: a, b, c" lines (wrapped lines joined)
    skills = []
    for ln in sections.get("skills", []):
        s = BULLET.sub("", ln.strip())
        if not s:
            continue
        if ":" in s[:60]:
            cat, _, items = s.partition(":")
            skills.append([cat.strip(), items.strip()])
        elif skills:
            skills[-1][1] = (skills[-1][1] + " " + s).strip()
        else:
            skills.append(["", s])

    other = {k: _dated_lines(v) for k, v in sections.items()
             if k in ("education", "certifications", "projects") or k.startswith("extra:")}
    return {"name": name, "headline": headline, "contact": contact, "summary": summary, "experience": jobs,
            "skills": skills, "other": other, "order": order, "titles": titles}


def _dated_lines(lines):
    """['School: Degree', 'Aug 2023 – May 2025'] -> [('School: Degree', 'Aug 2023 – May 2025')].
    A date on its own line (or at the end of a line) goes on the right of its line, like the job dates."""
    out = []
    for ln in (BULLET.sub("", x.strip()) for x in lines):
        if not ln:
            continue
        m = DATES.search(ln) or re.search(rf"({MONTH}\s+\d{{4}}|\b(19|20)\d{{2}})\s*$", ln, re.I)
        text = (ln[:m.start()] + ln[m.end():]).strip(" ,|–-") if m else ln
        date = m.group(0).strip() if m else ""
        if date and not text and out and not out[-1][1]:
            out[-1] = (out[-1][0], date)                        # date-only line: join it to the line above
        else:
            out.append((text, date))
    return out


# ---------------------------------------------------------------- JD keywords
GENERIC = {"services", "service", "systems", "system", "tools", "platform", "platforms", "applications", "cloud",
           "software", "engineering", "development", "technology", "data", "support", "operations",
           "devops", "site reliability", "site reliability engineering", "sre", "platform engineering",
           "cloud engineering", "devsecops"}   # job roles, not skills
def jd_terms(jd, resume_text):
    """JD skills in order of importance -> [(skill, how the JD spells it)]."""
    extra = matching.learn_skills(resume_text)
    found = matching.find_skills(jd, strict=True, extra=extra)
    low = jd or ""
    out = []
    def first_pos(skill):
        pos = [m.start() for a in [skill] + matching.SKILLS.get(skill, []) for m in [matching._pattern(a).search(low.lower())] if m]
        return min(pos) if pos else 10 ** 6

    for skill, n in sorted(found.items(), key=lambda kv: (-min(kv[1], 3), first_pos(kv[0]))):
        if skill.lower() in GENERIC:
            continue
        spelled = skill
        alts = [skill] + matching.SKILLS.get(skill, [])
        for a in alts:
            if a.lower() in matching.AMBIGUOUS:
                continue
            m = matching._pattern(a).search(low.lower())
            if m:
                spelled = low[m.start():m.end()]
                break
        if spelled.islower() and len(spelled) <= 4:
            spelled = spelled.upper()                         # "aws" -> "AWS"
        out.append((skill, spelled))
    return out


def gaps(job, resume_text):
    """JD keywords (hard skills first, then soft skills) the resume doesn't show: what the user may tick."""
    return [disp for disp, key, w, kind in matching.jd_keywords(job.get("jd") or "", resume_text, job.get("company") or "")
            if not matching.has_keyword(resume_text, disp, key)]


# ---------------------------------------------------------------- tailor
USE_LINES = {   # how a ticked skill is shown in the work experience
    "monitoring": (r"prometheus|grafana|datadog|splunk|new relic|elk|elastic|kibana|dynatrace|nagios|zabbix|appdynamics|opentelemetry",
                   "Used {skills} for monitoring, dashboards and alerting on production services."),
    "cicd": (r"gitlab|argo|github actions|circleci|bamboo|spinnaker|tekton|teamcity|azure devops|octopus|harness|flux",
             "Used {skills} to build and run CI/CD and deployment pipelines."),
    "config": (r"ansible|chef|puppet|salt",
               "Used {skills} for configuration management and server automation."),
    "containers": (r"helm|openshift|istio|rancher|ecs|fargate|aks|gke|podman|kustomize",
                   "Used {skills} to package, deploy and run applications on containers and Kubernetes."),
    "cloud": (r"azure|gcp|google cloud|oracle cloud|oci",
              "Worked with {skills} for cloud infrastructure and deployments."),
    "observability": (r"monitoring|observability|logging|alerting|cloudwatch|tracing",
                      "Drove {skills} for production services, building dashboards and alerts that catch issues early."),
    "iac": (r"terraform|cloudformation|pulumi|infrastructure as code|bicep|crossplane",
            "Managed cloud resources with {skills}, keeping every change version-controlled and reproducible."),
    "testing": (r"test|selenium|jmeter|cypress|pytest|junit|qa\b|quality",
                "Applied {skills} in release validation to catch defects before production."),
    "network_os": (r"network|dns|tcp|firewall|vpn|load balanc|unix|linux|windows server|bash|shell",
                   "Worked with {skills} while operating and troubleshooting servers and services."),
    "languages": (r"python|java\b|golang|\bgo\b|javascript|typescript|ruby|groovy|powershell|scala|c#|\.net|sql",
                  "Wrote {skills} code and scripts to automate builds, deployments and routine operations."),
    "process": (r"incident|change management|release management|root cause|on-call|on call|postmortem|runbook|"
                r"agile|scrum|sdlc|itil|servicenow|jira|sla|slo|compliance|security",
                "Followed {skills} practices with development, QA and operations teams."),
    "cloud_svc": (r"aws|amazon|ec2|s3|lambda|eks|ecs|rds|iam|vpc|cloud",
                  "Used {skills} to build and run cloud infrastructure."),
    "containers2": (r"kubernetes|k8s|docker|container|microservice",
                    "Ran {skills} workloads in production, from build to rollout."),
    "cicd2": (r"jenkins|ci/cd|ci cd|continuous|pipeline|codepipeline|maven|gradle|git\b|github|bitbucket",
              "Built and maintained {skills} workflows for frequent, reliable releases."),
    "other": (r"$^", "Worked hands-on with {skills} in day-to-day {title} work."),
}


CATEGORY_HINTS = [  # (skill words, words in the master's category name)
    (r"aws|amazon|azure|gcp|google cloud|ec2|s3|lambda|eks|ecs|rds|iam|vpc|cloudfront|route ?53|oracle cloud", r"cloud|aws|azure|gcp"),
    (r"kubernetes|k8s|docker|helm|openshift|istio|container|eks|aks|gke|rancher|podman|kustomize|microservice", r"container|orchestr|kubernetes"),
    (r"terraform|cloudformation|pulumi|ansible|chef|puppet|salt|iac|infrastructure as code|bicep|crossplane", r"infrastructure|iac|config"),
    (r"jenkins|gitlab|github|argo|ci/?cd|circleci|bamboo|spinnaker|tekton|teamcity|maven|gradle|git\b|bitbucket|azure devops|build|release|nexus|artifactory|sonar", r"ci|cd|build|devops|version"),
    (r"python|bash|shell|powershell|go\b|golang|java|javascript|typescript|ruby|perl|sql|yaml|json|groovy|scripting", r"script|program|language|automation"),
    (r"prometheus|grafana|datadog|splunk|new relic|elk|elastic|kibana|cloudwatch|dynatrace|nagios|zabbix|appdynamics|opentelemetry|monitor|logging|alert|observab|incident|sre|slo|sla", r"observ|monitor|logging"),
    (r"security|iam|kms|vault|secrets|sast|dast|snyk|trivy|owasp|devsecops|soc ?2|encryption|zero trust", r"secur"),
    # business / HR / operations
    (r"workforce|capacity|resource|headcount|demand|supply|forecast|roster|rota|schedul|utili[sz]ation|bench|shift",
     r"planning|workforce|resourc|capacity"),
    (r"recruit|sourcing|talent|mobility|onboarding|interview|employer brand|redeploy|staffing|candidate",
     r"talent|recruit|mobility|staffing|acquisition"),
    (r"analytic|reporting|\bmi\b|dashboard|kpi|scorecard|excel|power bi|data", r"analytic|report|data"),
    (r"workday|successfactors|peoplesoft|servicenow|oracle hcm|hris|quintiq|jda|bullhorn|ats\b|office|copilot|sap\b",
     r"system|tool|technolog|software"),
    (r"stakeholder|leadership|coaching|mentor|team|people management|line management|customer|client|service delivery",
     r"leader|stakeholder|management|customer|client"),
    (r"compliance|employment law|working time|union|policy|employee relations|grievance|health and safety|risk|audit",
     r"compliance|employee|policy|hr\b|governance|regulat"),
]
NO_ADD_CATS = re.compile(r"language|award|honou?r|domain|industr|interest|hobb|certif|education|reference", re.I)


def _split_items(text):
    """'a, b (c, d), e' -> ['a', 'b (c, d)', 'e'] (commas inside brackets kept)."""
    items, depth, cur = [], 0, ""
    for ch in text:
        depth += ch in "([" and 1 or (ch in ")]" and -1 or 0)
        if ch == "," and depth == 0:
            items.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(cur.strip())
    return items


def _skills_for_jd(cats, jd_spellings):
    cats = [[c, _split_items(items)] for c, items in cats]
    if not cats:
        return [["", ", ".join(jd_spellings)]] if jd_spellings else []
    all_low = " ".join(" ".join(i) for _, i in cats).lower()
    for sp in jd_spellings:
        if matching._pattern(sp).search(all_low):
            continue                                          # already written this way somewhere
        target = None
        for skill_pat, cat_pat in CATEGORY_HINTS:
            if re.search(skill_pat, sp, re.I):
                target = next((c for c in cats if re.search(cat_pat, c[0], re.I)), None)
                if target:
                    break
        if not target:                                        # never into Languages / Awards / Domain
            target = next((c for c in cats if re.search(r"skill|competenc|expertise|other|core|technical", c[0], re.I)
                           and not NO_ADD_CATS.search(c[0])), None)
        if not target:
            target = next((c for c in cats if c[0] == "Additional Skills"), None)
            if not target:
                target = ["Additional Skills", []]
                at = next((i for i, c in enumerate(cats) if NO_ADD_CATS.search(c[0])), len(cats))
                cats.insert(at, target)
        target[1].append(nice(sp))
        all_low += " " + sp.lower()
    pats = [matching._pattern(sp) for sp in jd_spellings]
    for c in cats:                                            # JD keywords first inside each category
        c[1].sort(key=lambda item: 0 if any(p.search(item.lower()) for p in pats) else 1)
    return [[c, ", ".join(items)] for c, items in cats]


def r_added(have, in_resume):
    return [sp for s, sp in have if s not in in_resume]


PRODUCTS = {"workday", "successfactors", "peoplesoft", "oracle hcm", "bamboohr", "cornerstone", "cipd", "prince2",
            "microsoft office", "hris", "working time regulations"}


def nice(d):
    """'Rostering' -> 'rostering' inside a sentence (tool names and acronyms keep their capitals)."""
    if d and d[0].isupper() and d[1:2].islower() and d.lower() not in PRODUCTS and \
            d.lower() in {k.lower() for k in matching.BUSINESS_SKILLS} | {a for v in matching.BUSINESS_SKILLS.values() for a in v}:
        return d[0].lower() + d[1:]
    return d


def _join(items):
    items = list(dict.fromkeys(nice(i) for i in items if i))
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


LEAD_WORDS = re.compile(r"\b(lead|principal|staff|head|director|manager|chief|architect|vp)\b", re.I)
SENIOR_WORDS = re.compile(r"\b(senior|sr\.?)\s+", re.I)


def summary_title(job_title, resume_text):
    """The JD's job title for the summary (ATS tools look for it), without a level the resume can't back up."""
    t = re.sub(r"\s*[\(\[|].*$", "", job_title or "").strip()
    t = re.split(r"\s+[-–—/]\s+|,", t)[0].strip()                    # "Lead Software Engineer - Cloud, AWS" -> first part
    years = matching.years_of_experience(resume_text) or 0
    if years < 8:
        t = LEAD_WORDS.sub("", t)
    if years < 5:
        t = SENIOR_WORDS.sub("", t)
    t = re.sub(r"\b(i{1,3}|iv|[1-4])$", "", re.sub(r"\s+", " ", t)).strip(" -,")
    return t or None


TRAITS = re.compile(r"self[- ]motivated|self[- ]starter|fast[- ]paced|detail[- ]oriented|proactive|target[- ]driven|"
                    r"results[- ]driven|organi[sz]ed|resilient|flexible|adaptable", re.I)


def _role_of(header):
    """'Cognizant — Senior HR Executive, Workforce Planning' -> 'Senior HR Executive'."""
    parts = re.split(r"\s+[—–|-]\s+|,\s*", header or "")
    titles = [p for p in parts if re.search(r"engineer|manager|executive|analyst|developer|lead|specialist|consultant|"
                                           r"officer|partner|director|administrator|architect|coordinator|associate", p, re.I)]
    return (titles[0] if titles else parts[-1] if parts else "").strip()


def tailor(job, resume_text, confirmed=(), roles=()):
    """Return the tailored resume as a dict (same shape as parse()).

    What an ATS checks, and what this does about it:
      - hard skills: every JD keyword the candidate has is in Skills, spelled as in the JD, and in the summary or
        a work bullet
      - job title: the JD's title replaces the title in the summary's first sentence (only if it fits the profile)
      - soft skills: the ones you tick are added to the summary
      - relevance: the bullets that use the JD's keywords come first
    The master's layout, headline, job intros and sections are kept. Only skills in the resume or ticked are used."""
    r = parse(resume_text)
    confirmed = [c for c in confirmed if c]
    full_text = resume_text + "\n" + "\n".join(confirmed)
    kws = matching.jd_keywords(job.get("jd") or "", resume_text, job.get("company") or "")
    ticked = {c.lower() for c in confirmed}
    is_have = lambda d, k: matching.has_keyword(full_text, d, k) or d.lower() in ticked or k in ticked
    hard = [(d, k, w) for d, k, w, kind in kws if kind == "hard" and is_have(d, k)]
    soft = [(d, k, w) for d, k, w, kind in kws if kind == "soft" and is_have(d, k)]
    in_resume = lambda d, k: matching.has_keyword(resume_text, d, k)
    added = [d for d, k, w in hard if not in_resume(d, k)]                    # ticked by the user, not in the resume
    tech = matching.is_tech(resume_text)

    roles = list(roles or []) or matching.roles_from_resume(resume_text)
    fit = matching.title_fit(job.get("title") or "", roles)
    title = summary_title(job.get("title") or "", resume_text) if fit else None

    # 1. summary: the master's summary; the JD title replaces the master's title (only when the job fits the profile);
    #    JD keywords not yet in the summary are named once; ticked soft skills at the end
    summary = r["summary"]
    sentences = re.split(r"(?<=[.!?])\s+", summary, maxsplit=1)
    first = sentences[0]
    m = re.match(r"^(.{3,60}?)\s+(with|having|offering|bringing)\s+", first)
    if title and m and title.lower() not in first.lower():
        first = title + first[m.end(1):]
    summary = (first + (" " + sentences[1] if len(sentences) > 1 else "")).strip()
    if summary and not summary.endswith((".", "!", "?")):
        summary += "."
    top = [d for d, k, w in hard if not matching.has_keyword(summary, d, k)]
    top = [d for d in top if not any(d != o and d.lower() in o.lower() for o in top)][:6]   # "GitHub" in "GitHub Actions"
    if top:
        summary += f" Key skills for this role: {_join(top)}."
    soft_new = [d for d, k, w in soft if not matching.has_keyword(summary + resume_text, d, k)]
    traits = [d for d in soft_new if TRAITS.search(d)]
    skills_soft = [re.sub(r"\s+skills?$", "", d, flags=re.I) for d in soft_new if d not in traits]
    if skills_soft:
        summary += f" Brings strong {_join(skills_soft)} skills."
    if traits:
        summary += f" {_join(traits).capitalize()}."
    r["summary"] = summary

    # 2. bullets: the ones using the JD's keywords first; JD spelling added next to the resume's own word
    pats = {d: [matching._pattern(d), matching._pattern(k)] + [matching._pattern(a) for n, al in matching.SKILLS.items()
                                                             if n.lower() == k for a in [n] + al] for d, k, w in hard}
    weight = {d: w for d, k, w in hard}

    def hits(b):
        low = b.lower()
        return sum(weight[d] for d, ps in pats.items() if any(p.search(low) for p in ps))

    for jb in r["experience"]:
        jb["bullets"] = sorted(jb["bullets"], key=hits, reverse=True)
    all_bullets = lambda: " ".join(jb.get("intro", "") + " " + " ".join(jb["bullets"]) for jb in r["experience"])
    for d, k, w in hard:                                                       # "Kubernetes" -> "Kubernetes (K8s)"
        if matching._pattern(d).search(all_bullets().lower()) or matching._pattern(d).search(resume_text.lower()):
            continue
        done = False
        for jb in r["experience"]:
            for i, b in enumerate(jb["bullets"]):
                for p in pats[d][1:]:
                    mm = p.search(b.lower())
                    if mm and not done:
                        jb["bullets"][i] = b[:mm.end()] + f" ({d})" + b[mm.end():]
                        done = True

    # 3. skills the candidate confirmed (ticked) but the resume doesn't show go into the latest job, once.
    #    Tech resumes: also keywords that are only in Skills, in plain sentences by kind of tool.
    #    Other resumes: one plain line, never technical sentences.
    in_bullets = lambda d: any(p.search(all_bullets().lower()) for p in pats[d])
    if tech:
        need_line = [d for d, k, w in hard if d in added or (not in_bullets(d) and w >= 1)]
    else:
        need_line = [d for d in added if not in_bullets(d)]
    if need_line and r["experience"]:
        new_bullets, left = [], list(dict.fromkeys(need_line))
        role = _role_of(r["experience"][0]["header"]) or (fit or "")
        if tech:
            for kind, (pattern, sentence) in USE_LINES.items():
                group = left if kind == "other" else [x for x in left if re.search(pattern, x, re.I)]
                if group:
                    new_bullets.append(sentence.format(skills=_join(group), title=fit or title or role))
                    left = [x for x in left if x not in group]
        else:
            new_bullets.append(f"Applied {_join(left)} in day-to-day {role or 'role'} responsibilities.")
        r["experience"][0]["bullets"][1:1] = new_bullets      # right under the strongest bullet of the latest job

    # 4. skills: the master's categories, JD keywords first and spelled the JD's way, missing ones added
    r["skills"] = _skills_for_jd(r["skills"], [d for d, k, w in hard])
    r["added"] = added
    return r


# ---------------------------------------------------------------- PDF (one column, real text = ATS-safe)
_FONT_PATHS = [  # Calibri (same as most master resumes), then Arial, then Linux fonts
    ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
    (str(Path(__file__).parent / "fonts" / "Carlito-Regular.ttf"), str(Path(__file__).parent / "fonts" / "Carlito-Bold.ttf")),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf", "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]
_PLAIN = str.maketrans({"–": "-", "—": "-", "•": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "·": "|", "…": "..."})


def to_pdf(r):
    try:
        from fpdf import FPDF
    except ImportError:                                       # install the free PDF package once, automatically
        import subprocess
        import sys
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "fpdf2"], check=False)
        try:
            import importlib
            importlib.invalidate_caches()
            from fpdf import FPDF
        except ImportError:
            raise RuntimeError("Could not install the free PDF package automatically. Stop Tailor&Track (Ctrl+C), run  "
                               "python -m pip install fpdf2  and then  python -m streamlit run app.py")
    pdf = FPDF(format="A4", unit="pt")
    pdf.set_auto_page_break(True, margin=30)
    pdf.set_margins(28, 26, 28)
    font, fix = "Helvetica", (lambda s: (s or "").translate(_PLAIN).encode("latin-1", "replace").decode("latin-1"))
    for regular, bold in _FONT_PATHS:
        if Path(regular).exists() and Path(bold).exists():
            pdf.add_font("Body", "", regular)
            pdf.add_font("Body", "B", bold)
            font, fix = "Body", (lambda s: s or "")
            break
    pdf.add_page()
    w = pdf.w - pdf.l_margin - pdf.r_margin
    LH, SIZE = 12.6, 10.3

    def heading(key, default):
        pdf.ln(1)
        pdf.set_font(font, "B", 10.8)
        pdf.cell(w, 13, fix(r.get("titles", {}).get(key) or default), new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y()
        pdf.set_line_width(0.6)
        pdf.line(pdf.l_margin, y, pdf.l_margin + w, y)
        pdf.ln(2)

    def left_right(left, right, bold_left=True):
        """'Company, Title' (bold) on the left, dates on the right, same line."""
        pdf.set_font(font, "", SIZE)
        right_w = pdf.get_string_width(fix(right)) + 6 if right else 0
        y = pdf.get_y()
        head, sep, tail = left.partition(":") if ": " in left else (left, "", "")
        pdf.set_font(font, "B", SIZE)
        if sep:                                               # "University: Degree" -> bold university only
            text = f"**{fix(head)}**:{fix(tail)}"
            pdf.set_font(font, "", SIZE)
            pdf.multi_cell(w - right_w, LH, text, markdown=True, align="L", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(w - right_w, LH, fix(left), align="L", new_x="LMARGIN", new_y="NEXT")
        end = pdf.get_y()
        if right:
            pdf.set_xy(pdf.l_margin + w - right_w, y)
            pdf.set_font(font, "", SIZE)
            pdf.cell(right_w, LH, fix(right), align="R")
            pdf.set_xy(pdf.l_margin, end)

    # name and contact, centred (like the master)
    if r.get("name"):
        pdf.set_font(font, "B", 13)
        pdf.cell(w, 16, fix(r["name"]), align="C", new_x="LMARGIN", new_y="NEXT")
    if r.get("headline"):                                     # the master's own headline line, unchanged
        pdf.set_font(font, "", 10.8)
        pdf.multi_cell(w, 13, fix(r["headline"]), align="C", new_x="LMARGIN", new_y="NEXT")
    if r.get("contact"):
        pdf.set_font(font, "", 10.8)
        pdf.multi_cell(w, 13, fix(r["contact"]), align="C", new_x="LMARGIN", new_y="NEXT")

    def summary():
        if r["summary"]:
            heading("summary", "Summary")
            pdf.set_font(font, "", SIZE)
            pdf.multi_cell(w, LH, fix(r["summary"]), align="L", new_x="LMARGIN", new_y="NEXT")

    def experience():
        if r["experience"]:
            heading("experience", "Work Experience")
            for jb in r["experience"]:
                left_right(jb["header"], jb["dates"])
                pdf.set_font(font, "", SIZE)
                if jb.get("intro"):
                    pdf.multi_cell(w, LH, fix(jb["intro"]), align="L", new_x="LMARGIN", new_y="NEXT")
                for b in jb["bullets"]:
                    pdf.set_x(pdf.l_margin + 6)
                    pdf.cell(12, LH, fix("•") if font == "Body" else "-")
                    pdf.multi_cell(w - 18, LH, fix(b), align="L", new_x="LMARGIN", new_y="NEXT")

    def skills():
        if r["skills"]:
            heading("skills", "Skills")
            pdf.set_font(font, "", SIZE)
            for cat, items in r["skills"]:
                text = f"**{fix(cat)}:** {fix(items)}" if cat else fix(items)
                pdf.multi_cell(w, LH, text, markdown=True, align="L", new_x="LMARGIN", new_y="NEXT")

    def dated(key, default):
        lines = r["other"].get(key) or []
        if lines:
            heading(key, default)
            for text, date in lines:
                left_right(text, date)

    parts = {"summary": summary, "experience": experience, "skills": skills,
             "education": lambda: dated("education", "Education"),
             "certifications": lambda: dated("certifications", "Certifications"),
             "projects": lambda: dated("projects", "Projects")}
    for k in r.get("order") or []:
        if k.startswith("extra:"):                            # Awards, Languages, Volunteering … as in the master
            parts[k] = (lambda key: lambda: dated(key, key[6:].title()))(k)
    order = [k for k in r.get("order") or [] if k in parts]
    order += [k for k in ("summary", "experience", "skills", "projects", "education", "certifications") if k not in order]
    for k in order:
        parts[k]()
    return bytes(pdf.output())