# OpenClaw — App State Reference

**Last updated:** 2026-03-15

---

## What is OpenClaw?

A self-hosted, local-first job hunting pipeline for a software engineer actively searching for remote Web3 / backend / AI roles. It runs entirely inside Docker (`docker compose up`), exposes a React dashboard at `http://localhost:8000`, and has no external server cost. It scrapes multiple job sources, scores every listing against a candidate profile using an LLM, tailors your LaTeX resume to each role, compiles it to PDF, and lets you manage the whole application workflow from one UI.

---

## Architecture Overview

```
Docker container (single service)
│
├── Stage 1 build (node:20-slim)
│   └── React + Vite frontend → compiled to /src/frontend/dist
│
└── Stage 2 runtime (python:3.12-slim)
    ├── texlive-latex-extra + latexmk   → PDF compilation
    ├── Playwright + Chromium            → JS-rendered scraping
    ├── FastAPI (uvicorn --reload)       → API + serves React SPA
    └── APScheduler                      → daily 08:00 IST scrape
```

**Volumes mounted at runtime (no rebuild needed for Python changes):**
- `./data` → `/app/data` — SQLite DB, compiled resumes, PDFs
- `./resume` → `/app/resume` (read-only) — your master LaTeX resume source
- `./src/backend` → `/app/src/backend` — hot-reload Python code

The React build is baked into the image at `/app/src/frontend/dist`. FastAPI serves it as a SPA for all non-API routes.

---

## Directory Structure

```
openclaw-scraper/
├── src/
│   ├── backend/
│   │   ├── main.py        FastAPI app, all API routes, APScheduler
│   │   ├── db.py          SQLite helpers, schema, migrations
│   │   ├── scraper.py     All scrapers + filtering + scoring
│   │   ├── tailor.py      Resume tailoring, PDF compilation, fit-check
│   │   └── llm.py         OpenAI / Anthropic client wrapper
│   └── frontend/
│       ├── src/
│       │   ├── App.jsx         Router + nav layout
│       │   ├── pages/
│       │   │   ├── Jobs.jsx    Queue tab + All Results tab + Paste URL
│       │   │   ├── Funded.jsx  Funded companies table
│       │   │   ├── Resumes.jsx Resume variants list + download
│       │   │   ├── Journal.jsx Daily work log
│       │   │   └── Config.jsx  Search config + candidate profile
│       │   ├── components/
│       │   │   ├── TailorModal.jsx    Tailor flow, fit-warning handling
│       │   │   └── JobDetailModal.jsx Sidebar job detail view
│       │   └── api.js          All fetch calls to FastAPI
│       └── dist/               Built by Docker Stage 1
├── data/
│   ├── jobs.db             SQLite database (persisted via volume)
│   └── resumes/            Output dirs for each tailored variant
├── resume/                 Master LaTeX resume (mounted read-only)
├── docs/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env                    API keys (never committed)
└── .env.example
```

---

## Database Schema

**`jobs`** — every scraped and manually-pasted job
| column | type | notes |
|---|---|---|
| id | TEXT PK | MD5 hash of source + url |
| source | TEXT | hn_jobs / hn_whoishiring / web3career / cryptorank_funding / dropstab_funding / manual |
| title | TEXT | |
| company | TEXT | |
| url | TEXT | |
| description | TEXT | up to 2000 chars |
| score | INTEGER | 0–100, LLM-scored |
| reason | TEXT | ≤120 char explanation from LLM |
| status | TEXT | new / applied / skipped / tailored / filtered |
| work_type | TEXT | remote / hybrid / onsite / unspecified |
| location | TEXT | |
| posted_at | TEXT | ISO datetime where available |
| found_at | TEXT | IST timestamp of scrape |

