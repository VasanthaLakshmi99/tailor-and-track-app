"""Collects new jobs (posted within the Date posted window) automatically, every few hours.

Where from (all free):
  - company career sites, no key: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday,
    Recruitee, BambooHR, Breezy HR, and Bullhorn (the system most staffing / recruiting agencies use)
  - public job feeds, no key: Himalayas, We Work Remotely, Remotive, Remote OK, Jobicy, The Muse, Arbeitnow
  - optional free keys: Jooble, JSearch (RapidAPI free plan)

LinkedIn, Dice, ZipRecruiter and Indeed are NOT collected here: their rules forbid
automatic collection and it can get accounts blocked. Use the J button there.

Each job is kept for a profile only if its title fits the profile's target roles and
(if set) its locations. Every job goes through the normal duplicate check.
"""
VERSION = "2026-11-01c"   # all Tailor&Track files must have the same version
import html
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

import db
import matching

UA = {"User-Agent": "TailorTrack/1.0 (personal job tracker)"}
PAUSE = 0.7            # seconds between requests to the same site, to be polite
BOARD_THREADS = 6      # companies checked at the same time (each one is a different site)
WINDOW_HOURS = 24          # default; changed with the "Date posted" filter on Find jobs
WINDOWS = {"Past 30 minutes": 0.5, "Past 1 hour": 1, "Past 3 hours": 3, "Past 6 hours": 6, "Past 10 hours": 10,
           "Past 24 hours": 24, "Past 3 days": 72, "Past week": 168, "Past month": 720}


def window_hours():
    """How far back to collect (hours, can be 0.5). Set with the Date posted filter on Find jobs."""
    try:
        h = float(db.setting("window_hours", str(WINDOW_HOURS)) or WINDOW_HOURS)
        return h if h > 0 else WINDOW_HOURS
    except ValueError:
        return WINDOW_HOURS


def window_label(h=None):
    h = window_hours() if h is None else h
    named = next((k for k, v in WINDOWS.items() if v == h), None)
    if named:
        return named
    return f"Past {h:g} hours" if h < 48 else f"Past {h / 24:g} days"


# ---------------------------------------------------------------- experience filter (per profile)
def exp_range(p):
    """(min, max) years a job may ask for. Default: anything up to the candidate's years + 2."""
    pid = (p or {}).get("id")
    years = matching.years_of_experience((p or {}).get("text") or "")
    def num(key, default):
        try:
            v = db.setting(f"{key}_{pid}", "")
            return float(v) if v != "" else default
        except ValueError:
            return default
    return num("exp_min", 0.0), num("exp_max", float(years + 2) if years is not None else 99.0)


def exp_ok(jd, p):
    """True if the years the JD asks for are inside the profile's range (or the JD doesn't say)."""
    need = matching.jd_years(jd or "")
    if need is None:
        return True
    lo, hi = exp_range(p)
    return lo <= need <= hi
_lock = threading.Lock()

