from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import escape

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from tariff_radar.models import EventPage
from tariff_radar.storage import EventStore


def create_app(store: EventStore | None = None) -> FastAPI:
    event_store = store or EventStore("data/tariff-radar.db")
    app = FastAPI(
        title="Tariff Radar API",
        version="0.1.0",
        description="Source-backed signals about tariff and trade-remedy changes.",
    )

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/events", response_model=EventPage)
    def events(
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0, le=1_000_000),
        reporter: str | None = Query(None, max_length=100),
        source: str | None = Query(None, max_length=100),
        q: str | None = Query(None, max_length=200),
    ) -> EventPage:
        items = event_store.list_events(
            limit=limit, offset=offset, reporter=reporter, source=source, query=q
        )
        total = event_store.count_events(reporter=reporter, source=source, query=q)
        return EventPage(total=total, items=items)

    @app.get("/api/v1/digest")
    def digest(days: int = Query(1, ge=1, le=3650)) -> dict[str, object]:
        since = datetime.now(UTC) - timedelta(days=days)
        items = event_store.list_events(limit=500, since=since)
        lines = [f"# Tariff Radar — last {days} day(s)", ""]
        if not items:
            lines.append("No new tariff signals were collected in this period.")
        for event in items:
            actor = f" ({event.reporter})" if event.reporter else ""
            lines.extend(
                [
                    f"- **{event.title}**{actor}",
                    f"  {event.published_at.date().isoformat()} · {event.source} · {event.source_url}",
                ]
            )
        return {
            "generated_at": datetime.now(UTC),
            "count": len(items),
            "markdown": "\n".join(lines),
        }

    @app.get("/", response_class=HTMLResponse)
    def dashboard(
        q: str | None = Query(None, max_length=200),
        reporter: str | None = Query(None, max_length=100),
    ) -> str:
        items = event_store.list_events(limit=100, query=q, reporter=reporter)
        cards = "".join(_event_card(item) for item in items)
        empty = "<div class='empty'>No matching tariff signals yet. Run the sync command.</div>"
        return _page(cards or empty, q or "", reporter or "", event_store.count_events())

    return app


def _event_card(event: object) -> str:
    from tariff_radar.models import TariffEvent

    assert isinstance(event, TariffEvent)
    reporter = escape(event.reporter or "Multi-country / unspecified")
    summary = escape(event.summary[:420])
    url = escape(str(event.source_url), quote=True)
    return f"""
    <article class="card">
      <div class="meta"><span>{escape(event.measure_type.replace("_", " "))}</span><time>{event.published_at.date()}</time></div>
      <h2><a href="{url}" target="_blank" rel="noopener">{escape(event.title)}</a></h2>
      <p>{summary}</p>
      <footer><strong>{reporter}</strong><span>{escape(event.source)}</span></footer>
    </article>"""


def _page(cards: str, q: str, reporter: str, total: int) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tariff Radar</title><style>
:root{{--ink:#14201d;--muted:#67736f;--paper:#f3f1ea;--accent:#ff5b35;--green:#184c3b;--line:#d7d4ca}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 Inter,ui-sans-serif,system-ui}}
header{{background:var(--green);color:white;padding:48px max(5vw,24px) 34px;border-bottom:6px solid var(--accent)}}
.brand{{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;max-width:1180px;margin:auto}} h1{{font:800 clamp(42px,8vw,92px)/.88 Georgia,serif;margin:0;letter-spacing:-.055em}} .tag{{max-width:420px;color:#c9d8d2}}
main{{max-width:1180px;margin:auto;padding:28px max(2vw,16px) 60px}} form{{display:grid;grid-template-columns:2fr 1fr auto;gap:10px;margin-bottom:28px}}
input,button{{border:1px solid var(--line);border-radius:4px;padding:13px 14px;font:inherit;background:white}}button{{background:var(--accent);border-color:var(--accent);font-weight:800;cursor:pointer}}
.stats{{display:flex;justify-content:space-between;color:var(--muted);margin-bottom:14px;text-transform:uppercase;font-size:12px;letter-spacing:.12em}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.card{{background:#fff;border:1px solid var(--line);padding:22px;box-shadow:4px 4px 0 #d9d5ca}}
.card h2{{font:700 25px/1.15 Georgia,serif;margin:12px 0}}a{{color:inherit;text-decoration-thickness:2px;text-decoration-color:var(--accent)}}.card p{{color:#46514d}}
.meta,footer{{display:flex;justify-content:space-between;gap:12px;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}}footer{{border-top:1px solid var(--line);padding-top:14px;margin-top:20px}}footer strong{{color:var(--green)}}.empty{{padding:70px;text-align:center;border:1px dashed var(--muted)}}
@media(max-width:720px){{.brand{{display:block}}.tag{{margin-top:20px}}form{{grid-template-columns:1fr}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><div class="brand"><h1>Tariff<br>Radar</h1><div class="tag">Official signals. Traceable sources. A machine-readable watchtower for tariff and trade-remedy changes.</div></div></header>
<main><form><input name="q" value="{escape(q, quote=True)}" placeholder="Search products, countries, measures…"><input name="reporter" value="{escape(reporter, quote=True)}" placeholder="Reporting country"><button>Filter</button></form>
<div class="stats"><span>{total} stored signals</span><span><a href="/docs">API documentation →</a></span></div><section class="grid">{cards}</section></main></body></html>"""


app = create_app()
