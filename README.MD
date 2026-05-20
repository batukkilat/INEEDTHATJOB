# INEEDTHATJOB — Master Prompt

You are a senior software engineer helping build **INEEDTHATJOB**, a solo-developer autonomous job application system. The developer works on their own laptop using Claude Code. Every decision must optimize for **shipping speed, maintainability by one person, and practical results** — not architectural beauty.

---

## What This System Does

INEEDTHATJOB is a personal tool that:

1. **Scrapes/ingests job listings** from Indonesian job platforms (LinkedIn, Glints, JobStreet)
2. **Scores job compatibility** against the user's professional profile
3. **Generates tailored resumes** per job (ATS-optimized, DOCX + PDF)
4. **Generates tailored cover letters** per job
5. **Composes and sends application emails** via SMTP
6. **Autonomously applies** to jobs via browser automation — with a **mandatory review gate** before submission
7. **Runs on-demand or on a schedule** (cron-style)
8. **Provides a simple web dashboard** for monitoring, reviewing, and approving applications

---

## Architecture: Monolith, Single Process, GUI-First

This is a **Python monolith** — one process serves both the web dashboard and runs the application pipeline. No microservices. No containers. No frontend build step.

The dashboard is **server-rendered HTML** using FastAPI + Jinja2 + HTMX. No React, no Next.js, no npm. HTMX gives you interactive UI (inline editing, live updates, modals) with zero JavaScript build tooling. TailwindCSS via CDN for styling.

```
ineedthatjob/
├── main.py                     # Entrypoint: starts FastAPI server + scheduler
├── config.py                   # Pydantic Settings, all configuration
├── db/
│   ├── models.py               # SQLModel ORM models
│   ├── database.py             # SQLite engine + session management
│   └── migrations/             # Alembic migrations
├── profile/
│   ├── models.py               # Professional identity data structures
│   └── service.py              # CRUD for skills, experiences, achievements
├── jobs/
│   ├── models.py               # Job listing data structures
│   ├── scrapers/
│   │   ├── base.py             # Abstract scraper interface
│   │   ├── linkedin.py
│   │   ├── glints.py
│   │   └── jobstreet.py
│   ├── scorer.py               # Job-profile compatibility scoring
│   └── service.py              # Ingest, deduplicate, score
├── generation/
│   ├── resume.py               # Resume tailoring logic
│   ├── cover_letter.py         # Cover letter generation
│   ├── email_composer.py       # Application email drafting
│   └── prompts/                # All LLM prompt templates (plain text files)
│       ├── resume_tailor.txt
│       ├── cover_letter.txt
│       ├── email_draft.txt
│       └── job_parser.txt
├── apply/
│   ├── engine.py               # Application orchestrator
│   ├── email_sender.py         # SMTP email sending
│   └── browser/
│       ├── base.py             # Abstract ATS adapter interface
│       ├── greenhouse.py
│       ├── lever.py
│       ├── workday.py
│       └── generic.py          # Generic career page handler
├── web/
│   ├── app.py                  # FastAPI app factory, route registration
│   ├── routes/
│   │   ├── dashboard.py        # GET / — overview stats, recent activity
│   │   ├── jobs.py             # Job listing views, filtering, detail
│   │   ├── applications.py     # Review queue, approve/reject, status
│   │   ├── profile.py          # Profile editor
│   │   ├── settings.py         # Config editor
│   │   └── api.py              # HTMX partial endpoints (fragments)
│   ├── templates/
│   │   ├── base.html           # Layout: nav, sidebar, Tailwind CDN, HTMX
│   │   ├── dashboard.html
│   │   ├── jobs/
│   │   │   ├── list.html
│   │   │   └── detail.html
│   │   ├── applications/
│   │   │   ├── review.html     # THE key page: review & approve applications
│   │   │   └── history.html
│   │   ├── profile/
│   │   │   └── editor.html
│   │   └── partials/           # HTMX fragments for inline updates
│   │       ├── job_row.html
│   │       ├── app_card.html
│   │       └── stats.html
│   └── static/
│       └── custom.css          # Minimal overrides if needed
├── scheduler.py                # APScheduler: cron-style pipeline runs
├── pipeline.py                 # Orchestrates: scrape → score → generate → queue for review
└── utils/
    ├── llm.py                  # OpenAI API wrapper
    ├── logging.py              # Structured logging setup
    └── files.py                # PDF/DOCX generation helpers
```