SUGGESTED = [  # well-known companies with public boards; Tailor&Track checks each one on the first collect
    ("greenhouse", "airbnb", "Airbnb"), ("greenhouse", "stripe", "Stripe"), ("greenhouse", "databricks", "Databricks"),
    ("greenhouse", "robinhood", "Robinhood"), ("greenhouse", "coinbase", "Coinbase"), ("greenhouse", "dropbox", "Dropbox"),
    ("greenhouse", "pinterest", "Pinterest"), ("greenhouse", "lyft", "Lyft"), ("greenhouse", "cloudflare", "Cloudflare"),
    ("greenhouse", "gitlab", "GitLab"), ("greenhouse", "datadog", "Datadog"), ("greenhouse", "mongodb", "MongoDB"),
    ("greenhouse", "twilio", "Twilio"), ("greenhouse", "okta", "Okta"), ("greenhouse", "figma", "Figma"),
    ("greenhouse", "discord", "Discord"), ("greenhouse", "reddit", "Reddit"), ("greenhouse", "instacart", "Instacart"),
    ("greenhouse", "gusto", "Gusto"), ("greenhouse", "brex", "Brex"), ("greenhouse", "samsara", "Samsara"),
    ("greenhouse", "asana", "Asana"), ("greenhouse", "elastic", "Elastic"), ("greenhouse", "affirm", "Affirm"),
    ("lever", "palantir", "Palantir"), ("ashby", "openai", "OpenAI"), ("ashby", "ramp", "Ramp"),
    ("ashby", "notion", "Notion"), ("ashby", "linear", "Linear"),
    # companies with large US DevOps / SRE / cloud teams
    ("greenhouse", "pagerduty", "PagerDuty"), ("greenhouse", "newrelic", "New Relic"), ("greenhouse", "grafanalabs", "Grafana Labs"),
    ("greenhouse", "cockroachlabs", "Cockroach Labs"), ("greenhouse", "fivetran", "Fivetran"), ("greenhouse", "chime", "Chime"),
    ("greenhouse", "roblox", "Roblox"), ("greenhouse", "doordashusa", "DoorDash"), ("greenhouse", "airtable", "Airtable"),
    ("greenhouse", "vercel", "Vercel"), ("greenhouse", "postman", "Postman"), ("greenhouse", "twitch", "Twitch"),
    ("greenhouse", "squarespace", "Squarespace"), ("greenhouse", "flexport", "Flexport"), ("greenhouse", "nerdwallet", "NerdWallet"),
    ("greenhouse", "sofi", "SoFi"), ("greenhouse", "duolingo", "Duolingo"), ("greenhouse", "anthropic", "Anthropic"),
    ("greenhouse", "scaleai", "Scale AI"), ("greenhouse", "toast", "Toast"), ("lever", "plaid", "Plaid"),
    ("lever", "spotify", "Spotify"),
    # big product companies with their own public career search
    ("amazon", "amazon", "Amazon"), ("microsoft", "microsoft", "Microsoft"),
    # large US product / enterprise companies on Workday
    ("workday", "nvidia.wd5/NVIDIAExternalCareerSite", "NVIDIA"), ("workday", "salesforce.wd12/External_Career_Site", "Salesforce"),
    ("workday", "adobe.wd5/external_experienced", "Adobe"), ("workday", "intel.wd1/External", "Intel"),
    ("workday", "paypal.wd1/jobs", "PayPal"), ("workday", "dell.wd1/External", "Dell"),
    ("workday", "hp.wd5/ExternalCareerSite", "HP"), ("workday", "workday.wd5/Workday", "Workday"),
    ("workday", "crowdstrike.wd5/crowdstrikecareers", "CrowdStrike"), ("workday", "redhat.wd5/jobs", "Red Hat"),
    ("workday", "autodesk.wd1/Ext", "Autodesk"), ("workday", "broadcom.wd1/External_Career", "Broadcom / VMware"),
    ("workday", "motorolasolutions.wd5/Careers", "Motorola Solutions"), ("workday", "zillow.wd5/Zillow_Group_External", "Zillow"),
    ("workday", "disney.wd5/disneycareer", "Disney"), ("workday", "comcast.wd5/Comcast_Careers", "Comcast"),
    ("workday", "3m.wd1/Search", "3M"), ("workday", "boeing.wd1/EXTERNAL_CAREERS", "Boeing"),
    ("workday", "gm.wd5/Careers_GM", "General Motors"), ("workday", "walmart.wd5/WalmartExternal", "Walmart"),
    ("workday", "target.wd5/targetcareers", "Target"), ("workday", "pfizer.wd1/PfizerCareers", "Pfizer"),
    ("workday", "humana.wd5/Humana_External_Career_Site", "Humana"), ("workday", "cvshealth.wd1/CVS_Health_Careers", "CVS Health"),
    # banks / fintech on Workday
    ("workday", "capitalone.wd12/Capital_One", "Capital One"), ("workday", "mastercard.wd1/CorporateCareers", "Mastercard"),
    ("workday", "wellsfargo.wd1/WellsFargoJobs", "Wells Fargo"), ("workday", "citi.wd5/2", "Citi"),
    ("workday", "fmr.wd1/FidelityCareers", "Fidelity"),
    # SmartRecruiters
    ("smartrecruiters", "Visa", "Visa"), ("smartrecruiters", "ServiceNow", "ServiceNow"), ("smartrecruiters", "BoschGroup", "Bosch"),
    # more tech product companies (Greenhouse / Ashby / Lever)
    ("greenhouse", "rubrik", "Rubrik"), ("greenhouse", "purestorage", "Pure Storage"), ("greenhouse", "block", "Block (Square)"),
    ("greenhouse", "peloton", "Peloton"), ("greenhouse", "etsy", "Etsy"), ("greenhouse", "hubspotjobs", "HubSpot"),
    ("greenhouse", "zscaler", "Zscaler"), ("greenhouse", "nutanix", "Nutanix"), ("greenhouse", "sumologic", "Sumo Logic"),
    ("greenhouse", "launchdarkly", "LaunchDarkly"), ("greenhouse", "harness", "Harness"), ("greenhouse", "tanium", "Tanium"),
    ("greenhouse", "mozilla", "Mozilla"), ("greenhouse", "wikimedia", "Wikimedia"), ("greenhouse", "webflow", "Webflow"),
    ("ashby", "snowflake", "Snowflake"), ("ashby", "confluent", "Confluent"), ("ashby", "deel", "Deel"),
    ("ashby", "zapier", "Zapier"), ("ashby", "supabase", "Supabase"), ("ashby", "posthog", "PostHog"),
    ("ashby", "mercury", "Mercury"), ("ashby", "retool", "Retool"), ("ashby", "benchling", "Benchling"),
    ("lever", "netflix", "Netflix"), ("lever", "kraken123", "Kraken"), ("lever", "attentive", "Attentive"),
    # pack 3 (2026-11): more companies that hire DevOps / SRE / cloud / platform engineers.
    # A link that doesn't work is switched off automatically on the first collect.
    ("greenhouse", "spacex", "SpaceX"), ("greenhouse", "andurilindustries", "Anduril"), ("greenhouse", "waymo", "Waymo"),
    ("greenhouse", "fastly", "Fastly"), ("greenhouse", "cribl", "Cribl"), ("greenhouse", "digitalocean98", "DigitalOcean"),
    ("greenhouse", "coreweave", "CoreWeave"), ("greenhouse", "wizinc", "Wiz"), ("greenhouse", "sigmacomputing", "Sigma Computing"),
    ("greenhouse", "chronosphere", "Chronosphere"), ("greenhouse", "temporaltechnologies", "Temporal"),
    ("greenhouse", "circleci", "CircleCI"), ("greenhouse", "netlify", "Netlify"), ("greenhouse", "grammarly", "Grammarly"),
    ("greenhouse", "intercom", "Intercom"), ("greenhouse", "klaviyo", "Klaviyo"), ("greenhouse", "mixpanel", "Mixpanel"),
    ("greenhouse", "carta", "Carta"), ("greenhouse", "chainalysis", "Chainalysis"), ("greenhouse", "dataiku", "Dataiku"),
    ("greenhouse", "faire", "Faire"), ("greenhouse", "lattice", "Lattice"), ("greenhouse", "nuro", "Nuro"),
    ("greenhouse", "oscar", "Oscar Health"), ("greenhouse", "thumbtack", "Thumbtack"), ("greenhouse", "vimeo", "Vimeo"),
    ("greenhouse", "warbyparker", "Warby Parker"), ("greenhouse", "yext", "Yext"), ("greenhouse", "zocdoc", "Zocdoc"),
    ("greenhouse", "betterment", "Betterment"), ("greenhouse", "bitgo", "BitGo"), ("greenhouse", "calendly", "Calendly"),
    ("greenhouse", "doximity", "Doximity"), ("greenhouse", "gemini", "Gemini"), ("greenhouse", "justworks", "Justworks"),
    ("greenhouse", "marqeta", "Marqeta"), ("greenhouse", "nextdoor", "Nextdoor"), ("greenhouse", "opendoor", "Opendoor"),
    ("greenhouse", "outreach", "Outreach"), ("greenhouse", "pendo", "Pendo"), ("greenhouse", "seatgeek", "SeatGeek"),
    ("greenhouse", "verkada", "Verkada"), ("greenhouse", "zoominfo", "ZoomInfo"), ("greenhouse", "coupang", "Coupang"),
    ("greenhouse", "datavant", "Datavant"), ("greenhouse", "headspace", "Headspace"), ("greenhouse", "imc", "IMC Trading"),
    ("greenhouse", "point72", "Point72"), ("greenhouse", "twosigma", "Two Sigma"), ("greenhouse", "hudsonrivertrading", "Hudson River Trading"),
    ("greenhouse", "jumptrading", "Jump Trading"), ("greenhouse", "drweng", "DRW"), ("greenhouse", "affinity", "Affinity"),
    ("greenhouse", "appian", "Appian"), ("greenhouse", "braze", "Braze"), ("greenhouse", "c3iot", "C3 AI"),
    ("greenhouse", "clari", "Clari"), ("greenhouse", "collibra", "Collibra"), ("greenhouse", "contentful", "Contentful"),
    ("greenhouse", "dbtlabsinc", "dbt Labs"), ("greenhouse", "everbridge", "Everbridge"), ("greenhouse", "expensify", "Expensify"),
    ("greenhouse", "fanatics", "Fanatics"), ("greenhouse", "flatironhealth", "Flatiron Health"), ("greenhouse", "gofundme", "GoFundMe"),
    ("greenhouse", "hims", "Hims & Hers"), ("greenhouse", "iterable", "Iterable"), ("greenhouse", "jfrog", "JFrog"),
    ("greenhouse", "komodohealth", "Komodo Health"), ("greenhouse", "lucidsoftware", "Lucid Software"),
    ("greenhouse", "mavenclinic", "Maven Clinic"), ("greenhouse", "medallia", "Medallia"), ("greenhouse", "nium", "Nium"),
    ("greenhouse", "onepassword", "1Password"), ("greenhouse", "pagaya", "Pagaya"), ("greenhouse", "qualtrics", "Qualtrics"),
    ("greenhouse", "redcanary", "Red Canary"), ("greenhouse", "rokt", "Rokt"), ("greenhouse", "sentinellabs", "SentinelOne"),
    ("greenhouse", "sprinklr", "Sprinklr"), ("greenhouse", "stackadapt", "StackAdapt"), ("greenhouse", "tempus", "Tempus"),
    ("greenhouse", "thetradedesk", "The Trade Desk"), ("greenhouse", "upstart", "Upstart"), ("greenhouse", "via", "Via"),
    ("greenhouse", "wealthfront", "Wealthfront"), ("greenhouse", "xometry", "Xometry"), ("greenhouse", "zipline", "Zipline"),
    ("greenhouse", "clickhouse", "ClickHouse"), ("greenhouse", "planetscale", "PlanetScale"), ("greenhouse", "redis", "Redis"),
    ("greenhouse", "couchbaseinc", "Couchbase"), ("greenhouse", "yugabyte", "Yugabyte"), ("greenhouse", "starburst", "Starburst"),
    ("lever", "binance", "Binance"), ("lever", "wealthsimple", "Wealthsimple"), ("lever", "zoox", "Zoox"),
    ("lever", "mistral", "Mistral AI"), ("lever", "highspot", "Highspot"), ("lever", "eventbrite", "Eventbrite"),
    ("lever", "shieldai", "Shield AI"), ("lever", "whoop", "WHOOP"), ("lever", "veeva", "Veeva Systems"),
    ("ashby", "rippling", "Rippling"), ("ashby", "vanta", "Vanta"), ("ashby", "1password", "1Password"),
    ("ashby", "snyk", "Snyk"), ("ashby", "modal", "Modal"), ("ashby", "replit", "Replit"), ("ashby", "cohere", "Cohere"),
    ("ashby", "perplexity", "Perplexity"), ("ashby", "elevenlabs", "ElevenLabs"), ("ashby", "harvey", "Harvey"),
    ("ashby", "sierra", "Sierra"), ("ashby", "plaid", "Plaid"), ("ashby", "neon", "Neon"), ("ashby", "render", "Render"),
    ("ashby", "fly", "Fly.io"), ("ashby", "tailscale", "Tailscale"), ("ashby", "airbyte", "Airbyte"),
    ("workday", "jnj.wd5/JNJJobs", "Johnson & Johnson"), ("workday", "cisco.wd5/Cisco_Careers", "Cisco"),
    ("workday", "statestreet.wd1/Global", "State Street"), ("workday", "bankofamerica.wd1/BofA_Careers", "Bank of America"),
    ("workday", "usbank.wd1/US_Bank_Careers", "U.S. Bank"), ("workday", "pnc.wd5/External", "PNC"),
    ("workday", "truist.wd1/Careers", "Truist"), ("workday", "td.wd3/TD_Bank_Careers", "TD Bank"),
    ("workday", "geico.wd1/External", "GEICO"), ("workday", "travelers.wd5/External", "Travelers"),
    ("workday", "allstate.wd5/allstate_careers", "Allstate"), ("workday", "progressive.wd5/Progressive", "Progressive"),
    ("workday", "elevancehealth.wd1/ANT", "Elevance Health"), ("workday", "cigna.wd5/cignacareers", "Cigna"),
    ("workday", "unitedhealthgroup.wd5/External", "UnitedHealth Group"), ("workday", "kohls.wd1/kohlscareers", "Kohl's"),
    ("workday", "lowes.wd5/LWS_External_CS", "Lowe's"), ("workday", "homedepot.wd5/CareerDepot", "The Home Depot"),
    ("workday", "bestbuy.wd5/BestBuy", "Best Buy"), ("workday", "nike.wd1/nke", "Nike"),
    ("workday", "ford.wd1/Ford_External_Careers", "Ford"), ("workday", "stellantis.wd3/External_Career_Site_ID01", "Stellantis"),
    ("workday", "rivian.wd1/Careers", "Rivian"), ("workday", "lucid.wd5/External", "Lucid Motors"),
    ("workday", "verizon.wd12/verizon-careers", "Verizon"), ("workday", "tmobile.wd1/External", "T-Mobile"),
    ("workday", "att.wd1/ATTGeneral", "AT&T"), ("workday", "charter.wd5/Spectrum_Careers", "Charter / Spectrum"),
    ("workday", "accenture.wd103/AccentureCareers", "Accenture"), ("workday", "kpmg.wd1/KPMG_Careers", "KPMG US"),
    ("workday", "pwc.wd3/Global_Experienced_Careers", "PwC"), ("workday", "deloitte.wd1/US", "Deloitte US"),
    ("workday", "leidos.wd5/External", "Leidos"), ("workday", "boozallen.wd1/BAH_Jobs", "Booz Allen Hamilton"),
    ("workday", "gdit.wd5/External_Career_Site", "GDIT"), ("workday", "caci.wd1/External", "CACI"),
    ("workday", "snapchat.wd1/snap", "Snap"), ("workday", "ebay.wd5/apply", "eBay"), ("workday", "intuit.wd1/Intuit", "Intuit"),
    ("workday", "vmware.wd1/VMware", "VMware"), ("workday", "netapp.wd1/NetApp_Careers", "NetApp"),
    ("workday", "equinix.wd1/External", "Equinix"), ("workday", "kla.wd1/Search", "KLA"),
    ("workday", "amd.wd1/External", "AMD"), ("workday", "qualcomm.wd5/External", "Qualcomm"),
    ("workday", "micron.wd1/External", "Micron"), ("workday", "western-digital.wd1/WesternDigitalCareers", "Western Digital"),
    ("workday", "fiserv.wd5/EXT", "Fiserv"), ("workday", "globalpayments.wd1/Global_Payments_Careers", "Global Payments"),
    ("workday", "fis.wd5/SearchJobs", "FIS"), ("workday", "spglobal.wd5/SPGI_Careers", "S&P Global"),
    ("workday", "blackrock.wd1/BlackRock_Professional", "BlackRock"), ("workday", "ms.wd5/External", "Morgan Stanley"),
    ("workday", "dowjones.wd1/Dow_Jones_Career", "Dow Jones"), ("workday", "warnerbros.wd5/global", "Warner Bros. Discovery"),
    ("workday", "kelloggs.wd1/Kellanova", "Kellanova"), ("workday", "generalmills.wd5/Careers", "General Mills"),
    ("workday", "dowjones.wd1/Dow_Jones_Career", "Dow Jones"),
    # Oracle Cloud career sites (host/siteNumber)
    ("oracle", "jpmc.fa.oraclecloud.com/CX_1001", "JPMorgan Chase"), ("oracle", "eeho.fa.us2.oraclecloud.com/CX_45001", "Oracle"),
    # SmartRecruiters
    ("smartrecruiters", "Experian", "Experian"), ("smartrecruiters", "Wipro", "Wipro"), ("smartrecruiters", "Equinox", "Equinox"),
    ("smartrecruiters", "LinkedIn3", "LinkedIn"), ("smartrecruiters", "Square", "Square"), ("smartrecruiters", "Ubisoft2", "Ubisoft"),
    ("smartrecruiters", "Sanofi", "Sanofi"), ("smartrecruiters", "Avanade", "Avanade"), ("smartrecruiters", "Publicis Groupe", "Publicis Sapient"),
]
FEEDS = {"jooble": "Jooble", "jsearch": "JSearch", "usajobs": "USAJOBS", "reed": "Reed (UK)",
         "arbeitsagentur": "Arbeitsagentur (DE)", "jobtech": "Arbetsförmedlingen (SE)", "francetravail": "France Travail (FR)",
         "findwork": "Findwork", "himalayas": "Himalayas", "wwr": "We Work Remotely", "remotive": "Remotive", "themuse": "The Muse",
         "arbeitnow": "Arbeitnow", "remoteok": "Remote OK", "jobicy": "Jobicy"}
