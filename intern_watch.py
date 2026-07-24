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

# --------------------------------------------------------------------------
# Filter settings
# --------------------------------------------------------------------------
SEASONS = [s.strip() for s in os.environ.get("SEASONS", "2027").split(",") if s.strip()]
CATEGORIES = [c.strip() for c in os.environ.get("CATEGORIES", "").split(",") if c.strip()]
EXCLUDE_SPONSORSHIP = [s.strip() for s in os.environ.get(
    "EXCLUDE_SPONSORSHIP", "no-sponsorship,citizens-only").split(",") if s.strip()]
TITLE_INCLUDE = [k.strip().lower() for k in os.environ.get("TITLE_INCLUDE", "").split(",") if k.strip()]
TITLE_EXCLUDE = [k.strip().lower() for k in os.environ.get("TITLE_EXCLUDE", "").split(",") if k.strip()]
# REGIONS: all / eu   (eu -> only Europe-located listings)
REGIONS = [r.strip().lower() for r in os.environ.get("REGIONS", "all").split(",") if r.strip()]
NTFY_MAX_PER_RUN = int(os.environ.get("NTFY_MAX_PER_RUN", "12"))


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
    is_faang: bool = False
    flags: list = field(default_factory=list)

    @property
    def is_eu(self) -> bool:
        loc = self.location.lower()
        return any(k in loc for k in EU_KEYWORDS)

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


def md_url(cell: str) -> str:
    m = HREF_RE.search(cell)
    if m:
        return m.group(1)
    m = MD_LINK_RE.search(cell)
    return m.group(2) if m else ""


def parse_speedy(md: str, source_name: str) -> list[Job]:
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

        jobs.append(Job(
            uid=f"{source_name}:{url.split('?')[0]}",
            company=company,
            title=md_clean(cell("position") or cell("role")),
            location=md_clean(cell("location")),
            url=url, source=source_name,
            salary=md_clean(cell("salary")),
            category="AI/ML" if source_name.endswith("ai") else "Software",
            is_faang=section.startswith("faang") or is_faang_company(company),
        ))
    return jobs


def parse_vansh(md: str) -> list[Job]:
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
        jobs.append(Job(
            uid=f"vansh:{url.split('?')[0]}", company=company, title=title.strip(),
            location=md_clean(cells[2]), url=url, source="vansh",
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
            is_faang=is_faang_company(comp),
        ))
    return out


SOURCES = [
    ("engine",      fetch_engine),
    ("speedy_usa",  lambda: parse_speedy(http_get(SPEEDY_USA), "speedy_usa")),
    ("speedy_intl", lambda: parse_speedy(http_get(SPEEDY_INTL), "speedy_intl")),
    ("speedy_ai",   lambda: parse_speedy(http_get(SPEEDY_AI_INTL), "speedy_ai")),
    ("vansh",       lambda: parse_vansh(http_get(VANSH))),
    ("eu",          lambda: parse_eu(http_get(EU_REPO))),
]


def matches(job: Job) -> bool:
    if REGIONS and "all" not in REGIONS and "eu" in REGIONS and not job.is_eu:
        return False
    if SEASONS and job.season:
        if not any(s.lower() in job.season.lower() for s in SEASONS):
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
        send_email(cfg, f"{group} {len(jobs)} new internship listings", "\n".join(body))


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

    all_jobs = []
    for name, fn in SOURCES:
        try:
            g = fn()
            all_jobs.extend(g)
            print(f"[{name}] {len(g)}", file=sys.stderr)
        except Exception as e:
            print(f"[{name}] ERROR: {e}", file=sys.stderr)

    uniq = {}
    for j in all_jobs:
        k = j.url.split("?")[0]
        if k in uniq:
            if j.is_faang:
                uniq[k].is_faang = True
            if j.salary and not uniq[k].salary:
                uniq[k].salary = j.salary
            if j.season and not uniq[k].season:
                uniq[k].season = j.season
        else:
            uniq[k] = j

    jobs = [j for j in uniq.values() if matches(j)]
    if faang_only:
        jobs = [j for j in jobs if j.is_faang]

    state = load_state()
    seen = set(state["seen"])
    new = [j for j in jobs if j.uid not in seen]
    faang_new = [j for j in new if j.is_faang]
    other_new = [j for j in new if not j.is_faang]

    print(f"\ntotal {len(all_jobs)} | unique {len(uniq)} | filtered {len(jobs)} | "
          f"NEW {len(new)} (FAANG+ {len(faang_new)} / other {len(other_new)})", file=sys.stderr)

    if dry:
        for grp, lst in (("🔥 FAANG+", faang_new), ("🆕 Other", other_new)):
            if not lst:
                continue
            print(f"\n===== {grp} ({len(lst)}) =====")
            for j in lst:
                meta = " | ".join(b for b in (j.season, j.category, j.sponsorship, j.salary) if b)
                print(f"- [{j.source}]{' 🇪🇺' if j.is_eu else ''} {j.label()}")
                if meta:
                    print(f"    {meta}")
                print(f"    {j.url}")
    elif seed:
        print("--seed: marked as seen, no notifications sent.", file=sys.stderr)
    else:
        cfg = load_config()
        faang_topic = cfg.get("NTFY_TOPIC_FAANG") or cfg.get("NTFY_TOPIC")
        notify_group(cfg, faang_new, "🔥 FAANG+", faang_topic,
                     ["fire", "rotating_light"], "urgent")
        if not faang_only:
            notify_group(cfg, other_new, "🆕", cfg.get("NTFY_TOPIC"),
                         ["briefcase"], "high")
        for repo, path in WATCH_REPOS:
            if repo in state["repos_announced"]:
                continue
            if http_exists(f"{RAW}/{repo}/{path}"):
                send_ntfy(cfg, cfg.get("NTFY_TOPIC"), f"🎉 {repo} is live!",
                          "New season repo has been published.",
                          click=f"https://github.com/{repo}",
                          tags=["tada"], priority="high")
                state["repos_announced"].append(repo)

    state["seen"] = sorted(seen | {j.uid for j in jobs})
    save_state(state)


if __name__ == "__main__":
    main()
