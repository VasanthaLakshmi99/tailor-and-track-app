"""Tailor&Track database, profiles and duplicate checking.

All data lives in one file: tailortrack.db (SQLite, comes with Python).
Back it up by copying that file.

Every job belongs to a PROFILE (one candidate). Duplicates are checked per
profile, so applying for candidate A never blocks candidate B.
"""
VERSION = "2026-11-03a"   # all Tailor&Track files must have the same version
import difflib
import io
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import matching

BASE = Path(__file__).parent
DB_PATH = BASE / "tailortrack.db"
if not DB_PATH.exists() and (BASE / "jobpilot.db").exists():   # data from the old name (JobPilot) is kept
    (BASE / "jobpilot.db").rename(DB_PATH)
RESUME_DIR = BASE / "resumes"          # default; can be changed in the app (Profiles -> Where resumes are saved)
RESUME_DIR.mkdir(exist_ok=True)

SIMILAR_DAYS = 30        # similar role at same company within this many days -> warning
SIMILAR_RATIO = 0.80     # how alike two titles must be to count as "similar"

JOB_COLUMNS = """
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL,
    company TEXT, title TEXT, location TEXT, source TEXT,
    apply_url TEXT, jd TEXT,
    job_key TEXT,
    company_norm TEXT, title_norm TEXT,
    status TEXT DEFAULT 'new',          -- new / applied / hidden
    warning TEXT,                       -- e.g. similar role applied recently
    match INTEGER, missing TEXT,        -- missing = JSON list of skills
    resume_file TEXT, tailored_match INTEGER,
    saved_at TEXT, applied_at TEXT,
    UNIQUE(profile_id, job_key)
"""


# ---------------------------------------------------------------- setup

class _Connection(sqlite3.Connection):
    """'with connect() as con:' commits (or rolls back) AND closes the connection.
    (Plain sqlite3 only commits, leaving the file open: after a few hundred, macOS refuses to open more.)"""
    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def connect():
    con = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False, factory=_Connection)
    con.row_factory = sqlite3.Row
    return con


def _columns(con, table):
    return [r["name"] for r in con.execute(f"PRAGMA table_info({table})")]