KEY_FEEDS = {"jooble": ("jooble_key",), "jsearch": ("rapidapi_key",), "usajobs": ("usajobs_key", "usajobs_email"),
             "reed": ("reed_key",), "francetravail": ("ft_id", "ft_secret"), "findwork": ("findwork_key",)}
COUNTRY_FEEDS = {"usajobs": "United States", "reed": "United Kingdom", "arbeitsagentur": "Germany",
                 "jobtech": "Sweden", "francetravail": "France"}   # official job boards of one country   # optional free keys
JSEARCH_TERMS = 3   # free plan = 200 searches a month, so only the top 3 roles, 1 page each (about 90 a month)   # need a free API key
SNIPPET_SOURCES = {"Jooble", "Reed"}
TITLE_ONLY_OK = {"Arbeitsagentur"}   # official board; if its JD can't be read, the title decides   # these give a short JD; the full JD comes when you open the job with J
MIN_MATCH = 30   # a collected job must share at least this % of its skills with the resume


# ---------------------------------------------------------------- database
def init():
    db.init_db()   # creates the 'sources' table and the profile 'locations' column


def boards():
    with db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM sources ORDER BY name COLLATE NOCASE")]


def add_board(provider, token, name=""):
    if not name and provider == "bullhorn":              # "33/abc|https://jobs.agency.com" -> "Jobs.Agency.Com"
        site = token.partition("|")[2]
        name = re.sub(r"^https?://(www\.|jobs\.|careers\.)?", "", site).split("/")[0].split(".")[0].title() or "Agency"
    with db.connect() as con:
        con.execute("INSERT OR IGNORE INTO sources(provider, token, name) VALUES(?,?,?)",
                    (provider, token, name or token.replace("-", " ").title()))


def update_board(bid, active=None, name=None):
    with db.connect() as con:
        if active is not None:
            con.execute("UPDATE sources SET active=? WHERE id=?", (1 if active else 0, bid))
        if name:
            con.execute("UPDATE sources SET name=? WHERE id=?", (name, bid))


def remove_board(bid):
    with db.connect() as con:
        con.execute("DELETE FROM sources WHERE id=?", (bid,))


def _board_status(bid, status):
    with db.connect() as con:
        con.execute("UPDATE sources SET last_checked=?, last_status=? WHERE id=?", (db.now(), status, bid))


# ---------------------------------------------------------------- recognise a careers link
PATTERNS = [
    ("greenhouse", r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)"),
    ("greenhouse", r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)"),
    ("greenhouse", r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)"),
    ("lever", r"jobs(?:\.eu)?\.lever\.co/([A-Za-z0-9_.-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
    ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    ("workable", r"apply\.workable\.com/(?:api/v\d/widget/accounts/)?([A-Za-z0-9_-]+)"),
    ("workday", r"([a-z0-9-]+\.wd\d+)\.myworkdayjobs\.com/(?:wday/cxs/[a-z0-9-]+/)?(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)"),
    ("bullhorn", r"public-rest(\d+)\.bullhornstaffing\.com(?::443)?/rest-services/([A-Za-z0-9]+)"),
    ("recruitee", r"([a-z0-9-]+)\.recruitee\.com"),
    ("bamboohr", r"([a-z0-9-]+)\.bamboohr\.com"),
    ("breezy", r"([a-z0-9-]+)\.breezy\.hr"),
    ("oracle", r"([a-z0-9-]+\.fa(?:\.[a-z0-9]+)?\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z-]+/sites/([A-Za-z0-9_]+)"),
]
_SKIP_TOKENS = {"embed", "jobs", "v1", "api", "job_board", "js", "www", "app", "help", "marketing"}


def parse_board(text):
    for provider, pat in PATTERNS:
        m = re.search(pat, text or "", re.I)
        if m and m.group(1).lower() not in _SKIP_TOKENS:
            if provider == "workday":                       # token = "tenant.wd5/Site"
                return provider, f"{m.group(1).lower()}/{m.group(2)}"
            if provider == "oracle":                        # token = "host/CX_1001"
                return provider, f"{m.group(1).lower()}/{m.group(2)}"
            if provider == "bullhorn":                      # token = "33/corpToken"
                return provider, f"{m.group(1)}/{m.group(2)}"
            return provider, m.group(1)
    return None


def discover(url):
    """Find the career board behind any careers page link. Returns (provider, token) or None."""
    url = (url or "").strip()
    hit = parse_board(url)
    if hit:
        return hit
    if not url.startswith("http"):
        url = "https://" + url
    r = requests.get(url, headers=UA, timeout=20)
    hit = parse_board(r.text)
    if hit:
        return hit
    from urllib.parse import urlparse
    root = "{0.scheme}://{0.netloc}".format(urlparse(r.url or url))
    try:                                                     # Bullhorn career portal (most staffing agencies)
        cfg = requests.get(f"{root}/app.json", headers=UA, timeout=15).json().get("service") or {}
        if cfg.get("corpToken") and cfg.get("swimlane"):
            return "bullhorn", f"{cfg['swimlane']}/{cfg['corpToken']}|{root}"
    except (ValueError, requests.RequestException, AttributeError):
        pass
    return None


# ---------------------------------------------------------------- helpers
def _text(html_str):
    t = html.unescape(html_str or "")
    t = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", "\n", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", t)).strip()


