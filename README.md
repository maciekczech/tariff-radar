# Tariff Radar

Open-source radar for **official tariff and trade-remedy signals**, initially covering U.S. documents plus WTO and EU publication feeds. It polls machine-readable sources, filters non-customs false positives, normalizes source-backed events, and exposes them through a REST API, a searchable dashboard, and Markdown digests.

> **MVP boundary:** this is a change-signal index, not a customs calculator or legal advice. Every event links to its source. Exact duty calculation requires product classification, origin, preferences, quotas and effective-date rules.

The first sync bootstraps the latest 45 days of matching U.S. Federal Register pages and the items currently exposed by each RSS feed. It is not a complete historical archive; continuous scheduled collection builds the history from that point forward.

## What works today

- U.S. Federal Register JSON API ingestion (tariffs, Section 301/232, anti-dumping, countervailing duties, safeguards)
- WTO official RSS ingestion
- European Commission DG Trade official RSS ingestion
- EUR-Lex Official Journal L legislation-feed ingestion
- Idempotent SQLite storage — corrected items update instead of duplicating
- Source failure isolation and per-source error reporting
- Persistent per-source run ledger exposed by the API
- `GET /api/v1/events` with query, reporter, source and pagination filters
- `GET /api/v1/digest?days=1` for downstream X/YouTube/report workflows
- Responsive dashboard at `/` and OpenAPI docs at `/docs`
- Six-hour GitHub Actions rolling snapshot plus CI, Docker and Compose

## Quick start

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run tariff-radar sync
uv run tariff-radar serve --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. Data defaults to `data/tariff-radar.db`; override it with `--db PATH` or `TARIFF_RADAR_DB`.

```bash
uv run tariff-radar sources
uv run tariff-radar digest --days 7
uv run tariff-radar publish-x --days 1
curl 'http://localhost:8000/api/v1/events?q=steel&limit=20'
```

## Optional X publishing

`publish-x` is dry-run by default: it renders a numbered thread with source links and never touches an account. Live posting uses [xurl](https://github.com/xdevplatform/xurl), the official X API CLI, so OAuth tokens stay in xurl's own profile rather than this application's database or environment.

One-time account setup must be completed manually outside an agent session:

1. Create an app in the X Developer Portal and enable OAuth 2.0 user authentication with `tweet.write`.
2. Install xurl and register/authenticate the app following its official instructions.
3. Verify with `xurl auth status` and `xurl whoami`.
4. Preview with `uv run tariff-radar publish-x --days 1`.
5. Post only after review: `uv run tariff-radar publish-x --days 1 --state-file data/x-state.json --execute`.

The state file makes retries resume a partially published thread instead of creating a second root post. The daily scheduler also uses a lock and one-run-per-Warsaw-date marker. Its morning brief prioritizes final measures over routine proceedings, deduplicates repeated topics, and falls back to the most consequential seven-day developments instead of sending an empty report on quiet days. It remains Discord-only until `TARIFF_RADAR_POST_TO_X=true` is explicitly injected into its runtime. No X credentials are committed to this repository.

### Docker

```bash
docker compose up --build
```

The API and six-hour collector share a persistent volume.

The scheduled GitHub workflow keeps a rolling cached database and publishes a seven-day artifact. It does not host the API; production deployments should use the persistent Compose volume or another durable database.

## API

```http
GET /healthz
GET /api/v1/events?limit=100&offset=0&reporter=United%20States&source=WTO%20News&q=steel
GET /api/v1/sources
GET /api/v1/digest?days=7
GET /docs
```

Example event fields:

```json
{
  "external_id": "2026-17050",
  "source": "US Federal Register",
  "source_url": "https://www.federalregister.gov/...",
  "source_document_url": "https://www.govinfo.gov/...pdf",
  "title": "Silicon Metal ... Antidumping Duty Orders",
  "published_at": "2026-08-21T00:00:00Z",
  "reporter": "United States",
  "measure_type": "anti_dumping",
  "targets": [],
  "products": [],
  "hs_codes": []
}
```

Empty structured arrays mean “not extracted yet”, not “not applicable”.

## Source provenance

| Source | Official entry point | Used as |
|---|---|---|
| U.S. Federal Register | https://www.federalregister.gov/developers/documentation/api/v1 | JSON announcements; links to official GovInfo PDFs |
| WTO | https://www.wto.org/english/res_e/webcas_e/rss_e.htm | Official news RSS |
| European Commission DG Trade | https://policy.trade.ec.europa.eu/news_en | Official trade-news RSS |
| EUR-Lex Official Journal L | https://eur-lex.europa.eu/EN/display-feed.rss?rssId=222 | Official EU legislation RSS |
| WTO Tariff & Trade Data | https://ttd.wto.org/en | Documented expansion source; annual data and tariff-action tracker |
| EU TARIC | https://taxation-customs.ec.europa.eu/online-services/online-services-and-databases-customs/eu-customs-tariff-taric_en | Documented expansion source; daily raw tariff measures |
| GOV.UK Trade Tariff API | https://api.trade-tariff.service.gov.uk/ | Documented expansion source; OAuth credentials currently required |

See [architecture and roadmap](docs/architecture.md) for source limitations and the line-level rate-diff plan.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest --cov=tariff_radar --cov-report=term-missing
```

Tests use captured fixtures; a separate live `sync` is the network smoke test.

## License

MIT. Source publishers retain rights in their source material; follow each source's terms and attribution rules when republishing content.