def init_db():
    """Create tables. Also upgrades a database from the single-profile version."""
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL, roles TEXT DEFAULT '',
            filename TEXT, data BLOB, text TEXT, uploaded_at TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS removed (
            id INTEGER PRIMARY KEY,
            company TEXT, title TEXT, source TEXT, apply_url TEXT,
            reason TEXT, found_at TEXT
        );
        """)

        # first profile: from the old master resume if there was one
        if not con.execute("SELECT 1 FROM profiles LIMIT 1").fetchone():
            old = None
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='master_resume'").fetchone():
                old = con.execute("SELECT * FROM master_resume LIMIT 1").fetchone()
            con.execute("INSERT INTO profiles(name,roles,filename,data,text,uploaded_at,created_at) VALUES(?,?,?,?,?,?,?)",
                        ("My profile", "", old["filename"] if old else None, old["data"] if old else None,
                         old["text"] if old else None, old["uploaded_at"] if old else None, now()))
        first = con.execute("SELECT MIN(id) FROM profiles").fetchone()[0]

        # jobs table: create, or upgrade the old one (no profile_id) keeping all rows
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='jobs'").fetchone()
        if not exists:
            con.execute(f"CREATE TABLE jobs ({JOB_COLUMNS})")
        elif "profile_id" not in _columns(con, "jobs"):
            con.execute("ALTER TABLE jobs RENAME TO jobs_old")
            con.execute(f"CREATE TABLE jobs ({JOB_COLUMNS})")
            cols = [c for c in _columns(con, "jobs_old") if c in _columns(con, "jobs")]
            con.execute(f"INSERT INTO jobs(profile_id,{','.join(cols)}) SELECT ?,{','.join(cols)} FROM jobs_old", (first,))
            con.execute("DROP TABLE jobs_old")
        if "profile_id" not in _columns(con, "removed"):
            con.execute("ALTER TABLE removed ADD COLUMN profile_id INTEGER")
            con.execute("UPDATE removed SET profile_id=?", (first,))
        if "posted_at" not in _columns(con, "jobs"):              # when the company posted the job (UTC, ISO)
            con.execute("ALTER TABLE jobs ADD COLUMN posted_at TEXT")
        if con.execute("SELECT value FROM settings WHERE key='norm_version'").fetchone() is None \
                and "company_norm" in _columns(con, "jobs"):
            for r in con.execute("SELECT id, company, title FROM jobs").fetchall():
                con.execute("UPDATE jobs SET company_norm=?, title_norm=? WHERE id=?",
                            (norm_company(r["company"]), norm_title(r["title"]), r["id"]))
            con.execute("INSERT OR REPLACE INTO settings VALUES('norm_version', '2')")
        if con.execute("SELECT value FROM settings WHERE key='extract_version'").fetchone() is None:
            for r in con.execute("SELECT id, filename, data FROM profiles WHERE data IS NOT NULL").fetchall():
                try:                                            # read saved master resumes again, in page order
                    con.execute("UPDATE profiles SET text=? WHERE id=?", (extract_text(r["filename"] or "r.pdf", r["data"]), r["id"]))
                except Exception:
                    pass
            con.execute("INSERT OR REPLACE INTO settings VALUES('extract_version', '2')")
        for col, kind in (("ats_after", "INTEGER"), ("ats_json", "TEXT")):   # ATS check of the tailored resume
            if col not in _columns(con, "jobs"):
                con.execute(f"ALTER TABLE jobs ADD COLUMN {col} {kind}")
        if "origin" not in _columns(con, "jobs"):                 # 'collect' | 'j' | 'import' | 'manual'
            con.execute("ALTER TABLE jobs ADD COLUMN origin TEXT")
        for col in ("tailor_status", "tailor_note"):          # automatic tailoring (step 2)
            if col not in _columns(con, "jobs"):
                con.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")
        if "confirmed_skills" not in _columns(con, "profiles"):
            con.execute("ALTER TABLE profiles ADD COLUMN confirmed_skills TEXT DEFAULT ''")
        if "locations" not in _columns(con, "profiles"):          # where the candidate wants to work
            con.execute("ALTER TABLE profiles ADD COLUMN locations TEXT DEFAULT ''")
        con.execute("""CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY, provider TEXT, token TEXT, name TEXT,
            active INTEGER DEFAULT 1, last_checked TEXT, last_status TEXT,
            UNIQUE(provider, token))""")
        con.execute("CREATE INDEX IF NOT EXISTS ix_jobs_company ON jobs(profile_id, company_norm)")
        if not con.execute("SELECT 1 FROM settings WHERE key='active_profile'").fetchone():
            con.execute("INSERT INTO settings VALUES('active_profile', ?)", (str(first),))


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- profiles

def profiles():
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT id,name,roles,filename,uploaded_at,text,confirmed_skills,locations FROM profiles ORDER BY name COLLATE NOCASE")]


def profile(pid):
    with connect() as con:
        r = con.execute("SELECT id,name,roles,filename,uploaded_at,text,confirmed_skills,locations FROM profiles WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


def active_profile_id():
    with connect() as con:
        r = con.execute("SELECT value FROM settings WHERE key='active_profile'").fetchone()
        pid = int(r["value"]) if r else None
        if pid and con.execute("SELECT 1 FROM profiles WHERE id=?", (pid,)).fetchone():
            return pid
        return con.execute("SELECT MIN(id) FROM profiles").fetchone()[0]


def set_active_profile(pid):
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO settings VALUES('active_profile', ?)", (str(pid),))


def add_profile(name, roles=""):
    with connect() as con:
        cur = con.execute("INSERT INTO profiles(name,roles,created_at) VALUES(?,?,?)", (name.strip(), roles.strip(), now()))
        return cur.lastrowid


def update_profile(pid, name, roles, locations=None):
    with connect() as con:
        con.execute("UPDATE profiles SET name=?, roles=? WHERE id=?", (name.strip(), roles.strip(), pid))
        if locations is not None:
            con.execute("UPDATE profiles SET locations=? WHERE id=?", (locations.strip(), pid))


def delete_profile(pid):
    """Deletes the profile AND all its jobs. Keeps at least one profile."""
    with connect() as con:
        if con.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] <= 1:
            return False
        con.execute("DELETE FROM jobs WHERE profile_id=?", (pid,))
        con.execute("DELETE FROM removed WHERE profile_id=?", (pid,))
        con.execute("DELETE FROM profiles WHERE id=?", (pid,))
    if active_profile_id() == pid:
        set_active_profile(profiles()[0]["id"])
    return True


def role_list(p):
    return [r.strip() for r in re.split(r"[,\n]", (p or {}).get("roles") or "") if r.strip()]


def roles_for_search(p):
    """Target roles, or (if none are set) the job titles found in the uploaded resume."""
    return role_list(p) or matching.roles_from_resume((p or {}).get("text") or "")


# ---------------------------------------------------------------- resumes

def extract_text(filename, data):
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        pages = PdfReader(io.BytesIO(data)).pages
        try:        # layout mode keeps the page order (name and contact on top, dates next to the job)
            text = "\n".join((p.extract_text(extraction_mode="layout") or "") for p in pages)
            text = "\n".join(re.sub(r"(\S) {3,}(?=\S)", r"\1  ", ln).strip() for ln in text.splitlines())
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
        except Exception:
            text = ""
        return text if len(text) > 50 else "\n".join((p.extract_text() or "") for p in pages)
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts += [c.text for c in row.cells]
        return "\n".join(parts)
    raise ValueError("Please upload a PDF or DOCX file")


def save_resume(pid, filename, data):
    text = extract_text(filename, data)
    with connect() as con:
        con.execute("UPDATE profiles SET filename=?, data=?, text=?, uploaded_at=? WHERE id=?",
                    (filename, data, text, now(), pid))
    rescore(pid)
    return text


def resume_text(pid):
    p = profile(pid)
    return (p or {}).get("text") or ""


def confirmed_list(p):
    return [x.strip() for x in re.split(r"[,\n]", (p or {}).get("confirmed_skills") or "") if x.strip()]


def scoring_text(p):
    """Resume text + skills the candidate confirmed in Tailor&Track."""
    text = (p or {}).get("text") or ""
    extra = confirmed_list(p)
    return text + ("\nConfirmed skills: " + ", ".join(extra) if text and extra else "")


def add_confirmed_skills(pid, skills):
    p = profile(pid)
    have = confirmed_list(p)
    for s_ in skills:
        if s_ and s_.lower() not in {h.lower() for h in have}:
            have.append(s_)
    set_confirmed_skills(pid, ", ".join(have))


def set_confirmed_skills(pid, text):
    with connect() as con:
        con.execute("UPDATE profiles SET confirmed_skills=? WHERE id=?", (text.strip(), pid))
    rescore(pid)


def match_for(pid, jd, title=""):
    """Match % + missing skills + which target role the title fits."""
    p = profile(pid)
    text = scoring_text(p)
    pct, _, missing = matching.score(jd or "", text, title, roles_for_search(p))
    return {"match": pct if text else None, "missing": missing,
            "fit": matching.title_fit(title, roles_for_search(p)), "has_roles": bool(roles_for_search(p))}


def rescore(pid):
    p = profile(pid)
    text, roles = scoring_text(p), roles_for_search(p)
    with connect() as con:
        for r in con.execute("SELECT id, jd, title FROM jobs WHERE profile_id=?", (pid,)).fetchall():
            pct, _, missing = matching.score(r["jd"] or "", text, r["title"] or "", roles)
            con.execute("UPDATE jobs SET match=?, missing=? WHERE id=?", (pct, json.dumps(missing), r["id"]))


def rescore_all():
    for p in profiles():
        rescore(p["id"])


# ---------------------------------------------------------------- cleaning

COMPANY_SUFFIXES = {
    "inc", "llc", "ltd", "limited", "pvt", "private", "corp", "corporation",
    "co", "company", "plc", "gmbh", "llp", "the",
}
TITLE_SWAPS = {"sr": "senior", "jr": "junior", "mgr": "manager", "engg": "engineer",
               "eng": "engineer", "dev": "developer"}


def norm_company(name):
    n = re.sub(r"\(.*?\)", " ", (name or "").lower())        # "Apex Systems (Everforth Apex)" -> "apex systems"
    words = re.sub(r"[^a-z0-9 ]+", " ", n).split()
    words = [w for w in words if w not in COMPANY_SUFFIXES]
    return " ".join(words)


def norm_title(title):
    t = re.sub(r"\(.*?\)", " ", (title or "").lower())      # drop "(Remote)" etc.
    t = re.sub(r"\b(job\s*(#|id|no\.?|number)?\s*:?\s*|req\s*#?\s*|r)\d{4,}\b", " ", t)   # "Job# 3055896", "R12345"
    words = re.sub(r"[^a-z0-9+# ]+", " ", t).split()
    return " ".join(TITLE_SWAPS.get(w, w) for w in words)


def detect_source(url):
    host = urlparse(url or "").netloc.lower()
    for key, name in [("linkedin", "LinkedIn"), ("dice", "Dice"), ("ziprecruiter", "ZipRecruiter"),
                      ("indeed", "Indeed"), ("glassdoor", "Glassdoor"), ("naukri", "Naukri"),
                      ("monster", "Monster"), ("foundit", "foundit"), ("simplyhired", "SimplyHired"),
                      ("wellfound", "Wellfound"), ("builtin", "Built In"), ("greenhouse", "Greenhouse"),
                      ("lever", "Lever"), ("ashby", "Ashby"), ("myworkdayjobs", "Workday"),
                      ("smartrecruiters", "SmartRecruiters"), ("workable", "Workable"), ("icims", "iCIMS"),
                      ("taleo", "Taleo"), ("jobvite", "Jobvite"), ("bamboohr", "BambooHR")]:
        if key in host:
            return name
    return "Company site" if host else "Manual"


def job_key(url, company):
    """One fingerprint per job, even if the link has different tracking text."""
    u = urlparse((url or "").strip())
    host, path, qs = u.netloc.lower(), u.path, parse_qs(u.query)
    if "linkedin" in host:
        m = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", path)
        jid = m.group(1) if m else (qs.get("currentJobId") or [None])[0]
        if jid:
            return f"linkedin:{jid}"
    if "indeed" in host and (qs.get("jk") or qs.get("vjk")):
        return f"indeed:{(qs.get('jk') or qs.get('vjk'))[0]}"
    if qs.get("gh_jid"):                       # Greenhouse job shown on a company's own site
        return f"greenhouse:{qs['gh_jid'][0]}"
    if "glassdoor" in host and qs.get("jl"):
        return f"glassdoor:{qs['jl'][0]}"
    if "ziprecruiter" in host and (qs.get("lk") or qs.get("jid")):
        return f"ziprecruiter:{(qs.get('lk') or qs.get('jid'))[0]}"
    if "ziprecruiter" in host and qs.get("match_token"):     # .../job-redirect?match_token=... : the job id is inside
        tok = qs["match_token"][0]
        try:
            import base64
            raw = base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4))
            m = re.search(rb"[A-Za-z0-9_-]{22}", raw)
            if m:
                return f"ziprecruiter:{m.group(0).decode()}"
        except ValueError:
            pass
        return f"ziprecruiter:{tok[:60]}"
    if "dice" in host:
        m = re.search(r"/job-detail/([0-9a-fA-F-]{8,})", path)
        if m:
            return f"dice:{m.group(1).lower()}"
    frag = u.fragment if re.search(r"\d", u.fragment or "") else ""      # "jobs.agency.com/#/jobs/501" (Bullhorn)
    clean = (host.replace("www.", "") + path.rstrip("/") + ("#" + frag if frag else "")).lower()
    return f"{norm_company(company)}|{clean}" if clean else f"{norm_company(company)}|manual|{now()}"


def titles_similar(a, b):
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR_RATIO


def _date(ts):
    return (ts or "")[:10]


# ---------------------------------------------------------------- duplicate check (per profile)

SHORT_JD = 1200   # a saved JD shorter than this (empty, or a search-page summary) is replaced by the full JD


def _saved_without_jd(pid, company, title, url, new_jd=None):
    """A job saved earlier (e.g. imported from Excel) that has no JD yet, or only a short summary
    and new_jd is clearly longer."""
    with connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE profile_id=? AND job_key=?", (pid, job_key(url, company))).fetchone() \
            or con.execute("SELECT * FROM jobs WHERE profile_id=? AND company_norm=? AND title_norm=?",
                           (pid, norm_company(company), norm_title(title))).fetchone()
    if row is None or row["status"] == "applied":
        return None
    have = len((row["jd"] or "").strip())
    if have == 0:
        return row
    if have < SHORT_JD and new_jd is not None and len(new_jd.strip()) > have + 200:
        return row
    return None


def check_duplicate(pid, company, title, url):
    """Returns (level, message).
    level: 'new' | 'warning' (save, but be careful) | 'blocked' (do not save)."""
    old = _saved_without_jd(pid, company, title, url)
    if old is not None or _saved_without_jd(pid, company, title, url, new_jd="x" * (SHORT_JD + 300)) is not None:
        return "warning", "Saved earlier without the full JD. Click Save to add the JD and match %."
    key = job_key(url, company)
    cn, tn = norm_company(company), norm_title(title)
    with connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE profile_id=? AND job_key=?", (pid, key)).fetchone()
        if row:
            if row["status"] == "applied":
                return "blocked", f"Already applied {_date(row['applied_at'])} ({row['source']})"
            return "blocked", f"Already saved {_date(row['saved_at'])} ({row['source']})"
        same_company = con.execute("SELECT * FROM jobs WHERE profile_id=? AND company_norm=?", (pid, cn)).fetchall()

    # same job posted on another board
    for r in same_company:
        if r["title_norm"] == tn:
            if r["status"] == "applied":
                return "blocked", f"Already applied {_date(r['applied_at'])} ({r['source']})"
            return "blocked", f"Same job already saved from {r['source']}"

    # similar role at the same company, applied recently
    cutoff = (datetime.now() - timedelta(days=SIMILAR_DAYS)).strftime("%Y-%m-%d")
    for r in same_company:
        if r["status"] == "applied" and _date(r["applied_at"]) >= cutoff and titles_similar(r["title_norm"], tn):
            return "warning", (f"Similar role applied {_date(r['applied_at'])}: "
                               f"{r['title']} ({r['source']})")
    return "new", "New job"


def has_job(pid, company, url):
    """True if this exact posting is already saved for the profile."""
    with connect() as con:
        return con.execute("SELECT 1 FROM jobs WHERE profile_id=? AND job_key=?", (pid, job_key(url, company))).fetchone() is not None


# ---------------------------------------------------------------- badges on search results

ID_KEYS = ("linkedin:", "dice:", "indeed:", "ziprecruiter:", "glassdoor:", "greenhouse:")


def _short(ts):
    try:
        return datetime.strptime(ts[:10], "%Y-%m-%d").strftime("%d %b")
    except (TypeError, ValueError):
        return ""


def lookup(pid, company, title, url):
    """What Tailor&Track knows about a job card on a search page: applied / saved / similar / None."""
    with connect() as con:
        key = job_key(url, company) if url else ""
        row = None
        if key.startswith(ID_KEYS):
            row = con.execute("SELECT * FROM jobs WHERE profile_id=? AND job_key=?", (pid, key)).fetchone()
        if not row and company and title:
            row = con.execute("SELECT * FROM jobs WHERE profile_id=? AND company_norm=? AND title_norm=?",
                              (pid, norm_company(company), norm_title(title))).fetchone()
        if row:
            if row["status"] == "applied":
                return {"status": "applied", "label": f"Applied {_short(row['applied_at'])}"}
            same_site = key and row["job_key"] == key
            return {"status": "saved", "label": "Saved" if same_site else f"Saved from {row['source']}"}
        if company and title:
            cutoff = (datetime.now() - timedelta(days=SIMILAR_DAYS)).strftime("%Y-%m-%d")
            tn = norm_title(title)
            for r in con.execute("SELECT * FROM jobs WHERE profile_id=? AND company_norm=? AND status='applied'",
                                 (pid, norm_company(company))):
                if _date(r["applied_at"]) >= cutoff and titles_similar(r["title_norm"], tn):
                    return {"status": "similar", "label": f"Similar role applied {_short(r['applied_at'])}"}
    return {"status": None}


# ---------------------------------------------------------------- saving jobs

def save_job(pid, company, title, apply_url, jd, location="", source="", posted_at=None, origin="manual"):
    """Check for duplicates, then save. Returns dict(level, message, id, match)."""
    company, title, apply_url = (company or "").strip(), (title or "").strip(), (apply_url or "").strip()
    if not company or not title:
        return {"level": "error", "message": "Company and role title are required", "id": None}
    source = source or detect_source(apply_url)

    old = _saved_without_jd(pid, company, title, apply_url, new_jd=jd or "")
    if old is not None:                      # imported without (full) JD: fill it in now, don't add a second copy
        if not (jd or "").strip():
            return {"level": "blocked", "message": "Already saved (still no JD)", "id": None}
        m = match_for(pid, jd, title)
        with connect() as con:
            con.execute("UPDATE jobs SET jd=?, match=?, missing=?, location=COALESCE(NULLIF(location,''),?) WHERE id=?",
                        (jd, m["match"] or 0, json.dumps(m["missing"]), location, old["id"]))
        return {"level": "warning", "message": "JD added to the job you saved earlier", "id": old["id"], "match": m["match"]}

    level, message = check_duplicate(pid, company, title, apply_url)
    if level == "blocked":
        with connect() as con:
            con.execute("INSERT INTO removed(profile_id,company,title,source,apply_url,reason,found_at) VALUES(?,?,?,?,?,?,?)",
                        (pid, company, title, source, apply_url, message, now()))
        return {"level": level, "message": message, "id": None}

    m = match_for(pid, jd, title)
    with connect() as con:
        cur = con.execute("""INSERT INTO jobs(profile_id,company,title,location,source,apply_url,jd,job_key,
                             company_norm,title_norm,status,warning,match,missing,saved_at,posted_at,origin)
                             VALUES(?,?,?,?,?,?,?,?,?,?,'new',?,?,?,?,?,?)""",
                          (pid, company, title, location, source, apply_url, jd, job_key(apply_url, company),
                           norm_company(company), norm_title(title),
                           message if level == "warning" else None,
                           m["match"] or 0, json.dumps(m["missing"]), now(), posted_at, origin))
    return {"level": level, "message": message if level == "warning" else "Saved", "id": cur.lastrowid,
            "match": m["match"]}


# ---------------------------------------------------------------- automatic tailoring queue

def resume_dir():
    """Folder for tailored resumes: the one chosen in the app, or 'resumes' next to the app."""
    chosen = (setting("resume_dir") or "").strip()
    folder = Path(chosen).expanduser() if chosen else RESUME_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def move_resumes(new_folder):
    """Move every saved tailored resume into new_folder (keeps the per-candidate sub-folders).
    Returns how many files were moved."""
    import shutil
    target = Path(new_folder).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    moved = 0
    with connect() as con:
        for r in con.execute("SELECT id, resume_file FROM jobs WHERE resume_file IS NOT NULL AND resume_file != ''").fetchall():
            src = Path(r["resume_file"])
            if not src.exists() or target in src.parents:
                continue
            dest = target / src.parent.name / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            con.execute("UPDATE jobs SET resume_file=? WHERE id=?", (str(dest), r["id"]))
            moved += 1
    set_setting("resume_dir", str(target))
    return moved


def setting(key, default=""):
    with connect() as con:
        r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def set_setting(key, value):
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, value))


def queue_tailoring(job_ids):
    with connect() as con:
        con.executemany("UPDATE jobs SET tailor_status='queued', tailor_note=NULL WHERE id=? AND status='new' "
                        "AND COALESCE(tailor_status,'') NOT IN ('queued','working')", [(i,) for i in job_ids])


def cancel_queue(pid):
    with connect() as con:
        con.execute("UPDATE jobs SET tailor_status=NULL WHERE profile_id=? AND tailor_status='queued'", (pid,))


def next_queued():
    with connect() as con:
        r = con.execute("SELECT * FROM jobs WHERE tailor_status='queued' ORDER BY match DESC, id LIMIT 1").fetchone()
        return dict(r) if r else None


def job(job_id):
    with connect() as con:
        r = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(r) if r else None


def set_tailor_status(job_id, status, note=None, resume_file=None, tailored_match=None):
    with connect() as con:
        if resume_file is not None:
            con.execute("UPDATE jobs SET tailor_status=?, tailor_note=?, resume_file=?, tailored_match=? WHERE id=?",
                        (status, note, resume_file, tailored_match, job_id))
        else:
            con.execute("UPDATE jobs SET tailor_status=?, tailor_note=? WHERE id=?", (status, note, job_id))


def queue_counts(pid):
    with connect() as con:
        rows = con.execute("SELECT tailor_status s, COUNT(*) n FROM jobs WHERE profile_id=? GROUP BY s", (pid,)).fetchall()
        return {r["s"] or "": r["n"] for r in rows}


def mark_applied(job_id, applied=True, when=None):
    """when: 'YYYY-MM-DD[ HH:MM:SS]' for applications made earlier (e.g. imported from Excel)."""
    with connect() as con:
        con.execute("UPDATE jobs SET status=?, applied_at=? WHERE id=?",
                    ("applied" if applied else "new", (when or now()) if applied else None, job_id))
        if applied and when:                                  # an old application: it was found back then too
            con.execute("UPDATE jobs SET saved_at=? WHERE id=?", (when, job_id))


def hide_job(job_id):
    with connect() as con:
        con.execute("UPDATE jobs SET status='hidden' WHERE id=?", (job_id,))


def delete_jobs(job_ids):
    """Delete saved jobs that were NOT applied (applied jobs are kept for reports)."""
    with connect() as con:
        con.executemany("DELETE FROM jobs WHERE id=? AND status!='applied'", [(i,) for i in job_ids])


# ---------------------------------------------------------------- application form autofill (J button)
APPLY_FIELDS = [   # (key, label, help)
    ("first_name", "First name", ""), ("last_name", "Last name", ""),
    ("email", "Email", ""), ("phone", "Phone", "e.g. +1 734 555 0100"),
    ("linkedin", "LinkedIn URL", ""), ("github", "GitHub URL", ""), ("website", "Portfolio / website", ""),
    ("city", "City", ""), ("state", "State / province", ""), ("zip", "ZIP / postal code", ""),
    ("country", "Country", ""), ("address", "Street address", "optional"),
    ("current_company", "Current company", ""), ("current_title", "Current job title", ""),
    ("years", "Years of experience", "e.g. 4"),
    ("work_auth", "Authorized to work in this country?", "Yes / No"),
    ("sponsorship", "Need visa sponsorship now or in future?", "Yes / No"),
    ("relocate", "Willing to relocate?", "Yes / No"),
    ("salary", "Expected salary", "e.g. 120000"), ("notice", "Notice period / start date", "e.g. 2 weeks"),
    ("visa", "Visa status", "e.g. H-1B, GC, Citizen, OPT"),
]


def _guess_contact(p):
    """Fill what the master resume already says (email, phone, LinkedIn, GitHub, name, years)."""
    text = (p or {}).get("text") or ""
    g = {}
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if m:
        g["email"] = m.group(0).rstrip(".")
    m = re.search(r"(\+?\d[\d\s().-]{8,}\d)", text[:1500])
    if m:
        g["phone"] = re.sub(r"\s+", " ", m.group(1)).strip()
    for key, host in (("linkedin", "linkedin.com"), ("github", "github.com")):
        m = re.search(r"(?:https?://)?(?:www\.)?" + re.escape(host) + r"/[\w\-/%.]+", text, re.I)
        if m:
            g[key] = m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)
    parts = ((p or {}).get("name") or "").split()
    if parts:
        g["first_name"], g["last_name"] = parts[0], " ".join(parts[1:])
    years = matching.years_of_experience(text)
    if years:
        g["years"] = str(years)
    return g


def apply_info(pid):
    """The candidate's answers for application forms: saved values, else guesses from the resume."""
    p = profile(pid)
    try:
        saved = json.loads(setting(f"apply_info_{pid}") or "{}")
    except ValueError:
        saved = {}
    info = _guess_contact(p)
    info.update({k: v for k, v in saved.items() if str(v).strip()})
    if info.get("first_name") or info.get("last_name"):
        info["full_name"] = f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
    if info.get("city"):
        info["location"] = ", ".join(x for x in (info.get("city"), info.get("state"), info.get("country")) if x)
    return info


