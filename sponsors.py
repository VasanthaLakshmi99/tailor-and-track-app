"""Visa sponsorship check.

1. UK: the Home Office "Register of licensed sponsors: workers" (official, free, updated every working day,
   about 120,000 employers). Tailor&Track downloads it once a week and checks every company against it.
2. Any country: what the JD itself says ("visa sponsorship available" / "unable to sponsor").
"""
VERSION = "2026-11-03a"   # all Tailor&Track files must have the same version
import csv
import io
import re
import threading
import time
from datetime import datetime, timedelta

import requests

import db

UA = {"User-Agent": "TailorTrack/1.0 (personal job tracker)"}
GOVUK_API = "https://www.gov.uk/api/content/government/publications/register-of-licensed-sponsors-workers"
GOVUK_PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
REFRESH_DAYS = 7
_lock = threading.Lock()
_CACHE = {"names": None, "words": None}

SUFFIX = {"ltd", "limited", "plc", "llp", "llc", "inc", "uk", "u.k", "group", "holdings", "holding", "co", "company",
          "the", "corp", "corporation", "gmbh", "services", "service", "international", "europe", "emea", "global",
          "trading", "t", "a", "as", "of", "and", "&"}


def norm(name):
    """'Capgemini UK PLC' -> 'capgemini'; 'Tata Consultancy Services Limited' -> 'tata consultancy'."""
    n = (name or "").lower().replace("&", " and ")
    n = re.sub(r"\(.*?\)", " ", n)
    words = [w for w in re.sub(r"[^a-z0-9 ]+", " ", n).split() if w not in SUFFIX]
    return " ".join(words)


def _names(row_name):
    """A register row can be 'Company A Ltd t/a Brand B': index both names."""
    parts = re.split(r"\s+(?:t/a|trading as)\s+", row_name or "", flags=re.I)
    return [p for p in (norm(x) for x in parts) if p]


# ---------------------------------------------------------------- download and store
def _csv_url():
    try:
        r = requests.get(GOVUK_API, headers=UA, timeout=30)
        if r.ok:
            for doc in (r.json().get("details") or {}).get("attachments") or []:
                url = doc.get("url") or ""
                if url.lower().endswith(".csv"):
                    return url
    except (requests.RequestException, ValueError):
        pass
    r = requests.get(GOVUK_PAGE, headers=UA, timeout=30)          # fallback: the link on the page
    m = re.search(r'https://assets\.publishing\.service\.gov\.uk/[^"\']+?\.csv', r.text or "")
    return m.group(0) if m else None


def refresh(force=False):
    """Download the UK register if it is older than a week. Returns (rows, message)."""
    if not _lock.acquire(blocking=False):
        return 0, "Already downloading"
    try:
        last = db.setting("uk_sponsors_updated")
        if not force and last and datetime.now() - datetime.fromisoformat(last) < timedelta(days=REFRESH_DAYS):
            return count(), "Up to date"
        url = _csv_url()
        if not url:
            return count(), "Could not find the register file on GOV.UK"
        r = requests.get(url, headers=UA, timeout=120)
        r.raise_for_status()
        text = r.content.decode("utf-8-sig", errors="replace")
        rows = []
        for row in csv.DictReader(io.StringIO(text)):
            name = (row.get("Organisation Name") or "").strip()
            if not name:
                continue
            route = (row.get("Route") or "").strip()
            rating = (row.get("Type & Rating") or "").strip()
            town = (row.get("Town/City") or "").strip()
            for n in _names(name):
                rows.append((n, name, town, rating, route))
        if len(rows) < 1000:
            return count(), "The register file looked wrong; kept the old copy"
        with db.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS uk_sponsors (norm TEXT, name TEXT, town TEXT, rating TEXT, route TEXT)")
            con.execute("DELETE FROM uk_sponsors")
            con.executemany("INSERT INTO uk_sponsors VALUES (?,?,?,?,?)", rows)
            con.execute("CREATE INDEX IF NOT EXISTS uk_sponsors_norm ON uk_sponsors(norm)")
        db.set_setting("uk_sponsors_updated", datetime.now().isoformat(timespec="seconds"))
        _CACHE["names"] = None
        return count(), f"Downloaded {len(rows):,} sponsor names"
    except requests.RequestException as e:
        return count(), f"Download failed: {str(e)[:80]}"
    finally:
        _lock.release()


def refresh_in_background():
    threading.Thread(target=refresh, daemon=True, name="tt-sponsors").start()


def count():
    try:
        with db.connect() as con:
            return con.execute("SELECT COUNT(*) FROM uk_sponsors").fetchone()[0]
    except Exception:
        return 0


