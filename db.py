"""
db.py — HFWatch database schema and helpers
SQLite backend for PSK Reporter spot storage
"""

import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / "hfwatch.db"

BAND_MAP = [
    (1_800_000,   2_000_000,  "160m"),
    (3_500_000,   4_000_000,  "80m"),
    (5_330_500,   5_403_500,  "60m"),
    (7_000_000,   7_300_000,  "40m"),
    (10_100_000, 10_150_000,  "30m"),
    (14_000_000, 14_350_000,  "20m"),
    (18_068_000, 18_168_000,  "17m"),
    (21_000_000, 21_450_000,  "15m"),
    (24_890_000, 24_990_000,  "12m"),
    (28_000_000, 29_700_000,  "10m"),
    (50_000_000, 54_000_000,  "6m"),
]

BAND_ORDER = ["160m","80m","60m","40m","30m","20m","17m","15m","12m","10m","6m"]


def freq_to_band(freq_hz: int) -> str | None:
    for lo, hi, name in BAND_MAP:
        if lo <= freq_hz <= hi:
            return name
    return None


def get_conn(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(db_path: str | Path = DEFAULT_DB):
    """Create tables if they don't exist, and migrate existing schema."""
    with get_conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS spots (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                flow_start        INTEGER NOT NULL,
                sender_callsign   TEXT    NOT NULL,
                receiver_callsign TEXT    NOT NULL,
                receiver_locator  TEXT    NOT NULL,
                frequency_hz      INTEGER NOT NULL,
                band              TEXT,
                mode              TEXT,
                snr               INTEGER,

                inserted_at       INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                UNIQUE(sender_callsign, receiver_callsign, flow_start, frequency_hz)
            );

            CREATE INDEX IF NOT EXISTS idx_spots_band_time
                ON spots(band, flow_start);

            CREATE INDEX IF NOT EXISTS idx_spots_flow
                ON spots(flow_start);


            CREATE TABLE IF NOT EXISTS fetch_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                grid        TEXT    NOT NULL,
                spots_found INTEGER NOT NULL DEFAULT 0,
                spots_new   INTEGER NOT NULL DEFAULT 0,
                error       TEXT
            );

            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO config(key, value) VALUES ('grid', 'CN87');
            INSERT OR IGNORE INTO config(key, value) VALUES ('grids', 'CN87');
            INSERT OR IGNORE INTO config(key, value) VALUES ('fetch_interval_minutes', '15');
            INSERT OR IGNORE INTO config(key, value) VALUES ('prune_days', '90');
        """)

        # Migrate existing spots table if target_grid column missing
        cols = [r[1] for r in conn.execute("PRAGMA table_info(spots)").fetchall()]
        if 'target_grid' not in cols:
            print("Migrating database: adding target_grid column...")
            conn.execute("ALTER TABLE spots ADD COLUMN target_grid TEXT NOT NULL DEFAULT 'CN87'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_spots_target_grid ON spots(target_grid, band, flow_start)")
            conn.commit()
            print("Migration complete.")

    print(f"Database initialised at {db_path}")


def get_config(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_config(conn: sqlite3.Connection, key: str, value: str):
    conn.execute(
        "INSERT INTO config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    conn.commit()


def get_grids(conn: sqlite3.Connection) -> list[str]:
    """Return list of configured collection grids."""
    cfg = get_config(conn)
    grids_str = cfg.get("grids", cfg.get("grid", "CN87"))
    return [g.strip().upper() for g in grids_str.split(",") if g.strip()]


def set_grids(conn: sqlite3.Connection, grids: list[str]):
    """Save list of collection grids."""
    set_config(conn, "grids", ",".join(g.upper() for g in grids))


def get_active_grids(conn: sqlite3.Connection) -> list[str]:
    """Return grids that actually have spot data in the DB."""
    rows = conn.execute(
        "SELECT DISTINCT target_grid FROM spots ORDER BY target_grid"
    ).fetchall()
    return [r[0] for r in rows]


def prune_old_spots(conn: sqlite3.Connection, days: int = 90) -> int:
    """Delete spots older than `days` days. Returns number of rows deleted."""
    cutoff = int(time.time()) - (days * 86400)
    conn.execute("DELETE FROM spots WHERE flow_start < ?", (cutoff,))
    conn.commit()
    deleted = conn.execute("SELECT changes()").fetchone()[0]
    return deleted


if __name__ == "__main__":
    init_db()
