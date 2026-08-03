#!/usr/bin/env python3
"""
intern_watch.py v3 — Multi-source internship early-warning system.
FAANG+ gets a separate channel (high priority) + European sources.

SOURCES
  engine       zshah101 Internship Engine JSON API (3,870 companies, hourly, US)
  speedy_usa   speedyapply/2027-SWE-College-Jobs README.md      (US, split into FAANG+/Quant/Other)
  speedy_intl  speedyapply/2027-SWE-College-Jobs INTERN_INTL.md (INTERNATIONAL - Europe is here)
  speedy_ai    speedyapply/2027-AI-College-Jobs   INTERN_INTL.md (AI/ML, international)
  vansh        vanshb03/Summer2027-Internships                  (US/Canada, community)
  eu           LorenzoLaCorte/european-tech-internships-2026     (Europe, community)

FAANG+ DETECTION
  - In speedyapply files, the "### FAANG+" section is read directly.
  - In other sources, company names are matched against the FAANG_COMPANIES list.
  FAANG+ listings are sent as a SEPARATE, HIGH-PRIORITY notification
  (optionally to its own ntfy topic: NTFY_TOPIC_FAANG).

Usage
  python3 intern_watch.py --dry-run     # show without sending notifications
  python3 intern_watch.py --seed        # mark existing listings as "seen"
  python3 intern_watch.py --faang-only  # only notify FAANG+
  python3 intern_watch.py --readme      # only rewrite the README listing tables
  python3 intern_watch.py               # normal
"""

import json
import os
import re
import smtplib
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

STATE_DIR = Path(os.environ.get("INTERN_WATCH_HOME", Path.home() / ".local/share/intern-watch"))
STATE_FILE = STATE_DIR / "state.json"
UA = {"User-Agent": "intern-watch/3.0"}

RAW = "https://raw.githubusercontent.com"
ENGINE_JSON = (f"{RAW}/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships"
               "/main/docs/api/jobs.json")
SPEEDY_USA = f"{RAW}/speedyapply/2027-SWE-College-Jobs/main/README.md"
SPEEDY_INTL = f"{RAW}/speedyapply/2027-SWE-College-Jobs/main/INTERN_INTL.md"
SPEEDY_AI_INTL = f"{RAW}/speedyapply/2027-AI-College-Jobs/main/INTERN_INTL.md"
VANSH = f"{RAW}/vanshb03/Summer2027-Internships/dev/README.md"
EU_REPO = f"{RAW}/LorenzoLaCorte/european-tech-internships-2026/main/README.md"

# New grad boards. Same column layouts as the internship files above, so they go
# through the very same parsers.
SPEEDY_NG_USA = f"{RAW}/speedyapply/2027-SWE-College-Jobs/main/NEW_GRAD_USA.md"
SPEEDY_NG_INTL = f"{RAW}/speedyapply/2027-SWE-College-Jobs/main/NEW_GRAD_INTL.md"
SPEEDY_NG_AI = f"{RAW}/speedyapply/2027-AI-College-Jobs/main/NEW_GRAD_INTL.md"
VANSH_NG = f"{RAW}/vanshb03/New-Grad-2027/dev/README.md"

WATCH_REPOS = [("SimplifyJobs/Summer2027-Internships", "dev/README.md")]

# --------------------------------------------------------------------------
# FAANG+ company list (for matching in sources without a speedyapply section)
# --------------------------------------------------------------------------
FAANG_COMPANIES = {
    "google", "alphabet", "deepmind", "google deepmind", "youtube",
    "meta", "facebook", "instagram", "whatsapp",
    "apple", "amazon", "aws", "amazon web services",
    "microsoft", "netflix", "nvidia",
    "tiktok", "bytedance", "tesla", "palantir", "openai", "anthropic",
    "uber", "airbnb", "linkedin", "salesforce", "adobe", "oracle", "ibm",
    "stripe", "databricks", "snowflake", "coinbase", "dropbox", "pinterest",
    "snap", "snapchat", "twitter", "roblox", "doordash", "instacart",
    "robinhood", "figma", "notion", "scale ai", "xai", "waymo", "cruise",
    "spotify", "shopify", "atlassian", "cloudflare", "datadog", "twilio",
    "qualcomm", "intel", "amd", "arm", "broadcom", "samsung", "sony",
    "reddit", "discord", "block", "square", "paypal", "ebay", "booking",
    "mistral", "cohere", "perplexity", "rivian", "lucid", "sap", "siemens",
}

