# OpenClaw

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="MIT License" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-Frontend-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React" />
  <img src="https://img.shields.io/badge/Vite-Build-646CFF?style=for-the-badge&logo=vite&logoColor=white" alt="Vite" />
  <img src="https://img.shields.io/badge/TailwindCSS-UI-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white" alt="Tailwind CSS" />
  <img src="https://img.shields.io/badge/SQLite-Storage-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/Ollama-LLM-000000?style=for-the-badge&logo=ollama&logoColor=white" alt="Ollama" />
  <img src="https://img.shields.io/badge/Docker-Local_Runtime-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
</p>

<p align="center">
  Self-hosted job-search intelligence for technical candidates: discover roles, score fit, tailor resumes, and manage the application workflow from one local-first system.
</p>

OpenClaw combines deterministic job discovery, candidate-profile-aware fit scoring, resume tailoring, outreach support, and application tracking into a single workflow. The current product is a Dockerized FastAPI backend with a React frontend, backed by SQLite and designed around plugin-based sourcing plus LLM-assisted ranking and editing.

## End-to-end flow

```text
Candidate profile + search intent
  -> campaign planner
  -> reusable campaign (roles, aliases, avoid terms, queries, plugins, location rules)
  -> discovery plugins (ATS, Ollama web, HN, Web3, manual URLs)
  -> URL normalization and dedupe
  -> fetch + parse job pages / ATS payloads
  -> deterministic filters (role mismatch, onsite-only, seniority cap, avoid terms)
  -> LLM fit scoring (score, reason, fit band, matched role family, red flags)
  -> SQLite persistence (jobs, campaigns, runs, results, variants, outreach state)
  -> React dashboard for review and status management
  -> optional resume tailoring from saved job / URL / pasted JD
  -> PDF + ZIP resume artifacts under data/resumes/
  -> optional outreach, journal, and interview-prep workflows
```

## Why this exists

Most job search tooling is either:

- too shallow, acting like a thin wrapper around public job boards
- too manual, forcing candidates to repeat the same evaluation and resume-edit loops
- too opaque, relying on black-box recommendations without showing evidence

OpenClaw takes a different approach:

- discover jobs from multiple sources using explicit plugins
- preserve provenance for how each role was found
- score jobs against a stored candidate profile and campaign intent
- tailor a source LaTeX resume into role-specific variants
- keep the full search workflow in one system instead of scattered notes, links, and drafts

## What the repo does

At a practical level, OpenClaw supports five core workflows:

1. Campaign-based job discovery
2. Fit scoring against a candidate profile
3. Resume tailoring from saved jobs, pasted JDs, or arbitrary URLs
4. Search memory and workflow management in SQLite
5. Outreach and interview-prep helpers around the job search process

## Project status

OpenClaw is actively usable as a personal system and is being shaped into a more public-facing OSS project. The architecture is real and end-to-end, but some repository-level OSS polish is still in progress, especially around contribution docs and tests.

## Feature overview

### Campaign-based discovery

Instead of saving flat keyword lists, OpenClaw stores reusable search campaigns derived from natural-language intent.

Example:

```text
Find remote or India-friendly AI-native backend, FDE/Solutions, DevRel, backend, fullstack, developer-tools, and Web3 infra roles. Avoid pure sales, pure support, senior/staff-only, and onsite-only roles.
```

The backend turns that prompt into a structured campaign:

- campaign name
- role families
- title aliases
- avoid terms
- search queries
- enabled discovery plugins
- location preferences
- max experience cap

That campaign can then be rerun, archived, restored, or inspected historically.

### Deterministic discovery plugins

Discovery is implemented as a plugin registry under `src/backend/discovery/`.

Current plugins:

- `ollama_web`: uses Ollama-backed web search results
- `ats`: pulls directly from public ATS job boards
- `hn`: Hacker News hiring discovery
- `web3`: Web3-specific discovery sources
- `manual`: materializes user-supplied URLs

This separation matters because the system does not treat "search" as a single monolithic LLM call. Each plugin returns concrete URLs or jobs, which are then normalized, deduplicated, filtered, and scored.

Deprecated:

- container-side Bing / DuckDuckGo HTML search is not part of the supported discovery path because challenge pages make it unreliable in Dockerized environments

### ATS-native sourcing

OpenClaw talks directly to public Greenhouse, Lever, and Ashby job boards instead of relying only on generic search results.

That gives the system:

- stable structured job data
- fewer hallucinated or dead links
- reusable ATS company registries
- explicit separation between ATS discovery and campaign execution

ATS companies are stored in SQLite and refreshed explicitly via the API.

### Fit scoring with candidate context

Every job can be scored against the stored candidate profile and the active campaign.

Current fit metadata includes:

- `score`
- `reason`
- `fit_band`
- `matched_role_family`
- `red_flags`

The system also applies deterministic filters before scoring, such as:

- obvious role mismatch
- onsite-only rejection
- seniority cap checks from JD text
- avoid-term rejection

### Resume tailoring pipeline

OpenClaw can tailor resumes from:

- a saved job in the database
- a pasted job description
- a direct job URL

The tailoring flow is intentionally constrained:

- the source resume is a LaTeX project mounted read-only from `resume/`
- only selected content files are editable by the model
- structural/style files are copied through unchanged
- outputs are written to `data/resumes/`
- PDF and ZIP artifacts are produced for downstream use

This makes the system useful for serious role-specific customization without turning the resume into an uncontrolled LLM document.

### Outreach, interview prep, and search memory

The repo also includes:

- outreach contact storage and template management
- contact discovery helpers using Serper, ScraperAPI, or Hunter
- interview-answer generation grounded in candidate context
- a journal for search memory and resume update ideas

## Technical architecture

### Stack

- Backend: FastAPI
- Frontend: React + Vite + Tailwind
- Database: SQLite
- Runtime: Docker Compose
- Scheduling: APScheduler
- LLM providers: Ollama, OpenAI, Anthropic
- Scraping/fetching: `requests`, `aiohttp`, `BeautifulSoup`, `Playwright`
- Resume output: LaTeX + `latexmk`

### Runtime model

The repository builds into a single app container:

```text
React build stage -> frontend dist assets
Python runtime    -> FastAPI API + static frontend serving
SQLite volume     -> jobs, campaigns, variants, outreach state
Resume mount      -> source LaTeX resume, read-only
```

`docker compose up --build` produces a local application at `http://localhost:8000`.

### High-level execution flow

```text
User prompt
  -> campaign planner
  -> discovery plugins
  -> URL normalization / dedupe
  -> hard filters
  -> fit scoring
  -> SQLite persistence
  -> React UI
  -> optional resume tailoring / outreach actions
```

### Backend modules

```text
src/backend/
  main.py                FastAPI app, routes, scheduler, SPA serving
  db.py                  schema, migrations, persistence helpers
  llm.py                 provider abstraction and task-specific model routing
  campaigns.py           campaign planning, execution, and fit evaluation
  tailor.py              resume tailoring, PDF compilation, variant packaging
  scraper.py             scrape orchestration and generic parsing helpers
  sources_ats.py         ATS registry discovery and ATS board fetchers
  outreach.py            contacts, templates, provider-backed outreach helpers
  discovery/
    base.py              plugin interface
    registry.py          plugin registry
    ollama_web.py
    ats.py
    hn.py
    web3.py
    manual.py
```

### Frontend modules

```text
src/frontend/src/
  App.jsx
  api.js
  pages/
    Jobs.jsx
    Campaigns.jsx
    Funded.jsx
    Resumes.jsx
    ResumeEdit.jsx
    Journal.jsx
    InterviewPrep.jsx
    Outreach.jsx
    Config.jsx
  components/
    JobDetailModal.jsx
    TailorModal.jsx
    TailorResult.jsx
    QueueTab.jsx
    AllResultsTab.jsx
```

## Data model

SQLite is the system of record. The app persists:

- `jobs`
- `campaigns`
- `campaign_runs`
- `campaign_results`
- `funded_companies`
- `ats_companies`
- `resume_variants`
- `journal`
- `outreach_contacts`
- `outreach_templates`
- `config`
- `llm_batches`

Notable design choices:

- jobs store provenance such as `found_by_plugin`, `found_by_query`, and canonical URLs
- campaigns are soft-archived rather than hard-deleted
- schema upgrades are handled by startup-time migrations in `db.py`
- generated resumes and PDFs live on disk under `data/resumes/`, while metadata lives in SQLite

## API surface

The backend exposes a fairly complete local API for the frontend and automation.

Major route groups:

- Jobs: `/api/jobs`, `/api/jobs/all`, `/api/jobs/{job_id}`
- Scraping and batches: `/api/scrape`, `/api/scrape/status`, `/api/batches`
- Campaigns: `/api/campaigns`, `/api/campaigns/{id}/run`, `/api/campaigns/{id}/results`
- Discovery utilities: `/api/discovery/run`, `/api/discovery/ats/refresh`
- Resume and profile: `/api/tailor`, `/api/resume/edit`, `/api/variants/*`, `/api/profile`
- Journal and resume-diff helpers: `/api/journal`, `/api/resumediff`
- Outreach: `/api/outreach/providers`, `/api/outreach/contacts`, `/api/outreach/templates`, `/api/outreach/send`
- Interview prep: `/api/interview/answer`

FastAPI also serves the built frontend for all non-API routes.

## Why the README is structured this way

This README follows the common OSS pattern of making the first screen answer five questions quickly:

- what the project does
- why it is useful
- how to get started
- what tech it uses
- what its current status is

The badge row and the end-to-end flow are there for fast scanning when someone lands on the repository from a post, profile, or shared link.

## Local setup

### Prerequisites

- Docker Desktop
- a local `resume/` LaTeX project if you want tailoring
- Ollama running on the host if you use `MODEL_PROVIDER=ollama`

### 1. Clone and configure

```bash
git clone <your-fork-or-repo-url>
cd job-search-agent-uzair
cp .env.example .env
```