**`funded_companies`** — companies that raised recent funding rounds
| column | type | notes |
|---|---|---|
| id | TEXT PK | |
| company | TEXT | |
| amount | TEXT | e.g. "$5M" |
| round_type | TEXT | Seed / Series A / etc. |
| careers_url | TEXT | found via DuckDuckGo search |
| source_url | TEXT | link to CryptoRank project page |
| announced_at | TEXT | date from source |
| found_at | TEXT | IST timestamp |

**`ats_companies`** — registry of companies to poll via ATS APIs
| column | type | notes |
|---|---|---|
| id | TEXT PK | MD5 of platform+slug |
| platform | TEXT | greenhouse / lever / ashby |
| slug | TEXT | company slug used in ATS API URL |
| company_name | TEXT | display name |
| discovered_via | TEXT | seed / hn_whoishiring / github_hww / github_remoteintech |
| last_fetched | TEXT | ISO timestamp of last successful job fetch |
| active | INTEGER | 1 = active, 0 = disabled |

**`config`** — key/value store
| key | value |
|---|---|
| search | JSON blob with filter settings (see below) |
| profile | Candidate profile text (used by LLM scoring + tailoring) |
| ats_github_discovery_last_run | ISO timestamp of last GitHub list fetch (weekly) |

**search config keys:**
| key | default | description |
|---|---|---|
| keywords | web3, blockchain, ... | Job text must match ≥1 keyword |
| work_type | ["remote"] | Allowed work types |
| min_yoe / max_yoe | 0 / 5 | YoE range filter |
| exclude_locations | [...] | Strings that must not appear in job text |
| score_threshold | 60 | Minimum LLM score to surface a job |
| skip_title_patterns | [...] | Title substrings that instantly disqualify a job (pre-LLM). Catches marketing, HR, mechanical engineer, etc. Edit via Config page raw JSON. |

**`journal`** — daily work log entries
| column | type |
|---|---|
| id | INTEGER AUTOINCREMENT |
| entry | TEXT |
| created_at | TEXT (IST ISO) |

**`resume_variants`** — every tailored resume ever generated
| column | type | notes |
|---|---|---|
| id | TEXT PK | MD5 of company+timestamp |
| job_id | TEXT | FK to jobs.id if sourced from a job listing |
| company | TEXT | |
| title | TEXT | |
| variant_name | TEXT | |
| out_dir | TEXT | path inside container: /app/data/resumes/company_YYYYMMDD_HHMM |
| zip_path | TEXT | Overleaf-ready zip |
| pdf_path | TEXT | compiled PDF path (empty if latexmk failed) |
| changed_files | TEXT | JSON array of sections actually modified |
| job_score | INTEGER | score at time of tailoring |
| created_at | TEXT | IST ISO timestamp |

**Migrations** run automatically on every startup via `_migrate()` — adds missing columns with `ALTER TABLE ... ADD COLUMN` without destroying data.

---

## API Routes

