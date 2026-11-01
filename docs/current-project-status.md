**Project: Automated Job Hunting Pipeline**

**What I'm building**

A personal job hunting system that runs as a Telegram bot in Docker on my Mac. The idea is to automate the most tedious parts of job searching — discovering relevant jobs, filtering out irrelevant ones, and tailoring my resume for each application — while keeping me in control of the actual applying. No automated applications, just automated discovery and preparation.

**Background context**

I'm Suhel Kapadia, a full stack engineer with 2+ years of experience based in Gujarat, India. My stack is primarily Web3 (Solidity, ERC4337, Ethers.js, Wagmi), backend (Go, Node.js, NestJS, Python, PostgreSQL, Redis, RabbitMQ), and AI pipelines (LangChain, PGVector). Currently working at RapbitNode building enterprise AI data pipelines, and part-time at Syntax Studios. Looking for remote roles in Web3, backend, or AI — never onsite, never pure frontend.

My resume lives on Overleaf and is split across multiple `.tex` files (`resume.tex`, `_header.tex`, `sections/experience.tex`, `sections/skills.tex`, `sections/objective.tex`, `sections/projects.tex`, etc.).

---

**Job sources being scraped**

- `news.ycombinator.com/jobs` — paid YC startup job postings, clean HTML scrape
- HN "Who Is Hiring" monthly thread — via the HN Algolia API (`hn.algolia.com/api`), returns clean JSON, no scraping needed
- `web3.career/remote-jobs` — remote Web3 jobs, server-rendered HTML scrape
- `cryptorank.io/funding-rounds` — recently funded crypto/Web3 companies; the idea is companies that just raised are actively hiring with low application competition. For each company found, the system searches for their careers page on Lever, Greenhouse, or Ashby automatically
- `dropstab.com/latest-fundraising-rounds` — another funding rounds source (JS-rendered, handled via browser automation)

Sources intentionally skipped for now due to aggressive bot protection: LinkedIn, Glassdoor, Wellfound, hiring.cafe. These can be handled manually by pasting job URLs directly into the Telegram bot.

---

**Features built**

**Core pipeline**

- Scrapes all sources on demand or automatically every morning at 08:00 IST via APScheduler
- Keyword filtering before scoring (saves API calls) — keywords, work type (remote/onsite/hybrid), location exclusions, and YoE range are all configurable from Telegram
- Work type and location auto-detected from job text; onsite jobs auto-score 0
- Each job scored 0–100 against my candidate profile using OpenAI (`gpt-4o-mini` for scoring, `gpt-4o` for tailoring)
- All jobs saved to SQLite with score, source, reason, work type, location, and status

**Telegram bot interface**

- Inline keyboard menu on every message — no need to remember commands
- `/scrape` or 🔍 button — runs a fresh scrape, sends a digest of matched jobs
- 📋 My Queue — lists new jobs above the score threshold with per-job buttons: ✍️ Tailor, 🔗 Open link, ⏭ Skip
- 📊 All Results — paginated view of every scraped job with score, source, work type, and status, 10 per page
- 💰 Funded Companies — shows recently funded companies with careers page links
- ⚙️ Config — view and edit search settings (keywords, work type filter, location exclusions, score threshold) without touching code, e.g. `/config work_type remote,hybrid`
- 💾 Backup DB — sends the raw SQLite file to Telegram chat so data persists even on free hosting with no persistent disk
- `/applied <id>` and `/skip <id>` — status tracking

**Resume tailoring**

- `/tailor <job_id>` or `/tailor <url>` — fetches the full job description, sends all content `.tex` files to `gpt-4o`, gets back only the files that changed as JSON, merges with originals
- Output is a complete `.zip` file sent directly to Telegram — can be uploaded straight to Overleaf via "Upload Project"
- Only content files are modified (`experience.tex`, `skills.tex`, `objective.tex`, `projects.tex`, `achievements.tex`, `security.tex`) — structural and style files (`TLCresume.sty`, `resume.tex`, `_header.tex`) are never touched

**Daily journal → resume sync**

- `/journal <what you worked on today>` — logs work entries with IST timestamp
- `/resumediff` — sends all recent journal entries to the LLM, compares against current resume, returns specific suggested bullet points and skill additions as LaTeX-ready text

**LLM provider abstraction**

- A `llm.py` wrapper means the whole system works with either OpenAI or Anthropic
- Controlled via `.env`: `MODEL_PROVIDER=openai` or `MODEL_PROVIDER=anthropic`, `MODEL_NAME`, `MODEL_API_KEY`
- Can also set a separate `TAILOR_MODEL` so you use a cheap model for scoring and a better one only for tailoring

---

**Tech stack**

- Python 3.12
- `python-telegram-bot` v21 for the Telegram interface
- `APScheduler` for the daily cron
- `requests` + `BeautifulSoup` for scraping
- `openai` / `anthropic` SDKs for LLM calls
- SQLite for job storage, config, and journal
- Docker + Docker Compose for running everything cleanly on Mac without polluting the host

---

**Current status**

The bot is running in Docker and working end-to-end. Scraping, scoring, filtering, the Telegram interface with inline keyboards, job status tracking, and the DB backup flow are all functional. The resume tailoring to zip flow is implemented but not yet tested end-to-end. The journal and `/resumediff` features are implemented but not yet tested. Next steps are testing the tailor flow with a real job, validating the zip uploads correctly to Overleaf, and then looking at hosting options (Render or Railway for free-tier cloud hosting, using the Telegram DB backup as the persistence strategy).