EU_KEYWORDS = [
    "united kingdom", "london", "manchester", "edinburgh", "cambridge", "oxford",
    "glasgow", "bristol", "leeds", "birmingham", "scotland", "england",
    "germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt",
    "stuttgart", "cologne", "köln", "düsseldorf", "dresden", "leipzig", "hannover",
    "france", "paris", "lyon", "toulouse", "grenoble", "sophia antipolis",
    "netherlands", "amsterdam", "eindhoven", "rotterdam", "utrecht", "the hague", "delft",
    "switzerland", "zurich", "zürich", "geneva", "lausanne", "basel",
    "ireland", "dublin", "cork",
    "spain", "madrid", "barcelona", "valencia",
    "italy", "milan", "milano", "rome", "roma", "turin", "torino",
    "sweden", "stockholm", "gothenburg", "lund",
    "denmark", "copenhagen", "norway", "oslo", "finland", "helsinki", "espoo",
    "poland", "warsaw", "warszawa", "krakow", "kraków", "wroclaw", "gdansk",
    "austria", "vienna", "wien", "graz",
    "belgium", "brussels", "leuven", "ghent",
    "portugal", "lisbon", "lisboa", "porto",
    "czech", "prague", "praha", "brno",
    "romania", "bucharest", "cluj", "cluj-napoca", "timisoara",
    "hungary", "budapest", "greece", "athens", "bulgaria", "sofia",
    "luxembourg", "estonia", "tallinn", "lithuania", "vilnius", "latvia", "riga",
    "turkey", "türkiye", "istanbul", "ankara", "izmir",
    "europe", "emea",
]

# Turkey is kept no matter what: it wins over every EXCLUDE_REGIONS group below,
# so an "Istanbul, Middle East" style location still comes through.
TURKEY_KEYWORDS = [
    "turkey", "türkiye", "turkiye", "istanbul", "ankara", "izmir", "bursa", "antalya",
]

# Location groups that can be dropped via EXCLUDE_REGIONS.
# Matched on WORD BOUNDARIES, not substrings — "Romania" contains "oman" and
# "Indiana" contains "india", both of which a naive `in` test would throw away.
REGION_GROUPS = {
    "middle-east": [
        "middle east", "mena", "gulf",
        "united arab emirates", "uae", "dubai", "abu dhabi", "sharjah",
        "saudi arabia", "ksa", "riyadh", "jeddah", "dhahran", "dammam", "neom",
        "qatar", "doha", "kuwait", "kuwait city", "bahrain", "manama",
        "oman", "muscat", "yemen", "sanaa",
        # Israel is deliberately absent: it is Middle East geographically, but it is
        # kept on purpose. Add its cities here to drop it.
        "jordan", "amman", "lebanon", "beirut", "syria", "damascus",
        "iraq", "baghdad", "erbil", "iran", "tehran",
    ],
    "africa": [
        "africa", "south africa", "cape town", "johannesburg", "pretoria", "durban",
        "egypt", "cairo", "giza", "alexandria",
        "morocco", "casablanca", "rabat", "marrakech",
        "tunisia", "tunis", "algeria", "algiers",
        "nigeria", "lagos", "abuja", "kenya", "nairobi",
        "ghana", "accra", "ethiopia", "addis ababa", "uganda", "kampala",
        "tanzania", "dar es salaam", "rwanda", "kigali", "senegal", "dakar",
        "zimbabwe", "harare", "zambia", "lusaka", "mauritius", "namibia", "botswana",
    ],
    "south-asia": [
        "south asia", "india", "bharat",
        "bangalore", "bengaluru", "hyderabad", "pune", "chennai", "mumbai", "bombay",
        "new delhi", "delhi", "noida", "gurgaon", "gurugram", "kolkata", "ahmedabad",
        "jaipur", "kochi", "trivandrum", "thiruvananthapuram", "coimbatore", "indore",
        "chandigarh", "mysore", "mysuru", "vizag", "visakhapatnam",
        "pakistan", "karachi", "lahore", "islamabad",
        "bangladesh", "dhaka", "sri lanka", "colombo",
        "nepal", "kathmandu", "bhutan", "maldives", "afghanistan", "kabul",
    ],
}

# --------------------------------------------------------------------------
# Filter settings
# --------------------------------------------------------------------------
SEASONS = [s.strip() for s in os.environ.get("SEASONS", "2027").split(",") if s.strip()]
YEAR_RE = re.compile(r"\b(20\d{2})\b")
# "2026/27" and "2026-27" mean two academic years; spell the second one out so the
# year check below sees it, otherwise a 2026/27 posting looks like 2026-only.
SPLIT_YEAR_RE = re.compile(r"\b(20\d{2})\s*[/-]\s*(\d{2})\b")
# Years named in SEASONS, e.g. ["Summer 2027"] -> {"2027"}. Empty disables the
# title-year check, which is what a season filter like "Summer" alone should do.
SEASON_YEARS = {y for s in SEASONS for y in YEAR_RE.findall(s)}
CATEGORIES = [c.strip() for c in os.environ.get("CATEGORIES", "").split(",") if c.strip()]
EXCLUDE_SPONSORSHIP = [s.strip() for s in os.environ.get(
    "EXCLUDE_SPONSORSHIP", "no-sponsorship,citizens-only").split(",") if s.strip()]