All at `http://localhost:8000`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/jobs` | Jobs by status (new/applied/etc), paginated, sorted by score desc |
| GET | `/api/jobs/all` | All jobs with optional source/status filter |
| GET | `/api/jobs/{id}` | Single job detail |
| POST | `/api/jobs/{id}/status` | Update status: new / applied / skipped / tailored |
| POST | `/api/scrape` | Trigger scrape (background, non-blocking). Accepts optional `sources` list |
| GET | `/api/scrape/status` | Returns `{running, last_result, last_run}` |
| POST | `/api/tailor` | Tailor resume. Body: `{job_id?, url?, raw_jd?, variant_name?, force?}` |
| GET | `/api/variants` | List all resume variants |
| GET | `/api/variants/{id}/pdf` | Download compiled PDF |
| GET | `/api/variants/{id}/zip` | Download Overleaf-ready ZIP |
| GET | `/api/funded` | List funded companies |
| GET | `/api/journal` | Get journal entries |
| POST | `/api/journal` | Add a journal entry |
| POST | `/api/resumediff` | LLM analysis of journal → resume update suggestions |
| GET | `/api/config` | Get search config |
| PUT | `/api/config` | Save search config |
| GET | `/api/profile` | Get candidate profile text |
| PUT | `/api/profile` | Save candidate profile text |
| POST | `/api/profile/sync-from-journal` | LLM rewrites profile using recent journal entries (preview only — not auto-saved) |

---

## Scraping Pipeline

### How a scrape run works

1. `POST /api/scrape` triggers `_run_scrape_bg()` as a FastAPI background task.
2. `scraper.run_scrape(sources)` is called in a thread pool executor (non-blocking).
3. Each enabled scraper returns a list of raw job dicts.
4. `passes_filters()` checks each job against the search config.
5. Filtered jobs are scored via LLM (`score_job()`).
6. All jobs saved to DB (`INSERT OR IGNORE` — duplicates skipped).
7. Result summary stored in `_scrape_state` for `/api/scrape/status`.
8. APScheduler also triggers a full scrape every day at **08:00 IST**.

### Sources

**`hn_jobs`** — Hacker News YC company job posts
Uses the **Algolia HN search API** (`search_by_date`, `tags=job`) with a 30-day cutoff filter. Returns the most recent job posts, not the mixed old/new HTML page. Gets `posted_at` from `created_at` field. Typically ~30–40 recent postings.

**`hn_whoishiring`** — HN "Who is Hiring?" thread
Finds the latest monthly "Ask HN: Who is Hiring?" thread via Algolia, then fetches its children (comments) from the HN items API. Each top-level comment is treated as a job post. Parses company name from the first pipe-delimited segment of the first line. Gets `posted_at` from comment's `created_at_i` epoch timestamp.
**Side-effect:** every comment is scanned for Greenhouse/Lever/Ashby URLs, which are auto-added to `ats_companies` for future fetching.

**`web3career`** — web3.career/remote-jobs
Uses Playwright (headless Chromium, 3s wait) to render the JS-heavy page. The page uses a `<table>` where each job has multiple `<td data-jobid="N">` cells:
- `td[data-jobid][scope='row']` → title cell, contains `<a href="/slug/N"><h2>Title</h2></a>`
- next sibling td → company in `<h3>`
- next → `<time datetime="...">` for `posted_at`
- next → location text
- last → badge/tag elements

Extracts title, company, URL, location, `posted_at`, and tags. Falls back to first-per-jobid approach if no `scope=row` cells found.

**`cryptorank_funding`** — cryptorank.io/funding-rounds
Uses Playwright with 3 scroll passes to load the infinite-scroll table. Parses `<table tbody tr>` rows; extracts company name, funding amount (any cell with `$`/`M`/`B`/`K` + digits), round type (seed/series/etc. keywords), and announcement date (month name / year pattern). Skips header rows, "Sum:" rows, and duplicates. Saves to `funded_companies` with the CryptoRank project page URL as `source_url`. Then runs `_find_careers()` on each company to look for a careers page.

**`dropstab`** — dropstab.com/latest-fundraising-rounds
Uses Playwright (3s wait). Parses `tbody tr` rows for company, amount, and round type. Also runs `_find_careers()` per company. Saves to `funded_companies`.

**`ats`** — Direct ATS platform APIs (Greenhouse, Lever, Ashby)
Polls the `ats_companies` table for all active companies not fetched in the last 23 hours. Uses `aiohttp` + `asyncio` to fan out 200+ API calls in parallel (30 concurrent connections, 3 per host). Returns full job descriptions with no scraping, no auth, no rate limits.

| Platform | API endpoint | Key fields returned |
|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | HTML description, location |
| Lever | `api.lever.co/v0/postings/{slug}?mode=json` | descriptionPlain, workplaceType, commitment |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{slug}` | descriptionPlain, isRemote, workplaceType |

