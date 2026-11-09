"""Tailor&Track - run with:  streamlit run app.py"""
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import api_server
import db
import matching
import collectors
import report
import sponsors
import uk_employers
import tailor
import autotailor

st.set_page_config(page_title="Tailor&Track", page_icon="🧵", layout="wide")

# ---------------------------------------------------------------- are all files from the same update?
VERSION = "2026-11-03a"
_old = [f"{m.__name__}.py" for m in (db, matching, collectors, api_server, tailor, report, autotailor, sponsors, uk_employers)
        if getattr(m, "VERSION", None) != VERSION]
if _old:
    st.error("Some Tailor&Track files are from an older update: **" + ", ".join(_old) + "**.  \n"
             "Replace them with the latest files (same folder as app.py), then press **Ctrl+C** in the terminal "
             "and run `streamlit run app.py` again.")
    st.stop()


@st.cache_resource  # runs once, when the app starts
def start_receiver():
    db.init_db()
    db.rescore_all()  # keeps every saved job's match % up to date with the latest scoring
    collectors.prune_waiting()  # removes collected jobs that don't fit the resume roles / level / location
    status = api_server.start()
    if status == "running":   # only one copy of the app runs the daily collector
        collectors.start_daily()
        if any(sponsors.needs_visa(p) for p in db.profiles()):
            sponsors.refresh_in_background()      # UK register of licensed sponsors, once a week
        if any("united kingdom" in ",".join(sponsors.needs_visa(p) + collectors.locations_for(p)).lower()
               for p in db.profiles()) and not db.setting("uk_finder_at"):
            collectors.start_uk_finder()          # careers sites of the big UK sponsor employers, once
    return status


RECEIVER = start_receiver()