### Why this structure:

- **Flat and obvious.** Any file is findable in 2 seconds.
- **No abstraction layers.** No repository pattern, no DTOs, no service layer indirection. A module does what its name says.
- **Prompts live in plain text files.** Easy to iterate without touching Python.
- **One scraper per file.** When Glints changes their page layout, you fix one file.
- **Templates are plain HTML.** No JSX, no build step. Edit, refresh, done.
- **HTMX for interactivity.** Review/approve buttons, live status updates, inline editing — no custom JavaScript needed.

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12+ | Best ecosystem for LLM + scraping + browser automation |
| Database | SQLite (via SQLModel) | Zero config, single file, portable, fast enough for thousands of jobs |
| Web framework | FastAPI | Async, fast, good with Jinja2 templates |
| Templating | Jinja2 | Server-rendered, no build step |
| Interactivity | HTMX | Rich UI behavior (modals, inline edits, polling) with zero JS build tooling |
| Styling | TailwindCSS (CDN) | Clean UI without writing CSS. No npm/build step. |
| LLM | OpenAI API (GPT-4o / GPT-4o-mini) | Structured outputs, reliable |
| Browser automation | Playwright | Best headless browser lib |
| Scheduling | APScheduler | In-process, no external deps |
| Email | smtplib (stdlib) | SMTP sending, no third-party service |
| Resume output | python-docx + weasyprint | DOCX for ATS uploads, PDF for attachments |
| Config | Pydantic Settings | Typed env var loading from .env file |

### What we are NOT using and why:

| Excluded | Reason |
|---|---|
| PostgreSQL | Overhead for a single-user local app. SQLite handles this. |
| Redis | No caching layer needed at this scale. |
| Kafka / Celery | Sequential processing is fine for one user. APScheduler handles timing. |
| React / Next.js / Vue | Build tooling complexity. Jinja2 + HTMX delivers the same UX for a dashboard. |
| Docker | Run natively. Add later if you want to deploy to a server. |
| Elasticsearch / pgvector | Job matching uses structured scoring, not vector search. |

> **Upgrade path:** If you later need richer frontend interactivity (drag-and-drop, complex state), you can swap in Alpine.js or a small React widget on specific pages without touching the rest.

---

## Database Design

### Core Principle: The Professional Identity is the source of truth. Resumes are generated artifacts.

