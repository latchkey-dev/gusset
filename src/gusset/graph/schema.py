"""SQLite schema for the code graph.

Node kinds: module (one per file), class, function, method.
Edge kinds: calls, imports, inherits.
Unresolved references are counted, never silently invented — the oracle
must be able to say "this edge exists" with a straight face.
"""

import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id       INTEGER PRIMARY KEY,
    path     TEXT NOT NULL UNIQUE,   -- repo-relative, POSIX separators
    language TEXT NOT NULL,
    sha      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS symbols (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,        -- bare name, e.g. "helper"
    qualname   TEXT NOT NULL,        -- dotted path, e.g. "pkg.lib.helper"
    kind       TEXT NOT NULL,        -- module | class | function | method
    start_line INTEGER NOT NULL,     -- 1-based
    end_line   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualname ON symbols(qualname);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);

CREATE TABLE IF NOT EXISTS edges (
    id   INTEGER PRIMARY KEY,
    src  INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    dst  INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,              -- calls | imports | inherits
    line INTEGER NOT NULL,           -- 1-based, where the reference occurs
    UNIQUE (src, dst, kind, line)
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);

CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    name, qualname, content='symbols', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS symbols_ai AFTER INSERT ON symbols BEGIN
    INSERT INTO symbols_fts(rowid, name, qualname)
    VALUES (new.id, new.name, new.qualname);
END;
CREATE TRIGGER IF NOT EXISTS symbols_ad AFTER DELETE ON symbols BEGIN
    INSERT INTO symbols_fts(symbols_fts, rowid, name, qualname)
    VALUES ('delete', old.id, old.name, old.qualname);
END;
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    return conn
