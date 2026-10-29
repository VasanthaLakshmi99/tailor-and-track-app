"""Step 2: tailoring helpers.

- build_prompt(): one prompt with the rules + JD + the candidate's resume, to paste
  into ChatGPT or Claude. The rules keep the resume truthful: JD skills the
  candidate doesn't have are listed for you to confirm, never added silently.
- save_tailored(): stores the uploaded resume as Company_Role.pdf, checks its new
  match % and remembers it for the job (used later in Apply & Track and the report).
"""
VERSION = "2026-10-30a"   # all Tailor&Track files must have the same version
import json
import re

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
    pct, _, missing = matching.score(job.get("jd") or "", text)
    with db.connect() as con:
        con.execute("UPDATE jobs SET resume_file=?, tailored_match=?, tailor_status='done', tailor_note=NULL WHERE id=?",
                    (str(path), pct, job["id"]))
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
    data = autotailor.to_pdf(autotailor.tailor(job, resume, confirmed))
    return save_tailored(job, "auto.pdf", data)