TITLE_INCLUDE = [k.strip().lower() for k in os.environ.get("TITLE_INCLUDE", "").split(",") if k.strip()]
TITLE_EXCLUDE = [k.strip().lower() for k in os.environ.get("TITLE_EXCLUDE", "").split(",") if k.strip()]
# REGIONS: all / eu   (eu -> only Europe-located listings)
REGIONS = [r.strip().lower() for r in os.environ.get("REGIONS", "all").split(",") if r.strip()]
# EXCLUDE_REGIONS: drop listings located in these groups. "none" keeps everything.
EXCLUDE_REGIONS = [r.strip().lower() for r in os.environ.get(
    "EXCLUDE_REGIONS", "middle-east,africa,south-asia").split(",")
    if r.strip() and r.strip().lower() != "none"]
NTFY_MAX_PER_RUN = int(os.environ.get("NTFY_MAX_PER_RUN", "12"))
# MAX_AGE_DAYS: drop postings older than this. 0 disables the cutoff.
# Listings whose sources gave no date are always kept — there is nothing to judge.
MAX_AGE_DAYS = int(os.environ.get("MAX_AGE_DAYS", "30"))

for _g in EXCLUDE_REGIONS:
    if _g not in REGION_GROUPS:
        print(f"EXCLUDE_REGIONS: unknown group {_g!r}, expected one of "
              f"{', '.join(sorted(REGION_GROUPS))}", file=sys.stderr)


def compile_keywords(keywords: list[str]) -> "re.Pattern":
    """Word-boundary alternation, longest first so 'south africa' wins over 'africa'."""
    parts = sorted(set(keywords), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(k) for k in parts) + r")\b")


TURKEY_RE = compile_keywords(TURKEY_KEYWORDS)
EXCLUDED_RE = {g: compile_keywords(k) for g, k in REGION_GROUPS.items()}


US_KEYWORDS = [
    "united states", "usa", "u.s.", "remote - us", "washington dc", "washington, dc",
    "new york", "san francisco", "seattle", "austin", "boston", "chicago", "atlanta",
    "denver", "san jose", "sunnyvale", "mountain view", "palo alto", "santa clara",
    "cupertino", "redmond", "bellevue", "los angeles", "san diego", "dallas", "houston",
]
# Two-letter US state codes, matched against the tail of a "City, ST" location.
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}


@dataclass
class Job:
    uid: str
    company: str
    title: str
    location: str
    url: str
    source: str
    season: str = ""
    category: str = ""
    sponsorship: str = ""
    salary: str = ""
    posted: str = ""          # ISO date "YYYY-MM-DD", best effort, "" if unknown
    posted_raw: str = ""      # what the source actually said ("18d", "Jul 31", ...)
    track: str = "intern"     # "intern" or "newgrad" — separate boards, separate topics
    is_faang: bool = False
    flags: list = field(default_factory=list)

    @property
    def is_eu(self) -> bool:
        loc = self.location.lower()
        return any(k in loc for k in EU_KEYWORDS)

    @property
    def is_us(self) -> bool:
        loc = self.location.lower()
        if any(k in loc for k in US_KEYWORDS):
            return True
        # "Needham, MA" / "Remote - Santa Clara, CA +2"
        for part in re.split(r"[/,+]", self.location):
            tail = part.strip().split(" ")[-1].strip()
            if tail in US_STATES:
                return True
        return False

    @property
    def age_days(self):
        """Days since the posting went up, or None when no source gave a date."""
        if not self.posted:
            return None
        try:
            return (today_utc() - date.fromisoformat(self.posted)).days
        except ValueError:
            return None

    @property
    def excluded_region(self) -> str:
        """Name of the EXCLUDE_REGIONS group this listing falls in, or "".

        A posting open in several places ("Atlanta, GA / Bengaluru, India") is only
        dropped when EVERY location is excluded — one reachable office is enough."""
        loc = self.location.lower()
        if not loc or TURKEY_RE.search(loc):
            return ""
        hit = ""
        for part in (p.strip() for p in loc.split("/")):
            if not part:
                continue
            found = next((g for g in EXCLUDE_REGIONS
                          if g in EXCLUDED_RE and EXCLUDED_RE[g].search(part)), "")
            if not found:
                return ""      # this location is fine, keep the posting
            hit = hit or found
        return hit

    @property
    def region(self) -> str:
        if self.is_eu:
            return "🇪🇺 EU/UK"
        if self.is_us:
            return "🇺🇸 US"
        return "🌍 Other"

    @property
    def visa(self) -> str:
        """What the source says about work authorisation — never a guarantee,
        just the strongest signal available."""
        if self.sponsorship == "no-sponsorship":
            return "🛂 No sponsorship"
        if self.sponsorship == "citizens-only":
            return "🇺🇸 Citizen/PR only"
        if self.is_eu:
            return "❔ EU/UK right to work"
        if self.is_us:
            # F-1/CPT is an internship mechanism; a graduate hire needs OPT (which
            # requires a US degree) or an H-1B, which is a different problem entirely.
            return ("❔ US OPT/H-1B needed" if self.track == "newgrad"
                    else "❔ US F-1/CPT likely")
        return "❔ Not stated"

    def label(self) -> str:
        s = f"{self.company} — {self.title}"
        if self.location:
            s += f" ({self.location})"
        return s


def http_get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def http_exists(url: str, timeout: int = 15) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
        return True
    except (urllib.error.HTTPError, urllib.error.URLError):
        return False


def is_faang_company(name: str) -> bool:
    n = name.strip().lower()
    if n in FAANG_COMPANIES:
        return True
    for c in FAANG_COMPANIES:
        if len(c) > 3 and n.startswith(c + " "):
            return True
    return False


MD_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
HREF_RE = re.compile(r'href="([^"]+)"')
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
TAG_RE = re.compile(r"<[^>]+>")
SEP_RE = re.compile(r"^[\s:|-]+$")
HEADER_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$")
FLAG_CHARS = ["🛂", "🇺🇸", "🔒", "🔥", "🎓"]


def md_clean(cell: str) -> str:
    t = re.sub(r"</?br\s*/?>", " / ", cell)
    t = MD_LINK_RE.sub(lambda m: m.group(1), t)
    t = TAG_RE.sub("", t)
    return t.replace("**", "").replace("&amp;", "&").strip()


AGE_RE = re.compile(r"^\s*(\d+)\s*(h|hr|hrs|hour|hours|d|day|days|w|wk|wks|week|weeks|"
                    r"mo|mos|month|months|y|yr|yrs|year|years)\s*$", re.I)
AGE_DAYS = {"h": 0, "d": 1, "w": 7, "m": 30, "y": 365}


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def age_to_date(txt: str) -> str:
    """speedyapply's Age column: '18d' / '3mo' / '5h' -> ISO date."""
    m = AGE_RE.match(md_clean(txt))
    if not m:
        return ""
    unit = AGE_DAYS[m.group(2)[0].lower()]
    return (today_utc() - timedelta(days=int(m.group(1)) * unit)).isoformat()


def mmm_dd_to_date(txt: str) -> str:
    """vanshb03's Date Posted column: 'Jul 31' -> ISO date.
    The year is absent, so assume the most recent occurrence: anything that
    would land in the future belongs to last year."""
    t = md_clean(txt)
    if not t:
        return ""
    today = today_utc()
    for fmt in ("%b %d", "%B %d", "%b %d %Y", "%B %d %Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(t, fmt).date()
        except ValueError:
            continue
        if "%Y" not in fmt:
            d = d.replace(year=today.year)
            if d > today + timedelta(days=2):
                d = d.replace(year=today.year - 1)
        return d.isoformat()
    return ""


def iso_to_date(txt: str) -> str:
    """'2026-08-01T12:00:00-04:00' -> '2026-08-01'."""
    if not txt:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", txt.strip())
    return m.group(1) if m else ""


def md_url(cell: str) -> str:
    m = HREF_RE.search(cell)
    if m:
        return m.group(1)
    m = MD_LINK_RE.search(cell)
    return m.group(2) if m else ""


def parse_speedy(md: str, source_name: str, track: str = "intern") -> list[Job]:
    """speedyapply: split into '### FAANG+' / '### Quant' / '### Other'.
    Column layout VARIES by file:
      USA : Company | Position | Location | Salary | Posting | Age
      INTL: Company | Position | Location | Posting | Age      (no Salary)
    So column indexes are derived from the header row."""
    jobs, section, last_company = [], "", ""
    cols: dict[str, int] = {}

    for line in md.splitlines():
        h = HEADER_RE.match(line.strip())
        if h:
            section = h.group(1).lower()
            last_company = ""
            continue
        m = MD_ROW_RE.match(line.strip())
        if not m or SEP_RE.match(m.group(1)):
            continue
        cells = [c.strip() for c in m.group(1).split("|")]

        # header row -> update the column map
        names = [md_clean(c).lower() for c in cells]
        if "company" in names and ("position" in names or "role" in names):
            cols = {n: i for i, n in enumerate(names)}
            last_company = ""
            continue
        if not cols or len(cells) < len(cols):
            continue

        def cell(key, default=""):
            i = cols.get(key)
            return cells[i] if i is not None and i < len(cells) else default

        company = md_clean(cell("company"))
        if company in ("↳", "->", ""):
            company = last_company
        else:
            last_company = company

        url = md_url(cell("posting"))
        if not url.startswith("http") or not company:
            continue

        age = md_clean(cell("age"))
        jobs.append(Job(
            uid=f"{source_name}:{url.split('?')[0]}",
            company=company,
            title=md_clean(cell("position") or cell("role")),
            location=md_clean(cell("location")),
            url=url, source=source_name,
            salary=md_clean(cell("salary")),
            posted=age_to_date(age), posted_raw=age, track=track,
            category="AI/ML" if "ai" in source_name.split("_") else "Software",
            is_faang=section.startswith("faang") or is_faang_company(company),
        ))
    return jobs


def parse_vansh(md: str, source_name: str = "vansh", track: str = "intern") -> list[Job]:
    """vanshb03: Company | Role | Location | Application | Date"""
    jobs, last_company = [], ""
    for line in md.splitlines():
        m = MD_ROW_RE.match(line.strip())
        if not m or SEP_RE.match(m.group(1)):
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 4:
            continue
        if md_clean(cells[0]).lower() == "company":
            continue
        url = md_url(cells[3])
        if not url.startswith("http"):
            continue
        ctxt = md_clean(cells[0])
        if ctxt in ("↳", "->", ""):
            company = last_company
        else:
            company = ctxt
            for f in FLAG_CHARS:
                company = company.replace(f, "")
            company = company.strip()
            last_company = company
        flags = [f for f in FLAG_CHARS if f in cells[1] or f in cells[0]]
        if "🔒" in flags:
            continue
        title = md_clean(cells[1])
        for f in FLAG_CHARS:
            title = title.replace(f, "")
        sponsorship = "unknown"
        if "🛂" in flags:
            sponsorship = "no-sponsorship"
        if "🇺🇸" in flags:
            sponsorship = "citizens-only"
        posted_raw = md_clean(cells[4]) if len(cells) > 4 else ""
        jobs.append(Job(
            uid=f"{source_name}:{url.split('?')[0]}", company=company, title=title.strip(),
            location=md_clean(cells[2]), url=url, source=source_name, track=track,
            posted=mmm_dd_to_date(posted_raw), posted_raw=posted_raw,
            sponsorship=sponsorship, flags=flags, is_faang=is_faang_company(company),
        ))
    return jobs


def parse_eu(md: str) -> list[Job]:
    """LorenzoLaCorte: company|title|location|link (lowercase).
    Internship sections only; New Grad / PhD are skipped."""
    jobs, section = [], ""
    for line in md.splitlines():
        h = HEADER_RE.match(line.strip())
        if h:
            section = h.group(1).lower()
            continue
        if "internship" not in section or "phd" in section:
            continue
        m = MD_ROW_RE.match(line.strip())
        if not m or SEP_RE.match(m.group(1)):
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 4 or cells[0].lower() == "company":
            continue
        url = md_url(cells[3])
        if not url.startswith("http"):
            continue
        raw_company = md_clean(cells[0])
        jobs.append(Job(
            uid=f"eu:{url.split('?')[0]}", company=raw_company.title(),
            title=md_clean(cells[1]).capitalize(), location=md_clean(cells[2]),
            url=url, source="eu",
            category="AI/ML" if " ml " in f" {section} " else "Software",
            is_faang=is_faang_company(raw_company),
        ))
    return jobs


def fetch_engine() -> list[Job]:
    d = json.loads(http_get(ENGINE_JSON))
    out = []
    for j in d.get("jobs", []):
        comp = j.get("company", "").strip()
        out.append(Job(
            uid=f"engine:{j.get('id')}", company=comp, title=j.get("title", "").strip(),
            location=j.get("location", "").strip(), url=j.get("url", ""), source="engine",
            season=j.get("season", ""), category=j.get("category", ""),
            sponsorship=j.get("sponsorship", "unknown"), salary=j.get("salary") or "",
            posted=iso_to_date(j.get("posted_at") or j.get("first_seen_at") or ""),
            posted_raw=iso_to_date(j.get("posted_at") or j.get("first_seen_at") or ""),
            is_faang=is_faang_company(comp),
        ))
    return out


SOURCES = [
    # (name, fetcher, track)
    ("engine",         fetch_engine, "intern"),
    ("speedy_usa",     lambda: parse_speedy(http_get(SPEEDY_USA), "speedy_usa"), "intern"),
    ("speedy_intl",    lambda: parse_speedy(http_get(SPEEDY_INTL), "speedy_intl"), "intern"),
    ("speedy_ai",      lambda: parse_speedy(http_get(SPEEDY_AI_INTL), "speedy_ai"), "intern"),
    ("vansh",          lambda: parse_vansh(http_get(VANSH)), "intern"),
    ("eu",             lambda: parse_eu(http_get(EU_REPO)), "intern"),

    ("speedy_ng_usa",  lambda: parse_speedy(http_get(SPEEDY_NG_USA),
                                            "speedy_ng_usa", "newgrad"), "newgrad"),
    ("speedy_ng_intl", lambda: parse_speedy(http_get(SPEEDY_NG_INTL),
                                            "speedy_ng_intl", "newgrad"), "newgrad"),
    ("speedy_ng_ai",   lambda: parse_speedy(http_get(SPEEDY_NG_AI),
                                            "speedy_ng_ai", "newgrad"), "newgrad"),
    ("vansh_ng",       lambda: parse_vansh(http_get(VANSH_NG),
                                           "vansh_ng", "newgrad"), "newgrad"),
]


def season_years(text: str) -> set:
    """Every year named in a title/season string, with '2026/27' counted as both."""
    expanded = SPLIT_YEAR_RE.sub(lambda m: f"{m.group(1)} 20{m.group(2)}", text)
    return set(YEAR_RE.findall(expanded))


def matches(job: Job) -> bool:
    if REGIONS and "all" not in REGIONS and "eu" in REGIONS and not job.is_eu:
        return False
    if job.excluded_region:
        return False
    if MAX_AGE_DAYS > 0 and job.age_days is not None and job.age_days > MAX_AGE_DAYS:
        return False
    if SEASONS and job.season:
        if not any(s.lower() in job.season.lower() for s in SEASONS):
            return False
    # Only the engine API fills in .season; speedyapply and vansh bury it in the
    # title ("... - Fall 2026"), which is how 2026 postings used to slip through.
    # A title naming several years counts as a match if any of them is wanted.
    if SEASON_YEARS:
        years = season_years(f"{job.title} {job.season}")
        if years and not (years & SEASON_YEARS):
            return False
    if CATEGORIES and job.category:
        if not any(c.lower() == job.category.lower() for c in CATEGORIES):
            return False
    if EXCLUDE_SPONSORSHIP and job.sponsorship in EXCLUDE_SPONSORSHIP:
        return False
    blob = f"{job.title} {job.season}".lower()
    if TITLE_INCLUDE and not any(k in blob for k in TITLE_INCLUDE):
        return False
    if TITLE_EXCLUDE and any(k in blob for k in TITLE_EXCLUDE):
        return False
    return True


# --------------------------------------------------------------------------
# README listing tables
# --------------------------------------------------------------------------
README_FILE = Path(os.environ.get("README_FILE", Path(__file__).with_name("README.md")))
NEWGRAD_FILE = Path(os.environ.get("NEWGRAD_FILE", Path(__file__).with_name("NEW_GRAD.md")))
README_START = "<!-- LISTINGS:START -->"
README_END = "<!-- LISTINGS:END -->"
README_MAX_ROWS = int(os.environ.get("README_MAX_ROWS", "150"))

SOURCE_LABELS = {
    "engine": "engine", "speedy_usa": "speedy/US", "speedy_intl": "speedy/INTL",
    "speedy_ai": "speedy/AI", "vansh": "vansh", "eu": "eu",
    "speedy_ng_usa": "speedy/NG-US", "speedy_ng_intl": "speedy/NG-INTL",
    "speedy_ng_ai": "speedy/NG-AI", "vansh_ng": "vansh/NG",
}

# Everything that differs between the two boards, in one place.
TRACKS = {
    "intern": {
        "file": README_FILE, "noun": "internship", "emoji": "🔥",
        "topic": "NTFY_TOPIC", "faang_topic": "NTFY_TOPIC_FAANG",
    },
    "newgrad": {
        "file": NEWGRAD_FILE, "noun": "new grad", "emoji": "🎓",
        "topic": "NTFY_TOPIC_NEWGRAD", "faang_topic": "NTFY_TOPIC_NEWGRAD_FAANG",
    },
}


def sort_key(job: Job):
    """Newest first; listings with no date sink to the bottom, alphabetically."""
    return (0 if job.posted else 1, job.posted and _neg_date(job.posted),
            job.company.lower(), job.title.lower())


def _neg_date(iso: str) -> str:
    """Invert an ISO date so a plain ascending sort puts newest first."""
    return "".join(str(9 - int(c)) if c.isdigit() else c for c in iso)


def cell(text: str, limit: int = 0) -> str:
    t = " ".join(str(text).split()).replace("|", "\\|")
    if limit and len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return t or "—"


def age_label(job: Job) -> str:
    if not job.posted:
        return "—"
    days = job.age_days
    if days is None:
        return job.posted
    if days <= 0:
        return f"{job.posted} (today)"
    return f"{job.posted} ({days}d)"


def render_table(jobs: list[Job]) -> str:
    if not jobs:
        return "_No listings match your filters right now._\n"
    shown, hidden = jobs[:README_MAX_ROWS], jobs[README_MAX_ROWS:]
    out = ["| Posted | Company | Role | Location | Region | Visa situation | Salary | Source |",
           "|---|---|---|---|---|---|---|---|"]
    for j in shown:
        role = cell(j.title, 70)
        role = f"[{role}]({j.url})" if j.url else role
        out.append("| " + " | ".join([
            age_label(j), cell(j.company, 32), role, cell(j.location, 40),
            j.region, j.visa, cell(j.salary, 18),
            SOURCE_LABELS.get(j.source, j.source),
        ]) + " |")
    if hidden:
        out.append("")
        out.append(f"_+{len(hidden)} older listings not shown "
                   f"(raise `README_MAX_ROWS` to include them)._")
    return "\n".join(out) + "\n"


def render_listings(jobs: list[Job], track: str = "intern") -> str:
    cfg = TRACKS[track]
    ordered = sorted(jobs, key=sort_key)
    faang = [j for j in ordered if j.is_faang]
    other = [j for j in ordered if not j.is_faang]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    filters = ", ".join(f"`{k}={v}`" for k, v in (
        ("SEASONS", ",".join(SEASONS) or "any"),
        ("REGIONS", ",".join(REGIONS) or "all"),
        ("CATEGORIES", ",".join(CATEGORIES) or "any"),
        ("EXCLUDE_SPONSORSHIP", ",".join(EXCLUDE_SPONSORSHIP) or "none"),
        ("EXCLUDE_REGIONS", ",".join(EXCLUDE_REGIONS) or "none"),
        ("MAX_AGE_DAYS", str(MAX_AGE_DAYS) if MAX_AGE_DAYS > 0 else "off"),
    ))
    return "\n".join([
        README_START,
        "",
        "<!-- Generated by intern_watch.py — edits inside this block are overwritten. -->",
        "",
        f"## Current {cfg['noun']} openings — {len(jobs)} listings",
        "",
        f"Last updated **{stamp}** · {len(faang)} FAANG+ · {len(other)} other · "
        "sorted newest → oldest.",
        "",
        f"Active filters: {filters}",
        "",
        "**Visa column:** what the *source* claims, not legal advice. "
        "🛂 = explicitly no sponsorship, 🇺🇸 = citizens/permanent residents only, "
        "❔ = not stated — for EU/UK postings that means the local right to work, and "
        + ("for US postings OPT (which needs a US degree) or an H-1B."
           if track == "newgrad" else
           "for US postings enrolment at a US school (F-1/CPT)."),
        "",
        f"### {cfg['emoji']} FAANG+ ({len(faang)})",
        "",
        render_table(faang),
        f"### 🆕 Other companies ({len(other)})",
        "",
        render_table(other),
        README_END,
        "",
    ])


def update_board(jobs: list[Job], track: str) -> None:
    path = TRACKS[track]["file"]
    if not path.exists():
        print(f"{path.name} not found, skipping {track} table update", file=sys.stderr)
        return
    text = path.read_text(encoding="utf-8")
    block = render_listings(jobs, track)
    if README_START in text and README_END in text:
        head, rest = text.split(README_START, 1)
        _, tail = rest.split(README_END, 1)
        new = head + block.rstrip("\n") + tail
    else:
        new = text.rstrip("\n") + "\n\n---\n\n" + block
    if new != text:
        path.write_text(new, encoding="utf-8")
        print(f"{path.name} updated: {len(jobs)} {track} listings", file=sys.stderr)
    else:
        print(f"{path.name} unchanged", file=sys.stderr)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"seen": [], "repos_announced": []}
    try:
        d = json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"seen": [], "repos_announced": []}
    d.setdefault("seen", [])
    d.setdefault("repos_announced", [])
    return d