def _load():
    if _CACHE["names"] is None:
        names = {}
        try:
            with db.connect() as con:
                for r in con.execute("SELECT norm, name, rating, route FROM uk_sponsors"):
                    names.setdefault(r["norm"], []).append((r["name"], r["rating"], r["route"]))
        except Exception:
            pass
        _CACHE["names"] = names
        first = {}
        for n in names:                                   # first word -> names (for "Capgemini" vs "Capgemini UK Ops")
            first.setdefault(n.split()[0], []).append(n)
        _CACHE["words"] = first
    return _CACHE["names"], _CACHE["words"]


def uk_sponsor(company):
    """The register entry for this company, or None. {'name', 'routes', 'rating', 'exact'}"""
    n = norm(company)
    if len(n) < 2:
        return None
    names, first = _load()
    if not names:
        return None
    hit, exact = names.get(n), True
    if not hit and len(n) >= 4:                           # "Capgemini" -> "capgemini uk operations"
        for cand in first.get(n.split()[0], []):
            if cand.startswith(n + " ") or (n.startswith(cand + " ") and len(cand) >= 6) or \
                    (len(n.split()) > 1 and set(n.split()) <= set(cand.split())):
                hit, exact = names[cand], False
                break
    if not hit:
        return None
    routes = sorted({route for _, _, route in hit if route})
    rating = next((rt for _, rt, _ in hit if "A rating" in rt), hit[0][1])
    return {"name": hit[0][0], "routes": routes, "rating": rating, "exact": exact,
            "skilled_worker": any("skilled worker" in r.lower() for r in routes) or not routes}


# ---------------------------------------------------------------- what the JD says
NO_SPONSOR = re.compile(
    r"(unable|not able|cannot|can ?not|can't|won't|will not|do not|don't|does not|doesn't|are not able)\s+(to\s+)?"
    r"(offer|provide|support|consider|accept)?\s*(visa\s+|work permit\s+)?sponsor|"
    r"no (visa\s+)?sponsorship|sponsorship (is )?(not|un)available|not (offer|provide)\w* (visa )?sponsorship|"
    r"without (the need for |requiring )?(visa\s+)?sponsorship|must (already )?have (the |full )?right to work|"
    r"(do|does) not (currently )?(offer|provide) sponsorship|not eligible for sponsorship", re.I)
YES_SPONSOR = re.compile(
    r"(visa|work permit|skilled worker)\s+sponsorship\s+(is\s+)?(available|provided|offered|considered|possible)|"
    r"(we|will|can|able to)\s+(can\s+)?(offer|provide|support)\s+(visa\s+)?sponsorship|"
    r"sponsorship (is )?(available|offered|provided|considered)|we (can|will) sponsor|open to sponsor|"
    r"sponsor (a |the )?(skilled worker|work) visa|relocation and visa support|visa support (is )?(available|provided)", re.I)


def jd_says(jd):
    """'yes' / 'no' / None: what the JD says about visa sponsorship."""
    jd = jd or ""
    if NO_SPONSOR.search(jd):
        return "no"
    if YES_SPONSOR.search(jd):
        return "yes"
    return None


def check(company, jd="", location=""):
    """Everything the app shows about sponsorship for one job."""
    import collectors
    says = jd_says(jd)
    uk = "United Kingdom" in collectors.countries_in(location or "") if location else False
    reg = uk_sponsor(company) if (uk or not location) else None
    have_register = bool(_load()[0])
    if says == "no":
        label, level = "❌ JD says no visa sponsorship", "no"
    elif says == "yes":
        label, level = "✅ JD offers visa sponsorship", "yes"
    elif reg and reg["skilled_worker"]:
        label, level = f"✅ Licensed UK visa sponsor ({reg['name']})", "yes"
    elif reg:
        label, level = f"🟡 On the UK sponsor register, but not for Skilled Worker ({', '.join(reg['routes'])})", "maybe"
    elif uk and have_register:
        label, level = "⚠️ Not on the UK register of licensed sponsors", "no"
    else:
        label, level = "❔ Sponsorship not mentioned", None
    if says and reg and reg["skilled_worker"] and says == "no":
        label += " (the company is a licensed sponsor, but not for this job)"
    return {"level": level, "label": label, "register": reg, "jd": says, "uk": uk}


def needs_visa(p):
    """Countries where this profile needs visa sponsorship (Profiles page)."""
    return [c.strip() for c in (db.setting(f"visa_need_{(p or {}).get('id')}") or "").split(",") if c.strip()]