st.markdown("""
<style>
.block-container {padding-top: 2.2rem; max-width: 1100px;}
h1 {font-size: 1.8rem !important; font-weight: 700 !important; padding-bottom: 0.2rem !important;}
h3 {font-size: 1.05rem !important; font-weight: 700 !important;}
div[data-testid="stMetric"] {background: #F4F6F9; border-radius: 10px; padding: 10px 16px;}
div[data-testid="stMetricValue"] {font-size: 1.6rem;}
div[data-testid="stMetricLabel"] p {font-size: 0.85rem; color: #5B6270;}
section[data-testid="stSidebar"] {background: #F4F6F9;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- sidebar: who are we applying for?
db.init_db()
all_profiles = db.profiles()
PID = db.active_profile_id()
P = db.profile(PID)

with st.sidebar:
    st.markdown("## 🧵 Tailor&Track")
    ids = [p["id"] for p in all_profiles]
    chosen = st.selectbox("Working for", ids, index=ids.index(PID),
                          format_func=lambda i: next(p["name"] for p in all_profiles if p["id"] == i))
    if chosen != PID:
        db.set_active_profile(chosen)  # the J button follows this too
        st.rerun()
    page = st.radio("Steps", ["🔎  Find jobs", "✍️  Tailor resumes", "✅  Apply & track", "👤  Profiles"],
                    label_visibility="collapsed")
    st.divider()
    c = db.counts(PID)
    st.caption(f"Applied today for {P['name']}")
    st.markdown(f"### {c['applied_today']} / 50")
    st.progress(min(c["applied_today"] / 50, 1.0))


def profile_banner():
    roles = db.roles_for_search(P)
    if not P.get("text"):
        st.warning(f"**{P['name']}** has no resume yet. Upload it on the Find jobs page to get match scores.")
    elif not roles:
        st.info(f"Add target roles for **{P['name']}** on the 👤 Profiles page, so you can see which jobs fit.")
    else:
        note = "" if db.role_list(P) else " (read from the resume)"
        st.caption(f"👤 **{P['name']}** · resume: {P['filename']} · {roles_text(roles)}{note}")


def collect_filters():
    """Where, which kind of jobs and how many: used by Collect now and the automatic runs."""
    with st.container(border=True):
        f1, f2, f3 = st.columns([3, 2, 1.2])
        current = collectors.locations_for(P)
        options = ["Remote"] + sorted(collectors.COUNTRIES) + [c for c in current if c != "Remote" and c not in collectors.COUNTRIES]
        locs = f1.multiselect("📍 Locations (pick several: countries, Remote, or type a city and press Enter)", options,
                              default=[c for c in current if c in options], key=f"locs_{PID}", accept_new_options=True,
                              help="Every country's job boards are searched, and jobs in any of these places are kept. "
                                   "Add Remote to also keep remote jobs open to these countries.")
        if locs and [l.lower() for l in locs] != [c.lower() for c in current]:
            db.update_profile(PID, P["name"], P["roles"] or "", ", ".join(locs))
            st.rerun()
        modes = list(collectors.MATCH_MODES)
        mode = f2.selectbox("🎯 Which jobs", modes, index=modes.index(collectors.match_mode(P)),
                            format_func=collectors.MATCH_MODES.get, key=f"mode_{PID}",
                            help="Only target roles: job title must match a target role. "
                                 "+ related: also similar titles with 50%+ skills match. "
                                 "Any job my skills match: any title with 60%+ skills match (most jobs).")
        if mode != collectors.match_mode(P):
            db.set_setting(f"match_mode_{PID}", mode)
        tgt = f3.number_input("➕ Top up with older jobs to", 0, 200, collectors.target_jobs(), 5, key="topup_jobs_in",
                              help="0 = off (only jobs posted in the Date posted time). E.g. 30: if fewer than 30 "
                                   "matching jobs were posted in that time, the newest older ones (up to 7 days) are added.")
        if tgt != collectors.target_jobs():
            db.set_setting("topup_jobs", str(tgt))


def roles_text(roles):
    """Short line for many roles: 'roles: Workforce Planning Manager, Resource Manager, … +312 more'."""
    if not roles:
        return "no target roles yet"
    if len(roles) <= 6:
        return "roles: " + ", ".join(roles)
    return f"{len(roles)} target roles: " + ", ".join(roles[:4]) + f" … +{len(roles) - 4} more"


def master_resume_box():
    """Upload / check the master resume of the candidate picked in 'Working for'."""
    has = bool(P.get("text"))
    label = (f"📄 Master resume: {P['filename']}" if has
             else f"📄 Upload master resume for {P['name']} (do this first)")
    with st.expander(label, expanded=not has):
        up = st.file_uploader("Master resume (PDF or DOCX)", type=["pdf", "docx"], key=f"master_{PID}")
        if up and st.button("Save master resume", type="primary", key=f"save_master_{PID}"):
            try:
                text = db.save_resume(PID, up.name, up.getvalue())
                st.session_state["resume_msg"] = f"Saved. Read {len(text.split())} words. All jobs were re-scored."
                st.rerun()
            except Exception as e:
                st.error(f"Could not read this file: {e}")
        if has:
            st.caption(f"Uploaded {P['uploaded_at']}")
            st.text_area("Text Tailor&Track read from the resume (check it looks right)", P["text"],
                         height=180, disabled=True, key=f"master_text_{PID}")
    if "resume_msg" in st.session_state:
        st.success(st.session_state.pop("resume_msg"))


def _window_text():
    return collectors.window_label().lower()


def time_filter(label, key, current_hours=None, allow_any=False, help=None):
    """'Date posted' like LinkedIn, with extra short windows and a 'Custom' choice for any number of hours.
    Returns hours (float) or None for 'Any time'."""
    opts = (["Any time"] if allow_any else []) + list(collectors.WINDOWS) + ["Custom…"]
    cur = "Any time" if (allow_any and current_hours is None) else \
        next((k for k, v in collectors.WINDOWS.items() if v == current_hours), "Custom…")
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    pick = c1.selectbox(label, opts, index=opts.index(cur), key=key, help=help)
    if pick == "Any time":
        return None
    if pick == "Custom…":
        return c2.number_input("Hours", min_value=0.25, max_value=2160.0, step=0.5, key=key + "_h",
                               value=float(current_hours or 2), help="Type any number of hours, e.g. 2 or 0.5 (30 minutes)")
    return collectors.WINDOWS[pick]


def exp_filter(p, key):
    """Experience the JD may ask for: from-to years, typed by hand. Saved per profile."""
    lo, hi = collectors.exp_range(p)
    c1, c2 = st.columns(2)
    lo_new = c1.number_input("Experience from (yrs)", 0.0, 30.0, float(lo), 1.0, key=key + "_lo",
                             help="Skip jobs that ask for less experience than this")
    hi_new = c2.number_input("to (yrs)", 0.0, 30.0, float(min(hi, 30.0)), 1.0, key=key + "_hi",
                             help="Skip jobs that ask for more experience than this. Jobs that don't say are kept.")
    slack = collectors.exp_slack(p)
    slack_new = st.number_input("Also keep jobs asking up to this many years MORE", 0.0, 10.0, float(slack), 1.0,
                                key=key + "_slack", help="e.g. range 0–15 and 2 here: a JD asking 17 years is still kept. "
                                "The J button never blocks saving; it only shows the years the JD asks for.")
    if (lo_new, hi_new) != (lo, min(hi, 30.0)) or slack_new != slack:
        db.set_setting(f"exp_min_{p['id']}", str(lo_new))
        db.set_setting(f"exp_max_{p['id']}", str(hi_new))
        db.set_setting(f"exp_slack_{p['id']}", str(slack_new))
    return lo_new, hi_new


def visa_cell(j):
    v = sponsors.check(j.get("company"), j.get("jd") or "", j.get("location") or "")
    return {"yes": "✅", "no": "❌" if v["jd"] == "no" else "⚠️", "maybe": "🟡"}.get(v["level"], "❔") + \
        (" sponsor" if v["level"] == "yes" else " JD: no" if v["jd"] == "no" else " not on register"
         if v["level"] == "no" else " other route" if v["level"] == "maybe" else "")


def _ago(iso):
    """'3h ago', '2d ago' from an ISO time (UTC)."""
    if not iso:
        return "—"
    try:
        from datetime import datetime, timezone
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.astimezone()                      # saved_at is local time
        hours = (datetime.now(timezone.utc) - t).total_seconds() / 3600
    except ValueError:
        return "—"
    if hours < 1:
        return "just now"
    return f"{int(hours)}h ago" if hours < 24 else f"{int(hours // 24)}d ago"


def _age_hours(j):
    from datetime import datetime, timezone
    iso = j.get("posted_at") or j.get("saved_at")
    try:
        t = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.astimezone()
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600
    except ValueError:
        return 1e9


def collection_hints(last):
    """Tell the user plainly why the daily collection found nothing."""
    tips = []
    if not P.get("text"):
        tips.append(f"Upload **{P['name']}**'s master resume above. Tailor&Track reads it to decide which jobs to collect.")
    elif not db.roles_for_search(P):
        tips.append("Tailor&Track could not tell the job roles from this resume. Add target roles on the 👤 Profiles page.")
    n_sources = len([b for b in collectors.boards() if b["active"]]) + \
        len([f for f in collectors.FEEDS if collectors.feed_ready(f)])
    if last and last.get("errors") and len(last["errors"]) >= n_sources > 0:
        tips.append("Every source failed in the last run. Check the internet connection, then click Collect now.")
    if last and not tips and last.get("by_profile", {}).get(P["name"], 0) == 0:
        tips.append(f"No new matching jobs in the last run. Only jobs **posted in the {_window_text()}** that fit the "
                    f"resume are kept ({last.get('low_match', 0)} were skipped for a low skills match). "
                    "Try again later in the day, or add more companies in ⚙️ Collection settings.")
    for t in tips:
        st.info(t)
    few_jobs_help(last)


def few_jobs_help(last):
    """Where the jobs went in the last run, with one-click fixes for the filters that dropped the most."""
    if not last or not last.get("by_source"):
        return
    tot = {}
    for v in last["by_source"].values():
        for k, n in v.items():
            tot[k] = tot.get(k, 0) + n
    found, saved = tot.get("posted recently", 0), tot.get("saved", 0)
    if not found or saved >= 50:
        return
    with st.expander(f"📉 Why only {saved} new job(s)? {found} jobs were posted in the {_window_text()}"):
        rows = [(k, tot.get(k, 0)) for k in ("not a resume role", "wrong level", "wrong location", "experience", "no visa sponsor",
                                              "low skills match", "already in Tailor&Track", "duplicate blocked")]
        st.dataframe(pd.DataFrame([r for r in rows if r[1]], columns=["Skipped because", "Jobs"]), hide_index=True)
        c1, c2, c3 = st.columns(3)
        hours = collectors.window_hours()
        if hours < 72 and c1.button(f"⏱ Look back further (now {_window_text()})", width="stretch"):
            db.set_setting("window_hours", str(24 if hours < 24 else 72))
            collect_now(); st.rerun()
        lo, hi = collectors.exp_range(P)
        if tot.get("experience") and c2.button(f"🎓 Allow up to {hi + 3:g} years (now {hi:g})", width="stretch"):
            db.set_setting(f"exp_max_{PID}", str(hi + 3))
            collect_now(); st.rerun()
        if tot.get("not a resume role") and c3.button("🎯 Add more target roles", width="stretch"):
            st.info("Go to 👤 Profiles and add roles like Cloud Engineer, SRE, Platform Engineer, Build & Release Engineer, "
                    "AWS Engineer, Kubernetes Engineer, Infrastructure Engineer.")
        st.caption("Most jobs are posted on LinkedIn and Indeed, which can't be collected for free without breaking their "
                   "rules. Search there with **Past 24 hours** and use the **J button**: it shows the match %, "
                   "duplicates and the experience check on every job.")


REASON_COLS = ["jobs received", "posted recently", "not a resume role", "wrong level", "wrong location",
               "experience", "no visa sponsor", "low skills match", "already in Tailor&Track", "duplicate blocked", "saved"]


def last_run_details(last):
    """Per source: how many jobs came in and why they were skipped."""
    if not last:
        return
    with st.expander("🔍 What happened in the last run (why jobs were skipped)"):
        if last.get("skipped_feeds"):
            st.warning("Not used (no key saved): " + ", ".join(last["skipped_feeds"]) +
                       ". Add the key in ⚙️ Collection settings.")
        src = last.get("by_source") or {}
        if not src:
            st.caption("No job feed sent any job. Check the internet connection and the keys.")
        else:
            df = pd.DataFrame([{"Source": k, **{c: v.get(c, 0) for c in REASON_COLS}} for k, v in src.items()])
            df = df.sort_values("posted recently", ascending=False)
            st.dataframe(df, hide_index=True, width="stretch")
            st.caption("Company boards show only 'posted recently' onward. 'jobs received' is for the job feeds.")
        if last.get("errors"):
            st.markdown("**Problems**")
            for e in last["errors"][:15]:
                st.caption("⚠️ " + e)


def collect_now():
    with st.status(f"Collecting jobs posted in the {_window_text()}…", expanded=True) as box:
        bar = st.progress(0.0)
        summary = collectors.run(progress=lambda f, label: bar.progress(min(f, 1.0), text=label))
        if summary.get("busy"):
            box.update(label="Already collecting in the background (started automatically). "
                             "Wait 2–3 minutes, then click 🔄 Refresh list.", state="running")
        else:
            box.update(label=f"Done: {summary['new']} new jobs saved", state="complete")


def uk_sponsor_finder_box():
    """Careers sites of ~600 big UK visa-sponsor employers, found once and checked on every Collect."""
    import uk_employers
    total = len(uk_employers.employers())
    res = collectors.finder_results()
    found = {n: v for n, v in res.items() if v != "none"}
    st.markdown(f"**🇬🇧 Big UK visa-sponsor employers ({total})**  \n"
                f"Banks, consultancies, tech, pharma, retail, energy, universities, law firms and recruitment agencies "
                f"that hold a UK sponsor licence. Tailor&Track finds each one's careers site once and checks it on every "
                f"Collect. Checked **{len(res)}/{total}**, careers sites found **{len(found)}**.")
    if collectors._FINDER["running"]:
        st.info(f"⏳ Finding careers sites… {collectors._FINDER['done']}/{collectors._FINDER['total']} checked, "
                f"{collectors._FINDER['found']} found. You can keep using the app; click 🔄 Refresh list to update.")
    c1, c2 = st.columns(2)
    if c1.button("🔎 Find careers sites" if len(res) < total else "✓ Done · check for new ones",
                 disabled=collectors._FINDER["running"], width="stretch",
                 help="One time, runs in the background (about 10–20 minutes). Needs the internet."):
        collectors.start_uk_finder()
        st.rerun()
    if res and c2.button("↻ Check all again", disabled=collectors._FINDER["running"], width="stretch",
                         help="Companies sometimes move to a new careers site. Once every few months is enough."):
        collectors.start_uk_finder(force=True)
        st.rerun()
    if res:
        with st.expander(f"Which employers were found ({len(found)}) and which were not ({len(res) - len(found)})"):
            st.caption("Not found = the company uses a careers system that can't be read for free (SuccessFactors, Taleo, "
                       "iCIMS, its own website …). Its jobs still come through Reed, Jooble and JSearch, and the app adds "
                       "its careers site automatically when a saved job links to one it can read.")
            st.dataframe(pd.DataFrame([{"Company": n, "Careers site": v.split(":", 1)[0].title() if v != "none" else "—"}
                                       for n, v in sorted(res.items())]), hide_index=True, width="stretch", height=300)


def collection_settings():
    c1, c2 = st.columns(2)
    auto = c1.toggle("Collect new jobs automatically", value=db.setting("collect_auto", "1") == "1",
                     help="Runs while Tailor&Track is open (keep the terminal open). If the laptop was off, it runs when you start the app.")
    every = c2.selectbox("Every", collectors.EVERY_CHOICES, index=collectors.EVERY_CHOICES.index(collectors.collect_every())
                         if collectors.collect_every() in collectors.EVERY_CHOICES else 2,
                         format_func=lambda h: f"{h} hour{'s' if h > 1 else ''}")
    if auto != (db.setting("collect_auto", "1") == "1") or every != collectors.collect_every():
        db.set_setting("collect_auto", "1" if auto else "0")
        db.set_setting("collect_every_hours", str(every))
    nxt = collectors.next_collect()
    if nxt:
        st.caption(f"⏰ Next automatic collection: **{nxt.strftime('%d %b %H:%M') if nxt > datetime.now() else 'in a few minutes'}**. "
                   "Each run looks back at least to the previous run, so no new job is missed. "
                   "JSearch (200 free searches a month) is used on the first run of each day only.")
    st.markdown("**Free API keys (all optional, all official)**  \n"
                "Each one adds jobs from more job boards. Get the key from the link, paste it here, click Save keys. "
                "Country boards are used only when a profile wants that country (Profiles → Locations).")
    KEYS = [  # (setting, label, link, password?)
        ("jooble_key", "Jooble key · many countries", "https://jooble.org/api/about", True),
        ("rapidapi_key", "JSearch (RapidAPI) key · Google Jobs, all countries", "https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch", True),
        ("reed_key", "Reed key · United Kingdom", "https://www.reed.co.uk/developers/jobseeker", True),
        ("usajobs_key", "USAJOBS key · US government", "https://developer.usajobs.gov/apirequest/", True),
        ("usajobs_email", "Email used for the USAJOBS key", "", False),
        ("ft_id", "France Travail client ID · France", "https://francetravail.io/data/api/offres-emploi", False),
        ("ft_secret", "France Travail client secret", "", True),
        ("findwork_key", "Findwork key · software jobs, US / EU / remote", "https://findwork.dev/developers/", True),
    ]
    with st.form("api_keys"):
        cols = st.columns(2)
        vals = {}
        for n, (k, label, link, pw) in enumerate(KEYS):
            vals[k] = cols[n % 2].text_input(label, db.setting(k), type="password" if pw else "default",
                                            help=f"Get it free: {link}" if link else None)
        if st.form_submit_button("Save keys"):
            for k, v in vals.items():
                db.set_setting(k, v.strip())
            st.success("Saved. Click Collect now.")
    jp = st.number_input("JSearch pages per search (10 jobs each)", 1, 10, collectors.jsearch_pages(), 1,
                         help="More pages = more LinkedIn / Indeed / Google Jobs results. Watch your usage on the RapidAPI "
                              "dashboard: the free plan has 200 searches a month.")
    if jp != collectors.jsearch_pages():
        db.set_setting("jsearch_pages", str(jp))
    st.caption("No key needed: Arbeitsagentur (Germany), Arbetsförmedlingen (Sweden), company career sites and the remote-job feeds. "
               "Naukri, LinkedIn and Indeed have no free public API, so use the J button on their pages.")

    st.markdown("**Job feeds**")
    keys = list(collectors.FEEDS.items())
    for row in (keys[i:i + 5] for i in range(0, len(keys), 5)):
        for col, (key, label) in zip(st.columns(5), row):
            need = collectors.KEY_FEEDS.get(key)
            missing = need and not all(db.setting(k) for k in need)
            on = col.toggle(label + (" (add key)" if missing else ""), help=(
                                f"Used only when a profile wants {collectors.COUNTRY_FEEDS[key]}" if key in collectors.COUNTRY_FEEDS else None), value=db.setting(f"feed_{key}", "1") == "1",
                            key=f"feed_{key}", disabled=bool(missing))
            if not missing and on != (db.setting(f"feed_{key}", "1") == "1"):
                db.set_setting(f"feed_{key}", "1" if on else "0")

    uk_sponsor_finder_box()

    all_boards = collectors.boards()
    st.markdown(f"**Company career boards ({len(all_boards)})**  \nPaste a company's careers page link. "
                "Works with Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday, Oracle Cloud, Personio, Teamtailor, Recruitee, BambooHR, Breezy HR "
                "and Bullhorn (most staffing / recruiting agencies). All free, no key.")
    with st.form("add_board", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 2, 1], vertical_alignment="bottom")
        link = c1.text_input("Careers page link", placeholder="https://boards.greenhouse.io/stripe")
        nm = c2.text_input("Company name (optional)")
        add = c3.form_submit_button("Add", width="stretch")
    if add and link.strip():
        try:
            hit = collectors.discover(link)
            if hit:
                collectors.add_board(hit[0], hit[1], nm.strip())
                st.rerun()
            else:
                st.error("Tailor&Track couldn't find a supported job board on that page. "
                         "For other sites, open a job and use the J button.")
        except Exception as e:
            st.error(f"Could not open that link: {e}")
    if st.button(f"➕ Add {len(collectors.SUGGESTED)} suggested tech companies",
                 help="Airbnb, Stripe, Databricks, Datadog, GitLab, Cloudflare, OpenAI and more. "
                      "Each is checked on the next collect; ones that fail are marked so you can remove them."):
        for prov, tok, nm2 in collectors.SUGGESTED:
            collectors.add_board(prov, tok, nm2)
        st.rerun()
    sk = [b for b in all_boards if b["active"] and (b.get("empty_runs") or 0) >= collectors.SKIP_AFTER]
    if sk:
        s1, s2 = st.columns([3, 1], vertical_alignment="center")
        s1.caption(f"⏩ **{len(sk)}** company sites had no matching job in {collectors.SKIP_AFTER}+ collects in a row, so "
                   f"they're checked once a week only (makes Collect faster). Changing a profile's roles checks them again.")
        if s2.button("Check them all again", width="stretch"):
            collectors.reset_skips()
            st.rerun()
    if all_boards:
        for b in all_boards:
            if b["active"] and (b.get("empty_runs") or 0) >= collectors.SKIP_AFTER:
                b["last_status"] = f"⏩ weekly only (no match in {b['empty_runs']} runs) · " + (b["last_status"] or "")
        df = pd.DataFrame(all_boards)[["id", "active", "name", "provider", "last_status"]]
        df["provider"] = df["provider"].map(collectors.SOURCE_NAME).fillna(df["provider"])
        df["active"] = df["active"].astype(bool)
        df.insert(0, "remove", False)
        edited = st.data_editor(df, hide_index=True, width="stretch", key="boards_editor",
                                disabled=["provider", "last_status"],
                                column_config={"id": None, "remove": st.column_config.CheckboxColumn("Remove"),
                                               "active": st.column_config.CheckboxColumn("On"), "name": "Company",
                                               "provider": "Board", "last_status": "Last result"})
        if st.button("Save board changes"):
            for row in edited.to_dict("records"):
                if row["remove"]:
                    collectors.remove_board(row["id"])
                else:
                    collectors.update_board(row["id"], active=row["active"], name=row["name"])
            st.rerun()
    st.caption("LinkedIn, Dice, ZipRecruiter and Indeed can't be collected automatically (their rules forbid it). "
               "Use the J button there.")


IMPORT_COLS = {"company": ["company name", "company"], "title": ["role title", "title", "job title", "role"],
               "url": ["apply link", "apply url", "url", "link", "job link"], "jd": ["jd", "job description", "description"],
               "location": ["location"], "status": ["status"],
               "applied": ["applied date", "applied on", "date applied", "applied_at", "date"]}


def _as_date(v):
    """Excel / text date -> 'YYYY-MM-DD 12:00:00' (None if not a date)."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    try:
        return pd.to_datetime(str(v).strip(), errors="raise").strftime("%Y-%m-%d 12:00:00")
    except (ValueError, TypeError):
        return None


def _read_sheet(f):
    """Read an Excel/CSV list. Also understands a sheet without headers where a row holding only a date
    (e.g. 10/21/2026) starts the applications of that day: No | Company | Link | Role | JD | Status."""
    read = (lambda **kw: pd.read_csv(f, **kw)) if f.name.lower().endswith(".csv") else (lambda **kw: pd.read_excel(f, **kw))
    df = read()
    low = {str(c).strip().lower(): c for c in df.columns}
    col = {k: next((low[n] for n in names if n in low), None) for k, names in IMPORT_COLS.items()}
    if col["company"] and col["title"]:
        return df, col
    f.seek(0)
    raw = read(header=None).dropna(how="all")
    rows, day = [], None
    for _, r in raw.iterrows():
        vals = list(r.values) + [None] * 6
        rest = [v for v in vals[1:6] if not (v is None or (isinstance(v, float) and pd.isna(v)))]
        if not rest:                                   # a date row
            day = _as_date(vals[0]) or day
            continue
        rows.append({"Company Name": vals[1], "Apply Link": vals[2], "Role Title": vals[3], "JD": vals[4],
                     "Status": vals[5], "Applied Date": day})
    df = pd.DataFrame(rows)
    low = {c.lower(): c for c in df.columns}
    return df, {k: next((low[n] for n in names if n in low), None) for k, names in IMPORT_COLS.items()}


def import_jobs():
    st.caption("Columns: **Company Name, Role Title, Apply Link** (needed), **JD**, **Location**, **Status**, "
               "**Applied Date** (optional). Your old sheet with a date row before each day's applications works too. "
               "Every row goes through the duplicate check.")
    f = st.file_uploader("Excel or CSV file", type=["xlsx", "csv"], key="import_file")
    if not f:
        return
    try:
        df, col = _read_sheet(f)
    except Exception as e:
        st.error(f"Could not read the file: {e}")
        return
    if not (col["company"] and col["title"]):
        st.error("The file needs the columns Company Name and Role Title (and Apply Link).")
        return
    has_status = bool(col["status"]) and df[col["status"]].astype(str).str.lower().str.contains("appl").any()
    already = st.checkbox("These are jobs I **already applied to** (history: saved as Applied, so they are "
                          "blocked as duplicates and not shown in Jobs waiting)", value=has_status)
    st.write(f"{len(df)} rows found." + (" Applied dates found in the file." if col["applied"] else ""))
    if st.button(f"Import {len(df)} jobs for {P['name']}", type="primary"):
        counts = {"saved": 0, "applied": 0, "blocked": 0, "skipped": 0}
        no_jd = 0
        bar = st.progress(0.0)
        for i, (_, r) in enumerate(df.iterrows(), 1):
            bar.progress(i / len(df))
            get = lambda k: "" if not col[k] or pd.isna(r[col[k]]) else str(r[col[k]]).strip()
            url = get("url")
            if url.lower() == "open job":                # a hyperlink cell: pandas only sees its text
                url = ""
            if url and not url.lower().startswith(("http", "www.")):
                url = ""                                  # not a link (e.g. a stray number)
            if not get("company") or not get("title"):
                counts["skipped"] += 1
                continue
            res = db.save_job(PID, get("company"), get("title"), url, get("jd"), get("location"), origin="import")
            if res["level"] == "blocked":
                counts["blocked"] += 1
                continue
            if not res.get("id"):
                counts["skipped"] += 1
                continue
            is_applied = already or "appl" in get("status").lower()
            if is_applied:
                db.mark_applied(res["id"], True, _as_date(r[col["applied"]]) if col["applied"] else None)
                counts["applied"] += 1
            else:
                counts["saved"] += 1
                no_jd += 0 if get("jd") else 1
        st.success(f"Imported: {counts['applied']} as Applied · {counts['saved']} to Jobs waiting · "
                   f"duplicates blocked {counts['blocked']} · skipped {counts['skipped']}")
        if counts["applied"]:
            st.caption("Applied jobs are in Apply & track (Status: Applied) and count in the duplicate check, "
                       "the J button badges and the Excel reports.")
        if no_jd:
            st.info(f"{no_jd} waiting job(s) had no JD, so their match % is 0 for now. Open the job and click "
                    "**J → Save** to add the JD and match %.")


def add_by_hand():
    with st.form("add_job", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        company = c1.text_input("Company name *")
        title = c2.text_input("Role title *")
        location = c3.text_input("Location")
        url = st.text_input("Apply link")
        jd = st.text_area("Job description (JD)", height=140)
        ok = st.form_submit_button("Check & save", type="primary")
    if ok:
        st.session_state["last_save"] = (db.save_job(PID, company, title, url, jd, location), company, title)
        st.rerun()


# ---------------------------------------------------------------- page 1
def find_jobs_page():
    st.title("Find jobs")
    roles = db.roles_for_search(P)
    source = " (from the resume)" if not db.role_list(P) else ""
    st.caption(f"For **{P['name']}** · {roles_text(roles)}{source} · locations: "
               + (", ".join(collectors.locations_for(P)) or "anywhere"))
    if len(roles) > 6:
        with st.expander(f"🎯 Searches and all {len(roles)} target roles"):
            st.markdown("**Searched as:** " + ", ".join(collectors.core_terms(roles, 12)))
            st.caption("Every job title found is still checked against all target roles. "
                       "Change the roles on the 👤 Profiles page.")
            st.text(", ".join(roles))
    master_resume_box()

    if "last_save" in st.session_state:
        res, company, title = st.session_state.pop("last_save")
        {"error": st.error, "blocked": st.error, "warning": st.warning}.get(res["level"], st.success)(
            {"blocked": f"Not saved: {res['message']}", "warning": f"Saved, but careful: {res['message']}",
             "error": res["message"]}.get(res["level"], f"Saved: {company} · {title}"))

    a, b, cc = st.columns(3)
    a.metric("Saved today", c["saved_today"])
    b.metric("Duplicates blocked today", c["removed_today"])
    cc.metric("Waiting to apply", c["to_apply"])

    left, right = st.columns(2)
    with left.container(border=True, height=265):
        st.markdown("**J button** · LinkedIn, Dice, ZipRecruiter and any job site")
        st.caption("🟢 Connected" if RECEIVER == "running" else "🟠 Another Tailor&Track window is open")
        st.button("🔄 Refresh list", help="Click after saving jobs with the J button")
    with right.container(border=True, height=265):
        last = collectors.last_summary()
        nxt = collectors.next_collect()
        auto_txt = (f" · auto every {collectors.collect_every()} h, next {nxt.strftime('%H:%M')}"
                    if nxt and nxt > datetime.now() else (" · auto: soon" if nxt else " · auto off"))
        st.markdown(f"**Collection** · jobs posted in the {_window_text()}{auto_txt}")
        if collectors._lock.locked():
            st.caption("⏳ **Collecting right now in the background** (takes a few minutes). "
                       "Click 🔄 Refresh list in 2–3 minutes to see the new jobs.")
        elif last:
            mine = last.get("by_profile", {}).get(P["name"], 0)
            st.caption(f"Last run {last.get('finished', '')[:16]} · **{mine} new for {P['name']}**"
                       + (f" ({last['topped_up']} slightly older, to reach {last.get('target')})" if last.get("topped_up") else "")
                       + f" · {last['found']} new jobs checked · {len(last.get('errors') or [])} problem(s)"
                       + (f" · {last['skipped_boards']} quiet sites skipped" if last.get("skipped_boards") else ""))
        else:
            st.caption("Not run yet. Click Collect now: Tailor&Track reads the resume and searches for you.")
        h = time_filter("Date posted", "date_posted_collect", collectors.window_hours(),
                        help="Like LinkedIn's Date posted filter, plus 30 min / 1 / 3 / 6 / 10 hours and Custom. "
                             "Collect now and the automatic runs use this.")
        if h and abs(h - collectors.window_hours()) > 1e-9:
            db.set_setting("window_hours", str(h))
        d1, d2 = st.columns([3, 2], vertical_alignment="bottom")
        with d1.popover(f"🎓 Experience {collectors.exp_range(P)[0]:g}–{collectors.exp_range(P)[1]:g} yrs "
                        f"(+{collectors.exp_slack(P):g})", width="stretch"):
            exp_filter(P, "exp_collect")
            st.caption(f"Resume: {matching.years_of_experience(P.get('text') or '') or '?'} years. Jobs whose JD asks for "
                       "years outside this range are skipped. Jobs that don't mention years are kept.")
        go = d2.button("Collect now", type="primary", width="stretch")
    collect_filters()
    if go:
        collect_now()
        st.rerun()
    collection_hints(last)
    last_run_details(last)

    jobs_waiting_table()

    removed = db.removed_on(PID)
    with st.expander(f"🧹 Duplicates blocked today ({len(removed)})"):
        if removed:
            df = pd.DataFrame(removed)[["company", "title", "source", "reason", "found_at"]]
            df.columns = ["Company", "Role title", "Found on", "Why", "Time"]
            st.dataframe(df, hide_index=True, width="stretch")
        else:
            st.caption("None today.")
    with st.expander("⚙️ Collection settings (companies, feeds, time)"):
        collection_settings()
        if last and last.get("errors"):
            st.markdown("**Problems in the last run**")
            st.write("\n".join(f"- {e}" for e in last["errors"]))
    with st.expander("📥 Import jobs or your old applications (Excel or CSV)"):
        import_jobs()
    with st.expander("✋ Add a job by hand (if the J button can't read a site)"):
        add_by_hand()
    with st.expander("❓ How to install the J button (one time)"):
        st.markdown("""
1. Open Chrome and go to **chrome://extensions**
2. Turn on **Developer mode** (top right)
3. Click **Load unpacked** and choose the `extension` folder inside the Tailor&Track folder
4. Click the puzzle icon 🧩 in the Chrome toolbar and **pin** Tailor&Track
5. Keep this app running while you collect jobs
""")


# ---------------------------------------------------------------- LinkedIn-style filters for the job list
EXP_LEVELS = [("Internship / Entry level", 0, 1), ("Associate", 2, 3), ("Mid-Senior level", 4, 7),
              ("Senior", 8, 11), ("Director / Executive", 12, 99)]
WORKPLACES = ["Remote", "Hybrid", "On-site", "Not stated"]
JOB_TYPES = ["Full-time", "Contract", "Part-time", "Temporary", "Internship", "Not stated"]
SORTS = ["Most relevant", "Most recent", "Experience: low to high", "Company A–Z"]


def workplace(j):
    text = f"{j.get('location') or ''} {j.get('title') or ''}".lower()
    head = (j.get("jd") or "")[:800].lower()
    if "hybrid" in text or re.search(r"\bhybrid\b", head):
        return "Hybrid"
    if re.search(r"remote|work from home|wfh|anywhere", text) or re.search(r"\bfully remote\b|100% remote", head):
        return "Remote"
    return "On-site" if (j.get("location") or "").strip() else "Not stated"


def job_type(j):
    text = f"{j.get('title') or ''} {(j.get('jd') or '')[:1500]}".lower()
    for label, pat in (("Internship", r"\bintern(ship)?\b|placement year|graduate scheme"),
                       ("Contract", r"\bcontract(or)?\b|\bc2c\b|\bfixed[- ]term\b|\bftc\b|\binterim\b|freelance|day rate"),
                       ("Temporary", r"\btemporary\b|\btemp\b|seasonal"),
                       ("Part-time", r"\bpart[- ]time\b"),
                       ("Full-time", r"\bfull[- ]time\b|\bpermanent\b|\bperm\b")):
        if re.search(pat, text):
            return label
    return "Not stated"


def exp_level(need):
    if need is None:
        return "Not stated"
    return next(name for name, lo, hi in EXP_LEVELS if lo <= need <= hi)


def job_country(j):
    there = collectors.countries_in(j.get("location") or "")
    if there:
        return sorted(there)[0]
    return "Remote" if "remote" in (j.get("location") or "").lower() else "Other / not stated"


def linkedin_filters(saved):
    """A filter bar like LinkedIn's job search: search box, then one button per filter. Returns the filtered jobs."""
    k = f"wf_{PID}_"
    for j in saved:
        j["source"], j["company"] = j.get("source") or "Not stated", j.get("company") or "Not stated"
        j["need"] = matching.jd_years(j["jd"] or "")
        j["_level"], j["_place"], j["_type"], j["_country"] = exp_level(j["need"]), workplace(j), job_type(j), job_country(j)
        j["visa"] = visa_cell(j) if sponsors.needs_visa(P) else ""

    def opts(field):
        counts = {}
        for j in saved:
            counts[j[field]] = counts.get(j[field], 0) + 1
        return counts

    def label(name, chosen):
        if not chosen:
            return name
        shown = chosen if isinstance(chosen, str) else (chosen[0] if len(chosen) == 1 else f"{len(chosen)}")
        return f"● {name}: {shown}"

    query = st.text_input("Search", key=k + "q", placeholder="🔍 Search by title, skill, company or location",
                          label_visibility="collapsed")
    st.session_state.setdefault(k + "date", "Any time")
    row1 = st.columns(6, gap="small")
    row2 = st.columns([1, 1, 1, 1, 1.15, 1.1, 0.9], gap="small")

    def multi(col, name, field, key, order=None, help=None):
        counts = opts(field)
        options = [o for o in (order or sorted(counts)) if o in counts]
        cur = [c for c in st.session_state.get(k + key, []) if c in options]
        with col.popover(label(name, cur), width="stretch"):
            st.pills(name, options, selection_mode="multi", key=k + key,
                     format_func=lambda o: f"{o} ({counts.get(o, 0)})", help=help)
        return st.session_state.get(k + key) or []

    with row1[0].popover(label("Date posted", None if st.session_state[k + "date"] == "Any time"
                                 else st.session_state[k + "date"]), width="stretch"):
        st.radio("Date posted", ["Any time"] + list(collectors.WINDOWS), key=k + "date")
    levels = multi(row1[1], "Experience level", "_level", "level", [n for n, _, _ in EXP_LEVELS] + ["Not stated"],
                   help="From the years the JD asks for. Entry 0–1, Associate 2–3, Mid-Senior 4–7, Senior 8–11, Director 12+.")
    countries = multi(row1[2], "Location", "_country", "country")
    places = multi(row1[3], "Remote", "_place", "place", WORKPLACES)
    types = multi(row1[4], "Job type", "_type", "type", JOB_TYPES)
    companies = multi(row1[5], "Company", "company", "company")
    with row2[0].popover(label("Match", None if not st.session_state.get(k + "match") else
                               f"{st.session_state[k + 'match']}%+"), width="stretch"):
        st.select_slider("Match score at least", [0, 30, 40, 50, 60, 70, 80, 90], key=k + "match",
                         format_func=lambda v: "Any" if v == 0 else f"{v}%+")
    visa = []
    if sponsors.needs_visa(P):
        visa_counts = {}
        for j in saved:
            v = "✅ Sponsor" if j["visa"].startswith(("✅", "🟡")) else "❌ No sponsorship" if j["visa"].startswith(("❌", "⚠")) \
                else "❔ Not mentioned"
            j["_visa"] = v
        visa = multi(row2[1], "Visa", "_visa", "visa", ["✅ Sponsor", "❔ Not mentioned", "❌ No sponsorship"],
                     help=f"{P['name']} needs sponsorship for: {', '.join(sponsors.needs_visa(P))}")
    sources = multi(row2[2], "Source", "source", "source")
    with row2[3].popover(label("Sort", None if st.session_state.get(k + "sort", SORTS[0]) == SORTS[0]
                               else st.session_state[k + "sort"]), width="stretch"):
        st.radio("Sort by", SORTS, key=k + "sort")
    if row2[6].button("↺ Reset", width="stretch", help="Clear every filter"):
        for key in [x for x in st.session_state if str(x).startswith(k)]:
            del st.session_state[key]
        st.rerun()

    out = saved
    if query.strip():
        words = query.lower().split()
        out = [j for j in out if all(w in f"{j['title']} {j['company']} {j.get('location') or ''} {j['jd'] or ''}".lower()
                                     for w in words)]
    hours = collectors.WINDOWS.get(st.session_state[k + "date"])
    if hours:
        out = [j for j in out if _age_hours(j) <= hours]
    for chosen, field in ((levels, "_level"), (countries, "_country"), (places, "_place"), (types, "_type"),
                          (companies, "company"), (visa, "_visa"), (sources, "source")):
        if chosen:
            out = [j for j in out if j.get(field) in chosen]
    if st.session_state.get(k + "match"):
        out = [j for j in out if (j["match"] or 0) >= st.session_state[k + "match"]]
    sort = st.session_state.get(k + "sort", SORTS[0])
    if sort == "Most recent":
        out = sorted(out, key=_age_hours)
    elif sort == "Experience: low to high":
        out = sorted(out, key=lambda j: (j["need"] is None, j["need"] or 0))
    elif sort == "Company A–Z":
        out = sorted(out, key=lambda j: (j["company"] or "").lower())
    active = sum(bool(x) for x in (query.strip(), hours, levels, countries, places, types, companies, visa, sources,
                                   st.session_state.get(k + "match")))
    row2[4].markdown(f"**{len(out)}** of {len(saved)} jobs" + (f"  \n{active} filter(s) on" if active else ""))
    keep_ids = {j["id"] for j in out}
    drop = [j["id"] for j in saved if j["id"] not in keep_ids]
    with row2[5].popover("✅ Keep only these", width="stretch", disabled=not (active and drop)):
        st.markdown(f"Keep the **{len(out)}** job(s) shown and **delete the other {len(drop)}** waiting job(s) of "
                    f"{P['name']}. Tailor resumes and Apply & track then show only these.")
        st.caption("Applied jobs are never deleted. Deleted jobs are not collected again "
                   "(you can still save one with the J button).")
        if st.button(f"Delete {len(drop)} and keep {len(out)}", type="primary", key=k + "keep_go"):
            db.delete_jobs(drop)
            for key in [x for x in st.session_state if str(x).startswith(k)]:
                del st.session_state[key]
            st.session_state["deleted_msg"] = f"Kept {len(out)} job(s), deleted {len(drop)}."
            st.rerun()
    return out


def recycle_bin():
    """Deleted jobs (Keep only these, Delete low matches, delete ticks): restore them within 30 days."""
    gone = db.trash_list(PID)
    with st.expander(f"🗑 Recently deleted ({len(gone)}) · restore jobs you deleted"):
        if gone:
            df = pd.DataFrame([{"restore": False, "id": g["id"], "company": g["company"], "title": g["title"],
                                "deleted": (g["deleted_at"] or "")[:16]} for g in gone])
            ed = st.data_editor(df, hide_index=True, width="stretch", key=f"trash_{PID}",
                                disabled=["company", "title", "deleted"],
                                column_config={"restore": st.column_config.CheckboxColumn("Restore"), "id": None})
            pick = [int(i) for i in ed.loc[ed["restore"], "id"]]
            c1, c2 = st.columns(2)
            if c1.button(f"↩ Restore {len(pick)} ticked", disabled=not pick, width="stretch", key=f"trash_go_{PID}"):
                st.session_state["deleted_msg"] = f"Restored {db.restore_jobs(pick)} job(s) to Jobs waiting."
                st.rerun()
            if c2.button(f"↩ Restore all {len(gone)}", width="stretch", key=f"trash_all_{PID}"):
                st.session_state["deleted_msg"] = f"Restored {db.restore_jobs([g['id'] for g in gone])} job(s)."
                st.rerun()
        else:
            st.caption("Nothing deleted in the last 30 days (jobs deleted before this update are not in the bin).")
        st.caption("Jobs deleted **before this update** can't be restored, but you can let Collect find them again "
                   "(set Date posted far enough back, e.g. Past week, then Collect now).")
        if st.button("Let Collect find my earlier deleted jobs again", key=f"forget_{PID}"):
            st.session_state["deleted_msg"] = (f"OK: {db.forget_deleted(PID)} deleted job(s) can be collected again. "
                                               "Pick a Date posted that covers them and click Collect now.")
            st.rerun()


def jobs_waiting_table():
    """Saved jobs for this profile, best match first, with the JD and delete options."""
    saved = sorted(db.jobs(PID, status="new"), key=lambda j: j["match"] or 0, reverse=True)
    every_waiting = list(saved)                      # before the filters below (used by "Delete low matches")
    head, btn = st.columns([4, 1], vertical_alignment="bottom")
    head.subheader(f"Jobs waiting ({len(saved)})")
    if "deleted_msg" in st.session_state:
        st.success(st.session_state.pop("deleted_msg"))
    recycle_bin()
    if not saved:
        st.caption("No jobs yet. Use the J button, or click Collect now.")
        return

    saved = linkedin_filters(saved)
    if not saved:
        st.info("No waiting jobs match these filters. Change a filter above or click ↺ Reset.")
        return

    roles = db.roles_for_search(P)
    for j in saved:
        j["posted"] = _ago(j.get("posted_at")) if j.get("posted_at") else "saved " + _ago(j.get("saved_at"))
        fit = matching.title_fit(j["title"], roles) if roles else None
        kind = collectors.role_kind(j, P) if roles and not fit else None
        j["fit"] = ("✓ " + fit) if fit else ("≈ related role" if kind == "related" else
                                             "skills match" if kind == "other" else "⚠ not a target role" if roles else "")
        j["warning"] = j["warning"] or ""
        j["jd_short"] = " ".join((j["jd"] or "").split())[:400] or "— no JD yet: open the job and click J"
        j["exp"] = f"{j['need']}+ yrs" if j["need"] is not None else "—"
        j["visa"] = visa_cell(j)

    with btn.popover("🗑 Delete low matches", width="stretch"):
        cutoff = st.slider("Delete jobs below this match %", 0, 100, 50, step=5)
        low = [j["id"] for j in every_waiting if (j["match"] or 0) < cutoff]
        st.caption(f"Checks all {len(every_waiting)} waiting jobs, not only the ones the filters show. "
                   "Applied jobs are never deleted.")
        if st.button(f"Delete {len(low)} job(s)", type="primary", disabled=not low):
            db.delete_jobs(low)
            st.session_state["deleted_msg"] = f"Deleted {len(low)} low-match jobs."
            st.rerun()

    show_visa = bool(sponsors.needs_visa(P))
    cols = ["id", "company", "title", "fit", "match", "exp"] + (["visa"] if show_visa else []) + \
        ["posted", "jd_short", "source", "apply_url"] + \
        (["warning"] if any(j["warning"] for j in saved) else [])
    df = pd.DataFrame(saved)[cols]
    df.insert(0, "delete", False)
    edited = st.data_editor(
        df, hide_index=True, width="stretch", key=f"waiting_editor_{PID}", height=min(520, 38 + 35 * len(df)),
        disabled=[col for col in df.columns if col != "delete"],
        column_config={
            "delete": st.column_config.CheckboxColumn("Delete", width="small"),
            "id": None,  # hidden
            "company": st.column_config.TextColumn("Company", width="medium"),
            "title": st.column_config.TextColumn("Role title", width="medium"),
            "fit": "Role fit",
            "match": st.column_config.ProgressColumn("Match", min_value=0, max_value=100, format="%d%%", width="small"),
            "jd_short": st.column_config.TextColumn("JD (start)", width="large",
                                                    help="First lines of the job description. Read the full JD below the table."),
            "source": "Source",
            "exp": st.column_config.TextColumn("Exp.", width="small", help="Years of experience the JD asks for"),
            "visa": st.column_config.TextColumn("Visa", width="small",
                                               help="✅ licensed UK sponsor or the JD offers sponsorship · ❌ the JD says no · "
                                                    "⚠️ not on the UK register · ❔ not mentioned"),
            "posted": st.column_config.TextColumn("Posted", width="small",
                                                  help="When the company posted it. 'saved …' = posting date unknown."),
            "apply_url": st.column_config.LinkColumn("Job", display_text="Open ↗", width="small"),
            "warning": "Warning",
        },
    )
    picked = edited.loc[edited["delete"], "id"].tolist()
    if picked and st.button(f"🗑 Delete {len(picked)} ticked job(s)"):
        db.delete_jobs(picked)
        st.session_state["deleted_msg"] = f"Deleted {len(picked)} job(s)."
        st.rerun()

    with st.expander("📄 Read the full JD of a job"):
        ids = [j["id"] for j in saved]
        names = {j["id"]: f"{j['company']} · {j['title']} ({j['match'] or 0}%)" for j in saved}
        pick = st.selectbox("Job", ids, format_func=names.get, key=f"jd_pick_{PID}")
        job = next(j for j in saved if j["id"] == pick)
        if job["jd"]:
            st.code(job["jd"], language=None, wrap_lines=True, height=300)
        else:
            st.caption("No JD saved for this job yet. Open the job and click the J button, then Save.")


# ---------------------------------------------------------------- profiles page
def profiles_page():
    st.title("Profiles")
    st.caption("One profile per candidate. Each has its own resume, target roles, jobs, duplicate check and reports.")
    if "profile_msg" in st.session_state:
        st.success(st.session_state.pop("profile_msg"))

    resume_folder_box()

    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("➕ Expand all", width="stretch"):
        st.session_state["profiles_open"] = "all"
    if b2.button("➖ Collapse all", width="stretch"):
        st.session_state["profiles_open"] = "none"
    mode = st.session_state.get("profiles_open", "active")

    for p in all_profiles:
        cp = db.counts(p["id"])
        active = p["id"] == PID
        label = (f"{'🟢 ' if active else '👤 '}{p['name']} · {cp['to_apply']} waiting · "
                 f"{cp['applied_month']} applied this month · resume: {p['filename'] or 'none'}")
        opened = mode == "all" or (mode == "active" and active)
        with st.expander(label, expanded=opened):
            profile_box(p, active)

    # add a new profile
    with st.expander("➕ Add a profile", expanded=False):
        with st.form("new_profile", clear_on_submit=True):
            n = st.text_input("Candidate name", placeholder="e.g. Priya - QA")
            r = st.text_input("Target roles (comma separated)", placeholder="e.g. QA Engineer, Test Automation Engineer, SDET")
            lc = st.text_input("Locations (comma separated, blank = anywhere)", placeholder="e.g. United States, Remote")
            if st.form_submit_button("Add profile", type="primary") and n.strip():
                new_id = db.add_profile(n, r)
                db.update_profile(new_id, n, r, lc)
                db.set_active_profile(new_id)
                st.session_state["profile_msg"] = f"Added {n}. Now upload their resume here."
                st.rerun()


def resume_folder_box():
    """Where tailored resume PDFs are saved (e.g. a Google Drive or OneDrive folder, to save laptop space)."""
    current = db.resume_dir()
    with st.expander(f"📁 Where tailored resumes are saved: {current}"):
        st.caption("To save laptop space, choose a folder of **Google Drive for desktop** (e.g. `G:\\My Drive\\Tailor&Track resumes`) "
                   "or **OneDrive** (e.g. `C:\\Users\\ACER\\OneDrive\\Tailor&Track resumes`), or an external drive. "
                   "In Google Drive / OneDrive settings choose **Stream files** / **Files On-Demand** so the PDFs stay online.")
        with st.form("resume_folder"):
            new = st.text_input("Folder", str(current))
            move = st.checkbox("Also move the resumes already saved into this folder", value=True)
            if st.form_submit_button("Save folder", type="primary"):
                try:
                    if move:
                        n = db.move_resumes(new)
                        st.session_state["profile_msg"] = f"Resumes are now saved in {new}. Moved {n} existing file(s)."
                    else:
                        from pathlib import Path as _P
                        _P(new).expanduser().mkdir(parents=True, exist_ok=True)
                        db.set_setting("resume_dir", new.strip())
                        st.session_state["profile_msg"] = f"New resumes will be saved in {new}."
                    st.rerun()
                except OSError as e:
                    st.error(f"Can't use that folder: {e}")
    files, mb = db.disk_use()
    with st.expander(f"🧹 Free up space: {files} resume file(s), {mb} MB"):
        st.caption("Deletes tailored PDFs of jobs you did **not** apply to. Resumes of applied jobs are always kept. "
                   "The jobs stay in the list, so you can tailor them again if needed.")
        c1, c2 = st.columns([1, 1.4])
        days = c1.number_input("Older than (days)", 1, 365, 7, key="clean_days")
        old = db.old_resumes(PID, int(days))
        if c2.button(f"🗑 Delete {len(old)} old resume(s)", disabled=not old, width="stretch"):
            n, freed = db.clean_resumes(PID, int(days))
            st.session_state["profile_msg"] = f"Deleted {n} resume file(s), freed {freed} MB."
            st.rerun()


def profile_box(p, active):
    pid = p["id"]
    if not active and st.button(f"Work for {p['name']} now", key=f"use_{pid}", type="primary"):
        db.set_active_profile(pid)
        st.rerun()
    with st.form(f"edit_{pid}"):
        name = st.text_input("Name", p["name"])
        roles = st.text_input("Target roles (comma separated)", p["roles"] or "",
                              placeholder="e.g. DevOps Engineer, Cloud Engineer, Site Reliability Engineer, Platform Engineer")
        locs = st.text_input("Locations for automatic collection (comma separated, blank = from the resume)",
                             p.get("locations") or "", placeholder="e.g. United States, Remote")
        v1, v2 = st.columns([2, 1], vertical_alignment="bottom")
        visa = v1.text_input("Needs visa sponsorship for (countries, comma separated)",
                             db.setting(f"visa_need_{pid}"), placeholder="e.g. United Kingdom",
                             help="Shows ✅ / ❌ visa sponsorship on every job and in the J button. For the UK it checks "
                                  "the Home Office register of licensed sponsors (official, free).")
        only_sp = v2.checkbox("Collect only from visa sponsors", db.setting(f"visa_only_{pid}") == "1",
                              help="Automatic collection skips jobs whose JD says no sponsorship, and UK jobs from "
                                   "companies that are not licensed sponsors.")
        confirmed = st.text_area("Extra skills the candidate confirmed (not written in the resume)",
                                 p.get("confirmed_skills") or "", height=70,
                                 help="Filled when you tick skills on the Tailor page. Used for match % and every tailored resume.")
        if st.form_submit_button("Save"):
            if roles.strip() != (p["roles"] or "").strip():
                collectors.reset_skips()            # new roles: every company site may match again
            db.update_profile(pid, name or p["name"], roles, locs)
            db.set_setting(f"visa_need_{pid}", visa.strip())
            db.set_setting(f"visa_only_{pid}", "1" if only_sp else "0")
            if visa.strip():
                sponsors.refresh_in_background()
            db.set_confirmed_skills(pid, confirmed)
            db.rescore(pid)              # new match % and role fit for the saved jobs
            collectors.prune_waiting()   # removes collected jobs that no longer fit
            st.session_state["profile_msg"] = f"Saved {name or p['name']}."
            st.rerun()

    if sponsors.needs_visa(p):
        n, upd = sponsors.count(), (db.setting("uk_sponsors_updated") or "")[:10]
        s1, s2 = st.columns([3, 1], vertical_alignment="center")
        s1.caption(f"🛂 UK register of licensed sponsors: **{n:,}** employer names" + (f", updated {upd}" if upd else "") +
                   " (Home Office, refreshed weekly). Other countries: the app reads what the JD says about sponsorship.")
        if s2.button("Update now", key=f"sp_upd_{pid}"):
            with st.spinner("Downloading the register from GOV.UK…"):
                rows, msg = sponsors.refresh(force=True)
            st.session_state["profile_msg"] = f"UK sponsor register: {msg}."
            st.rerun()

    up = st.file_uploader(f"Master resume for {p['name']} (PDF or DOCX)", type=["pdf", "docx"], key=f"resume_{pid}")
    if up and st.button("Save resume", type="primary", key=f"save_resume_{pid}"):
        try:
            text = db.save_resume(pid, up.name, up.getvalue())
            st.session_state["profile_msg"] = f"Resume saved for {p['name']} ({len(text.split())} words). Jobs re-scored."
            st.rerun()
        except Exception as e:
            st.error(f"Could not read this file: {e}")
    if p.get("text"):
        st.caption(f"Current resume: {p['filename']} (uploaded {p['uploaded_at']})")
        known = sorted(matching.find_skills(p["text"]).keys(), key=str.lower)
        learned = matching.learn_skills(p["text"])
        st.markdown("**Skills found in this resume:** " + (", ".join(known) or "none"))
        if learned:
            st.markdown("**Extra skills from the Skills section:** " + ", ".join(learned))
        if st.toggle("Show the text read from the resume", key=f"show_text_{pid}"):
            st.text(p["text"])

    apply_info_box(p)

    if len(all_profiles) > 1:
        with st.popover(f"🗑 Delete profile {p['name']}"):
            st.write(f"This deletes **{p['name']}** and **all of their jobs**. It can't be undone.")
            if st.button("Yes, delete this profile", type="primary", key=f"del_{pid}"):
                db.delete_profile(pid)
                st.session_state["profile_msg"] = "Profile deleted."
                st.rerun()


def apply_info_box(p):
    """Answers the J button types into application forms (Fill application form)."""
    pid = p["id"]
    info = db.apply_info(pid)
    with st.expander(f"✍️ Application form answers for {p['name']} (J button → Fill application form)"):
        st.caption("Saved once, then on any application page click **J → ✍️ Fill application form**: name, email, phone, "
                   "LinkedIn, location, work authorization, sponsorship and similar questions are filled, and the "
                   "tailored resume for that job is attached. **You check the form and click Submit yourself.** "
                   "Blank boxes were guessed from the resume where possible.")
        with st.form(f"apply_info_{pid}"):
            cols = st.columns(3)
            vals = {k: cols[i % 3].text_input(label, info.get(k, ""), help=help or None, key=f"ai_{k}_{pid}")
                    for i, (k, label, help) in enumerate(db.APPLY_FIELDS)}
            if st.form_submit_button("Save answers", type="primary"):
                db.set_apply_info(pid, vals)
                st.session_state["profile_msg"] = f"Saved application answers for {p['name']}."
                st.rerun()


# ---------------------------------------------------------------- page 2: tailor resumes (by hand)
GRID = 3   # cards per row on the Tailor page


def tailor_page():
    st.title("Tailor resumes")
    profile_banner()
    if not P.get("text"):
        return

    waiting = sorted(db.jobs(PID, status="new"), key=lambda j: j["match"] or 0, reverse=True)
    todo = [j for j in waiting if not j["resume_file"]]
    done = [j for j in waiting if j["resume_file"]]
    ready = [j for j in done if (j["tailored_match"] or 0) >= tailor.READY]

    a, b, cc = st.columns(3)
    a.metric("To tailor", len(todo))
    b.metric("Tailored", len(done))
    cc.metric(f"Ready ({tailor.READY}%+ match)", len(ready))

    with st.container(border=True):
        st.markdown("**⚡ Auto-tailor** · builds the tailored PDF for you: JD keywords in Skills, the most relevant "
                    "bullets first, a summary for the role, and the JD skills you tick added to Skills and work experience.")
        tick_all = st.toggle("✅ Tick all JD skills for every job (the candidate has used them)",
                             value=db.setting(f"tick_all_{PID}", "0") == "1", key=f"tick_all_global_{PID}",
                             help="ON: every job's missing JD skills are added to that job's resume (Skills + work "
                                  "experience) without opening the cards. They are used only for that job's resume. "
                                  "OFF: only the master resume and the skills you confirmed are used.")
        if tick_all != (db.setting(f"tick_all_{PID}", "0") == "1"):
            db.set_setting(f"tick_all_{PID}", "1" if tick_all else "0")
        g1, g2, g3 = st.columns([2, 2, 3], vertical_alignment="bottom")
        floor = g1.selectbox("Jobs with match", [0, 50, 60, 70, 80], index=2,
                             format_func=lambda v: "All jobs" if v == 0 else f"{v}%+ (before tailoring)")
        batch = [j for j in todo if (j["match"] or 0) >= floor and (j["jd"] or "").strip()]
        go = g2.button(f"⚡ Auto-tailor {len(batch)} job(s)", type="primary", disabled=not batch, width="stretch")
        g3.caption("The new PDFs appear in the **Done** tab (⬇ download) and in Apply & track → Resume column. "
                   "Jobs without a JD are skipped: open them and click J first.")
        if go:
            bar, done_n, ready_n, errors = st.progress(0.0), 0, 0, []
            for k, j in enumerate(batch, 1):
                bar.progress(k / len(batch), text=f"{j['company']} · {j['title']}")
                try:
                    extra = autotailor.gaps(j, db.scoring_text(P)) if tick_all else []
                    _, pct, _ = tailor.auto_tailor(j, extra, remember=False)
                    done_n += 1
                    ready_n += pct >= tailor.READY
                except Exception as e:
                    errors.append(f"{j['company']}: {e}")
            st.session_state["tailor_msg"] = (100 if ready_n == done_n else 0,
                                              f"Auto-tailored {done_n} resume(s): see the **Done** tab. {ready_n} reached "
                                              f"{tailor.READY}%+." + (f" Problems: {'; '.join(errors[:3])}" if errors else ""))
            st.rerun()

    st.caption("Best quality (free): on a card, **🤖 Rewrite with Claude / ChatGPT** gives a prompt that rewrites the "
               "whole resume for the job; paste the AI's answer back and the PDF is built in the master's layout. "
               "⚡ Auto-tailor is instant but only adds and reorders JD keywords.")

    if "tailor_msg" in st.session_state:
        pct, msg = st.session_state.pop("tailor_msg")
        (st.success if pct >= tailor.READY else st.warning)(msg)

    bulk_upload(waiting)

    t1, t2 = st.tabs([f"To do ({len(todo)})", f"Done ({len(done)})"])
    with t1:
        if not todo:
            st.caption("Nothing to tailor. Save jobs with the J button or collect today's jobs first.")
        tailor_grid(todo, "todo")
    with t2:
        if not done:
            st.caption("No tailored resumes yet.")
        else:
            data, n = tailor.resumes_zip(done)
            z1, z2 = st.columns([2, 3], vertical_alignment="center")
            z1.download_button(f"⬇ Download all {n} tailored resumes (ZIP)", data, type="primary", width="stretch",
                               file_name=f"{tailor.safe_name(P['name'])}_tailored_resumes_{db.today()}.zip",
                               mime="application/zip", disabled=not n)
            z2.caption("One ZIP with every PDF below, named Company_Role.pdf. "
                       f"They are also in the folder: {db.resume_dir()}")
        tailor_grid(done, "done")


def bulk_upload(jobs):
    """Upload many tailored PDFs at once; each file is matched to its job by its name."""
    with st.expander("⬆️ Upload many tailored PDFs at once"):
        st.caption("Name each PDF like the card says (**Company_Role.pdf**, e.g. *Orbit_Health_Senior_DevOps_Engineer.pdf*). "
                   "Tailor&Track matches every file to its job. Check the list, change any wrong match, then click Save all.")
        files = st.file_uploader("Tailored resumes (PDF)", type=["pdf"], accept_multiple_files=True, key=f"bulk_{PID}")
        if not files:
            return
        names = {j["id"]: f"{j['company']} · {j['title']}" for j in jobs}
        ids = [0] + [j["id"] for j in jobs]
        picks = []
        for f in files:
            best = tailor.guess_job(f.name, jobs)
            c1, c2 = st.columns([2, 3], vertical_alignment="center")
            c1.markdown(f"📄 `{f.name}`")
            pick = c2.selectbox("Job", ids, index=ids.index(best["id"]) if best else 0, key=f"bulk_pick_{f.file_id}",
                                format_func=lambda i: "— skip this file —" if i == 0 else names[i],
                                label_visibility="collapsed")
            picks.append((f, pick))
        if st.button(f"Save all {sum(1 for _, p in picks if p)} resume(s)", type="primary"):
            done_n, ready_n, errors = 0, 0, []
            for f, pick in picks:
                if not pick:
                    continue
                job = next(j for j in jobs if j["id"] == pick)
                try:
                    _, pct, _ = tailor.save_tailored(job, f.name, f.getvalue())
                    done_n += 1
                    ready_n += pct >= tailor.READY
                except Exception as e:
                    errors.append(f"{f.name}: {e}")
            st.session_state["tailor_msg"] = (100 if ready_n == done_n else 0,
                                              f"Saved {done_n} resume(s), {ready_n} at {tailor.READY}%+ match. See the Done tab."
                                              + (f" Problems: {'; '.join(errors[:3])}" if errors else ""))
            st.rerun()


def pick_dates(key):
    """From / to date pickers. Returns (from_date, to_date), both included."""
    from datetime import date, timedelta
    c1, c2 = st.columns(2)
    a = c1.date_input("From", date.today() - timedelta(days=30), key=f"{key}_from", format="YYYY-MM-DD")
    b = c2.date_input("To", date.today(), key=f"{key}_to", format="YYYY-MM-DD")
    return (min(a, b), max(a, b))


@st.cache_data(max_entries=500, show_spinner=False)
def master_ats(jd, resume_text, title, company):
    return matching.ats_report(jd, resume_text, title, company)


PAGE = 12   # cards per page on the Tailor page (fewer cards = faster page)


def tailor_grid(jobs, key="grid"):
    pages = max(1, -(-len(jobs) // PAGE))
    page = 1
    if pages > 1:
        page = st.number_input(f"Page (of {pages}, {PAGE} jobs each)", 1, pages, 1, key=f"{key}_page_{PID}")
    shown = jobs[(page - 1) * PAGE: page * PAGE]
    for start in range(0, len(shown), GRID):
        for col, j in zip(st.columns(GRID), shown[start:start + GRID]):
            with col.container(border=True):
                tailor_card(j)


def ats_check(rep, tailored):
    """The ATS breakdown of one resume against one JD, with what to fix."""
    st.markdown(f"**ATS score {rep['score']}/100** · " + ("tailored resume" if tailored else "master resume"))
    for label, key, w in (("Hard skills", "hard", 55), ("Job title", "title", 15), ("Soft skills", "soft", 10),
                          ("Experience", "experience", 10), ("Education", "education", 5), ("Format", "format", 5)):
        st.progress(rep[key] / 100, text=f"{label} {rep[key]}%  (weight {w})")
    if rep.get("tips"):
        st.markdown("**To improve**")
        for tip in rep["tips"]:
            st.caption("• " + tip)
    st.caption("Same kind of check as Jobscan and similar ATS checkers. Tick only skills the candidate really has.")


def ai_rewrite_box(j):
    """Real rewriting by Claude or ChatGPT (free in the browser): copy the prompt, paste the answer back, get the PDF."""
    confirmed = db.confirmed_list(P)
    if db.setting(f"tick_all_{PID}", "0") == "1":            # Tick all: the candidate has the JD's other skills too
        confirmed = list(dict.fromkeys(confirmed + autotailor.gaps(j, db.scoring_text(P))))
    st.markdown("**1.** Copy the prompt (copy icon, top right of the box).")
    st.code(tailor.ai_prompt(j, db.scoring_text(P), confirmed), language=None, wrap_lines=True, height=110)
    l1, l2 = st.columns(2)
    l1.link_button("Open Claude ↗", "https://claude.ai/new", width="stretch")
    l2.link_button("Open ChatGPT ↗", "https://chatgpt.com/", width="stretch")
    if j.get("ats_json"):
        rep = json.loads(j["ats_json"])
        if rep.get("score", 0) < 95:
            st.warning(f"The tailored resume scores **{rep['score']}** on the ATS check. To get 95+, send this to the "
                       "same AI chat, then paste its new answer below:")
            st.code(tailor.improve_prompt(j, rep, confirmed), language=None, wrap_lines=True, height=90)
            missing_true = [k for k in rep.get("missing", []) if k.lower() not in {c.lower() for c in confirmed}]
            if missing_true:
                st.caption("Not added because the candidate hasn't confirmed them (tick them in ⚡ Auto-tailor or switch "
                           f"on Tick all, only if true): {', '.join(missing_true[:10])}")
    st.markdown("**2.** Paste it there and send. **3.** Copy the AI's whole answer and paste it here:")
    answer = st.text_area("AI answer", key=f"ai_ans_{j['id']}", height=160, label_visibility="collapsed",
                          placeholder="Paste the tailored resume the AI wrote…")
    if st.button("Build my tailored PDF", type="primary", key=f"ai_go_{j['id']}", width="stretch",
                 disabled=not answer.strip()):
        try:
            path, pct, miss, issues = tailor.save_ai_answer(j, answer, db.scoring_text(P))
            msg = (f"{j['company']} · {j['title']}: **{path.name}** built from the AI's rewrite. "
                   f"Match **{pct}%** (was {j['match']}%). Download it in the **Done** tab.")
            if issues:
                msg += " ⚠️ Check before sending: " + "; ".join(issues[:4]) + "."
            st.session_state["tailor_msg"] = (0 if issues else pct, msg)
            st.session_state.pop(f"ai_ans_{j['id']}", None)
            st.rerun()
        except Exception as e:
            st.error(str(e))
    st.caption("The PDF keeps the master's layout and fonts. Employers, dates and numbers are checked against the "
               "master resume, and anything new is flagged.")


def tailor_card(j):
    tm = j["tailored_match"]
    score = f"{j['match'] or 0}%" + (f" → **{tm}%** {'✅' if (tm or 0) >= tailor.READY else '⚠️'}" if j["resume_file"] else "")
    title = j["title"] if len(j["title"]) <= 48 else j["title"][:46] + "…"
    before = master_ats(j["jd"] or "", db.scoring_text(P), j["title"], j["company"]) if (j["jd"] or "").strip() else None
    after = json.loads(j["ats_json"]) if j.get("ats_json") else None
    ats = (f" · ATS {before['score']}" if before else "") + (f" → **{after['score']}**" if after else "")
    st.markdown(f"**{j['company']}**  \n{title}  \nMatch {score}{ats}")
    if not (j["jd"] or "").strip():
        st.caption("⚠️ No JD yet: open the job and click J first.")
    else:
        with st.popover("📊 ATS check", width="stretch"):
            ats_check(after or before, tailored=bool(after))
    with st.popover("🤖 Rewrite with Claude / ChatGPT (free)", width="stretch", disabled=not (j["jd"] or "").strip()):
        ai_rewrite_box(j)

    with st.popover("⚡ Auto-tailor this job", width="stretch", disabled=not (j["jd"] or "").strip()):
        gap = [g for g in autotailor.gaps(j, db.scoring_text(P))]
        all_on = db.setting(f"tick_all_{PID}", "0") == "1"
        if gap:
            st.markdown("**JD skills not in the master resume.** Tick the ones the candidate **has really used**: "
                        "they go into Skills and the work experience, and are remembered for every next job.")
            ticked = st.pills("Skills", gap, selection_mode="multi", default=gap if all_on else None,
                              key=f"gap_{j['id']}_{all_on}", label_visibility="collapsed")
            st.caption("All ticked because **Tick all** is ON at the top." if all_on else
                       "Tip: switch on **Tick all** at the top to tick these for every job.")
        else:
            ticked = []
            st.caption("The resume already shows every JD skill Tailor&Track found.")
        if st.button("Create tailored PDF", type="primary", key=f"auto_{j['id']}", width="stretch"):
            try:
                path, pct, miss = tailor.auto_tailor(j, ticked or [], remember=not all_on)
                msg = (f"{j['company']} · {j['title']}: **{path.name}** created. Match **{pct}%** (was {j['match']}%). "
                       "Download it in the **Done** tab.")
                if autotailor.to_pdf.pages < autotailor.MIN_PAGES:
                    msg += (f" It fills {autotailor.to_pdf.pages} pages: the master resume is short. Use **🤖 Rewrite "
                            "with Claude / ChatGPT** on this card for a 1.5–2 page version.")
                if pct < tailor.READY and miss:
                    msg += f" Not in the resume yet: {', '.join(miss[:8])}."
                st.session_state["tailor_msg"] = (pct, msg)
                st.rerun()
            except Exception as e:
                st.error(str(e))

    u1, u2 = st.columns([3, 2])
    with u1.popover("Upload PDF", icon="⬆️", width="stretch", help="Upload a resume you tailored yourself (PDF)"):
        up = st.file_uploader("Tailored resume (PDF only)", type=["pdf"], key=f"tl_{j['id']}")
        if up is not None:
            tag = f"tl_done_{j['id']}_{up.file_id}"
            if tag not in st.session_state:          # process each upload once
                try:
                    path, pct, miss = tailor.save_tailored(j, up.name, up.getvalue())
                    st.session_state[tag] = True
                    msg = f"{j['company']} · {j['title']}: saved as **{path.name}**. Match **{pct}%** (was {j['match']}%)."
                    if pct < tailor.READY and miss:
                        msg += f" Still missing: {', '.join(miss[:8])}. Add only if true."
                    st.session_state["tailor_msg"] = (pct, msg)
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not read this PDF: {e}")
    if j["apply_url"]:
        u2.link_button("Open ↗", j["apply_url"], width="stretch")
    if j["resume_file"]:
        p = Path(j["resume_file"])
        if p.exists():
            st.download_button(f"⬇ {p.name}", p.read_bytes(), file_name=p.name, key=f"dl_{j['id']}",
                               mime="application/pdf", width="stretch")


# ---------------------------------------------------------------- page 3: apply & track
def apply_page():
    st.title("Apply & track")
    profile_banner()

    a, b, cc, d = st.columns(4)
    a.metric("Ready to apply", c["to_apply"])
    b.metric("Applied today", c["applied_today"])
    cc.metric("This month", c["applied_month"])
    d.metric("This year", c["applied_year"])

    f1, f2, f5, f3, f4 = st.columns([2.6, 1.2, 1.3, 1.3, 1.1])
    search = f1.text_input("🔎 Search company or role", placeholder="Type a company or role title…")
    status = f2.selectbox("Status", ["Not applied", "Applied", "All"])
    period = f5.selectbox("When", report.PERIODS, index=len(report.PERIODS) - 1,
                          help="Applied jobs: the day you applied. Not applied: the day the job was saved.")
    sort = f3.selectbox("Sort by", ["Newest applied", "Oldest applied", "Best match", "Newest saved", "Oldest saved"]
                        if status == "Applied" else
                        ["Best match", "Newest saved", "Oldest saved", "Newest applied", "Oldest applied"])
    if period == "Custom dates…":
        period = pick_dates("track")
    min_match = f4.selectbox("Match score", [0, 50, 60, 70, 80, 90], format_func=lambda v: "Any" if v == 0 else f"{v}%+")

    start, end = report.period_range(period)
    in_period = lambda j: not start or start <= ((j["applied_at"] if j["status"] == "applied" else j["saved_at"]) or "")[:10] < end
    data = [j for j in db.jobs(PID, search=search.strip()) if j["status"] != "hidden"
            and (j["tailored_match"] or j["match"] or 0) >= min_match and in_period(j)]
    if status == "Not applied":
        data = [j for j in data if j["status"] != "applied"]
    elif status == "Applied":
        data = [j for j in data if j["status"] == "applied"]
    if sort.startswith("Oldest"):
        col = "applied_at" if sort.endswith("applied") else "saved_at"
        data.sort(key=lambda j: (not j[col], j[col] or ""))     # oldest first, empty dates last
    else:
        key = {"Best match": lambda j: j["tailored_match"] or j["match"] or 0,
               "Newest saved": lambda j: j["saved_at"] or "", "Newest applied": lambda j: j["applied_at"] or ""}[sort]
        data.sort(key=key, reverse=True)

    for jid, name, why in st.session_state.get("apply_blocked", []):
        st.error(f"⛔ **Not marked as applied: {name}.** {why}. Applying again can get the candidate (and you) "
                 "blocked by the company.")
        if st.button(f"I checked it, mark {name} as applied anyway", key=f"force_btn_{jid}"):
            db.mark_applied(jid, True)
            st.session_state["apply_blocked"] = [x for x in st.session_state["apply_blocked"] if x[0] != jid]
            st.rerun()
    if "apply_msg" in st.session_state:
        st.success(st.session_state.pop("apply_msg"))
    st.caption(f"{len(data)} job(s). Click **Open** to apply on the company site, then tick **Applied ✓**. "
               "Unticking it moves the job back to Not applied.")
    if data:
        df = pd.DataFrame([{
            "id": j["id"], "applied": j["status"] == "applied", "company": j["company"], "title": j["title"],
            "apply_url": j["apply_url"], "match": j["tailored_match"] or j["match"],
            "resume": api_server.resume_link(j),
            "source": j["source"], "saved": (j["saved_at"] or "")[:10], "applied_at": (j["applied_at"] or "")[:16],
            "exp": (lambda n: f"{n}+ yrs" if n is not None else "—")(matching.jd_years(j["jd"] or "")),
            **({"visa": visa_cell(j)} if sponsors.needs_visa(P) else {}),
            "jd": (j["jd"] or "")[:300].replace("\n", " "),
        } for j in data])
        edited = st.data_editor(
            df, hide_index=True, width="stretch", key=f"apply_editor_{PID}_{status}_{search}_{sort}_{min_match}_{period}", height=min(560, 38 + 35 * len(df)),
            disabled=[col for col in df.columns if col != "applied"],
            column_config={
                "id": None,
                "applied": st.column_config.CheckboxColumn("Applied ✓", width="small"),
                "company": st.column_config.TextColumn("Company name", width="medium"),
                "title": st.column_config.TextColumn("Role title", width="medium"),
                "apply_url": st.column_config.LinkColumn("Apply link", display_text="Open ↗", width="small"),
                "jd": st.column_config.TextColumn("JD (start)", width="large"),
                "match": st.column_config.NumberColumn("Match", format="%d%%", width="small"),
                "resume": st.column_config.LinkColumn("Resume (click to download)", width="medium",
                                                      display_text=r"/resume/\d+/([^?]+)\?"),
                "source": "Source", "saved": "Saved", "applied_at": "Applied on",
                "exp": st.column_config.TextColumn("Exp.", width="small", help="Years of experience the JD asks for"),
                "visa": st.column_config.TextColumn("Visa", width="small"),
            })
        changed = edited[edited["applied"] != df["applied"]]
        if len(changed):
            by_id = {j["id"]: j for j in data}
            stopped, n_on, n_off = [], 0, 0
            for row in changed.to_dict("records"):
                if row["applied"]:
                    j = by_id.get(row["id"]) or {}
                    hit = db.applied_conflict(PID, j.get("company"), j.get("title"), j.get("jd") or "", exclude_id=row["id"])
                    if hit and not st.session_state.get(f"force_apply_{row['id']}"):
                        stopped.append((row["id"], f"{j.get('company')} · {j.get('title')}", hit[1]))
                        continue
                    n_on += 1
                else:
                    n_off += 1
                db.mark_applied(row["id"], bool(row["applied"]))
            if stopped:
                st.session_state["apply_blocked"] = stopped
            st.session_state["apply_msg"] = (f"Marked {n_on} as applied. " if n_on else "") + \
                                            (f"{n_off} moved back to not applied." if n_off else "")
            st.rerun()


    # reports
    with st.container(border=True):
        st.subheader("📊 Excel report")
        r1, r2 = st.columns(2)
        period = r1.selectbox("Period", report.PERIODS, index=2)
        what = r2.radio("Include", ["Applied jobs only", "All saved jobs"], horizontal=True)
        if period == "Custom dates…":
            period = pick_dates("report")
        xls, n = report.excel(PID, period, applied_only=(what == "Applied jobs only"))
        label = report.file_label(PID, period)
        d1, d2 = st.columns(2)
        d1.download_button(f"⬇ Download Excel ({n} jobs)", xls, file_name=f"{label}.xlsx", type="primary",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", disabled=not n)
        z, nz = report.resumes_zip(PID, period)
        d2.download_button(f"⬇ Resumes used ({nz} files, ZIP)", z, file_name=f"{label}_resumes.zip",
                           mime="application/zip", disabled=not nz)
        st.caption("Excel columns: " + ", ".join(report.COLUMNS))

    duplicates_box()
    duplicate_rules_box()


def duplicate_rules_box():
    with st.expander("🔒 Duplicate application rules (strict)"):
        st.markdown("A job is **blocked** (J button, Collect now, and the Applied ✓ tick) when the candidate already applied:\n"
                    "1. to the **same company for the same role**, at any time (AWS = Amazon, JPMorgan Chase = "
                    "JPMorgan; Senior / II / Remote don't make it a different role)\n"
                    "2. to the **same job description** at any company: agencies re-post their clients' jobs\n"
                    "3. optional: to **any role at the same company** within the cooldown below (0 = off)\n\n"
                    "A **different role at the same company is allowed**.")
        c1, c2 = st.columns(2)
        strict = c1.toggle("Strict mode", value=db.strict_mode(), key="strict_dupes_t",
                           help="Off: rule 3 is not used, and a re-posted JD only gives a warning.")
        days = c2.number_input("Cooldown per company (days)", 0, 365, db.cooldown_days(), 5, key="cooldown_in",
                               help="0 = off (different roles at the same company are allowed). Set e.g. 30 only "
                                    "if a company limits how often a candidate may apply.")
        if strict != db.strict_mode():
            db.set_setting("strict_dupes", "1" if strict else "0")
        if days != db.cooldown_days():
            db.set_setting("company_cooldown", str(int(days)))
        st.caption("Applications made before Tailor&Track (or outside it) are only known if you import them: "
                   "Find jobs → 📥 Import (Excel/CSV with company, role, applied date). Import every past "
                   "application of each candidate so the checks see them.")


def duplicates_box():
    """Find the same job saved twice (same company + same role) and delete the extra copies."""
    groups = db.duplicate_groups(PID)
    extra = sum(len(g) - 1 for g in groups)
    with st.expander(f"🧹 Duplicate jobs: {extra} extra cop{'y' if extra == 1 else 'ies'} in {len(groups)} group(s)",
                     expanded=False):
        if not groups:
            st.success("No duplicates. Every job is saved once.")
            return
        st.caption("Same company + same role title saved more than once. ⭐ = the copy that is **kept** "
                   "(applied first, then the one with a tailored resume or JD). Untick ⭐ and tick another row to keep that one instead. "
                   "The kept copy gets the applied date, resume and JD of the deleted copies, so nothing is lost.")
        rows = [{"keep": i == 0, "group": n + 1, "id": r["id"], "company": r["company"], "title": r["title"],
                 "status": "Applied" if r["status"] == "applied" else "Not applied",
                 "applied": (r["applied_at"] or "")[:10], "saved": (r["saved_at"] or "")[:10],
                 "resume": "✓" if r["resume_file"] else "", "source": r["source"], "link": r["apply_url"]}
                for n, g in enumerate(groups) for i, r in enumerate(g)]
        ed = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch", key=f"dups_{PID}",
                            disabled=[c for c in rows[0] if c != "keep"],
                            column_config={"keep": st.column_config.CheckboxColumn("⭐ Keep"),
                                           "id": None, "link": st.column_config.LinkColumn("Link", display_text="Open")})
        keep = set(ed.loc[ed["keep"], "id"].astype(int))
        if st.button(f"🗑 Delete {extra} extra cop{'y' if extra == 1 else 'ies'}", type="primary"):
            n = db.remove_duplicates(PID, keep)
            st.session_state["apply_msg"] = f"Deleted {n} duplicate cop{'y' if n == 1 else 'ies'}."
            st.rerun()


# ---------------------------------------------------------------- router
if "Find" in page:
    find_jobs_page()
elif "Tailor" in page:
    tailor_page()
elif "Apply" in page:
    apply_page()
else:
    profiles_page()