def _when(value):
    """Turn the many date formats into a UTC datetime (or None)."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / (1000 if value > 1e11 else 1), tz=timezone.utc)
        v = str(value).strip().replace("Z", "+00:00")
        v = re.sub(r"(\.\d{6})\d+", r"\1", v)          # "…00.0000000" -> 6 digits
        d = datetime.fromisoformat(v)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def _get(url, **kw):
    for attempt in range(2):
        r = requests.get(url, headers=UA, timeout=25, **kw)
        if r.status_code == 429 and attempt == 0:
            time.sleep(min(float(r.headers.get("retry-after") or 10), 60))
            continue
        return r
    return r


# ---------------------------------------------------------------- fetchers (each returns a list of jobs)
def fetch_greenhouse(token, name):
    r = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"})
    if r.status_code == 404:
        raise LookupError("board not found")
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({"company": name, "title": j.get("title", ""), "location": (j.get("location") or {}).get("name", ""),
                    "url": j.get("absolute_url", ""), "jd": _text(j.get("content")),
                    "posted": _when(j.get("first_published") or j.get("updated_at"))})
    return out


def fetch_lever(token, name):
    r = None
    for base in ("https://api.lever.co", "https://api.eu.lever.co"):
        r = _get(f"{base}/v0/postings/{token}", params={"mode": "json"})
        if r.status_code != 404:
            break
    if r.status_code == 404:
        raise LookupError("board not found")
    r.raise_for_status()
    out = []
    for j in r.json():
        parts = [j.get("descriptionPlain") or _text(j.get("description"))]
        for lst in j.get("lists") or []:
            parts.append(f"{lst.get('text', '')}\n{_text(lst.get('content'))}")
        parts.append(j.get("additionalPlain") or "")
        cat = j.get("categories") or {}
        loc = cat.get("location") or ""
        if (j.get("workplaceType") or "").lower() == "remote" and "remote" not in loc.lower():
            loc = f"{loc} (Remote)".strip()
        out.append({"company": name, "title": j.get("text", ""), "location": loc, "url": j.get("hostedUrl", ""),
                    "jd": "\n\n".join(p for p in parts if p).strip(), "posted": _when(j.get("createdAt"))})
    return out


def fetch_ashby(token, name):
    r = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    if r.status_code == 404:
        raise LookupError("board not found")
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        if j.get("isListed") is False:
            continue
        loc = j.get("location") or ""
        if j.get("isRemote") and "remote" not in loc.lower():
            loc = f"{loc} (Remote)".strip()
        out.append({"company": name, "title": j.get("title", ""), "location": loc,
                    "url": j.get("jobUrl") or j.get("applyUrl", ""),
                    "jd": j.get("descriptionPlain") or _text(j.get("descriptionHtml")),
                    "posted": _when(j.get("publishedAt"))})
    return out


def fetch_smartrecruiters(token, name):
    r = _get(f"https://api.smartrecruiters.com/v1/companies/{token}/postings", params={"limit": 100})
    if r.status_code == 404:
        raise LookupError("board not found")
    r.raise_for_status()
    out = []
    for j in r.json().get("content", []):
        loc = j.get("location") or {}
        place = ", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x)
        if loc.get("remote") and "remote" not in place.lower():
            place = f"{place} (Remote)".strip()
        out.append({"company": (j.get("company") or {}).get("name") or name, "title": j.get("name", ""),
                    "location": place, "url": f"https://jobs.smartrecruiters.com/{token}/{j.get('id')}",
                    "jd": None, "posted": _when(j.get("releasedDate")),
                    "_detail": f"https://api.smartrecruiters.com/v1/companies/{token}/postings/{j.get('id')}"})
    return out


def fetch_workable(token, name):
    """Workable company page (apply.workable.com/<company>): free, no key."""
    r = _get(f"https://apply.workable.com/api/v1/widget/accounts/{token}", params={"details": "true"})
    if r.status_code == 404:
        raise LookupError("board not found")
    r.raise_for_status()
    data = r.json()
    out = []
    for j in data.get("jobs", []):
        place = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
        if j.get("telecommuting"):
            place = f"{place} (Remote)".strip()
        out.append({"company": data.get("name") or name, "title": j.get("title", ""), "location": place,
                    "url": j.get("url") or j.get("shortlink") or f"https://apply.workable.com/{token}/j/{j.get('shortcode')}",
                    "jd": _text(j.get("description")), "posted": _when(j.get("published_on") or j.get("created_at")),
                    "source": "Workable"})
    return out


def _search_terms(n=4):
    """Main roles of every profile, in order (used to search big company sites)."""
    return list(dict.fromkeys(r for p in db.profiles() for r in db.roles_for_search(p)[:n]))


def _workday_parts(token):
    host_part, site = token.split("/", 1)                 # "acme.wd5", "External"
    return f"https://{host_part}.myworkdayjobs.com", host_part.split(".")[0], site


def fetch_workday(token, name):
    """Workday company page (<company>.wd5.myworkdayjobs.com/<site>): free, no key.
    Big companies have thousands of jobs, so it searches only the resume roles."""
    base, tenant, site = _workday_parts(token)
    api = f"{base}/wday/cxs/{tenant}/{site}"
    now = datetime.now(timezone.utc)
    out, seen = [], set()
    for term in _search_terms():
        r = requests.post(f"{api}/jobs", headers={**UA, "Content-Type": "application/json"}, timeout=25,
                          json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": term})
        if r.status_code in (404, 422):
            raise LookupError("board not found")
        r.raise_for_status()
        for j in r.json().get("jobPostings", []):
            when = (j.get("postedOn") or "").lower()
            days = re.search(r"(\d+)\+? days? ago", when)
            if "today" in when:
                posted = now - timedelta(hours=1)
            elif "yesterday" in when:
                posted = now - timedelta(hours=23)
            elif days and "+" not in when:
                posted = now - timedelta(days=int(days.group(1)))
            else:
                continue                                  # "Posted 30+ Days Ago"
            path = j.get("externalPath") or ""
            if path in seen:
                continue
            seen.add(path)
            out.append({"company": name, "title": j.get("title", ""), "location": j.get("locationsText", ""),
                        "url": f"{base}/en-US/{site}{path}", "jd": None, "posted": posted, "source": "Workday",
                        "_detail": f"{api}{path}", "_kind": "workday"})
        time.sleep(PAUSE)
    return out


def _workday_jd(detail_url):
    r = _get(detail_url)
    if not r.ok:
        return ""
    info = r.json().get("jobPostingInfo") or {}
    return _text(info.get("jobDescription"))


def _all_roles():
    return [r for p in db.profiles() for r in db.roles_for_search(p)]


def _role_fits(title):
    """Cheap first check, so we only download the JD of jobs that may fit a profile."""
    roles = _all_roles()
    return bool(roles) and bool(matching.title_fit(title or "", roles))


def fetch_bullhorn(token, name):
    """Bullhorn public job board: used by most staffing / recruiting agencies. Free, no key.
    token = "<swimlane>/<corpToken>" or "<swimlane>/<corpToken>|<career site>"."""
    ids, _, site = token.partition("|")
    lane, corp = ids.split("/", 1)
    base = f"https://public-rest{lane}.bullhornstaffing.com/rest-services/{corp}"
    r = _get(f"{base}/search/JobOrder", params={
        "query": "(isOpen:1) AND (isDeleted:0)", "count": 200, "start": 0, "sort": "-dateLastPublished",
        "fields": "id,title,publishedCategory(id,name),address(city,state,countryCode),employmentType,"
                  "dateLastPublished,publicDescription,isOpen,isPublic,isDeleted"})
    if r.status_code in (401, 404):
        raise LookupError("board not found")
    r.raise_for_status()
    out = []
    for j in r.json().get("data", []):
        if j.get("isPublic") == 0:
            continue
        a = j.get("address") or {}
        place = ", ".join(x for x in (a.get("city"), a.get("state"), a.get("countryCode")) if x)
        url = f"{site}/#/jobs/{j.get('id')}" if site else f"{base}/jobs/{j.get('id')}"
        out.append({"company": name, "title": j.get("title", ""), "location": place, "url": url,
                    "jd": _text(j.get("publicDescription")), "posted": _when(j.get("dateLastPublished")),
                    "source": "Bullhorn"})
    return out


def fetch_recruitee(token, name):
    """Recruitee careers site (<company>.recruitee.com): free, no key."""
    r = _get(f"https://{token}.recruitee.com/api/offers/")
    if r.status_code == 404:
        raise LookupError("board not found")
    r.raise_for_status()
    out = []
    for j in r.json().get("offers", []):
        place = j.get("location") or ", ".join(x for x in (j.get("city"), j.get("state_code") or j.get("state_name"),
                                                            j.get("country_code")) if x)
        if j.get("remote") and "remote" not in place.lower():
            place = f"{place} (Remote)".strip()
        out.append({"company": j.get("company_name") or name, "title": j.get("title", ""), "location": place,
                    "url": j.get("careers_url") or j.get("careers_apply_url", ""),
                    "jd": _text((j.get("description") or "") + "\n" + (j.get("requirements") or "")),
                    "posted": _when(j.get("published_at") or j.get("created_at")), "source": "Recruitee"})
    return out


def fetch_bamboohr(token, name):
    """BambooHR careers page (<company>.bamboohr.com/careers): free, no key.
    The list has no dates, so the JD and posting date are read only for jobs whose title fits."""
    r = _get(f"https://{token}.bamboohr.com/careers/list")
    if r.status_code == 404:
        raise LookupError("board not found")
    r.raise_for_status()
    out = []
    for j in r.json().get("result", []):
        title = j.get("jobOpeningName", "")
        if not _role_fits(title):
            continue
        d = _get(f"https://{token}.bamboohr.com/careers/{j.get('id')}/detail")
        info = ((d.json().get("result") or {}).get("jobOpening") or {}) if d.ok else {}
        loc = j.get("location") or info.get("location") or {}
        place = ", ".join(x for x in (loc.get("city"), loc.get("state"), loc.get("addressCountry")) if x)
        if j.get("isRemote") or info.get("isRemote"):
            place = f"{place} (Remote)".strip()
        out.append({"company": name, "title": title, "location": place,
                    "url": f"https://{token}.bamboohr.com/careers/{j.get('id')}",
                    "jd": _text(info.get("description")), "posted": _when(info.get("datePosted")), "source": "BambooHR"})
        time.sleep(PAUSE)
    return out


def fetch_breezy(token, name):
    """Breezy HR careers site (<company>.breezy.hr): free, no key. JD read only for jobs whose title fits."""
    r = _get(f"https://{token}.breezy.hr/json")
    if r.status_code == 404:
        raise LookupError("board not found")
    r.raise_for_status()
    out = []
    for j in r.json():
        loc = j.get("location") or {}
        state = loc.get("state") or {}
        place = loc.get("name") or ", ".join(x for x in (loc.get("city"), state.get("id") if isinstance(state, dict) else state,
                                                          (loc.get("country") or {}).get("id") if isinstance(loc.get("country"), dict) else loc.get("country")) if x)
        if loc.get("is_remote") and "remote" not in (place or "").lower():
            place = f"{place} (Remote)".strip()
        out.append({"company": (j.get("company") or {}).get("name") or name, "title": j.get("name", ""),
                    "location": place, "url": j.get("url", ""), "jd": None,
                    "posted": _when(j.get("published_date")), "source": "Breezy HR",
                    "_detail": j.get("url", ""), "_kind": "breezy"})
    return out


def _breezy_jd(page_url):
    r = _get(page_url)
    if not r.ok:
        return ""
    m = re.search(r'<div class="description">(.*?)</div>\s*</div>', r.text, re.S)
    return _text(m.group(1) if m else "")


_COUNTRIES_NOW = ["United States"]   # set by run(): the countries the profiles want


def fetch_amazon(token, name):
    """amazon.jobs public search (the JSON the site itself uses). Free, no key."""
    out, seen = [], set()
    for term, country in [(t, c) for c in _COUNTRIES_NOW for t in _search_terms()]:
        r = _get("https://www.amazon.jobs/en/search.json",
                 params={"base_query": term, "country": COUNTRIES[country][1], "sort": "recent", "result_limit": 50, "offset": 0})
        if r.status_code == 404:
            raise LookupError("board not found")
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            path = j.get("job_path") or ""
            if path in seen:
                continue
            seen.add(path)
            try:
                posted = datetime.strptime(j.get("posted_date", ""), "%B %d, %Y").replace(tzinfo=timezone.utc) + timedelta(hours=12)
            except ValueError:
                posted = None
            jd = "\n\n".join(_text(j.get(k)) for k in ("description", "basic_qualifications", "preferred_qualifications") if j.get(k))
            out.append({"company": j.get("company_name") or "Amazon", "title": j.get("title", ""),
                        "location": j.get("normalized_location") or j.get("location") or "",
                        "url": f"https://www.amazon.jobs{path}", "jd": jd, "posted": posted, "source": "Amazon Jobs"})
        time.sleep(PAUSE)
    return out


def fetch_microsoft(token, name):
    """Microsoft careers public search (the JSON the site itself uses). Free, no key."""
    out, seen = [], set()
    for term, country in [(t, c) for c in _COUNTRIES_NOW for t in _search_terms()]:
        r = _get("https://gcsservices.careers.microsoft.com/search/api/v1/search",
                 params={"q": term, "lc": country, "l": "en_us", "pg": 1, "pgSz": 20, "o": "Recent", "flt": "true"})
        if r.status_code == 404:
            raise LookupError("board not found")
        r.raise_for_status()
        for j in ((r.json().get("operationResult") or {}).get("result") or {}).get("jobs") or []:
            jid = j.get("jobId")
            if jid in seen:
                continue
            seen.add(jid)
            props = j.get("properties") or {}
            jd = "\n\n".join(_text(props.get(k)) for k in ("description", "qualifications", "responsibilities") if props.get(k))
            out.append({"company": "Microsoft", "title": j.get("title", ""),
                        "location": props.get("primaryLocation") or "; ".join(props.get("locations") or []),
                        "url": f"https://jobs.careers.microsoft.com/global/en/job/{jid}", "jd": jd,
                        "posted": _when(j.get("postingDate")), "source": "Microsoft Careers"})
        time.sleep(PAUSE)
    return out


def fetch_oracle(token, name):
    """Oracle Cloud HCM career site (<host>.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001):
    the public JSON the career site itself uses. Free, no key. Used by JPMorgan Chase, Oracle and others."""
    host, site = token.split("/", 1)
    api = f"https://{host}/hcmRestApi/resources/latest"
    out, seen = [], set()
    for term in _search_terms():
        finder = (f'findReqs;siteNumber={site},facetsList=LOCATIONS;POSTING_DATES,limit=25,'
                  f'keyword="{term}",sortBy=POSTING_DATES_DESC')
        r = _get(f"{api}/recruitingCEJobRequisitions", params={"onlyData": "true", "expand": "requisitionList", "finder": finder})
        if r.status_code in (400, 404):
            raise LookupError("board not found")
        r.raise_for_status()
        for item in r.json().get("items") or []:
            for j in item.get("requisitionList") or []:
                jid = str(j.get("Id") or "")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                out.append({"company": name, "title": j.get("Title", ""),
                            "location": j.get("PrimaryLocation") or j.get("PrimaryLocationCountry") or "",
                            "url": f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{jid}",
                            "jd": None, "posted": _when(j.get("PostedDate")), "source": "Oracle Cloud",
                            "_detail": f"{api}/recruitingCEJobRequisitionDetails?onlyData=true&expand=all"
                                       f'&finder=ById;Id="{jid}",siteNumber={site}', "_kind": "oracle"})
        time.sleep(PAUSE)
    return out


def _oracle_jd(detail_url):
    r = _get(detail_url)
    if not r.ok:
        return ""
    items = r.json().get("items") or [{}]
    d = items[0] if items else {}
    return "\n\n".join(_text(d.get(k)) for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr",
                                                  "ExternalQualificationsStr") if d.get(k)).strip()


def fetch_usajobs(search_terms):
    """USAJOBS (US government jobs): free official API, key at developer.usajobs.gov (your email + key)."""
    headers = {"Host": "data.usajobs.gov", "User-Agent": db.setting("usajobs_email"),
               "Authorization-Key": db.setting("usajobs_key")}
    days = max(1, min(60, int(-(-window_hours() // 24))))
    out, seen = [], set()
    for term in search_terms:
        r = requests.get("https://data.usajobs.gov/api/search", headers=headers, timeout=30,
                         params={"Keyword": term, "DatePosted": days, "ResultsPerPage": 100, "SortField": "opendate"})
        if r.status_code in (401, 403):
            raise RuntimeError("API key not accepted: check the USAJOBS email and key")
        if not r.ok:
            continue
        for it in ((r.json().get("SearchResult") or {}).get("SearchResultItems") or []):
            d = it.get("MatchedObjectDescriptor") or {}
            url = d.get("PositionURI") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            det = (d.get("UserArea") or {}).get("Details") or {}
            jd = "\n\n".join(x for x in (det.get("JobSummary"), d.get("QualificationSummary"),
                                         "\n".join(det.get("MajorDuties") or [])) if x)
            out.append({"company": d.get("OrganizationName") or d.get("DepartmentName") or "US Government",
                        "title": d.get("PositionTitle", ""), "location": (d.get("PositionLocationDisplay") or "") + ", US",
                        "url": url, "jd": jd, "posted": _when(d.get("PublicationStartDate")), "source": "USAJOBS"})
        time.sleep(PAUSE)
    return out


def _recent_days():
    return max(1, int(-(-window_hours() // 24)))


def fetch_reed(search_terms):
    """Reed.co.uk (UK's biggest job board): official free API key at reed.co.uk/developers/jobseeker."""
    auth = (db.setting("reed_key"), "")
    out, seen = [], set()
    now = datetime.now(timezone.utc)
    for term in search_terms:
        r = requests.get("https://www.reed.co.uk/api/1.0/search", auth=auth, headers=UA, timeout=30,
                         params={"keywords": term, "resultsToTake": 100})
        if r.status_code in (401, 403):
            raise RuntimeError("API key not accepted: check the Reed key")
        if not r.ok:
            continue
        for j in r.json().get("results") or []:
            jid = j.get("jobId")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            posted = None
            m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(j.get("date") or ""))
            if m:                                             # "30/10/2026": the day only, so count it as noon
                posted = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 12, tzinfo=timezone.utc)
                if posted > now:
                    posted = now
            out.append({"company": j.get("employerName", ""), "title": j.get("jobTitle", ""),
                        "location": f"{j.get('locationName') or ''}, United Kingdom",
                        "url": j.get("jobUrl") or f"https://www.reed.co.uk/jobs/{jid}", "jd": None,
                        "posted": posted or now - timedelta(hours=1), "source": "Reed",
                        "_detail": f"https://www.reed.co.uk/api/1.0/jobs/{jid}", "_kind": "reed",
                        "_snippet": _text(j.get("jobDescription"))})
        time.sleep(PAUSE)
    return out