Company discovery layers (run in order each scrape):
1. **Seed list** — ~50 hardcoded web3/crypto/tech companies seeded on first run
2. **Common Crawl index** — queries CC's CDX API for all company slugs ever indexed across Greenhouse/Lever/Ashby domains. Discovers ~3,900 companies. Runs weekly.
3. **HN discovery** — ATS URLs extracted from `hn_whoishiring` comments each scrape
4. **GitHub lists** — `poteto/hiring-without-whiteboards` and `remoteintech/remote-jobs` fetched weekly

Batching: max 500 companies fetched per scrape run (oldest-first rotation). Full list covered in ~8 daily runs.

**`_find_careers(company_name)`** — DuckDuckGo careers page search
Searches `"<company>" jobs careers` via the DDG HTML endpoint. Prioritises results from known ATS domains (Lever, Greenhouse, Ashby, Workable). Also matches `/careers` or `/jobs` URLs where the company name slug appears in the URL. Unwraps DDG's `?uddg=` redirect wrapping.

### Filtering (`passes_filters`)

**Step 1 — Title pre-filter (`passes_title_filter`)** runs first. Checks job title against `skip_title_patterns` from config. Instantly drops non-relevant roles (marketing manager, mechanical engineer, recruiter, etc.) before any other check. Zero cost. Configurable via Config page raw JSON.

**Step 2 — Search config filter (`passes_filters`)** runs after title filter. Checks:
1. **Keywords** — job text must contain at least one keyword from config (case-insensitive)
2. **Work type** — if config has `work_type` list, job's detected work type must match (unspecified jobs pass through)
3. **Exclude locations** — any string in `exclude_locations` list must not appear in job text/location
4. **YoE cap** — regex `(\d+)\s*(?:\+|to|-|–)?\s*\d*\s*years?\s*(?:of\s*)?(?:experience|exp)` extracts required minimum years from description; if that number exceeds `max_yoe`, job is filtered out

Default config: keywords include web3/blockchain/solidity/fullstack/backend/go/python/AI/LLM, work_type=remote, max_yoe=5.

### Scoring (`score_job`)

Calls `llm.chat_json()` with a short prompt including the candidate profile (from DB) and the job details. Returns `{"score": 0-100, "reason": "..."}`. Uses the cheaper scoring model (`MODEL_NAME`, default `claude-haiku-4-5-20251001`). Score 0 forced if: physical presence required, or 5+ years experience required for a 2-year candidate.

---

## Resume Tailoring

### Flow

1. UI sends `POST /api/tailor` with `job_id` (or `url` or `raw_jd`), optional `variant_name`, and `force: false`.
2. **Fit check**: if `job_id`, reuses the already-computed score. Otherwise calls `check_fit()` (same LLM prompt as scoring). If score < 35 and `force=false`, returns `{"fit_warning": true, "score": N, "reason": "..."}`.
3. UI shows an amber warning box with the score and reason, offering "Tailor anyway" (retries with `force: true`) or "Skip".
4. If fit passes, `build_prompt()` assembles a LaTeX editing prompt with the job description and the 6 tailorable resume sections.
5. LLM (`TAILOR_MODEL`, default `claude-sonnet-4-6`) returns a JSON object of only the changed sections.
6. Output folder created at `/app/data/resumes/<company>_<YYYYMMDD_HHMM>/`.
7. All files written (changed + unchanged sections, header, style file).
8. `make_zip()` — creates an Overleaf-ready ZIP at `<out_dir>.zip`.
9. `compile_pdf()` — runs `latexmk -pdf -interaction=nonstopmode` inside the output dir. Produces `resume.pdf` if successful.
10. Variant saved to `resume_variants` table with paths to both ZIP and PDF.

### Resume file layout

The master resume lives at `./resume/` (mounted read-only). Structure expected:

