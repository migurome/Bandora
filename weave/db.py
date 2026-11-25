"""Conexión SQLite y esquema (versión 1)."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS artist (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, mbid TEXT UNIQUE, country TEXT, fans INTEGER DEFAULT 0,
  picture TEXT, link TEXT, preview TEXT, preview_title TEXT, level INTEGER NOT NULL DEFAULT 0, updated_at TEXT);
CREATE TABLE IF NOT EXISTS source_id (source TEXT, ext_id TEXT, artist_id INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE,
  PRIMARY KEY (source, ext_id));
CREATE TABLE IF NOT EXISTS alias (artist_id INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE, name TEXT, norm TEXT,
  PRIMARY KEY (artist_id, name));
CREATE INDEX IF NOT EXISTS alias_norm ON alias(norm);
CREATE TABLE IF NOT EXISTS genre (artist_id INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE, name TEXT, weight INTEGER, source TEXT,
  PRIMARY KEY (artist_id, name, source));
CREATE TABLE IF NOT EXISTS relation (a INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE, b INTEGER NOT NULL REFERENCES artist(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'similar', rank INTEGER, source TEXT NOT NULL, PRIMARY KEY (a, b, kind, source), CHECK (a <> b));
CREATE INDEX IF NOT EXISTS relation_b ON relation(b);
CREATE TABLE IF NOT EXISTS crawl (artist_id INTEGER PRIMARY KEY REFERENCES artist(id) ON DELETE CASCADE, target_level INTEGER, hops INTEGER,
  state TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, error TEXT);
INSERT OR IGNORE INTO meta VALUES ('schema_version', '1');
"""


def connect(path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30, isolation_level=None)  # transacciones explícitas en Store
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn
