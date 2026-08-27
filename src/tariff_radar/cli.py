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
    publish_x = sub.add_parser("publish-x", help="Preview or publish a daily X thread")
    publish_x.add_argument("--days", default=1, type=int)
    publish_x.add_argument("--state-file", type=Path)
    publish_x.add_argument(
        "--execute",
        action="store_true",
        help="Actually post through an already authenticated xurl profile",
    )
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
    elif args.command == "publish-x":
        from datetime import UTC, datetime, timedelta

        from tariff_radar.publishing import build_x_thread

        since = datetime.now(UTC) - timedelta(days=args.days)
        events = store.list_events(limit=100, since=since)
        total = store.count_events(since=since)
        posts = build_x_thread(events, generated_at=datetime.now(UTC), detected_total=total)
        if args.execute:
            from tariff_radar.publishers.xurl import publish_thread_with_xurl

            ids = publish_thread_with_xurl(posts, state_path=args.state_file)
            print(json.dumps({"posted": len(ids), "ids": ids}))
        else:
            for index, post in enumerate(posts, start=1):
                print(f"--- X POST {index}/{len(posts)} ---\n{post}\n")


if __name__ == "__main__":
    main()