def set_apply_info(pid, values):
    set_setting(f"apply_info_{pid}", json.dumps({k: (v or "").strip() for k, v in values.items()}))


def resume_for_form(pid, company, title, url):
    """(file name, bytes) to attach to an application: the tailored PDF for this job, else the master resume."""
    with connect() as con:
        key = job_key(url, company) if url else ""
        row = con.execute("SELECT * FROM jobs WHERE profile_id=? AND job_key=?", (pid, key)).fetchone() if key else None
        if not row and company and title:
            row = con.execute("SELECT * FROM jobs WHERE profile_id=? AND company_norm=? AND title_norm=?",
                              (pid, norm_company(company), norm_title(title))).fetchone()
    if row and row["resume_file"] and Path(row["resume_file"]).exists():
        f = Path(row["resume_file"])
        return f.name, f.read_bytes(), "tailored"
    p = profile(pid)
    if p and p.get("data"):
        return p.get("filename") or "resume.pdf", p["data"], "master"
    return None, None, None


def duplicate_groups(pid):
    """Groups of rows that are the same job saved more than once: same company + same role title
    (after cleaning "(Remote)", "Job# 123", "Sr." etc.). The first row of each group is the one to keep:
    applied first (earliest applied), then the one with a tailored resume, then a JD, then the oldest."""
    with connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM jobs WHERE profile_id=? AND status!='hidden'", (pid,))]
    groups = {}
    for r in rows:
        k = (r["company_norm"] or norm_company(r["company"]), r["title_norm"] or norm_title(r["title"]))
        if k[0] and k[1]:
            groups.setdefault(k, []).append(r)
    rank = lambda r: (r["status"] != "applied", r["applied_at"] or "9", not r["resume_file"],
                      not (r["jd"] or "").strip(), r["saved_at"] or "9", r["id"])
    out = [sorted(g, key=rank) for g in groups.values() if len(g) > 1]
    out.sort(key=lambda g: (g[0]["company"] or "").lower())
    return out


def remove_duplicates(pid, keep_ids=None):
    """Delete the extra copies found by duplicate_groups (applied copies too, because the same job
    counted twice spoils the reports). Keeps the first row of each group, or the ids in keep_ids.
    A deleted copy's 'applied' date moves to the kept row if the kept row was not marked applied.
    Returns how many rows were deleted."""
    gone = 0
    with connect() as con:
        for g in duplicate_groups(pid):
            keep = next((r for r in g if keep_ids and r["id"] in keep_ids), g[0])
            extras = [r for r in g if r["id"] != keep["id"]]
            applied = sorted(r["applied_at"] for r in g if r["status"] == "applied" and r["applied_at"])
            if applied and keep["status"] != "applied":
                con.execute("UPDATE jobs SET status='applied', applied_at=? WHERE id=?", (applied[0], keep["id"]))
            for r in extras:
                if not keep["resume_file"] and r["resume_file"]:
                    con.execute("UPDATE jobs SET resume_file=?, tailored_match=? WHERE id=?",
                                (r["resume_file"], r["tailored_match"], keep["id"]))
                    keep["resume_file"] = r["resume_file"]
                if not (keep["jd"] or "").strip() and (r["jd"] or "").strip():
                    con.execute("UPDATE jobs SET jd=? WHERE id=?", (r["jd"], keep["id"]))
                    keep["jd"] = r["jd"]
                con.execute("DELETE FROM jobs WHERE id=?", (r["id"],))
                gone += 1
    return gone


