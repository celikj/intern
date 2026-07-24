# intern-watch

Early-warning system for internship postings. Scans 6 sources and pushes a phone notification only for **new** postings. FAANG+ postings go out on a separate, high-priority channel.

Runs on GitHub Actions — you get notified even while your computer is off.

## Sources

| Source | Coverage |
|---|---|
| zshah101 Internship Engine (JSON API) | ATS data for 3,870 companies, hourly |
| speedyapply/2027-SWE-College-Jobs | US, split into FAANG+/Quant/Other |
| speedyapply INTERN_INTL.md | International (including Europe) |
| speedyapply/2027-AI-College-Jobs | AI/ML, international |
| vanshb03/Summer2027-Internships | US/Canada community list |
| LorenzoLaCorte/european-tech-internships | Europe |

Also notifies the moment `SimplifyJobs/Summer2027-Internships` opens.

---

## Setup

### 1. Create a repo

Create a new repo on GitHub (**Public** is recommended — see the note below), and add these files:

```
intern_watch.py
README.md
.github/workflows/watch.yml
```

```bash
git init
git add .
git commit -m "intern-watch setup"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/intern-watch.git
git push -u origin main
```

> **Public or private?** Scheduled workflows on public repos are unlimited and free.
> A private repo eats into your monthly Actions minutes (2,000 min/month on the free plan), but at every-5-hours this uses only a few minutes a day either way.
> Your notification topics are already stored in Secrets, so they stay hidden even if the repo is public.

### 2. Set up your phone

1. Install the **ntfy** app (Android: Play Store / F-Droid, iOS: App Store)
2. Subscribe to two topics — pick names that are **long and unguessable**
   (on ntfy.sh, anyone who knows the topic name can read the messages):
   - `intern-general-<random>`
   - `intern-faang-<random>`
3. Assign a custom ringtone / high priority to the FAANG topic in the app

### 3. Add secrets

Repo → **Settings → Secrets and variables → Actions → Secrets → New repository secret**

| Secret | Value |
|---|---|
| `NTFY_TOPIC` | your general topic name |
| `NTFY_TOPIC_FAANG` | your FAANG topic name |

Email is optional too: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `TO_EMAIL`.
For Gmail you need an [App Password](https://myaccount.google.com/apppasswords), not your regular password.

### 4. Filters (optional)

Same page, **Variables** tab → New repository variable

| Variable | Default | Description |
|---|---|---|
| `SEASONS` | `2027` | Season filter |
| `REGIONS` | `all` | `all` or `eu` (Europe/Turkey only) |
| `CATEGORIES` | *(empty)* | `Software`, `Data & ML/AI`, `AI/ML`, `Quant`, `Hardware`, `Security` |
| `EXCLUDE_SPONSORSHIP` | `no-sponsorship,citizens-only` | Filters out postings you're not eligible for |
| `TITLE_EXCLUDE` | `phd,ph.d,masters,master's,mba` | Filters out postings whose title contains these |
| `NTFY_MAX_PER_RUN` | `12` | Sends a single summary notification if this count is exceeded |

### 5. FIRST RUN — seed first!

⚠️ Skip this and all ~800 existing postings will count as "new".

Repo → **Actions** → `intern-watch` → **Run workflow** → mode: **`seed`** → Run

This marks all current postings as "seen" and commits them as `state/state.json`. No notifications are sent.

### 6. Done

From here it runs automatically every 5 hours. Only genuinely **new** postings trigger a notification.

---

## Usage notes

**Manual run:** Actions → Run workflow → choose mode
- `normal` — standard (default)
- `faang-only` — only notify for FAANG+
- `dry-run` — show in the log without sending notifications
- `seed` — mark existing postings as seen

**Viewing logs:** Actions → latest run → `Run scan` step.
It shows how many postings were found, how many are new, and how many are FAANG+.

**Changing filters:** Update the Variables — no code change needed.

---

## Good to know

- **Cron delay:** GitHub can delay scheduled jobs under load, but at a 5-hour cadence an occasional delay doesn't matter.
- **60-day rule:** If a repo has zero activity for 60 days, GitHub disables its scheduled workflows and emails you. This system commits state on every new posting, so it normally won't trigger — but if you do get that email, re-enable it with one click from Actions.
- **New season:** You'll get notified when `SimplifyJobs/Summer2027-Internships` opens. To add it to the source list, add a line to `SOURCES` in `intern_watch.py`.
- **Visa reality check:** Most sources are US-focused. US internships usually require students enrolled in the US (F-1/CPT). If you're in Europe, `REGIONS=eu` will give more relevant results.
