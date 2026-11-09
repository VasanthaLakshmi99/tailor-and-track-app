"""Step 2: tailoring helpers.

- build_prompt(): one prompt with the rules + JD + the candidate's resume, to paste
  into ChatGPT or Claude. The rules keep the resume truthful: JD skills the
  candidate doesn't have are listed for you to confirm, never added silently.
- save_tailored(): stores the uploaded resume as Company_Role.pdf, checks its new
  match % and remembers it for the job (used later in Apply & Track and the report).
"""
VERSION = "2026-11-03a"   # all Tailor&Track files must have the same version
import json
import re

import autotailor
import db
import matching

READY = 90  # match % at which a tailored resume counts as ready


def safe_name(text, limit=60):
    t = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip()).strip("_")
    return t[:limit] or "Job"


def file_name(job, ext=".pdf"):
    return f"{safe_name(job['company'], 40)}_{safe_name(job['title'], 60)}{ext}"


def build_prompt(job, resume_text):
    missing = json.loads(job.get("missing") or "[]")
    missing_line = ", ".join(missing) if missing else "none found"
    return f"""You are an expert resume writer. Tailor my resume for the job below so it passes ATS screening and reads well to a recruiter.

RULES
1. Use ONLY facts from my resume. Do not invent skills, tools, employers, job titles, dates, numbers or certifications.
2. Summary: rewrite it in 3-4 lines for this role, using the job's own words wherever they are true for me.
3. Skills: put the skills from my resume that this job asks for first, spelled exactly as the job spells them.
4. Experience: keep every employer, title and date. Reorder and reword the bullets so the most relevant come first. Start each bullet with an action verb and keep the numbers from my resume.
5. ATS format: one column, no tables, no images, no text boxes. Headings: Summary, Skills, Experience, Education, Certifications.
6. Maximum 2 pages.
7. After the resume, write a separate list called "SKILLS TO CONFIRM" with job skills that are NOT in my resume ({missing_line}). Do NOT put these in the resume. I will add one only if I really have it.

JOB: {job['title']} at {job['company']}

JOB DESCRIPTION:
{(job.get('jd') or '').strip()}

MY RESUME:
{(resume_text or '').strip()}
"""


def ai_prompt(job, resume_text, confirmed=()):
    """Prompt for Claude / ChatGPT: a real rewrite for this job (not just keywords), returned as plain text in the
    master resume's own layout, so Tailor&Track can turn the answer into the PDF."""
    kws = matching.jd_keywords(job.get("jd") or "", resume_text, job.get("company") or "")
    have = [d for d, k, w, kind in kws if kind == "hard" and (matching.has_keyword(resume_text, d, k)
                                                              or d.lower() in {c.lower() for c in confirmed})]
    missing = [d for d, k, w, kind in kws if kind == "hard" and d not in have]
    extra = f"\nSkills I confirm I have (not written in my resume yet): {', '.join(confirmed)}" if confirmed else ""
    return f"""You are a senior resume writer and ATS expert. Rewrite my resume for the job below, the way a top recruiter
would: change the wording and focus of the content, not just add keywords. Target: 90%+ ATS match, every line true.

FACTS (never break these)
- Use ONLY facts from my resume{' and the confirmed skills' if confirmed else ''}. Never invent employers, job titles, dates,
  degrees, certifications, tools, numbers or results. Keep every employer, job title and date exactly as in my resume.
- Keep every number and % that is in my resume; add no new ones.

REWRITE
1. Summary (3-4 lines): open with the job's title "{job.get('title', '')}" (or the closest title my experience supports),
   then my years of experience and the 5-6 strengths this job needs most, in the job's own words.
2. Work experience: rewrite EVERY bullet so it shows my real work in the language of this job's responsibilities.
   Most relevant bullets first, 4-7 per recent role, 2-4 per older role. Start with a strong action verb, show the
   result, and use the JD's exact keyword spelling (e.g. "Kubernetes (K8s)").
3. Use each of these JD keywords that I have at least twice across Summary, Skills and Experience:
   {', '.join(have) or '(none found)'}
4. Skills: same categories as my resume, JD keywords first, spelled exactly as in the JD.
5. Keep my sections, their order and their headings, and my name, headline and contact line, exactly as they are.

OUTPUT FORMAT (Tailor&Track turns it into the PDF, so follow it exactly)
- Plain text only: no markdown, no **, no #, no tables, no notes before or after the resume.
- Line 1: my name. Line 2: my headline line from my resume. Line 3: my contact line.
- Each section heading on its own line in CAPITALS (e.g. SUMMARY, WORK EXPERIENCE, SKILLS, EDUCATION).
- Each job: one line "Company — Job title | Mon YYYY – Mon YYYY" (dates exactly as in my resume), then bullets starting with "• ".
- Skills: one line per category, "Category: skill, skill, skill".
- Education / certifications: one line each, with the date at the end of the line.
- LENGTH: at least 1.5 pages and at most 2 pages. Summary 4-5 lines; 6-8 bullets for my most recent role, 5-7 for
  the one before, 3-5 for older roles; each bullet 1.5-2 lines (what I did, how, and the result). Make it longer by
  explaining the real work in my resume in more detail, never by inventing.
- After the resume, a line "SKILLS TO CONFIRM:" listing JD skills I don't show ({', '.join(missing[:15]) or 'none'}).
  Do NOT put those in the resume.

JOB: {job.get('title', '')} at {job.get('company', '')}

JOB DESCRIPTION:
{(job.get('jd') or '').strip()}

MY RESUME:
{(resume_text or '').strip()}{extra}
"""


