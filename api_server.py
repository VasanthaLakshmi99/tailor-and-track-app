"""Small local receiver for the J button Chrome extension.

Listens only on 127.0.0.1:8765 (your own laptop). The extension sends the job
it read from the page; this file checks duplicates and saves it with db.py.
app.py starts it automatically - you never run this file yourself.
"""
VERSION = "2026-11-03a"   # all Tailor&Track files must have the same version
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db

HOST, PORT = "127.0.0.1", 8765
MAX_BODY = 300_000  # bytes; a JD is never this big


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self):
        # only our extension sends this header; normal websites cannot write here
        return self.headers.get("X-JobPilot") == "1"

    def _send_resume(self):
        """GET /resume/<job id>/<file name>?t=<token>: download the resume used for that job."""
        from pathlib import Path
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        parts = u.path.split("/")
        token = (parse_qs(u.query).get("t") or [""])[0]
        if not token or token != db.setting("file_token"):
            return self._send(403, {"error": "forbidden"})
        try:
            job = db.job(int(parts[2]))
        except (IndexError, ValueError):
            job = None
        path = Path(job["resume_file"]) if job and job.get("resume_file") else None
        if not path or not path.exists():
            return self._send(404, {"error": "resume file not found"})
        data = path.read_bytes()
        kind = "application/pdf" if path.suffix.lower() == ".pdf" else \
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/resume/"):
            return self._send_resume()
        if not self._allowed():
            return self._send(403, {"error": "forbidden"})
        if self.path == "/ping":
            return self._send(200, {"ok": True, "app": "Tailor&Track"})
        if self.path == "/profiles":
            return self._send(200, {"active": db.active_profile_id(),
                                    "profiles": [{"id": p["id"], "name": p["name"]} for p in db.profiles()]})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._allowed():
            return self._send(403, {"error": "forbidden"})
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY:
            return self._send(413, {"error": "too large"})
        try:
            data = json.loads(self.rfile.read(size) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})

        company, title = data.get("company", ""), data.get("title", "")
        url, jd = data.get("url", ""), data.get("jd", "")
        try:
            pid = int(data.get("profile_id") or db.active_profile_id())
        except (TypeError, ValueError):
            pid = db.active_profile_id()
        if not db.profile(pid):
            return self._send(200, {"level": "error", "message": "Profile not found. Reopen the J box."})

        if self.path == "/lookup":          # badges on search result pages
            items = (data.get("items") or [])[:200]
            return self._send(200, {"profile": db.profile(pid)["name"], "results": [
                db.lookup(pid, (i.get("company") or "").strip(), (i.get("title") or "").strip(), (i.get("url") or "").strip())
                for i in items]})

        if self.path == "/active":          # profile picked in the J box -> also picked in the app
            db.set_active_profile(pid)
            return self._send(200, {"ok": True})

        if self.path == "/check":
            if company.strip() and title.strip():
                level, message = db.check_duplicate(pid, company, title, url)
            else:  # still give the match %, the user can type the missing field
                level, message = "error", "Fill in company name and role title"
            out = {"level": level, "message": message}
            m = db.match_for(pid, jd, title) if jd.strip() else {"match": None, "missing": [], "fit": None,
                                                                     "has_roles": bool(db.role_list(db.profile(pid)))}
            m["missing"] = m["missing"][:6]
            out.update(m)
            out["has_resume"] = bool(db.resume_text(pid))
            out.update(experience_check(pid, jd))
            out["visa"] = visa_check(pid, company, jd, data.get("location", ""))
            return self._send(200, out)

        if self.path == "/apply_info":      # J box "Fill application form"
            import base64
            name, data_, kind = db.resume_for_form(pid, company, title, url)
            return self._send(200, {"info": db.apply_info(pid), "resume_name": name, "resume_kind": kind,
                                    "resume_b64": base64.b64encode(data_).decode() if data_ else None})

        if self.path == "/save":
            res = db.save_job(pid, company, title, url, jd, data.get("location", ""), data.get("source", ""), origin="j")
            return self._send(200, res)

        self._send(404, {"error": "not found"})

    def log_message(self, *args):  # keep the terminal quiet
        pass


def visa_check(pid, company, jd, location):
    """Visa sponsorship for the J box: shown when the profile needs a visa, or when the JD talks about it."""
    import sponsors
    p = db.profile(pid)
    need = sponsors.needs_visa(p)
    v = sponsors.check(company, jd, location)
    if not need and not v["jd"]:
        return None
    reg = v["register"]
    return {"level": v["level"], "label": v["label"], "need": need,
            "register_name": reg["name"] if reg else None, "register_loaded": sponsors.count() > 0}


def experience_check(pid, jd):
    """Years the JD asks for vs the profile's experience range (Find jobs → 🎓 Experience)."""
    import collectors
    import matching
    need = matching.jd_years(jd or "")
    p = db.profile(pid)
    lo, hi = collectors.exp_range(p)
    have = matching.years_of_experience((p or {}).get("text") or "")
    return {"exp_need": need, "exp_min": lo, "exp_max": hi, "exp_have": have,
            "exp_ok": None if need is None else lo <= need <= hi + collectors.exp_slack(p)}


def resume_link(job):
    """Link that downloads the resume used for a job (works only on this laptop)."""
    from pathlib import Path
    from urllib.parse import quote
    if not job.get("resume_file"):
        return None
    return f"http://{HOST}:{PORT}/resume/{job['id']}/{quote(Path(job['resume_file']).name)}?t={db.setting('file_token')}"


def start():
    """Start the receiver in the background. Returns a status message."""
    import secrets
    if not db.setting("file_token"):
        db.set_setting("file_token", secrets.token_hex(16))
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        return "busy"  # port taken: Tailor&Track is probably already open in another window
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return "running"


if __name__ == "__main__":  # handy for testing on its own
    print(start(), f"on http://{HOST}:{PORT}")
    threading.Event().wait()