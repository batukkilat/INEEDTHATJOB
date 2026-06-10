# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Is

INEEDTHATJOB is a solo-developer autonomous job application system for the Indonesian job market (LinkedIn, Glints, JobStreet). It scrapes listings, scores them against a professional profile, generates tailored resumes/cover letters, and submits applications — with a mandatory human review gate before anything is sent.

---

## Running the App

```bash
# Install dependencies
pip install -e .

# Start the server (FastAPI + scheduler in one process)
python main.py

# Run the pipeline manually (scrape → score → generate → queue for review)
# Use the "Run Pipeline Now" button on the dashboard, or trigger directly:
python -c "from pipeline import run_pipeline; import asyncio; asyncio.run(run_pipeline())"
```

App runs at `http://localhost:8000` by default. Config lives in `.env` (see `config.py` for all keys).

---

## Architecture

**Python monolith.** One process: FastAPI serves the dashboard and also runs APScheduler for cron-style pipeline execution. No microservices, no containers, no frontend build step.

**Stack:** FastAPI + Jinja2 + HTMX + TailwindCSS (CDN) + SQLite via SQLModel + Groq API (Llama models) + Playwright

**The pipeline is sequential:**
```
Scrape → Score → Generate → Review (dashboard) → Apply
```
The first four steps are automated. Apply only fires after explicit user approval on the Review Queue page (`/review`).

**Database:** SQLite, single file at `DB_PATH`. SQLModel ORM. Schema created via `create_all`; migrations are hand-rolled `ALTER TABLE` statements in `db/database.py:run_migrations` (no Alembic). Core tables: `skills`, `experiences`, `achievements`, `education`, `certifications`, `projects`, `preferences`, `jobs`, `applications`, `activity_log`.

**Job status flow:**
```
new → scored → generating → review_ready → approved → applying → applied
                                         → skipped
                                                    → failed
```

**LLM usage:**
- Groq API (OpenAI-compatible endpoint, see `utils/llm.py`); scoring itself is a pure heuristic (`jobs/scorer.py`) to preserve the free-tier token budget
- `SCORING_MODEL` (llama-3.1-8b-instant) for bulk work (resume-tail cert extraction, contact-email detection)
- `GENERATION_MODEL` (llama-3.3-70b-versatile) for quality work (resume tailoring, cover letters, emails, resume import parsing)
- All prompts are plain `.txt` files in `generation/prompts/` — never hardcoded in Python
- Structured output via forced tool calls (`chat_with_tool`) for resume tailoring; JSON-in-text parsing elsewhere
- Temperature: `0` for parsing, `0.3` for resume bullets, cover letters, and emails

**Browser automation:** Playwright with one adapter file per ATS (`greenhouse.py`, `lever.py`, etc.). Use semantic selectors (aria labels, form labels, `data-*` attrs). Screenshot every attempt.

---

## Code Standards

- Type hints on all function signatures. Pydantic models for all structured data.
- `structlog` for logging — no `print()`. Log every pipeline step, LLM call, and application attempt.
- Functions over classes. Classes only for scrapers and ATS adapters (polymorphism needed).
- Tests only for non-obvious logic: scoring algorithm, resume content selection, prompt rendering, dedup. Skip CRUD and HTML templates.

---

## Key Constraints

- **Never invent experience.** The LLM selects and rephrases the user's real profile data. Every claim in a generated resume must trace to a database record.
- **Nothing submits without approval.** The review gate in the dashboard is mandatory — applications go nowhere until the user clicks Approve.
- **Bilingual.** Generated cover letters and emails must match the language of the job posting (English or Indonesian) unless the user overrides.
- **Salary in IDR, normalized to monthly.**

## What NOT to Build (yet)

Auth, multi-user, charts/analytics, Docker, CI/CD, vector search, interview tracking, mobile responsive design, notification system. Ship the pipeline first.

---

## Implementation Phases

1. **Phase 1** — Foundation: project setup, DB init, FastAPI shell, profile editor, resume import
2. **Phase 2** — Scraping + Scoring: LinkedIn scraper, job list/detail pages, scorer, dashboard counts
3. **Phase 3** — Generation: resume DOCX/PDF, cover letter, email, prompt files
4. **Phase 4** — Review + Apply: review queue UI, approve/reject, SMTP sender, Playwright + first ATS adapter
5. **Phase 5** — Scheduling + Polish: APScheduler, Glints + JobStreet scrapers, settings page, cost tracking
