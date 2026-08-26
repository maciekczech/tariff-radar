from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from tariff_radar.service import sync_sources
from tariff_radar.sources import default_sources
from tariff_radar.storage import EventStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tariff-radar")
    parser.add_argument("--db", default=os.getenv("TARIFF_RADAR_DB", "data/tariff-radar.db"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="Fetch all configured official sources")
    serve = sub.add_parser("serve", help="Run API and dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    digest = sub.add_parser("digest", help="Print a Markdown digest")
    digest.add_argument("--days", default=1, type=int)
    sub.add_parser("sources", help="List configured sources")
    return parser


def main() -> None:
    args = _parser().parse_args()
    store = EventStore(Path(args.db))
    if args.command == "sync":
        result = asyncio.run(sync_sources(store, default_sources()))
        print(json.dumps(result.__dict__, indent=2))
        if result.errors:
            raise SystemExit(1)
    elif args.command == "serve":
        import uvicorn

        from tariff_radar.api import create_app

        uvicorn.run(create_app(store), host=args.host, port=args.port)
    elif args.command == "digest":
        from datetime import UTC, datetime, timedelta

        since = datetime.now(UTC) - timedelta(days=args.days)
        events = store.list_events(limit=500, since=since)
        total = store.count_events(since=since)
        print(f"# Tariff Radar — last {args.days} day(s)\n")
        for event in events:
            print(f"- **{event.title}** — `{event.status}` — {event.source} ({event.source_url})")
        if total > len(events):
            print(f"\n_Truncated: showing {len(events)} of {total} signals._")
    elif args.command == "sources":
        for source in default_sources():
            print(f"{source.name}\t{source.url}")


if __name__ == "__main__":
    main()