def improve_prompt(job, rep, confirmed=()):
    """Second pass for Claude / ChatGPT when the tailored resume scores under 95 on the ATS check."""
    have = {c.lower() for c in confirmed}
    add = [k for k in rep.get("missing", []) if k.lower() in have]
    lines = []
    if add:
        lines.append(f"- Add these JD keywords (I confirm I have them) to Skills AND to a relevant bullet: {', '.join(add)}")
    if rep.get("too_few"):
        lines.append(f"- Use these keywords at least twice (Summary or Skills + a bullet): {', '.join(rep['too_few'])}")
    if rep.get("title", 100) < 100:
        lines.append(f"- Start the Summary with the job title \"{job.get('title', '')}\" (or the closest true title).")
    if rep.get("soft_missing"):
        lines.append(f"- Show these soft skills through real examples in bullets: {', '.join(rep['soft_missing'][:6])}")
    if rep.get("experience", 100) < 100:
        lines.append("- Make my total years of experience explicit in the Summary.")
    for tip in rep.get("tips", [])[:3]:
        lines.append(f"- {tip}")
    other = [k for k in rep.get("missing", []) if k.lower() not in have]
    return ("Improve the resume you just wrote so it scores 95+ on an ATS for the same job. Same rules as before: "
            "only true facts, same employers, titles, dates and numbers, same plain-text format, 1.5-2 pages, "
            "and return the whole resume again.\n\nChanges:\n" + ("\n".join(lines) or "- Use the JD's exact wording more.") +
            (f"\n\nDo NOT add these (I don't have them): {', '.join(other)}" if other else ""))


def _clean_ai(text):
    """Remove markdown and notes the AI may add, and cut 'SKILLS TO CONFIRM'."""
    text = re.split(r"\n\s*\**\s*SKILLS TO CONFIRM", text or "", flags=re.I)[0]
    lines = []
    for ln in text.replace("\r", "").splitlines():
        s = ln.strip()
        if s.startswith("```"):
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)                     # "## SUMMARY" -> "SUMMARY"
        s = s.replace("**", "").replace("__", "")
        s = re.sub(r"^[-*]\s+", "• ", s)                     # markdown bullets
        lines.append(s)
    while lines and not lines[0]:
        lines.pop(0)
    return "\n".join(lines).strip()


def _start_at_name(text, master_text):
    """Drop any chatter before the resume ('Here is your tailored resume:')."""
    m = autotailor.parse(master_text)
    lines = text.splitlines()
    marks = [x.strip().lower() for x in (m["name"], m["contact"]) if x and x.strip()]
    for i, ln in enumerate(lines[:12]):
        s = ln.strip().lower()
        if s and any(s == mk or (len(mk) > 8 and mk[:25] in s) for mk in marks):
            if marks and m["contact"] and s == m["contact"].strip().lower() and i > 0 and lines[i - 1].strip():
                i -= 1                                       # the name line just above the contact line
            return "\n".join(lines[i:])
    while lines and (lines[0].strip().endswith(":") or not lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines)


def check_ai(answer_text, master_text):
    """Facts check of an AI-written resume against the master: new employers, dates or numbers, lost jobs."""
    a, m = autotailor.parse(answer_text), autotailor.parse(master_text)
    words = lambda s: set(re.findall(r"[a-z]{3,}", (s or "").lower()))
    issues = []
    master_dates = {re.sub(r"\s+", " ", jb["dates"]).lower() for jb in m["experience"] if jb["dates"]}
    for jb in a["experience"]:
        d = re.sub(r"\s+", " ", jb["dates"]).lower()
        if d and master_dates and d not in master_dates:
            issues.append(f"Dates not in the master: {jb['header']} {jb['dates']}")
        if jb["header"] and m["experience"] and not any(words(jb["header"]) & words(mj["header"]) for mj in m["experience"]):
            issues.append(f"Employer / title not in the master: {jb['header']}")
    if m["experience"] and len(a["experience"]) < len([j for j in m["experience"] if j["header"] or j["dates"]]):
        issues.append(f"{len(m['experience']) - len(a['experience'])} job(s) of the master are missing")
    nums = lambda s: set(re.findall(r"\$?\d[\d,.]*\s?(?:%|\+|k|m|bn|x)?", (s or "").lower()))
    new_nums = sorted(n for n in nums(answer_text) - nums(master_text) if len(re.sub(r"\D", "", n)) >= 1
                      and not re.fullmatch(r"(19|20)\d\d", n.strip()))
    if new_nums:
        issues.append("Numbers not in the master: " + ", ".join(new_nums[:10]))
    if not a["experience"]:
        issues.append("No work experience found: check the answer follows the format")
    return a, issues


