"""SQLite storage shared by the sampler (writer) and the API (reader).

WAL mode lets the sampler keep writing while the API reads concurrently, which
is exactly the writer/reader split we have here. At ~1 Hz this is trivial load.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent / "fungal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL    NOT NULL,   -- unix epoch seconds, UTC
    voltage REAL    NOT NULL,   -- volts at the ADC input (amplifier output)
    raw     INTEGER             -- raw 16-bit ADC count, nullable
);
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(ts);
"""


@contextmanager
def connect(db_path=DB_PATH):
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path=DB_PATH):
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def insert_reading(ts, voltage, raw=None, db_path=DB_PATH):
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO readings (ts, voltage, raw) VALUES (?, ?, ?)",
            (ts, voltage, raw),
        )


def latest_reading(db_path=DB_PATH):
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT ts, voltage, raw FROM readings ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def readings_since(since_ts, limit=10000, db_path=DB_PATH):
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT ts, voltage, raw FROM readings "
            "WHERE ts > ? ORDER BY ts ASC LIMIT ?",
            (since_ts, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def count_and_span(db_path=DB_PATH):
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
            "FROM readings"
        ).fetchone()
        return dict(row)