def save_state(s: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s))


NTFY_PRIORITIES = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5, "max": 5}


def send_ntfy(cfg, topic, title, message, click="", tags=None, priority="default"):
    server = (cfg.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    # ntfy's JSON API only accepts an integer 1-5 here; a string priority
    # (even a documented alias like "urgent") makes the whole request 400.
    p = {"topic": topic, "title": title, "message": message,
         "priority": NTFY_PRIORITIES.get(priority, priority)}
    if click:
        p["click"] = click
    if tags:
        p["tags"] = tags
    try:
        urllib.request.urlopen(urllib.request.Request(
            server, data=json.dumps(p).encode(),
            headers={"Content-Type": "application/json"}), timeout=15)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"ntfy {e.code} for topic {topic!r}: {detail}", file=sys.stderr)
        raise


def send_email(cfg, subject, body):
    m = MIMEText(body, "plain", "utf-8")
    m["From"], m["To"], m["Subject"] = cfg["SMTP_USER"], cfg["TO_EMAIL"], subject
    with smtplib.SMTP(cfg["SMTP_HOST"], int(cfg["SMTP_PORT"])) as s:
        s.starttls()
        s.login(cfg["SMTP_USER"], cfg["SMTP_PASS"])
        s.send_message(m)


def notify_group(cfg, jobs, group, topic, tags, priority):
    if not jobs or not topic:
        return
    if cfg["_has_ntfy"]:
        if len(jobs) <= NTFY_MAX_PER_RUN:
            for j in jobs:
                extra = f"\n💰 {j.salary}" if j.salary else ""
                send_ntfy(cfg, topic, f"{group} {j.company}",
                          f"{j.title}\n📍 {j.location}{extra}\n[{j.source}]",
                          click=j.url, tags=tags, priority=priority)
        else:
            lines = [f"• {j.label()}" for j in jobs[:40]]
            if len(jobs) > 40:
                lines.append(f"... +{len(jobs)-40} more")
            send_ntfy(cfg, topic, f"{group} {len(jobs)} new listings",
                      "\n".join(lines), tags=tags, priority=priority)
    if cfg["_has_email"]:
        body = []
        for j in jobs:
            body.append(f"- {j.label()}")
            meta = " | ".join(b for b in (j.season, j.category, j.sponsorship, j.salary) if b)
            if meta:
                body.append(f"  {meta}")
            body.append(f"  {j.url}\n")
        send_email(cfg, f"{group} — {len(jobs)} new listings", "\n".join(body))