def old_resumes(pid, days):
    """Tailored resume files of jobs that were NOT applied and were saved more than `days` days ago."""
    cut = str((datetime.now() - timedelta(days=days)).date())
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT id, resume_file FROM jobs WHERE profile_id=? AND status!='applied' AND resume_file IS NOT NULL "
            "AND resume_file!='' AND substr(saved_at,1,10) < ?", (pid, cut))]


def clean_resumes(pid, days):
    """Delete those files from the disk (the jobs stay, so they can be tailored again). Returns (files, MB)."""
    n, size = 0, 0
    with connect() as con:
        for r in old_resumes(pid, days):
            f = Path(r["resume_file"])
            if f.exists():
                size += f.stat().st_size
                f.unlink()
                n += 1
            con.execute("UPDATE jobs SET resume_file=NULL, tailored_match=NULL, ats_after=NULL, ats_json=NULL, "
                        "tailor_status=NULL WHERE id=?", (r["id"],))
    return n, round(size / 1e6, 1)


def disk_use():
    """(number of files, MB) in the tailored resumes folder."""
    files = [f for f in Path(resume_dir()).rglob("*") if f.is_file()]
    return len(files), round(sum(f.stat().st_size for f in files) / 1e6, 1)


# ---------------------------------------------------------------- reading