```sql
-- The user's permanent professional profile
CREATE TABLE skills (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT,                  -- 'technical', 'soft', 'domain', 'language'
    proficiency TEXT,               -- 'expert', 'advanced', 'intermediate', 'beginner'
    years_experience REAL,
    keywords TEXT                   -- comma-separated ATS variants: "Python, python3, py"
);

CREATE TABLE experiences (
    id INTEGER PRIMARY KEY,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    start_date TEXT NOT NULL,       -- ISO format: 2023-01-15
    end_date TEXT,                  -- NULL = current position
    location TEXT,
    description TEXT,
    is_remote BOOLEAN DEFAULT FALSE
);

CREATE TABLE achievements (
    id INTEGER PRIMARY KEY,
    experience_id INTEGER REFERENCES experiences(id) ON DELETE CASCADE,
    description TEXT NOT NULL,      -- "Led migration to microservices architecture"
    metrics TEXT,                   -- "Reduced deploy time by 60%"
    skills_used TEXT                -- comma-separated, for matching
);

CREATE TABLE education (
    id INTEGER PRIMARY KEY,
    institution TEXT NOT NULL,
    degree TEXT NOT NULL,
    field TEXT,
    start_date TEXT,
    end_date TEXT,
    gpa TEXT
);

CREATE TABLE certifications (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    issuer TEXT,
    date_obtained TEXT,
    expiry_date TEXT
);

CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    url TEXT,
    skills_used TEXT,
    highlights TEXT
);

-- User preferences (single row, acts as a settings table)
CREATE TABLE preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- enforce single row
    target_roles TEXT,              -- JSON array: ["Backend Engineer", "Full Stack"]
    target_locations TEXT,          -- JSON array: ["Remote", "Jakarta", "Bandung"]
    min_salary REAL,
    max_salary REAL,
    salary_currency TEXT DEFAULT 'IDR',
    preferred_languages TEXT,       -- JSON array: ["English", "Indonesian"]
    industries_include TEXT,        -- JSON array, or NULL for any
    industries_exclude TEXT,        -- JSON array
    company_size_preference TEXT    -- 'startup', 'mid', 'enterprise', 'any'
);

-- Job listings (ingested from scrapers)
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL,             -- 'linkedin', 'glints', 'jobstreet'
    external_id TEXT,                   -- platform-specific ID for dedup
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    description TEXT,
    salary_min REAL,
    salary_max REAL,
    currency TEXT DEFAULT 'IDR',
    job_type TEXT,                      -- 'full-time', 'contract', 'part-time', 'internship'
    remote_type TEXT,                   -- 'remote', 'hybrid', 'onsite'
    experience_level TEXT,              -- 'junior', 'mid', 'senior', 'lead'
    posted_date TEXT,
    scraped_at TEXT NOT NULL,
    raw_html TEXT,                      -- preserve for re-parsing
    compatibility_score REAL,           -- 0.0 to 1.0
    score_breakdown TEXT,               -- JSON: {"skills": 0.8, "experience": 0.7, ...}
    status TEXT DEFAULT 'new',          -- see status flow below
    UNIQUE(platform, external_id)
);

-- Generated application materials (derived artifacts, never source of truth)
CREATE TABLE applications (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_path TEXT,                   -- path to generated DOCX
    resume_pdf_path TEXT,               -- path to generated PDF
    resume_content TEXT,                -- JSON: structured resume data used for generation
    cover_letter TEXT,
    email_subject TEXT,
    email_body TEXT,
    apply_method TEXT,                  -- 'email', 'browser_greenhouse', 'browser_lever', etc.
    applied_at TEXT,
    apply_status TEXT DEFAULT 'pending_review',
    -- 'pending_review' → 'approved' → 'submitting' → 'submitted'
    --                   → 'rejected' (user skipped)
    --                   → 'failed' (automation error)
    error_log TEXT,
    screenshot_path TEXT,               -- on failure, path to screenshot
    created_at TEXT NOT NULL
);

-- Activity log for dashboard feed
CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,               -- 'scraped', 'scored', 'generated', 'approved', 'submitted', 'failed'
    job_id INTEGER REFERENCES jobs(id),
    details TEXT
);

-- Indexes
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_score ON jobs(compatibility_score DESC);
CREATE INDEX idx_jobs_platform_extid ON jobs(platform, external_id);
CREATE INDEX idx_applications_job ON applications(job_id);
CREATE INDEX idx_applications_status ON applications(apply_status);
CREATE INDEX idx_activity_timestamp ON activity_log(timestamp DESC);
```

### Job Status Flow:
```
new → scored → generating → review_ready → approved → applying → applied
                                         → skipped (user rejected)
                                                    → failed (retry-able)
```

---

## Core Pipeline

The system runs as a sequential pipeline. The dashboard shows progress and queues items for human review.

```
┌─────────┐    ┌─────────┐    ┌──────────┐    ┌──────────────┐    ┌─────────┐
│ SCRAPE  │───>│  SCORE  │───>│ GENERATE │───>│    REVIEW    │───>│  APPLY  │
│ LinkedIn│    │ & rank  │    │ resume + │    │  (dashboard) │    │ submit  │
│ Glints  │    │         │    │ CL +     │    │  approve or  │    │ via ATS │
│ JobStr. │    │         │    │ email    │    │  reject each │    │ or email│
└─────────┘    └─────────┘    └──────────┘    └──────────────┘    └─────────┘
     │              │               │                │                  │
     └──────────────┴───────────────┴────── automated ───┘       after approval
```

### Step 1: Scrape
- Run configured scrapers for LinkedIn Indonesia, Glints, JobStreet
- Deduplicate by `(platform, external_id)`
- Store raw HTML + parsed structured data
- Handle Indonesian and English language listings
- Status → `new`

### Step 2: Score
- For each `new` job, compute compatibility score against the professional profile
- Scoring factors (weighted, configurable):
  - **Skill match** — % of required skills the user has
  - **Experience level match** — years vs. requirement
  - **Location/remote fit** — preference alignment
  - **Salary fit** — if available, compare against preferences
  - **Title relevance** — does job title match target roles?
  - **Language match** — job language vs. user's language skills
- Use GPT-4o-mini with structured outputs to parse job requirements from descriptions
- Status → `scored`

### Step 3: Generate (for jobs above score threshold)
- **Resume**: Select relevant experiences/achievements, tailor bullet points for this specific job, optimize ATS keywords. Output DOCX + PDF.
- **Cover letter**: Match tone to company culture, reference specific requirements from the listing. Support English and Indonesian based on the job's language.
- **Application email**: If apply method is email, draft professional outreach with attachment references.
- All generation uses the user's real data only. **Never invent experience.**
- Status → `review_ready`

### Step 4: Review (Dashboard — THE critical interaction)
- Applications appear in a **review queue** on the dashboard
- For each application, the user sees:
  - Job details (title, company, score breakdown)
  - Generated resume (rendered preview + download link)
  - Generated cover letter (editable)
  - Generated email (editable, if email application)
  - Approve / Edit / Reject buttons
- User can inline-edit cover letter and email before approving
- **Nothing is submitted without explicit user approval**
- Status → `approved` or `skipped`

### Step 5: Apply (only approved applications)
- **Email applications**: Send via SMTP with resume DOCX/PDF attached
- **ATS applications**: Playwright fills forms using the ATS adapter
- Screenshot every submission (success or failure)
- Status → `applied` or `failed`

---

## Dashboard Pages

The dashboard is minimal and functional. No charts unless they earn their place.

### 1. Dashboard Home (`/`)
- **Pipeline status**: "Last run: 2 hours ago. Next scheduled: tomorrow 9:00 AM"
- **Counts**: X jobs scraped today, Y scored above threshold, Z awaiting review, W applied
- **Recent activity feed**: Last 20 actions from activity_log
- **Quick action button**: "Run Pipeline Now"

### 2. Jobs (`/jobs`)
- **Filterable table**: By platform, status, score range, date
- **Columns**: Title, Company, Platform, Score, Status, Date
- **Sort by score** (default, descending)
- **Click row** → job detail page

### 3. Job Detail (`/jobs/{id}`)
- Full job description
- Score breakdown (visual: skill match, experience match, etc.)
- Generated materials if they exist (resume preview, cover letter, email)
- Action buttons: Generate Materials, Skip Job

### 4. Review Queue (`/review`) — **Most important page**
- Cards for each `review_ready` application
- Each card shows: job title + company, compatibility score, and expandable sections for:
  - Resume (rendered HTML preview of the generated content)
  - Cover letter (editable textarea)
  - Email (editable subject + body textarea, if applicable)
- **Approve** (sends to apply queue) / **Reject** (marks as skipped)
- Bulk approve option for high-confidence applications

### 5. Application History (`/history`)
- All past applications with status
- Filter by: submitted, failed, skipped
- Failed applications show error log + screenshot link

### 6. Profile (`/profile`)
- View and edit: skills, experiences, achievements, education, certifications, projects
- Import from existing resume file (upload PDF/DOCX → LLM parses into structured data)
- Each section has inline add/edit/delete via HTMX

### 7. Settings (`/settings`)
- Job preferences (target roles, locations, salary range)
- Scraping config (which platforms, max pages)
- Application config (apply mode, delay between applications)
- Email settings (SMTP config, test send button)
- Schedule config (enable/disable, cron expression with human-readable preview)

---

## LLM Usage Rules

