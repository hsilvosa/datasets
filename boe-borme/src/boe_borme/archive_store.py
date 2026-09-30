"""Persistent, content-addressed archive and append-only extraction ledger."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .io_utils import atomic_bytes


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def digest(content: bytes | str) -> str:
    return hashlib.sha256(content.encode() if isinstance(content, str) else content).hexdigest()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def official_url(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname not in ("boe.es", "www.boe.es"):
        return None
    if parts.username or parts.password or parts.port not in (None, 80, 443):
        return None
    return urlunsplit(("https", "www.boe.es", parts.path, parts.query, ""))


@dataclass(frozen=True)
class ArchiveConfig:
    root: Path
    legacy_raw: Path | None = None
    start_date: str = "2023-01-01"
    end_date: str | None = "2025-12-31"
    include_legislation: bool = True
    request_delay_seconds: float = 0.3
    max_workers: int = 4
    timeout_seconds: int = 120
    max_retries: int = 5
    refresh_days: int = 7
    recheck_after_days: int = 30
    chunk_chars: int = 4000
    chunk_overlap: int = 400
    ocr_min_confidence: float = 0.9
    ocr_dpi: int = 200

    @classmethod
    def load(cls, path: str | Path) -> ArchiveConfig:
        path = Path(path).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown archive settings: {sorted(unknown)}")
        for name in ("root", "legacy_raw"):
            if data.get(name):
                value = Path(data[name])
                data[name] = value if value.is_absolute() else path.parent.parent / value
        config = cls(**data)
        from datetime import date
        if date.fromisoformat(config.start_date) > date.fromisoformat(config.end):
            raise ValueError("start_date must not follow end_date")
        if not 0 <= config.chunk_overlap < config.chunk_chars:
            raise ValueError("chunk_overlap must be smaller than chunk_chars")
        if config.max_workers < 1 or config.request_delay_seconds < 0:
            raise ValueError("Invalid worker count or request delay")
        if config.recheck_after_days < 1 or config.refresh_days < 0:
            raise ValueError("Invalid recheck interval")
        return config

    @property
    def end(self) -> str:
        return self.end_date or utcnow()[:10]


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "manifest.sqlite", timeout=60)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT,
          status TEXT, config_json TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS resources (
          url TEXT PRIMARY KEY, kind TEXT NOT NULL, priority INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', sha256 TEXT,
          etag TEXT, last_modified TEXT, checked_at TEXT,
          attempts INTEGER NOT NULL DEFAULT 0, error TEXT);
        CREATE INDEX IF NOT EXISTS resource_queue ON resources(status, priority);
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, publication TEXT, publication_date TEXT, title TEXT,
          category TEXT, metadata_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS document_versions (
          document_id TEXT, metadata_sha256 TEXT, metadata_json TEXT,
          observed_at TEXT, run_id TEXT, PRIMARY KEY(document_id, metadata_sha256));
        CREATE TABLE IF NOT EXISTS links (
          document_id TEXT NOT NULL, url TEXT NOT NULL, role TEXT NOT NULL,
          required INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY(document_id, url, role));
        CREATE INDEX IF NOT EXISTS links_url ON links(url);
        CREATE TABLE IF NOT EXISTS snapshots (
          id INTEGER PRIMARY KEY, url TEXT, sha256 TEXT, size_bytes INTEGER,
          path TEXT, headers_json TEXT, retrieved_at TEXT, run_id TEXT,
          status TEXT NOT NULL DEFAULT 'pending', error TEXT,
          UNIQUE(url, sha256));
        CREATE TABLE IF NOT EXISTS observations (
          id INTEGER PRIMARY KEY, url TEXT, sha256 TEXT, http_status INTEGER,
          observed_at TEXT, run_id TEXT, headers_json TEXT);
        CREATE TABLE IF NOT EXISTS records (
          seq INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, table_name TEXT NOT NULL,
          document_id TEXT, publication TEXT, year INTEGER, source_url TEXT,
          source_sha256 TEXT, parser_version TEXT, payload_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS record_table ON records(table_name, seq);
        CREATE INDEX IF NOT EXISTS record_document ON records(document_id,table_name,source_url,source_sha256);
        CREATE TABLE IF NOT EXISTS exports (
          filename TEXT PRIMARY KEY, table_name TEXT, last_seq INTEGER, sha256 TEXT);
        CREATE TABLE IF NOT EXISTS issues (
          key TEXT PRIMARY KEY, document_id TEXT, url TEXT, category TEXT,
          detail TEXT, resolved INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE VIEW IF NOT EXISTS current_records AS
          SELECT r.* FROM records r JOIN resources s ON r.source_url=s.url
          AND r.source_sha256=s.sha256 WHERE s.status='downloaded'
          AND r.parser_version=COALESCE((SELECT value FROM settings WHERE key='parser_version'),r.parser_version);
        CREATE VIEW IF NOT EXISTS rag_chunks_current AS
          SELECT r.* FROM current_records r WHERE table_name='rag_chunks'
          AND COALESCE(json_extract(payload_json,'$.requires_review'),0)=0
          AND COALESCE(json_extract(payload_json,'$.is_latest_version'),1)=1;
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def enqueue(self, url: str, kind: str, priority: int = 50,
                document_id: str | None = None, role: str | None = None,
                required: bool = True) -> str | None:
        url = official_url(url)
        if not url:
            if required and document_id:
                self.issue(document_id, "", "external_resource", "Non-BOE resource requires review")
            return None
        self.db.execute(
            "INSERT OR IGNORE INTO resources(url,kind,priority) VALUES(?,?,?)",
            (url, kind, priority),
        )
        self.db.execute("UPDATE resources SET kind=?,status='pending' WHERE url=? AND kind<>?",
                        (kind, url, kind))
        if document_id:
            cursor = self.db.execute("INSERT OR IGNORE INTO links VALUES(?,?,?,?)",
                                     (document_id, url, role or kind, int(required)))
            if cursor.rowcount:
                self.db.execute("UPDATE snapshots SET status='pending' WHERE url=? AND "
                                "sha256=(SELECT sha256 FROM resources WHERE url=?)",
                                (url, url))
        return url

    def document(self, document_id: str, publication: str, day: str | None,
                 title: str | None, metadata: dict, category: str, run_id: str) -> None:
        payload = json_text(metadata)
        self.db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                        "publication_date=excluded.publication_date,title=excluded.title,"
                        "metadata_json=excluded.metadata_json",
                        (document_id, publication, day, title, category, payload))
        self.db.execute("INSERT OR IGNORE INTO document_versions VALUES(?,?,?,?,?)",
                        (document_id, digest(payload), payload, utcnow(), run_id))

    def snapshot(self, url: str, content: bytes, headers: dict, run_id: str,
                 retrieved_at: str | None = None) -> str:
        checksum = digest(content)
        path = Path("objects") / checksum[:2] / checksum
        target = self.root / path
        if not target.exists():
            atomic_bytes(target, content)
        elif digest(target.read_bytes()) != checksum:
            raise RuntimeError(f"Corrupt archive object: {target}")
        stamp = retrieved_at or utcnow()
        self.db.execute("INSERT OR IGNORE INTO snapshots"
                        "(url,sha256,size_bytes,path,headers_json,retrieved_at,run_id)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (url, checksum, len(content), str(path), json_text(headers), stamp, run_id))
        lower = {k.lower(): v for k, v in headers.items()}
        self.db.execute("UPDATE resources SET status='downloaded',sha256=?,etag=?,"
                        "last_modified=?,checked_at=?,error=NULL WHERE url=?",
                        (checksum, lower.get("etag"), lower.get("last-modified"), stamp, url))
        self.db.execute("INSERT INTO observations(url,sha256,http_status,observed_at,run_id,"
                        "headers_json) VALUES(?,?,200,?,?,?)",
                        (url, checksum, stamp, run_id, json_text(headers)))
        return checksum

    def issue(self, document_id: str, url: str, category: str, detail: str) -> None:
        key = digest(json_text([document_id, url, category, detail]))
        self.db.execute("INSERT OR IGNORE INTO issues VALUES(?,?,?,?,?,0)",
                        (key, document_id, url, category, detail))

    def record(self, table: str, document_id: str, url: str, checksum: str,
               parser_version: str, item_id: str, payload: dict) -> None:
        doc = self.db.execute("SELECT publication,publication_date FROM documents WHERE id=?",
                              (document_id,)).fetchone()
        year = int(doc["publication_date"][:4]) if doc and doc["publication_date"] else None
        key = digest(json_text([table, document_id, url, checksum, parser_version, item_id]))
        self.db.execute("INSERT OR IGNORE INTO records"
                        "(key,table_name,document_id,publication,year,source_url,source_sha256,"
                        "parser_version,payload_json) VALUES(?,?,?,?,?,?,?,?,?)",
                        (key, table, document_id, doc["publication"] if doc else None, year,
                         url, checksum, parser_version, json_text(payload)))
