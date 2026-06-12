#!/usr/bin/env python3
"""
prune.py — HFWatch database pruning
Deletes spots older than prune_days (configured in the database, default 90).
Called nightly by hfwatch-prune.timer.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_conn, prune_old_spots, get_config, DEFAULT_DB

def main():
    parser = argparse.ArgumentParser(description="HFWatch database pruning")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite database")
    args = parser.parse_args()

    db = Path(args.db)
    conn = get_conn(db)
    days = int(get_config(conn).get("prune_days", 90))
    deleted = prune_old_spots(conn, days)
    print(f"Pruned {deleted} spots older than {days} days.")
    conn.close()

if __name__ == "__main__":
    main()
