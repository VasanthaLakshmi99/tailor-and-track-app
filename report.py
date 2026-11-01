"""Excel report (and ZIP of resumes) for a candidate, for any period."""
VERSION = "2026-11-01c"   # all Tailor&Track files must have the same version
import io
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import db

PERIODS = ["Today", "This week", "This month", "Last month", "This year", "All time", "Custom dates…"]
COLUMNS = ["Company Name", "Apply Link", "Role Title", "JD", "Status", "Applied Date", "Source", "Location",
           "Match %", "Resume File", "Saved Date", "Candidate"]


def period_range(period):
    """(start, end) as 'YYYY-MM-DD' strings, end exclusive; None = no limit.
    period is a name from PERIODS or a (from_date, to_date) pair, both days included."""
    if isinstance(period, (tuple, list)):
        a, b = period
        return str(a), str(b + timedelta(days=1))
    today = datetime.now().date()
    if period == "Today":
        return str(today), str(today + timedelta(days=1))
    if period == "This week":
        start = today - timedelta(days=today.weekday())
        return str(start), str(today + timedelta(days=1))
    if period == "This month":
        return str(today.replace(day=1)), str(today + timedelta(days=1))
    if period == "Last month":
        first = today.replace(day=1)
        prev = (first - timedelta(days=1)).replace(day=1)
        return str(prev), str(first)
    if period == "This year":
        return str(today.replace(month=1, day=1)), str(today + timedelta(days=1))
    return None, None


def rows(pid, period, applied_only=True):
    start, end = period_range(period)
    p = db.profile(pid)
    out = []
    for j in db.jobs(pid):
        if j["status"] == "hidden":
            continue
        if applied_only and j["status"] != "applied":
            continue
        day = (j["applied_at"] if applied_only else (j["applied_at"] or j["saved_at"])) or ""
        if start and not (start <= day[:10] < end):
            continue
        out.append({
            "Company Name": j["company"], "Apply Link": j["apply_url"], "Role Title": j["title"],
            "JD": (j["jd"] or "")[:32000],                      # Excel's cell limit
            "Status": "Applied" if j["status"] == "applied" else "Not applied",
            "Applied Date": (j["applied_at"] or "")[:16], "Source": j["source"], "Location": j["location"],
            "Match %": j["tailored_match"] or j["match"],
            "Resume File": Path(j["resume_file"]).name if j["resume_file"] else "",
            "Saved Date": (j["saved_at"] or "")[:16], "Candidate": p["name"] if p else "",
            "_resume_path": j["resume_file"],
        })
    out.sort(key=lambda r: (r["Applied Date"] or r["Saved Date"]), reverse=True)
    return out


def excel(pid, period, applied_only=True):
    data = rows(pid, period, applied_only)
    df = pd.DataFrame(data, columns=COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="Applications")
        ws = xw.sheets["Applications"]
        widths = {"A": 26, "B": 40, "C": 32, "D": 60, "E": 12, "F": 17, "G": 14, "H": 22, "I": 9, "J": 34, "K": 17, "L": 18}
        for col, w in widths.items():
            ws.column_dimensions[col].width = w
        from openpyxl.styles import Alignment, Font, PatternFill
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="2F5BEA")
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=cell.column_letter in ("A", "C", "D"))
            link = row[1]
            if link.value:
                link.hyperlink = link.value
                link.font = Font(color="2448C8", underline="single")
            ws.row_dimensions[row[0].row].height = 60
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        summary = xw.book.create_sheet("Summary")
        summary.append(["Candidate", data[0]["Candidate"] if data else ""])
        summary.append(["Period", period_name(period)])
        summary.append(["Applications", sum(1 for r in data if r["Status"] == "Applied")])
        summary.append(["Created", db.now()])
    return buf.getvalue(), len(data)


def resumes_zip(pid, period):
    buf = io.BytesIO()
    n = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rows(pid, period, applied_only=True):
            path = r["_resume_path"]
            if path and Path(path).exists():
                z.write(path, Path(path).name)
                n += 1
    return buf.getvalue(), n


def period_name(period):
    if isinstance(period, (tuple, list)):
        return f"{period[0]} to {period[1]}"
    return period


def file_label(pid, period):
    p = db.profile(pid)
    import re
    who = re.sub(r"[^A-Za-z0-9]+", "_", p["name"] if p else "profile").strip("_")
    return f"TailorTrack_{who}_{period_name(period).replace(' ', '_')}_{db.today()}"