def _reed_jd(detail_url):
    r = requests.get(detail_url, auth=(db.setting("reed_key"), ""), headers=UA, timeout=25)
    return _text(r.json().get("jobDescription")) if r.ok else ""


def fetch_arbeitsagentur(search_terms):
    """Bundesagentur für Arbeit (Germany's official job board, 1M+ jobs): free, the key is public."""
    headers = {**UA, "X-API-Key": "jobboerse-jobsuche"}
    out, seen = [], set()
    for term in search_terms:
        r = requests.get("https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs", headers=headers,
                         timeout=30, params={"was": term, "veroeffentlichtseit": min(100, _recent_days()),
                                             "size": 100, "page": 1, "angebotsart": 1})
        if not r.ok:
            continue
        for j in r.json().get("stellenangebote") or []:
            ref = j.get("refnr") or j.get("referenznummer")
            if not ref or ref in seen:
                continue
            seen.add(ref)
            place = j.get("arbeitsort") or {}
            out.append({"company": j.get("arbeitgeber", ""), "title": j.get("titel") or j.get("beruf") or "",
                        "location": ", ".join(x for x in (place.get("ort"), place.get("region"), place.get("land") or "Germany") if x),
                        "url": j.get("externeUrl") or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}",
                        "jd": None, "posted": _when(j.get("aktuelleVeroeffentlichungsdatum") or j.get("modifikationsTimestamp")),
                        "source": "Arbeitsagentur", "_kind": "arbeitsagentur",
                        "_detail": "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/" +
                                   __import__("base64").b64encode(ref.encode()).decode()})
        time.sleep(PAUSE)
    return out


def _arbeitsagentur_jd(detail_url):
    try:
        r = requests.get(detail_url, headers={**UA, "X-API-Key": "jobboerse-jobsuche"}, timeout=25)
        return _text(r.json().get("stellenangebotsBeschreibung")) if r.ok else ""
    except (requests.RequestException, ValueError):
        return ""


def fetch_jobtech(search_terms):
    """Arbetsförmedlingen / JobTech (Sweden's official job board): free, no key."""
    after = (datetime.now() - timedelta(hours=window_hours())).strftime("%Y-%m-%dT%H:%M:%S")
    out, seen = [], set()
    for term in search_terms:
        r = requests.get("https://jobsearch.api.jobtechdev.se/search", headers={**UA, "accept": "application/json"},
                         timeout=30, params={"q": term, "published-after": after, "limit": 100})
        if not r.ok:
            continue
        for j in r.json().get("hits") or []:
            if j.get("id") in seen:
                continue
            seen.add(j.get("id"))
            addr = j.get("workplace_address") or {}
            out.append({"company": (j.get("employer") or {}).get("name", ""), "title": j.get("headline", ""),
                        "location": ", ".join(x for x in (addr.get("municipality"), addr.get("region"), addr.get("country") or "Sweden") if x),
                        "url": (j.get("application_details") or {}).get("url") or j.get("webpage_url") or "",
                        "jd": (j.get("description") or {}).get("text") or "", "posted": _when(j.get("publication_date")),
                        "source": "Arbetsförmedlingen"})
        time.sleep(PAUSE)
    return out


_FT_TOKEN = {"value": None, "until": 0}


def _francetravail_token():
    if _FT_TOKEN["value"] and time.time() < _FT_TOKEN["until"]:
        return _FT_TOKEN["value"]
    r = requests.post("https://entreprise.francetravail.fr/connexion/oauth2/access_token", params={"realm": "/partenaire"},
                      data={"grant_type": "client_credentials", "client_id": db.setting("ft_id"),
                            "client_secret": db.setting("ft_secret"), "scope": "api_offresdemploiv2 o2dsoffre"}, timeout=25)
    if not r.ok:
        raise RuntimeError("France Travail: client id / secret not accepted")
    d = r.json()
    _FT_TOKEN.update(value=d["access_token"], until=time.time() + int(d.get("expires_in", 1400)) - 60)
    return _FT_TOKEN["value"]


def fetch_francetravail(search_terms):
    """France Travail (France's official job board): free id + secret at francetravail.io."""
    days = next((d for d in (1, 3, 7, 14, 31) if d >= _recent_days()), 31)
    out, seen = [], set()
    for term in search_terms:
        r = requests.get("https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search", timeout=30,
                         headers={**UA, "Authorization": f"Bearer {_francetravail_token()}", "Accept": "application/json"},
                         params={"motsCles": term, "publieeDepuis": days, "range": "0-149"})
        if r.status_code == 204 or not r.ok:
            continue
        for j in r.json().get("resultats") or []:
            if j.get("id") in seen:
                continue
            seen.add(j.get("id"))
            out.append({"company": (j.get("entreprise") or {}).get("nom", ""), "title": j.get("intitule", ""),
                        "location": f"{(j.get('lieuTravail') or {}).get('libelle', '')}, France",
                        "url": (j.get("origineOffre") or {}).get("urlOrigine") or
                               f"https://candidat.francetravail.fr/offres/recherche/detail/{j.get('id')}",
                        "jd": j.get("description") or "", "posted": _when(j.get("dateCreation")), "source": "France Travail"})
        time.sleep(PAUSE)
    return out


def fetch_findwork(search_terms):
    """Findwork.dev (software / DevOps jobs, mostly US + Europe + remote): free key at findwork.dev."""
    headers = {**UA, "Authorization": f"Token {db.setting('findwork_key')}"}
    out, seen = [], set()
    for term in search_terms:
        r = requests.get("https://findwork.dev/api/jobs/", headers=headers, timeout=30,
                         params={"search": term, "sort_by": "date"})
        if r.status_code in (401, 403):
            raise RuntimeError("API key not accepted: check the Findwork key")
        if not r.ok:
            continue
        for j in r.json().get("results") or []:
            if j.get("url") in seen:
                continue
            seen.add(j.get("url"))
            loc = j.get("location") or ""
            out.append({"company": j.get("company_name", ""), "title": j.get("role", ""),
                        "location": (loc + (" (Remote)" if j.get("remote") else "")).strip() or ("Remote" if j.get("remote") else ""),
                        "url": j.get("url", ""), "jd": _text(j.get("text")), "posted": _when(j.get("date_posted")),
                        "source": "Findwork"})
        time.sleep(PAUSE)
    return out


def _smartrecruiters_jd(detail_url):
    r = _get(detail_url)
    if not r.ok:
        return ""
    sec = (r.json().get("jobAd") or {}).get("sections") or {}
    return "\n\n".join(_text((sec.get(k) or {}).get("text")) for k in
                       ("jobDescription", "qualifications", "additionalInformation", "companyDescription")).strip()


JOOBLE_SITE = {"gb": "uk"}      # Jooble's country sites: in.jooble.org, uk.jooble.org, de.jooble.org …