```
resume/
├── resume.tex              main file (includes all sections)
├── _header.tex             personal info, contact links
├── TLCresume.sty           custom LaTeX class
└── sections/
    ├── objective.tex       ← tailored per role
    ├── experience.tex      ← tailored per role
    ├── skills.tex          ← tailored per role
    ├── projects.tex        ← tailored per role
    ├── achievements.tex    ← tailored per role
    ├── security.tex        ← tailored per role
    ├── education.tex       (copied, not modified)
    ├── certifications.tex  (copied, not modified)
    ├── hobbies.tex         (copied, not modified)
    └── por.tex             (copied, not modified)
```

---

## Candidate Profile

Stored in the `config` table under key `profile`. Defaults to a short plaintext summary of Suhel's stack, experience level, and preferences. Used in every LLM scoring and tailoring call.

**Update methods:**
- **Config page** → paste directly into textarea → Save
- **Journal page** → "Sync Profile from Journal" → shows LLM-generated preview → confirm Save
- **Config page** → "Sync from Journal" button → same flow

---

## Frontend Pages

**Jobs (`/`)** — two tabs:
- *Queue*: new/high-score jobs, each card shows title, company, score, tags. Click to open `JobDetailModal` sidebar. Tailor button opens `TailorModal`.
- *All Results*: full paginated list with source and status filters.
- *Paste Job URL*: text field at top for manually adding jobs from any source (hiring.cafe, LinkedIn, etc.). Fetches JD from URL, runs fit check, adds to DB.

**Funded (`/funded`)** — table of funded companies from CryptoRank/Dropstab with columns: Company, Amount, Round, Date, and links to the CryptoRank page and careers page. Client-side search filter.

**Resumes (`/resumes`)** — list of all tailored variants, sorted newest first. Shows company, job title, score at time of tailoring, changed files count, timestamp. Download PDF or ZIP per variant.

**Journal (`/journal`)** — textarea to log daily work. Entries stored with IST timestamps. "Suggest Resume Updates" button calls `/api/resumediff` and shows LLM suggestions. "Sync Profile from Journal" previews an updated candidate profile before saving.

**Config (`/config`)** — editable JSON fields for:
- Keywords (tag list)
- Work type allowed (remote/hybrid/onsite checkboxes)
- Max YoE
- Score threshold
- Exclude locations
- Candidate profile textarea

---

## LLM Configuration

Set in `.env`:

```
MODEL_PROVIDER=anthropic          # or openai
MODEL_API_KEY=sk-ant-...
MODEL_NAME=claude-haiku-4-5-20251001   # used for scoring (fast, cheap)
TAILOR_MODEL=claude-sonnet-4-6         # used for tailoring (more capable)
```

`llm.py` abstracts both providers behind `chat(prompt)` and `chat_json(prompt)`.

---

## Setup & Running

```bash
cp .env.example .env
# fill in MODEL_API_KEY

docker compose up --build
# first build ~5-10 min (downloads texlive + Playwright chromium)
# subsequent starts are fast

# open http://localhost:8000
```

Hot reload: any change to `./src/backend/*.py` is picked up instantly by uvicorn's `--reload` (no rebuild needed).

To trigger a manual scrape from the UI: Jobs page → "Scrape Now" button.

---

## Known Limitations

- **web3career** loads only the first page (~15 jobs). No pagination implemented yet.
- **dropstab** selectors are broad and may need tuning if the site changes its markup.
- **`_find_careers()`** is rate-limited by DuckDuckGo; with 19+ companies it can return empty results for some. No retry/backoff.
- **PDF compilation** fails silently if `resume.tex` uses packages not in `texlive-latex-extra`. Check `/app/data/resumes/<variant>/` for `.log` file.
- **`/api/resumediff`** has the resume overview hardcoded in the prompt (not reading from the actual `.tex` files). Should be updated to read from the master resume.
- **ATS slug accuracy** — seed list slugs are best-effort guesses; wrong slugs 404 silently. Discovery layers (HN, GitHub) add verified slugs over time.
- **ATS first run** — seeds ~150 companies; the `last_fetched` logic means subsequent daily scrapes only re-hit companies not fetched in the last 23 hours, so the second day onward is fast.