1. **Structured outputs only.** Every LLM call that extracts or classifies data returns a Pydantic model, not freeform text. Cover letters and emails are freeform by nature but constrained by explicit prompt templates.

2. **Never invent data.** The LLM selects, rephrases, and tailors the user's existing profile data. It does not create new experiences, skills, or achievements. Every claim in a generated resume must trace to a record in the database.

3. **Prompts are plain text files** in `generation/prompts/`. Loaded at runtime. Easy to version, diff, iterate. No prompt strings hardcoded in Python.

4. **Model selection by cost:**
   - GPT-4o-mini → bulk work (scoring, job requirement parsing, deduplication)
   - GPT-4o → quality work (resume tailoring, cover letters, emails)

5. **Temperature settings:**
   - `temperature=0` for parsing and scoring (deterministic)
   - `temperature=0.3` for resume bullet point tailoring
   - `temperature=0.5` for cover letters and emails (slight creativity)

6. **Bilingual support.** Prompts must handle English and Indonesian job listings. Cover letters and emails should match the language of the job posting unless the user overrides.

7. **Log every LLM call.** Model, input token count, output token count, latency, cost estimate. This is your spend tracking.

---

## Browser Automation Rules

1. **ATS adapters are separate modules.** One file per ATS. When a platform changes their form layout, you fix one file.

2. **Indonesian job platform specifics:**
   - **Glints**: Custom application flow, may require Glints account session
   - **JobStreet**: Uses their own ATS, needs a dedicated adapter
   - **LinkedIn**: Easy Apply flow is the primary target
   - **Company career pages**: Fall through to Greenhouse/Lever/Workday adapters or generic handler

3. **Use semantic selectors** — aria labels, form labels, `data-*` attributes, placeholder text. Avoid brittle CSS class selectors.

4. **Retry with backoff.** 3 retries, exponential backoff. Network errors and page load races are expected.

5. **Screenshot every application attempt.** Success and failure. Store in `data/screenshots/`. Essential for debugging and for the dashboard's history view.

6. **Session persistence.** Save browser cookies/state per platform so you don't re-login every run.

7. **Rate limiting.** Configurable delay between applications. Default: 60-120 seconds randomized. Don't get flagged.

8. **Headless by default, headed for debugging.** Single flag to toggle.

---

## Configuration

Single `.env` file, loaded by Pydantic Settings in `config.py`:

```env
# LLM
OPENAI_API_KEY=sk-...
SCORING_MODEL=gpt-4o-mini
GENERATION_MODEL=gpt-4o

# Scraping
SCRAPE_PLATFORMS=["linkedin", "glints", "jobstreet"]
SCRAPE_MAX_PAGES=5
LINKEDIN_SESSION_COOKIE=...
GLINTS_SESSION_COOKIE=...
JOBSTREET_SESSION_COOKIE=...

# Application
APPLY_DELAY_MIN_SECONDS=60
APPLY_DELAY_MAX_SECONDS=120

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=you@gmail.com
FROM_NAME=Your Full Name

# Scheduling
SCHEDULE_ENABLED=false
SCHEDULE_CRON=0 9 * * 1-5            # Weekdays at 9 AM WIB

# Server
HOST=127.0.0.1
PORT=8000

# Storage paths
DB_PATH=./data/ineedthatjob.db
OUTPUT_DIR=./data/output
SCREENSHOT_DIR=./data/screenshots
LOG_DIR=./data/logs
```

Job preferences (target roles, salary, locations) are stored in the `preferences` database table, editable via the dashboard Settings page — not in the .env file.

---

## Implementation Order

Each phase produces a working, usable tool before moving to the next.

### Phase 1: Foundation + Dashboard Shell + Profile (Week 1)
- [ ] Project setup: `pyproject.toml`, directory structure, config loading
- [ ] Database: SQLite + SQLModel, all tables, Alembic init
- [ ] FastAPI app with Jinja2 + HTMX + Tailwind CDN
- [ ] Dashboard layout (nav, sidebar, empty pages)
- [ ] Profile editor page: add/edit/delete skills, experiences, achievements, education
- [ ] Profile import: upload existing resume PDF/DOCX → LLM parses into structured profile
- **Verify:** Open `localhost:8000`, navigate to profile, see your full professional identity. Edit a skill inline.

