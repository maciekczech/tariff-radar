from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tariff_radar.models import TariffEvent

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  external_id TEXT NOT NULL,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_document_url TEXT,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  published_at TEXT NOT NULL,
  effective_from TEXT,
  reporter TEXT,
  targets_json TEXT NOT NULL,
  products_json TEXT NOT NULL,
  hs_codes_json TEXT NOT NULL,
  measure_type TEXT NOT NULL,
  status TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_published ON events(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_reporter ON events(reporter);
CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  status TEXT NOT NULL,
  fetched_count INTEGER NOT NULL,
  inserted_count INTEGER NOT NULL,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_runs_source ON source_runs(source, id DESC);
"""


class EventStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def upsert_many(self, events: list[TariffEvent]) -> int:
        inserted = 0
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            for event in events:
                existed = connection.execute(
                    "SELECT 1 FROM events WHERE event_id = ?", (event.event_id,)
                ).fetchone()
                connection.execute(
                    """INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_id) DO UPDATE SET
                      source_url=excluded.source_url,
                      source_document_url=excluded.source_document_url,
                      title=excluded.title, summary=excluded.summary,
                      published_at=excluded.published_at,
                      effective_from=excluded.effective_from,
                      reporter=excluded.reporter, targets_json=excluded.targets_json,
                      products_json=excluded.products_json, hs_codes_json=excluded.hs_codes_json,
                      measure_type=excluded.measure_type, status=excluded.status,
                      raw_json=excluded.raw_json, updated_at=excluded.updated_at""",
                    (
                        event.event_id,
                        event.external_id,
                        event.source,
                        str(event.source_url),
                        str(event.source_document_url) if event.source_document_url else None,
                        event.title,
                        event.summary,
                        event.published_at.isoformat(),
                        event.effective_from.isoformat() if event.effective_from else None,
                        event.reporter,
                        json.dumps(event.targets),
                        json.dumps(event.products),
                        json.dumps(event.hs_codes),
                        event.measure_type,
                        event.status,
                        json.dumps(event.raw, default=str),
                        now,
                    ),
                )
                inserted += int(existed is None)
        return inserted

    def list_events(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        reporter: str | None = None,
        source: str | None = None,
        query: str | None = None,
        since: datetime | None = None,
    ) -> list[TariffEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        if reporter:
            clauses.append("reporter = ?")
            params.append(reporter)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if query:
            clauses.append("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')")
            literal = self._like_literal(query)
            params.extend([literal, literal])
        if since:
            clauses.append("published_at >= ?")
            params.append(since.isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([min(max(limit, 1), 500), max(offset, 0)])
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM events{where} ORDER BY published_at DESC LIMIT ? OFFSET ?",  # noqa: S608
                params,
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def count_events(
        self,
        *,
        reporter: str | None = None,
        source: str | None = None,
        query: str | None = None,
        since: datetime | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if reporter:
            clauses.append("reporter = ?")
            params.append(reporter)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if query:
            clauses.append("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')")
            literal = self._like_literal(query)
            params.extend([literal, literal])
        if since:
            clauses.append("published_at >= ?")
            params.append(since.isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            return int(
                connection.execute(
                    f"SELECT COUNT(*) FROM events{where}",  # noqa: S608
                    params,
                ).fetchone()[0]
            )

    def record_source_run(
        self,
        *,
        source: str,
        status: str,
        fetched_count: int,
        inserted_count: int,
        error: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO source_runs
                (source, fetched_at, status, fetched_count, inserted_count, error)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    source,
                    datetime.now(UTC).isoformat(),
                    status,
                    fetched_count,
                    inserted_count,
                    error,
                ),
            )

    def latest_source_runs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT source, fetched_at, status, fetched_count, inserted_count, error
                FROM source_runs AS run
                WHERE id = (SELECT MAX(id) FROM source_runs WHERE source = run.source)
                ORDER BY source"""
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _like_literal(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> TariffEvent:
        return TariffEvent(
            external_id=row["external_id"],
            source=row["source"],
            source_url=row["source_url"],
            source_document_url=row["source_document_url"],
            title=row["title"],
            summary=row["summary"],
            published_at=row["published_at"],
            effective_from=row["effective_from"],
            reporter=row["reporter"],
            targets=json.loads(row["targets_json"]),
            products=json.loads(row["products_json"]),
            hs_codes=json.loads(row["hs_codes_json"]),
            measure_type=row["measure_type"],
            status=row["status"],
            raw=json.loads(row["raw_json"]),
        )
