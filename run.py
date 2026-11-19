"""Start Tailor&Track:  python run.py   (or double-click start.bat)

Same as `streamlit run app.py`, but on Windows it first switches off the harmless
"WinError 995 / 10053 / 10054 · Task exception was never retrieved" messages that Windows
prints when the app is stopped or a browser tab is closed."""
VERSION = "2026-11-03a"   # all Tailor&Track files must have the same version
import asyncio
import logging
import sys
from pathlib import Path

if sys.platform == "win32":
    # the "selector" loop doesn't raise WinError 995 when the app stops (the default "proactor" loop does)
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from streamlit.web import cli as stcli      # noqa: E402  (after the loop policy is set)

if sys.platform == "win32":
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

if __name__ == "__main__":
    app = str(Path(__file__).with_name("app.py"))
    sys.argv = ["streamlit", "run", app] + sys.argv[1:]
    sys.exit(stcli.main())