### Phase 2: Job Scraping + Scoring (Week 2)
- [ ] Abstract scraper interface
- [ ] First scraper: LinkedIn Indonesia (most jobs, most familiar)
- [ ] Job list page with filtering and sorting
- [ ] Job detail page
- [ ] Compatibility scorer: LLM parses requirements + structured scoring
- [ ] Dashboard home with job counts
- **Verify:** Click "Run Pipeline" on dashboard, see scored jobs appear in the jobs table within minutes.

### Phase 3: Document Generation (Week 3)
- [ ] Resume tailoring: select relevant profile data → generate DOCX + PDF
- [ ] Cover letter generation (English + Indonesian)
- [ ] Email composition
- [ ] All prompt templates as plain text files
- [ ] Job detail page shows generated materials with preview
- **Verify:** Open a scored job, click "Generate", see tailored resume + cover letter rendered on the page.

### Phase 4: Review Queue + Application (Week 4-5)
- [ ] Review queue page: card-based layout, editable cover letter/email
- [ ] Approve/reject flow with HTMX
- [ ] Email sender (SMTP) with resume attachment
- [ ] Playwright setup + session management
- [ ] First ATS adapter (LinkedIn Easy Apply or Greenhouse)
- [ ] Application history page with status + screenshots
- [ ] Apply engine: picks approved applications, applies via correct method
- **Verify:** Full pipeline end-to-end: scrape → score → generate → review on dashboard → approve → application sent. Check your email outbox or ATS confirmation.

### Phase 5: Scheduling + Second Platform + Polish (Week 6)
- [ ] APScheduler integration, configurable via Settings page
- [ ] Second scraper (Glints)
- [ ] Third scraper (JobStreet)
- [ ] Settings page: edit preferences, scraping config, schedule
- [ ] Activity feed on dashboard home
- [ ] LLM cost tracking display
- **Verify:** Set schedule to run in 5 minutes. Walk away. Come back, see new jobs scraped and applications queued for review.

---

## Code Standards

- **Type hints everywhere.** All function signatures typed. Pydantic models for all structured data.
- **Logging, not print.** `structlog` for structured logging. Every pipeline step, every LLM call, every application attempt logged.
- **Functions over classes** for most logic. Classes only where polymorphism is needed (scrapers, ATS adapters).
- **Tests for non-obvious logic:** Scoring algorithm, resume content selection, prompt template rendering, dedup logic. Don't test CRUD or HTML templates.
- **Git from day 1.** Commit after every working increment.

---

## What NOT to Build

Until the pipeline works end-to-end and you've applied to 50+ jobs:

- ❌ User authentication (it's your laptop, you're the only user)
- ❌ Multi-user support
- ❌ Analytics dashboards with charts
- ❌ Docker / deployment infrastructure
- ❌ CI/CD pipeline
- ❌ Vector search / RAG
- ❌ Interview tracking / CRM features
- ❌ Job recommendation engine
- ❌ Mobile responsive design (laptop-only is fine)
- ❌ Notification system (you'll check the dashboard)

All of these are valid future features. None of them help you get hired faster right now.

---

## Indonesian Job Market Specifics

Things the system must handle that are specific to the Indonesian job market:

- **Bilingual listings.** Jobs may be in English, Indonesian, or mixed. The LLM must detect and match language in generated materials.
- **Salary in IDR.** Often listed as monthly, sometimes as annual. Normalize to monthly IDR for comparison.
- **Glints-specific fields:** Glints has structured skill tags, experience level filters, and their own application flow. The scraper should capture these structured fields, not just freeform description.
- **JobStreet format:** JobStreet Indonesia has its own resume format preferences and application flow. The adapter must handle this.
- **LinkedIn Indonesia:** Same as global LinkedIn, but filter by Indonesia location. Easy Apply is the primary target.
- **Regional awareness in cover letters:** Tone and formality expectations may differ by company type (Indonesian startup vs. multinational vs. government-linked).