def jobs(pid, status=None, search=""):
    sql, args = "SELECT * FROM jobs WHERE profile_id=?", [pid]
    if status:
        sql += " AND status=?"
        args.append(status)
    if search:
        sql += " AND (company LIKE ? OR title LIKE ?)"
        args += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY saved_at DESC"
    with connect() as con:
        return [dict(r) for r in con.execute(sql, args)]


def removed_on(pid, day=None):
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM removed WHERE profile_id=? AND found_at LIKE ? ORDER BY found_at DESC",
            (pid, (day or today()) + "%"))]


def counts(pid):
    t, m, y = today(), today()[:7], today()[:4]
    with connect() as con:
        one = lambda sql, a: con.execute(sql, (pid,) + a).fetchone()[0]
        return {
            "saved_today": one("SELECT COUNT(*) FROM jobs WHERE profile_id=? AND saved_at LIKE ?", (t + "%",)),
            "removed_today": one("SELECT COUNT(*) FROM removed WHERE profile_id=? AND found_at LIKE ?", (t + "%",)),
            "to_apply": one("SELECT COUNT(*) FROM jobs WHERE profile_id=? AND status='new' AND 1=?", (1,)),
            "applied_today": one("SELECT COUNT(*) FROM jobs WHERE profile_id=? AND status='applied' AND applied_at LIKE ?", (t + "%",)),
            "applied_month": one("SELECT COUNT(*) FROM jobs WHERE profile_id=? AND status='applied' AND applied_at LIKE ?", (m + "%",)),
            "applied_year": one("SELECT COUNT(*) FROM jobs WHERE profile_id=? AND status='applied' AND applied_at LIKE ?", (y + "%",)),
        }


init_db()
