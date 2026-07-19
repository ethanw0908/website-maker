# LocalSite Agent

LocalSite Agent is an approval-gated business-development controller for a Raspberry Pi or other Linux server. It discovers local businesses, audits public websites, scores leads, generates reviewed concept sites with Codex CLI, publishes approved concepts through GitHub and Vercel, and prepares outreach emails.

All pipeline information is stored in PostgreSQL and shown in a spreadsheet-style control centre. Google Sheets and Gmail are not required.

## Authentication model

- **GitHub:** one `GITHUB_TOKEN`. The account owner is detected automatically from the token.
- **Codex:** Sign in with ChatGPT through Codex CLI OAuth. No manually supplied OpenAI API key is required.
- **Vercel:** one personal `VERCEL_TOKEN`. No team ID is required.
- **Email:** configure any SMTP mailbox in the control centre. The SMTP password is encrypted before being stored in PostgreSQL.

The workflow remains human-controlled:

```text
Discovered → Audited → Awaiting approval → Generated → QA passed
→ Publish approval → Drafted → Manual send approval → Sent
```

There is no unrestricted automatic-send mode.

## Raspberry Pi / Debian start

Use a 64-bit operating system. Install Docker and Git, then:

```bash
git clone https://github.com/ethanw0908/website-maker.git
cd website-maker
cp .env.example .env
```

Generate secure application secrets:

```bash
ADMIN_KEY=$(openssl rand -hex 32)
APP_SECRET=$(openssl rand -hex 32)
sed -i "s/^ADMIN_API_KEY=.*/ADMIN_API_KEY=$ADMIN_KEY/" .env
sed -i "s/^APP_SECRET_KEY=.*/APP_SECRET_KEY=$APP_SECRET/" .env
```

Add your Google Places, GitHub, and Vercel tokens to `.env`:

```env
GOOGLE_PLACES_API_KEY=
GITHUB_TOKEN=
VERCEL_TOKEN=
```

Keep publication disabled during setup:

```env
ALLOW_REPOSITORY_CREATION=false
ALLOW_VERCEL_DEPLOYMENT=false
```

Build and start:

```bash
docker compose up --build -d
docker compose ps
curl http://localhost:8000/api/health
```

Open:

```text
http://YOUR_PI_IP:8000
```

Enter the `ADMIN_API_KEY` from `.env`.

## Connect Codex with ChatGPT OAuth

The Compose stack includes a persistent `codex_auth` volume. Run:

```bash
docker compose run --rm worker codex --login
docker compose restart worker
```

Complete the Sign in with ChatGPT flow. The control centre Settings tab will show Codex as connected after the OAuth credentials are present.

You can also use:

```bash
./scripts/codex-login.sh
```

No `OPENAI_API_KEY` setting is used by the generator.

## Connect your email with SMTP

Open **Settings → SMTP connection** in the control centre and enter:

- SMTP host and port
- Username and password
- From email and display name
- Business name
- Physical postal address
- Unsubscribe email
- STARTTLS or SSL/TLS

Click **Save SMTP**, then **Test connection**. The test authenticates and sends no message.

Generated messages remain saved drafts. Sending requires opening the Email drafts tab and clicking **Send** for a specific recipient. Sent and failed events are recorded in PostgreSQL.

For Gmail or Microsoft accounts, use the provider's SMTP settings and an app password when the provider requires one. The application does not use the Gmail API.

## Saved spreadsheet-style dashboard

The control centre contains:

- Leads, scores, contacts, statuses, and editable saved notes
- Codex generation jobs and errors
- GitHub repositories and Vercel previews
- Email drafts and send status
- Integration status and SMTP settings

PostgreSQL is the system of record. Docker volumes preserve the database, Redis state, generated workspaces, and Codex OAuth credentials across container restarts.

## Enable publication

After generation and QA work correctly:

```env
ALLOW_REPOSITORY_CREATION=true
```

Restart:

```bash
docker compose up -d --force-recreate
```

After GitHub publication succeeds, optionally enable personal Vercel deployment:

```env
ALLOW_VERCEL_DEPLOYMENT=true
```

No `GITHUB_OWNER` or `VERCEL_TEAM_ID` setting is needed.

## Useful commands

```bash
docker compose logs -f
docker compose logs -f worker
docker compose restart
docker compose down
git pull origin main
docker compose up --build -d
```

`docker compose down` does not delete saved data. Do not run `docker compose down -v` unless you intentionally want to remove the PostgreSQL, Redis, workspace, and Codex OAuth volumes.

## Security

- Do not commit `.env`.
- Use a unique `APP_SECRET_KEY`; changing it prevents existing SMTP passwords from being decrypted.
- Do not expose port `8000` directly to the public internet without HTTPS and access controls.
- Keep GitHub and Vercel publication switches disabled until previews are reviewed.
- Respect suppression requests and the commercial-email rules that apply to each recipient.
