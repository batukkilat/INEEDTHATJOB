# INEEDTHATJOB

An automated job application assistant for the Indonesian job market. Point it at your resume, tell it what roles you want, and it finds, scores, and prepares applications — you just review and approve before anything gets sent.

**Supported platforms:** LinkedIn · Glints · JobStreet

---

## What it does

1. Scrapes job listings that match your target roles
2. Scores each listing against your profile (skills, experience, title, location, salary)
3. Queues high-scoring jobs in a review dashboard
4. Generates a tailored resume, cover letter, and email per job on demand
5. Sends applications via SMTP after your explicit approval

Nothing is submitted automatically. Every application requires a human click.

---

## Requirements

- Python 3.11+
- A [Groq API key](https://console.groq.com) (free tier is sufficient)
- An email account with SMTP access (Gmail recommended)

---

## Quick start

```bash
# 1. Install dependencies
pip install -e .

# 2. Add your Groq key to .env
echo "GROQ_API_KEY=gsk_your_key_here" > .env

# 3. Start the app
python main.py
```

Open **http://localhost:8000** in your browser.

All other settings (SMTP, target roles, salary, schedule) are configurable from the web UI — no manual `.env` editing needed after the initial key.

---

## First-time setup

After starting the app, do these three things:

1. **Import your resume** on the Profile page (PDF or DOCX)
2. **Set target roles** in Settings — e.g. "Finance Staff", "Accounting Officer"
3. **Configure SMTP** in Settings → Email (SMTP) if you want to send applications automatically

Then hit **Start Job Search** on the Dashboard.

---

## Configuration

Key values can be overridden in `.env`:

| Key | Default | Description |
|-----|---------|-------------|
| `GROQ_API_KEY` | — | Required. Get from console.groq.com |
| `GENERATION_MODEL` | `llama-3.3-70b-versatile` | Model for resumes and cover letters |
| `SCORING_MODEL` | `llama-3.1-8b-instant` | Model for bulk scoring |
| `SMTP_HOST` | `smtp.gmail.com` | Configurable from Settings UI |
| `SMTP_PORT` | `587` | Configurable from Settings UI |
| `SCHEDULE_ENABLED` | `false` | Auto-run pipeline on cron |
| `SCHEDULE_CRON` | `0 9 * * 1-5` | Weekdays 9 AM |
| `MIN_SCORE_TO_GENERATE` | 0.55 | Edit in `pipeline.py` |

---

## Scoring

Jobs are scored across six weighted dimensions:

| Dimension | Weight |
|-----------|--------|
| Skill match | 35% |
| Experience match | 25% |
| Title relevance | 20% |
| Location match | 10% |
| Language match | 5% |
| Salary match | 5% |

Jobs scoring ≥ 55% are queued for review. Weights are editable in `jobs/scorer.py`.

---

## License

MIT