def fetch_jooble(search_terms, location="United States"):
    """Jooble: free API (jooble.org/api/about). Searches the job boards of the country.
    Outside the US it uses that country's Jooble site, and falls back to jooble.org."""
    key = db.setting("jooble_key")
    iso2 = COUNTRIES.get(location, ("us",))[0]
    hosts = ["jooble.org"] if iso2 == "us" else [f"{JOOBLE_SITE.get(iso2, iso2)}.jooble.org", "jooble.org"]
    out, seen = [], set()
    day = (datetime.now(timezone.utc) - timedelta(hours=window_hours())).strftime("%Y-%m-%d")
    for term in search_terms:
        for host in hosts:
            try:
                r = requests.post(f"https://{host}/api/{key}", headers=UA, timeout=25,
                                  json={"keywords": term, "location": "" if host != "jooble.org" else location,
                                        "datecreatedfrom": day, "ResultOnPage": 50})
            except requests.RequestException:
                continue
            if r.status_code in (401, 403) and host == hosts[-1]:
                raise RuntimeError("API key not accepted: check the Jooble key")
            if r.ok:
                break
        else:
            continue
        if not r.ok:
            continue
        for j in r.json().get("jobs", []):
            url = j.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            loc = j.get("location") or ""
            out.append({"company": j.get("company", ""), "title": _text(j.get("title")),
                        "location": f"{loc}, {location}" if loc else location, "url": url, "jd": _text(j.get("snippet")),
                        "posted": _when(j.get("updated")), "source": "Jooble"})
        time.sleep(PAUSE)
    return out


