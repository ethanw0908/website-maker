# LocalSite Agent

LocalSite Agent is an approval-gated business-development controller that discovers local companies, audits public website and contact information, scores leads, creates verified website concepts with Codex CLI, runs guardrails, publishes reviewed concepts to GitHub and Vercel, and prepares outreach drafts.

The default workflow is deliberately human-controlled:

```text
Discovered → Audited → Awaiting approval → Generated → QA passed → Publish approval → Drafted → Awaiting review
```

There is no automatic email-send endpoint. Repository creation and Vercel deployment are disabled until the corresponding environment flags are explicitly enabled.

## Included in this MVP

- FastAPI control API and GitHub-style control centre
- PostgreSQL system of record with Redis/Celery jobs
- Google Places Text Search discovery and Place ID deduplication
- Playwright website audit, screenshots, public business-email extraction, contact-form discovery, and MX checks
- Configurable lead scoring and manual approval gate
- Structured company research brief
- Isolated Codex CLI generation with bounded QA revisions
- Generated-site checks for required files, unindexed previews, placeholders, generic claims, and contact actions
- Private-first GitHub repository creation and optional Vercel preview deployment
- Personalized outreach draft generation with sender identification and opt-out language
- Emergency pause control, daily discovery cap, API authentication, tests, and CI

## Start locally

```bash
cp .env.example .env
# Set ADMIN_API_KEY and the integrations you plan to use.
docker compose up --build
```

Open `http://localhost:8000`, enter the same administrator key from `.env`, and use the discovery form.

## Safety switches

Keep these disabled while configuring and testing:

```env
ALLOW_REPOSITORY_CREATION=false
ALLOW_VERCEL_DEPLOYMENT=false
```

Enable them only after reviewing the generated briefs, QA results, repository ownership, Vercel scope, and jurisdiction-specific outreach requirements.

## Required credentials

- `GOOGLE_PLACES_API_KEY` for discovery
- Codex CLI authentication or `OPENAI_API_KEY` for generation
- `GITHUB_TOKEN` and `GITHUB_OWNER` for private concept repositories
- `VERCEL_TOKEN` and optional `VERCEL_TEAM_ID` for preview deployment

Secrets belong in `.env` or a secret manager and must never be committed. Generated concept sites must remain unindexed, must not pretend to be official, and must not accept bookings, payments, or customer information.

## API flow

1. `POST /api/discover`
2. Wait for the audit worker and review `GET /api/leads`
3. `POST /api/leads/{id}/approve`
4. Wait for Codex and QA
5. `POST /api/jobs/{id}/publish`
6. `POST /api/deployments/{id}/email-draft`

All protected routes require `X-Admin-Key` when `ADMIN_API_KEY` is configured.

## Production hardening still recommended

Before public or high-volume use, add Alembic migrations, encrypted OAuth-token storage, Google Sheets synchronization, Gmail draft creation, deeper accessibility/performance tooling, screenshot review in the UI, robust legal configuration by jurisdiction, observability, backups, and rate-limit accounting.