def save_ai_answer(job, answer_text, master_text):
    """Turn the pasted Claude / ChatGPT answer into the tailored PDF (master layout). Returns (path, pct, missing, issues)."""
    text = _start_at_name(_clean_ai(answer_text), master_text)
    if len(text) < 300:
        raise ValueError("The answer looks too short: paste the whole resume the AI wrote")
    r, issues = check_ai(text, master_text)
    m = autotailor.parse(master_text)
    r["name"] = r["name"] or m["name"]
    r["contact"] = r["contact"] or m["contact"]
    r["headline"] = r["headline"] or m["headline"]
    r["titles"] = {**r.get("titles", {}), **m.get("titles", {})}          # the master's own heading words
    if set(r.get("order") or []) <= set(m.get("order") or []):
        r["order"] = [k for k in m["order"] if k in set(r["order"])]        # and the master's section order
    data = autotailor.to_pdf(r)
    if autotailor.to_pdf.pages < autotailor.MIN_PAGES:
        issues.append(f"Only {autotailor.to_pdf.pages} pages: ask the AI \"Make it longer: at least 1.5 pages, more "
                      f"detail on my real work, same facts\" and paste the new answer")
    path, pct, missing = save_tailored(job, file_name(job), data)
    return path, pct, missing, issues


def save_tailored(job, filename, data):
    """Save the tailored resume for this job. Returns (path, new_match, missing)."""
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Please upload the tailored resume as a PDF file")
    ext = ".pdf"
    profile = db.profile(job["profile_id"])
    folder = db.resume_dir() / safe_name(profile["name"] if profile else "profile", 40)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / file_name(job, ext)
    path.write_bytes(data)
    text = db.extract_text(filename, data)
    pct, _, missing = matching.score(job.get("jd") or "", text, job.get("title") or "", db.roles_for_search(profile) if profile else ())
    rep = matching.ats_report(job.get("jd") or "", text, job.get("title") or "", job.get("company") or "")
    with db.connect() as con:
        con.execute("UPDATE jobs SET resume_file=?, tailored_match=?, tailor_status='done', tailor_note=NULL, "
                    "ats_after=?, ats_json=? WHERE id=?", (str(path), pct, rep["score"], json.dumps(rep), job["id"]))
    return path, pct, missing


def auto_tailor(job, ticked=(), remember=True):
    """Build the tailored PDF automatically (see autotailor.py). ticked = JD skills the user confirmed
    the candidate has used. remember=True keeps them for every next job of this candidate.
    Returns (path, new_match, still_missing)."""
    import autotailor
    profile = db.profile(job["profile_id"])
    if ticked and remember:
        db.add_confirmed_skills(job["profile_id"], list(ticked))
    confirmed = db.confirmed_list(db.profile(job["profile_id"])) + [t for t in ticked or [] if t]
    resume = (profile or {}).get("text") or ""
    if not resume.strip():
        raise ValueError("Upload the master resume first")
    if not (job.get("jd") or "").strip():
        raise ValueError("This job has no JD yet. Open it and click the J button first")
    data = autotailor.to_pdf(autotailor.tailor(job, resume, confirmed, roles=db.roles_for_search(profile)))
    return save_tailored(job, "auto.pdf", data)


def guess_job(filename, jobs):
    """Which job a tailored PDF belongs to, from its file name ('Orbit_Health_Senior_DevOps_Engineer.pdf')."""
    import difflib
    stem = re.sub(r"\.pdf$", "", filename or "", flags=re.I)
    stem = re.sub(r"\(\d+\)$", "", stem).strip()                  # "Name (1).pdf" from a second download
    low = re.sub(r"[^a-z0-9]+", " ", stem.lower()).strip()
    best, best_score = None, 0.0
    for j in jobs:
        target = re.sub(r"[^a-z0-9]+", " ", file_name(j, "").lower()).strip()
        company = re.sub(r"[^a-z0-9]+", " ", (j.get("company") or "").lower()).strip()
        score = difflib.SequenceMatcher(None, low, target).ratio()
        if company and company in low:
            score += 0.3
        if score > best_score:
            best, best_score = j, score
    return best if best_score >= 0.55 else None


def resumes_zip(jobs):
    """ZIP with the tailored PDF of each job. Returns (bytes, how_many)."""
    import io
    import zipfile
    from pathlib import Path
    buf, n, seen = io.BytesIO(), 0, set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for j in jobs:
            p = Path(j.get("resume_file") or "")
            if j.get("resume_file") and p.exists() and p.name not in seen:
                z.write(p, p.name)
                seen.add(p.name)
                n += 1
    return buf.getvalue(), n