Then update `.env` with your provider and API settings.

### 2. Start the app

```bash
docker compose up --build
```

Or use the helper script:

```bash
./start.sh
```

Open:

- `http://localhost:8000`

### 3. Stop the app

```bash
docker compose down
```

Or:

```bash
./stop.sh
```

## Environment configuration

The current `.env.example` supports the following model-related settings:

```env
MODEL_PROVIDER=ollama
MODEL_API_KEY=ollama
MODEL_NAME=qwen3:4b
OLLAMA_BASE_URL=http://host.docker.internal:11434

SCORE_MODEL=qwen3:4b
PLANNER_MODEL=qwen3:4b
TAILOR_MODEL=qwen3:4b
RESEARCH_MODEL=qwen3:4b

DEFAULT_THINK=false
SCORE_THINK=false
PLANNER_THINK=false
TAILOR_THINK=false
RESEARCH_THINK=low

OLLAMA_API_KEY=your_ollama_api_key
ENABLE_OLLAMA_WEB_SEARCH=false
OLLAMA_WEB_MAX_RESULTS=5
OLLAMA_CLOUD_NATIVE_JSON=false

SERPER_API_KEY=
SCRAPERAPI_KEY=
HUNTER_API_KEY=
```

Notes:

- `MODEL_PROVIDER` can target `ollama`, `openai`, or `anthropic`
- task-specific model routing is implemented in `src/backend/llm.py`
- supported generic search is API-backed `ollama_web`, not container-side HTML scraping of public search engines
- outreach-related API keys are optional unless you use those features
- some legacy env keys still exist in `.env.example`; the active app is no longer a Telegram bot

## Resume project expectations

The tailoring flow expects a LaTeX resume project similar to:

```text
resume/
  resume.tex
  _header.tex
  TLCresume.sty
  sections/
    summary.tex
    experience.tex
    skills.tex
    projects.tex
    achievements.tex
    education.tex
    certifications.tex
    por.tex
    security.tex
```

OpenClaw edits only a defined subset of files, primarily:

- `sections/summary.tex`
- `sections/experience.tex`
- `sections/skills.tex`
- `sections/projects.tex`
- `sections/achievements.tex`

The source `resume/` tree is mounted read-only. Generated variants are written under `data/resumes/`.

## Development workflow

### Backend

Python backend code is mounted directly into the container and runs via:

```bash
uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

In practice, backend edits hot-reload when using Docker Compose.

### Frontend

The container serves built frontend assets from `src/frontend/dist`, so local frontend development currently follows a build-and-refresh loop:

```bash
cd src/frontend
npm install
npm run build
```

Then refresh the browser. The built `dist/` directory is mounted into the app container.

## Support and contributions

This repository is currently maintained as a serious personal project rather than a fully community-operated one.

- If you want to study the architecture, the best starting points are `src/backend/main.py`, `src/backend/campaigns.py`, `src/backend/db.py`, and `src/backend/tailor.py`.
- If you want to extend discovery, add a new plugin under `src/backend/discovery/` and register it in `src/backend/discovery/registry.py`.
- If you plan to open the repo up to outside contributors, the next missing pieces are `LICENSE`, `CONTRIBUTING.md`, and a small automated test suite.

## Operational behavior

### Scheduling

On app startup, the backend scheduler registers:

- a daily scrape at `08:00` Asia/Kolkata
- batch polling every `5` minutes

### Persistence

Host-persisted state:

```text
data/jobs.db
data/resumes/
```

### Campaign lifecycle

Campaigns can be:

- created from natural-language prompts
- run on demand
- soft-archived
- restored later
- inspected via stored results and run history

## Current status

This repo is functional and substantial, but it is still a personal system evolving toward a cleaner OSS shape.

Current strengths:

- clear separation between discovery, scoring, tailoring, and persistence
- real local runtime with reproducible Docker setup
- practical UI for operating the workflow
- deterministic evidence capture around job discovery
- supported search paths are aligned with sources that work reliably inside Docker

Current rough edges:

- some older docs and env entries still reflect the Telegram-bot phase
- the repo does not yet present itself like a polished multi-contributor OSS project
- automated test coverage is not yet documented in the repository
- some module names and comments still carry legacy terminology

## Roadmap ideas

Reasonable next steps for the project:

- formalize the plugin interface and add contributor docs for new discovery sources
- add tests around campaign planning, fit filtering, and resume file transforms
- separate personal data defaults from reusable open-source defaults
- add export/import for campaigns and profile state
- add observability around scrape runs, scoring latency, and failure modes
- document deployment options beyond local Docker

## Who this is for

OpenClaw is a good fit if you want to study or extend:

- AI-assisted job-search tooling
- self-hosted personal knowledge/workflow systems
- FastAPI + React local applications
- LLM-assisted document tailoring with hard output constraints
- deterministic plugin-based discovery pipelines

It is especially relevant for engineers who want more control and inspectability than typical job boards provide.

## License

This project is licensed under the [MIT License](LICENSE).