def fetch_jsearch(search_terms, country="us", where="USA"):
    """JSearch on RapidAPI (free plan: 200 searches/month). Reads Google for Jobs, so it includes
    LinkedIn, Indeed, ZipRecruiter, Dice and company sites, with the full JD."""
    headers = {**UA, "X-RapidAPI-Key": db.setting("rapidapi_key"), "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
    out, seen = [], set()
    for term in search_terms[:JSEARCH_TERMS]:
        r = requests.get("https://jsearch.p.rapidapi.com/search", headers=headers, timeout=30,
                         params={"query": f"{term} in {where}", "date_posted": "today" if window_hours() <= 24 else "3days" if window_hours() <= 72 else
                                               "week" if window_hours() <= 168 else "month", "country": country,
                                 "page": 1, "num_pages": 1})
        if r.status_code in (401, 403):
            raise RuntimeError("API key not accepted: check the RapidAPI key and that you subscribed to JSearch (free plan)")
        if r.status_code == 429:
            raise RuntimeError("JSearch free limit used up for this month")
        if not r.ok:
            continue
        for j in r.json().get("data") or []:
            url = j.get("job_apply_link") or j.get("job_google_link") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            place = ", ".join(x for x in (j.get("job_city"), j.get("job_state"), j.get("job_country")) if x)
            if j.get("job_is_remote"):
                place = f"{place} (Remote)".strip()
            out.append({"company": j.get("employer_name", ""), "title": j.get("job_title", ""),
                        "location": place or "United States", "url": url, "jd": _text(j.get("job_description")),
                        "posted": _when(j.get("job_posted_at_datetime_utc") or j.get("job_posted_at_timestamp")),
                        "source": "JSearch"})
        time.sleep(PAUSE)
    return out


def fetch_himalayas(search_terms, country="US"):
    """Himalayas (himalayas.app/api): free, no key. Remote jobs; searched for US-friendly ones."""
    out, seen = [], set()
    for term in search_terms[:6]:
        for page in (1, 2):
            r = _get("https://himalayas.app/jobs/api/search", params={"q": term, "country": country, "sort": "recent", "page": page})
            if not r.ok:
                break
            jobs = r.json().get("jobs") or []
            for j in jobs:
                gid = j.get("guid") or j.get("applicationLink")
                if gid in seen:
                    continue
                seen.add(gid)
                where = ", ".join(j.get("locationRestrictions") or []) or "Anywhere"
                out.append({"company": j.get("companyName", ""), "title": j.get("title", ""),
                            "location": f"{where} (Remote)", "url": j.get("applicationLink") or j.get("guid") or "",
                            "jd": _text(j.get("description") or j.get("excerpt")), "posted": _when(j.get("pubDate")),
                            "source": "Himalayas"})
            time.sleep(PAUSE)
            if not jobs:
                break
    return out


def fetch_wwr():
    """We Work Remotely, DevOps & SysAdmin category (RSS): free, no key."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    r = _get("https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss")
    r.raise_for_status()
    out = []
    for it in ET.fromstring(r.content).iter("item"):
        raw = (it.findtext("title") or "").strip()
        company, _, title = raw.partition(": ")          # "Acme: Senior DevOps Engineer"
        if not title:
            company, title = "", raw
        try:
            posted = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            posted = None
        region = (it.findtext("region") or "Anywhere").strip()
        out.append({"company": company.strip(), "title": title.strip(), "location": f"{region} (Remote)",
                    "url": (it.findtext("link") or "").strip(), "jd": _text(it.findtext("description")),
                    "posted": posted, "source": "We Work Remotely"})
    return out


def feed_ready(f):
    """A feed is used when it is switched on and (for Jooble/JSearch) its free key is filled in."""
    return db.setting(f"feed_{f}", "1") == "1" and all(db.setting(k) for k in KEY_FEEDS.get(f, ()))


def fetch_remotive(search_terms):
    out, seen = [], set()
    for term in search_terms:
        r = _get("https://remotive.com/api/remote-jobs", params={"search": term, "limit": 100})
        if not r.ok:
            continue
        for j in r.json().get("jobs", []):
            if j.get("url") in seen:
                continue
            seen.add(j.get("url"))
            out.append({"company": j.get("company_name", ""), "title": j.get("title", ""),
                        "location": f"{j.get('candidate_required_location') or 'Anywhere'} (Remote)",
                        "url": j.get("url", ""), "jd": _text(j.get("description")),
                        "posted": _when(j.get("publication_date")), "source": "Remotive"})
        time.sleep(PAUSE)
    return out


def fetch_themuse(pages=5):
    out = []
    for page in range(pages):  # newest first
        r = _get("https://www.themuse.com/api/public/jobs", params={"page": page, "descending": "true"})
        if not r.ok:
            break
        results = r.json().get("results", [])
        if not results:
            break
        for j in results:
            out.append({"company": (j.get("company") or {}).get("name", ""), "title": j.get("name", ""),
                        "location": "; ".join(l.get("name", "") for l in j.get("locations") or []),
                        "url": (j.get("refs") or {}).get("landing_page", ""), "jd": _text(j.get("contents")),
                        "posted": _when(j.get("publication_date")), "source": "The Muse"})
        time.sleep(PAUSE)
    return out


def fetch_arbeitnow(pages=3):
    out = []
    for page in range(1, pages + 1):
        r = _get("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
        if not r.ok:
            break
        for j in r.json().get("data", []):
            loc = j.get("location") or ""
            if j.get("remote") and "remote" not in loc.lower():
                loc = f"{loc} (Remote)".strip()
            if "europe" not in loc.lower():
                loc = f"{loc}, Europe".strip(", ")          # Arbeitnow lists jobs in Germany/Europe
            out.append({"company": j.get("company_name", ""), "title": j.get("title", ""), "location": loc,
                        "url": j.get("url", ""), "jd": _text(j.get("description")), "posted": _when(j.get("created_at")),
                        "source": "Arbeitnow"})
        time.sleep(PAUSE)
    return out


def fetch_remoteok():
    r = _get("https://remoteok.com/api")
    r.raise_for_status()
    out = []
    for j in r.json():
        if not isinstance(j, dict) or not j.get("position"):
            continue                                # first item is their notice
        out.append({"company": j.get("company", ""), "title": j.get("position", ""),
                    "location": f"{j.get('location') or 'Anywhere'} (Remote)", "url": j.get("url") or j.get("apply_url", ""),
                    "jd": _text(j.get("description")), "posted": _when(j.get("epoch") or j.get("date")),
                    "source": "Remote OK"})
    return out


def fetch_jobicy():
    r = _get("https://jobicy.com/api/v2/remote-jobs", params={"count": 100})
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({"company": j.get("companyName", ""), "title": j.get("jobTitle", ""),
                    "location": f"{j.get('jobGeo') or 'Anywhere'} (Remote)", "url": j.get("url", ""),
                    "jd": _text(j.get("jobDescription") or j.get("jobExcerpt")), "posted": _when(j.get("pubDate")),
                    "source": "Jobicy"})
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby,
            "smartrecruiters": fetch_smartrecruiters, "workable": fetch_workable, "workday": fetch_workday,
            "bullhorn": fetch_bullhorn, "recruitee": fetch_recruitee, "bamboohr": fetch_bamboohr, "breezy": fetch_breezy,
            "amazon": fetch_amazon, "microsoft": fetch_microsoft, "oracle": fetch_oracle}
SOURCE_NAME = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "smartrecruiters": "SmartRecruiters",
               "workable": "Workable", "workday": "Workday", "bullhorn": "Bullhorn", "recruitee": "Recruitee",
               "bamboohr": "BambooHR", "breezy": "Breezy HR", "amazon": "Amazon Jobs", "microsoft": "Microsoft Careers",
               "oracle": "Oracle Cloud"}
DETAIL_READERS = {"workday": _workday_jd, "breezy": _breezy_jd, "oracle": _oracle_jd, "reed": _reed_jd,
                  "arbeitsagentur": _arbeitsagentur_jd}


# ---------------------------------------------------------------- does a job fit a profile?
def location_list(p):
    return [x.strip() for x in re.split(r"[,\n;]", (p or {}).get("locations") or "") if x.strip()]


US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
                "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
US_WORDS = re.compile(r"\b(usa|u\.s\.a?\.?|us|united states|america|north america|americas)\b", re.I)
# places that make a "remote" job NOT open to someone in the US
FOREIGN = re.compile(r"\b(europe|eu|emea|uk|united kingdom|england|london|germany|deutschland|berlin|munich|m\u00fcnchen|"
                     r"hamburg|frankfurt|cologne|k\u00f6ln|stuttgart|netherlands|amsterdam|france|paris|spain|madrid|"
                     r"barcelona|portugal|lisbon|italy|poland|warsaw|ireland|dublin|switzerland|zurich|z\u00fcrich|"
                     r"austria|vienna|sweden|stockholm|denmark|norway|finland|belgium|czech|prague|romania|greece|"
                     r"canada|toronto|vancouver|mexico|brazil|latam|latin america|argentina|colombia|india|bangalore|"
                     r"bengaluru|hyderabad|pune|chennai|apac|asia|singapore|japan|tokyo|china|australia|sydney|"
                     r"new zealand|israel|tel aviv|africa|dubai|uae|philippines|vietnam)\b", re.I)


US_STATE_NAMES = re.compile(r"\b(alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|"
                            r"hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|"
                            r"michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|"
                            r"new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|"
                            r"rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|"
                            r"west virginia|wisconsin|wyoming|district of columbia)\b", re.I)


def _is_us(raw):
    if US_WORDS.search(raw) or US_STATE_NAMES.search(raw):
        return True
    return any(m in US_STATES for m in re.findall(r"(?:,|\s|-)\s*([A-Z]{2})\b", raw))   # "Austin, TX"


# ---------------------------------------------------------------- countries (for the profile's location)
# name: (ISO-2, ISO-3, words that mean this country in a job location)
COUNTRIES = {
    "United States": ("us", "USA", ["usa", "u.s.", "u.s.a", "united states", "america"]),
    "India": ("in", "IND", ["india", "bengaluru", "bangalore", "hyderabad", "pune", "chennai", "mumbai", "delhi", "gurgaon",
                            "gurugram", "noida", "kolkata", "ahmedabad", "kochi", "coimbatore", "trivandrum", "jaipur", "indore"]),
    "United Kingdom": ("gb", "GBR", ["united kingdom", "uk", "england", "scotland", "wales", "london", "manchester",
                                     "birmingham", "edinburgh", "glasgow", "leeds", "bristol", "cambridge", "oxford", "belfast"]),
    "Canada": ("ca", "CAN", ["canada", "toronto", "vancouver", "montreal", "ottawa", "calgary", "waterloo", "edmonton",
                             "ontario", "british columbia", "quebec", "alberta"]),
    "Australia": ("au", "AUS", ["australia", "sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra"]),
    "Germany": ("de", "DEU", ["germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne",
                              "köln", "stuttgart", "düsseldorf", "dusseldorf", "leipzig"]),
    "Netherlands": ("nl", "NLD", ["netherlands", "amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague"]),
    "Ireland": ("ie", "IRL", ["ireland", "dublin", "cork", "galway"]),
    "France": ("fr", "FRA", ["france", "paris", "lyon", "toulouse", "nice", "marseille"]),
    "Spain": ("es", "ESP", ["spain", "madrid", "barcelona", "valencia", "malaga"]),
    "Portugal": ("pt", "PRT", ["portugal", "lisbon", "porto"]),
    "Italy": ("it", "ITA", ["italy", "milan", "rome", "turin"]),
    "Switzerland": ("ch", "CHE", ["switzerland", "zurich", "zürich", "geneva", "basel", "lausanne"]),
    "Austria": ("at", "AUT", ["austria", "vienna"]),
    "Belgium": ("be", "BEL", ["belgium", "brussels", "antwerp"]),
    "Sweden": ("se", "SWE", ["sweden", "stockholm", "gothenburg"]),
    "Denmark": ("dk", "DNK", ["denmark", "copenhagen"]),
    "Norway": ("no", "NOR", ["norway", "oslo"]),
    "Finland": ("fi", "FIN", ["finland", "helsinki"]),
    "Poland": ("pl", "POL", ["poland", "warsaw", "krakow", "kraków", "wroclaw", "gdansk"]),
    "Czech Republic": ("cz", "CZE", ["czech", "czechia", "prague", "brno"]),
    "Romania": ("ro", "ROU", ["romania", "bucharest", "cluj"]),
    "Singapore": ("sg", "SGP", ["singapore"]),
    "United Arab Emirates": ("ae", "ARE", ["united arab emirates", "uae", "dubai", "abu dhabi"]),
    "Saudi Arabia": ("sa", "SAU", ["saudi", "riyadh", "jeddah"]),
    "Qatar": ("qa", "QAT", ["qatar", "doha"]),
    "Japan": ("jp", "JPN", ["japan", "tokyo", "osaka"]),
    "New Zealand": ("nz", "NZL", ["new zealand", "auckland", "wellington"]),
    "Malaysia": ("my", "MYS", ["malaysia", "kuala lumpur"]),
    "Philippines": ("ph", "PHL", ["philippines", "manila", "cebu"]),
    "South Africa": ("za", "ZAF", ["south africa", "johannesburg", "cape town"]),
    "Israel": ("il", "ISR", ["israel", "tel aviv"]),
    "Brazil": ("br", "BRA", ["brazil", "são paulo", "sao paulo", "rio de janeiro"]),
    "Mexico": ("mx", "MEX", ["mexico", "mexico city", "guadalajara", "monterrey"]),
    "China": ("cn", "CHN", ["china", "beijing", "shanghai", "shenzhen"]),
    "Hong Kong": ("hk", "HKG", ["hong kong"]),
    "Vietnam": ("vn", "VNM", ["vietnam", "ho chi minh", "hanoi"]),
    "Pakistan": ("pk", "PAK", ["pakistan", "karachi", "lahore", "islamabad"]),
    "Bangladesh": ("bd", "BGD", ["bangladesh", "dhaka"]),
    "Sri Lanka": ("lk", "LKA", ["sri lanka", "colombo"]),
}
REGIONS = {  # a "remote" job open to a whole region
    "europe": ["United Kingdom", "Germany", "Netherlands", "Ireland", "France", "Spain", "Portugal", "Italy", "Switzerland",
               "Austria", "Belgium", "Sweden", "Denmark", "Norway", "Finland", "Poland", "Czech Republic", "Romania"],
    "eu": ["Germany", "Netherlands", "Ireland", "France", "Spain", "Portugal", "Italy", "Austria", "Belgium", "Sweden",
           "Denmark", "Finland", "Poland", "Czech Republic", "Romania"],
    "emea": ["United Kingdom", "Germany", "Netherlands", "Ireland", "France", "Spain", "Portugal", "Italy", "Switzerland",
             "Austria", "Belgium", "Sweden", "Denmark", "Norway", "Finland", "Poland", "Czech Republic", "Romania",
             "United Arab Emirates", "Saudi Arabia", "Qatar", "Israel", "South Africa"],
    "apac": ["India", "Australia", "Singapore", "Japan", "New Zealand", "Malaysia", "Philippines", "China", "Hong Kong",
             "Vietnam", "Pakistan", "Bangladesh", "Sri Lanka"],
    "asia": ["India", "Singapore", "Japan", "Malaysia", "Philippines", "China", "Hong Kong", "Vietnam", "Pakistan",
             "Bangladesh", "Sri Lanka", "United Arab Emirates", "Saudi Arabia", "Qatar", "Israel"],
    "north america": ["United States", "Canada", "Mexico"], "americas": ["United States", "Canada", "Mexico", "Brazil"],
    "latam": ["Mexico", "Brazil"], "latin america": ["Mexico", "Brazil"], "middle east": ["United Arab Emirates", "Saudi Arabia", "Qatar", "Israel"],
}
_ALIAS = {}
for _name, (_i2, _i3, _words) in COUNTRIES.items():
    for _w in _words + [_name.lower()]:
        _ALIAS[_w] = _name
_ALIAS_RE = re.compile(r"(?<![a-z])(" + "|".join(sorted(map(re.escape, _ALIAS), key=len, reverse=True)) + r")(?![a-z])")


def country_name(text):
    """'UK' / 'Bengaluru' / 'United States' -> canonical country name (or None)."""
    t = (text or "").strip()
    if not t:
        return None
    if _is_us(t) and not _ALIAS_RE.search(t.lower().replace("us", "")):
        return "United States"
    m = _ALIAS_RE.search(t.lower())
    return _ALIAS[m.group(1)] if m else None


def countries_in(raw):
    """All countries a job location mentions: 'London, UK; Remote - US' -> {'United Kingdom', 'United States'}."""
    found = {_ALIAS[m.group(1)] for m in _ALIAS_RE.finditer((raw or "").lower())}
    if "United States" not in found and _is_us(raw or ""):
        found.add("United States")
    if "United States" in found and re.search(r"\bus\b", (raw or "").lower()) and len(found) > 1 \
            and not re.search(r"\b(usa|united states|u\.s\.)\b", (raw or "").lower()) \
            and not any(m in US_STATES for m in re.findall(r"(?:,|\s|-)\s*([A-Z]{2})\b", raw or "")):
        found.discard("United States")                         # "us" inside another word list, e.g. "Remote (UK, us team)"
    return found


def locations_for(p):
    """The profile's locations; if none are set, read the country from the resume's contact line."""
    wanted = location_list(p)
    if wanted:
        return wanted
    text = (p or {}).get("text") or ""
    # the contact line (it has the phone or e-mail) says where the candidate lives; PDFs can put it anywhere
    contact = [ln for ln in text.splitlines() if "@" in ln or re.search(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", ln)]
    head = " ".join(contact[:3]) or text[:600]
    c = country_name(head)
    return [c, "Remote"] if c else []


def target_countries(profiles):
    """Countries the profiles want jobs in (US if none is known)."""
    out = []
    for p in profiles:
        for w in locations_for(p):
            c = country_name(w)
            if c and c not in out:
                out.append(c)
    return out or ["United States"]


def location_ok(job_location, wanted):
    """wanted: e.g. ['United Kingdom', 'Remote'] (empty = anywhere).
    A 'remote' job only counts if it is not tied to a country (or region) the candidate didn't choose."""
    if not wanted:
        return True
    raw = job_location or ""
    loc = raw.lower()
    wl = [w.strip().lower() for w in wanted if w.strip()]
    remote = "remote" in wl
    mine = {country_name(w) for w in wl if w != "remote"} - {None}
    if not loc.strip():
        return remote                                   # no location given: only ok for remote seekers
    there = countries_in(raw)
    if mine & there:
        return True
    for w in wl:                                        # a city / state typed by hand, e.g. "Michigan", "Austin"
        if w != "remote" and not country_name(w) and w in loc:
            return True
    if remote and re.search(r"remote|anywhere|worldwide|work from home|wfh|distributed", loc):
        if there - mine:
            return False                                # "Berlin (Remote)" for someone in India
        regions = [r for r in REGIONS if re.search(r"(?<![a-z])" + re.escape(r) + r"(?![a-z])", loc)]
        if regions and mine and not any(set(REGIONS[r]) & mine for r in regions):
            return False                                # "Remote - EMEA" for someone in the US
        return True
    return False


INTERN = re.compile(r"\b(intern|internship|working student|werkstudent|student|trainee|apprentice\w*|graduate program)\b", re.I)
TOP_LEVEL = re.compile(r"\b(director|head of|vp|vice president|chief|cto|cio)\b", re.I)
STAFF_LEVEL = re.compile(r"\b(principal|staff|distinguished|architect|fellow|manager)\b", re.I)


def level_ok(title, years):
    """Skip interns always; skip director/VP; skip staff/principal unless 8+ years."""
    if INTERN.search(title):
        return False
    if TOP_LEVEL.search(title):
        return years is not None and years >= 12
    if STAFF_LEVEL.search(title):
        return years is None or years >= 8
    return True


NOT_TECH_ROLE = re.compile(r"\b(sales|marketing|recruit\w*|account (executive|manager)|business development|"
                           r"customer success|human resources|hr (generalist|manager)|legal|attorney|paralegal|"
                           r"finance manager|accountant|copywriter)\b", re.I)


def fits(job, p, since):
    if not job.get("posted") or job["posted"] < since:
        return False
    return wrong_fit(job, p) is None


def skills_ok(job, p):
    """The job's skills must overlap with the resume (checked once the full JD is known)."""
    jd = job.get("jd") or ""
    if not jd.strip() and job.get("source") in TITLE_ONLY_OK:   # the JD comes when you open the job with J
        return True
    need = 1 if job.get("source") in SNIPPET_SOURCES else 3   # Jooble only gives a few lines of the JD
    if len(matching.find_skills(jd, strict=True)) < need:     # too few real skills to judge the fit
        return False
    pct, _, _ = matching.score(jd, db.scoring_text(p))
    return pct >= MIN_MATCH


def wrong_fit(job, p):
    """Why a job doesn't fit the profile's main roles / level / location (None = fits)."""
    title = job.get("title") or ""
    roles = db.roles_for_search(p)
    inner = " ".join(re.findall(r"\(([^)]+)\)", title))     # "IT Specialist (DevOps Engineer)" on USAJOBS
    if NOT_TECH_ROLE.search(title) or not (matching.title_fit(title, roles) or (inner and matching.title_fit(inner, roles))):
        return "not a resume role"
    if not level_ok(title, matching.years_of_experience((p or {}).get("text") or "")):
        return "wrong level"
    loc = job.get("location") or ""
    if job.get("source") == "Arbeitnow" and "europe" not in loc.lower():
        loc += ", Europe"
    if not location_ok(loc, locations_for(p)):
        return "wrong location"
    return None


AUTO_SOURCES = set(FEEDS.values()) | set(SOURCE_NAME.values())


def prune_waiting():
    """Remove jobs the daily collection saved earlier that no longer fit (never applied
    jobs, never jobs you saved yourself with the J button)."""
    gone = []
    for p in db.profiles():
        if not db.roles_for_search(p):
            continue
        for j in db.jobs(p["id"]):
            if j["status"] == "applied" or j.get("origin") != "collect":   # never touch J-button / imported jobs
                continue
            if wrong_fit(dict(j), p):
                gone.append(j["id"])
    db.delete_jobs(gone)
    return len(gone)


# ---------------------------------------------------------------- run
def _count(summary, source, reason):
    """Remember why jobs were kept or skipped, per source (shown under 'What happened in the last run')."""
    src = summary.setdefault("by_source", {}).setdefault(source, {})
    src[reason] = src.get(reason, 0) + 1


def _save_for_profiles(jobs, profiles, since, source, summary):
    for job in jobs:
        _count(summary, source, "posted recently")
        for p in profiles:
            why = wrong_fit(job, p)
            if why:
                _count(summary, source, why)
                continue
            if db.has_job(p["id"], job["company"], job["url"]):       # same posting as an earlier run: skip quietly
                _count(summary, source, "already in Tailor&Track")
                continue
            if job.get("jd") is None and job.get("_detail"):          # SmartRecruiters/Workday: JD only when needed
                try:
                    job["jd"] = DETAIL_READERS.get(job.get("_kind"), _smartrecruiters_jd)(job["_detail"])
                except (requests.RequestException, ValueError):
                    job["jd"] = ""
                job["jd"] = job["jd"] or job.get("_snippet") or ""
            if not exp_ok(job.get("jd"), p):                          # asks for more (or less) experience
                _count(summary, source, "experience")
                continue
            if not skills_ok(job, p):                                  # title fits, but skills don't
                summary["low_match"] = summary.get("low_match", 0) + 1
                _count(summary, source, "low skills match")
                continue
            res = db.save_job(p["id"], job["company"], job["title"], job["url"], job.get("jd") or "",
                              job.get("location", ""), job.get("source") or source,
                              posted_at=job["posted"].astimezone(timezone.utc).isoformat() if job.get("posted") else None,
                              origin="collect")
            key = "new" if res["level"] in ("new", "warning") else "duplicates"
            summary[key] += 1
            _count(summary, source, "saved" if key == "new" else "duplicate blocked")
            summary["by_profile"][p["name"]] = summary["by_profile"].get(p["name"], 0) + (key == "new")


def run(progress=None, auto=False):
    """Collect from every active board and feed. Returns a summary dict.
    auto=True (the every-N-hours run): looks back at least since the last run, and uses the
    JSearch free quota (200 searches a month) only on the first run of the day."""
    if not _lock.acquire(blocking=False):
        return {"busy": True}
    try:
        init()
        prune_waiting()
        hours = window_hours()
        if auto:
            hours = max(hours, collect_every() + 1)      # never miss jobs posted between two runs
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        profiles = [p for p in db.profiles() if db.roles_for_search(p)]
        summary = {"started": db.now(), "found": 0, "new": 0, "duplicates": 0, "low_match": 0, "errors": [], "by_profile": {},
                   "no_roles": [p["name"] for p in db.profiles() if not db.roles_for_search(p)]}
        if not profiles:
            summary["errors"].append("No profile has target roles or a resume yet (Profiles page).")
            return summary
        if not boards() or db.setting("suggested_version") != "3":   # add the well-known companies once
            for prov, tok, nm in SUGGESTED:
                add_board(prov, tok, nm)
            db.set_setting("suggested_version", "3")
        active = [b for b in boards() if b["active"]]
        feeds = [f for f in FEEDS if feed_ready(f)]
        if auto and db.setting("last_collect_day") == db.today():
            feeds = [f for f in feeds if f != "jsearch"]      # keep the free monthly quota
        summary["skipped_feeds"] = [FEEDS[f] for f in KEY_FEEDS if not feed_ready(f)]
        total = len(active) + len(feeds)
        step = 0
        def fetch_board(b):                     # runs in a few threads at once (different companies)
            try:
                return b, FETCHERS[b["provider"]](b["token"], b["name"]), None
            except Exception as e:
                return b, None, e
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=BOARD_THREADS) as pool:
            for fut in as_completed([pool.submit(fetch_board, b) for b in active]):
                b, jobs, err = fut.result()
                step += 1
                if progress:
                    progress(step / max(total, 1), f"{b['name']} ({SOURCE_NAME[b['provider']]})")
                try:
                    if err:
                        raise err
                    recent = [j for j in jobs if j.get("posted") and j["posted"] >= since]
                    summary["found"] += len(recent)
                    _save_for_profiles(recent, profiles, since, SOURCE_NAME[b["provider"]], summary)
                    _board_status(b["id"], f"OK · {len(jobs)} open · {len(recent)} new")
                except LookupError:
                    _board_status(b["id"], "Not found: switched off (check the link or remove it)")
                    update_board(b["id"], active=False)            # don't slow down the next runs
                    summary["errors"].append(f"{b['name']}: board not found")
                except requests.ConnectionError:
                    _board_status(b["id"], "No connection: check the internet, then Collect now")
                    summary["errors"].append(f"{b['name']}: no internet connection")
                except Exception as e:  # one broken board never stops the others
                    _board_status(b["id"], f"Error: {str(e)[:80]}")
                    summary["errors"].append(f"{b['name']}: {str(e)[:80]}")
        terms = sorted({r for p in profiles for r in db.roles_for_search(p)[:4]})   # main roles only (be polite)
        big_terms = list(dict.fromkeys(r for p in profiles for r in db.roles_for_search(p)[:8]))  # top 8 roles, in order
        countries = target_countries(profiles)
        _COUNTRIES_NOW[:] = countries
        feeds = [f for f in feeds if f not in COUNTRY_FEEDS or COUNTRY_FEEDS[f] in countries]
        summary["skipped_feeds"] = [FEEDS[f] for f in KEY_FEEDS if not feed_ready(f)
                                    and (f not in COUNTRY_FEEDS or COUNTRY_FEEDS[f] in countries)]
        each = lambda fn: [j for c in countries for j in fn(c)]          # run a feed once per country
        feed_fetch = {"jooble": lambda: each(lambda c: fetch_jooble(big_terms, location=c)),
                      "jsearch": lambda: each(lambda c: fetch_jsearch(big_terms, country=COUNTRIES[c][0],
                                                                                where="USA" if c == "United States" else c)),
                      "himalayas": lambda: each(lambda c: fetch_himalayas(big_terms, country=COUNTRIES[c][0].upper())),
                      "usajobs": lambda: fetch_usajobs(big_terms),
                      "reed": lambda: fetch_reed(big_terms), "arbeitsagentur": lambda: fetch_arbeitsagentur(big_terms),
                      "jobtech": lambda: fetch_jobtech(big_terms), "francetravail": lambda: fetch_francetravail(big_terms),
                      "findwork": lambda: fetch_findwork(terms),
                      "wwr": fetch_wwr,
                      "remotive": lambda: fetch_remotive(terms), "themuse": fetch_themuse,
                      "arbeitnow": fetch_arbeitnow, "remoteok": fetch_remoteok, "jobicy": fetch_jobicy}
        for f in feeds:
            step += 1
            if progress:
                progress(step / max(total, 1), FEEDS[f])
            try:
                jobs = feed_fetch[f]()
                recent = [j for j in jobs if j.get("posted") and j["posted"] >= since]
                _count(summary, FEEDS[f], "jobs received")
                summary["by_source"][FEEDS[f]]["jobs received"] = len(jobs)
                summary["found"] += len(recent)
                _save_for_profiles(recent, profiles, since, FEEDS[f], summary)
            except requests.ConnectionError:
                summary["errors"].append(f"{FEEDS[f]}: no internet connection")
            except Exception as e:
                summary["errors"].append(f"{FEEDS[f]}: {str(e)[:80]}")
        summary["finished"] = db.now()
        db.set_setting("last_collect", json.dumps(summary))
        db.set_setting("last_collect_day", db.today())
        db.set_setting("last_collect_at", datetime.now().isoformat(timespec="seconds"))
        return summary
    finally:
        _lock.release()


def last_summary():
    try:
        return json.loads(db.setting("last_collect") or "null")
    except ValueError:
        return None


# ---------------------------------------------------------------- every few hours, automatically
EVERY_CHOICES = [1, 2, 3, 4, 6, 8, 12, 24]


def collect_every():
    """Hours between automatic collections (default 3)."""
    try:
        return max(1, int(float(db.setting("collect_every_hours", "3") or 3)))
    except ValueError:
        return 3


def next_collect():
    """When the next automatic collection runs (datetime), or None if it is off."""
    if db.setting("collect_auto", "1") != "1":
        return None
    last = db.setting("last_collect_at")
    try:
        return datetime.fromisoformat(last) + timedelta(hours=collect_every()) if last else datetime.now()
    except ValueError:
        return datetime.now()


def _daily_loop():
    while True:
        try:
            nxt = next_collect()
            if nxt and datetime.now() >= nxt:
                run(auto=True)
        except Exception:
            pass
        time.sleep(300)  # check every 5 minutes


def start_daily():
    """While the app is open, collects every few hours (Collection settings, default every 3 hours)."""
    init()
    threading.Thread(target=_daily_loop, daemon=True, name="jobpilot-daily").start()