def load_config() -> dict:
    c = dict(os.environ)
    c["_has_email"] = all(c.get(k) for k in
                          ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "TO_EMAIL"))
    c["_has_ntfy"] = bool(c.get("NTFY_TOPIC"))
    if not c["_has_email"] and not c["_has_ntfy"]:
        sys.exit("No notification channel configured: set NTFY_TOPIC or SMTP_*.")
    return c


def main() -> None:
    dry = "--dry-run" in sys.argv
    seed = "--seed" in sys.argv
    faang_only = "--faang-only" in sys.argv
    readme_only = "--readme" in sys.argv

    all_jobs = []
    for name, fn, track in SOURCES:
        try:
            g = fn()
            all_jobs.extend(g)
            print(f"[{name}] {len(g)}", file=sys.stderr)
        except Exception as e:
            print(f"[{name}] ERROR: {e}", file=sys.stderr)

    uniq = {}
    for j in all_jobs:
        # keyed by track too: the same URL can legitimately sit on both boards
        k = (j.track, j.url.split("?")[0])
        if k in uniq:
            if j.is_faang:
                uniq[k].is_faang = True
            if j.salary and not uniq[k].salary:
                uniq[k].salary = j.salary
            if j.season and not uniq[k].season:
                uniq[k].season = j.season
            # keep the earliest known posting date — sources disagree by a day or two
            if j.posted and (not uniq[k].posted or j.posted < uniq[k].posted):
                uniq[k].posted, uniq[k].posted_raw = j.posted, j.posted_raw
            if j.sponsorship and uniq[k].sponsorship in ("", "unknown"):
                uniq[k].sponsorship = j.sponsorship
        else:
            uniq[k] = j

    listed = [j for j in uniq.values() if matches(j)]
    by_track = {t: [j for j in listed if j.track == t] for t in TRACKS}

    # --dry-run stays side-effect free unless a board rewrite is the point of the run
    if readme_only or not dry:
        for track, track_jobs in by_track.items():
            update_board(track_jobs, track)
    if readme_only:
        return

    print(f"\ntotal {len(all_jobs)} | unique {len(uniq)} | listed {len(listed)}",
          file=sys.stderr)

    state = load_state()
    seen = set(state["seen"])
    cfg = None if (dry or seed) else load_config()
    keep_seen = []

    for track, track_jobs in by_track.items():
        noun, emoji = TRACKS[track]["noun"], TRACKS[track]["emoji"]
        jobs = [j for j in track_jobs if j.is_faang] if faang_only else track_jobs
        keep_seen.extend(jobs)
        new = [j for j in jobs if j.uid not in seen]
        faang_new = [j for j in new if j.is_faang]
        other_new = [j for j in new if not j.is_faang]

        print(f"\n[{noun}] filtered {len(jobs)} | NEW {len(new)} "
              f"(FAANG+ {len(faang_new)} / other {len(other_new)})", file=sys.stderr)

        if dry:
            for grp, lst in ((f"{emoji} FAANG+", faang_new), ("🆕 Other", other_new)):
                if not lst:
                    continue
                print(f"\n===== [{noun}] {grp} ({len(lst)}) =====")
                for j in lst:
                    meta = " | ".join(b for b in (j.posted, j.season, j.category,
                                                  j.sponsorship, j.salary) if b)
                    print(f"- [{j.source}]{' 🇪🇺' if j.is_eu else ''} {j.label()}")
                    if meta:
                        print(f"    {meta}")
                    print(f"    {j.url}")
            continue
        if seed:
            continue

        # An unset topic means the board is silent — that is how the new grad
        # track stays opt-in instead of ambushing you with a thousand postings.
        topic = cfg.get(TRACKS[track]["topic"])
        if not topic:
            print(f"[{noun}] {TRACKS[track]['topic']} unset, notifications off",
                  file=sys.stderr)
            continue
        faang_topic = cfg.get(TRACKS[track]["faang_topic"]) or topic
        notify_group(cfg, faang_new, f"{emoji} FAANG+", faang_topic,
                     ["fire", "rotating_light"], "urgent")
        if not faang_only:
            notify_group(cfg, other_new, f"🆕 {noun}", topic, ["briefcase"], "high")

    if seed:
        print("--seed: marked as seen, no notifications sent.", file=sys.stderr)
    elif not dry:
        for repo, path in WATCH_REPOS:
            if repo in state["repos_announced"]:
                continue
            if http_exists(f"{RAW}/{repo}/{path}"):
                send_ntfy(cfg, cfg.get("NTFY_TOPIC"), f"🎉 {repo} is live!",
                          "New season repo has been published.",
                          click=f"https://github.com/{repo}",
                          tags=["tada"], priority="high")
                state["repos_announced"].append(repo)

    if dry:
        # --dry-run must not consume the "new" queue: persisting here would mark
        # everything as seen and those postings would never notify.
        return
    state["seen"] = sorted(seen | {j.uid for j in keep_seen})
    save_state(state)


if __name__ == "__main__":
    main()
