# Architecture

## Product boundary

Tariff Radar is an **official-signal index**, not a customs calculator and not legal advice. It answers “what tariff or trade-remedy change was announced?” and always links back to the issuing source. Exact payable duty depends on product classification, origin, preference, quota and effective date; those calculations belong to later country-specific rate adapters.

## Pipeline

```text
Official API/RSS → source adapter → relevance gate → normalized TariffEvent
                 → idempotent SQLite upsert → REST API / dashboard / Markdown digest
```

A failed source is isolated: other sources still ingest, the CLI reports errors by source, and a persistent source-run ledger records freshness and the latest error for `/api/v1/sources`. The stable key is `source + external_id`; reruns update corrected documents without duplicating them.

## Current sources

| Source | Machine format | Role | Limitation |
|---|---|---|---|
| U.S. Federal Register API | JSON, no API key | U.S. tariff, anti-dumping, countervailing and safeguard notices | Search results require relevance filtering; FederalRegister.gov is an informational XML rendition and links to official GovInfo PDFs |
| WTO latest-news feed | RSS | Multilateral notifications, disputes and global tariff signals | News signals, not a full line-level rate schedule |
| European Commission DG Trade news | RSS | EU tariff and trade-defence announcements | News signals, not the daily TARIC measure dump |
| EUR-Lex Official Journal L | RSS | Binding EU acts and regulations | Broad legislation feed; deterministic relevance filtering is required |

Federal Register collection paginates matching documents from a rolling 45-day window. WTO and DG Trade bootstrap from their current feed windows; regular collection is therefore required to avoid gaps and build a durable history.

## Expansion path

1. Add WTO–IMF Tariff Tracker snapshots when a documented redistribution endpoint is available.
2. Add EU TARIC raw-data snapshots and compute diffs by measure/product/origin/effective date.
3. Add authenticated GOV.UK Trade Tariff snapshots and diffs.
4. Add U.S. HTS revision diffing via USITC data.
5. Extract targets, products, HS codes, rates and effective dates with deterministic rules first, optionally with an LLM enrichment stage that never overwrites source text.
6. Add publication adapters for X threads, YouTube scripts and webhook notifications on top of `/api/v1/digest`.

## Data model

Each event retains source identity, source URL, official document URL when supplied, publication/effective dates, reporter, targets, products, HS codes, measure type and status. Empty structured fields mean “not extracted”, never “not applicable”. Raw source payload is stored internally for future reprocessing.

## Deployment

SQLite is sufficient for one collector and read-heavy API. Mount `/data` persistently. For horizontal scale, replace `EventStore` with PostgreSQL while preserving the API/model boundary. Run collection every six hours; source freshness, not polling frequency, is the practical limit.

The scheduled GitHub workflow restores and saves a rolling SQLite cache, then publishes a seven-day digest and database artifact. This is a hosted demonstration/snapshot, not the serving database. A deployed API and collector must share the persistent `/data` volume shown in `compose.yml`.
