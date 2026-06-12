#!/usr/bin/env python3
"""
collector.py — HFWatch PSK Reporter spot fetcher
Designed to run every 15 minutes via cron or systemd timer.
"""

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from db import DEFAULT_DB, freq_to_band, get_conn, init_db, get_config, set_config, get_grids, set_grids

PSKREPORTER_URL = "https://retrieve.pskreporter.info/query"

QUERY_PARAMS = {
    "rronly": "1",
    "modify": "grid",
    "flowStartSeconds": None,
    "receiverLocator": None,
    "frange": "1800000-54000000",
}

LOOKBACK_SECONDS = 1000


def fetch_spots(grid: str, lookback_seconds: int = LOOKBACK_SECONDS) -> list[dict]:
    params = dict(QUERY_PARAMS)
    params["receiverLocator"] = grid
    params["flowStartSeconds"] = f"-{lookback_seconds}"

    headers = {
        "User-Agent": "HFWatch/1.0 (ham-radio band activity tool; contact via github)",
        "Accept": "application/xml",
    }

    resp = requests.get(PSKREPORTER_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return parse_xml(resp.text)


def parse_xml(xml_text: str) -> list[dict]:
    spots = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"XML parse error: {e}", file=sys.stderr)
        return spots

    for report in root.iter("receptionReport"):
        spot = _extract_spot(report)
        if spot:
            spots.append(spot)

    if not spots:
        for report in root.iter("{http://xmlreporter.net/psk-report}receptionReport"):
            spot = _extract_spot(report)
            if spot:
                spots.append(spot)

    return spots


def _extract_spot(elem) -> dict | None:
    try:
        freq_str = elem.get("frequency", "0")
        freq_hz = int(freq_str) if freq_str else 0
        if freq_hz == 0:
            return None

        flow_start = elem.get("flowStartSeconds", "0")
        sender = elem.get("senderCallsign", "").upper().strip()
        receiver = elem.get("receiverCallsign", "").upper().strip()
        receiver_loc = elem.get("receiverLocator", "").upper().strip()
        mode = elem.get("mode", "").strip()
        snr_str = elem.get("sNR", "")
        snr = int(snr_str) if snr_str.lstrip("-").isdigit() else None

        if not sender or not receiver:
            return None

        return {
            "flow_start": int(flow_start),
            "sender_callsign": sender,
            "receiver_callsign": receiver,
            "receiver_locator": receiver_loc,
            "frequency_hz": freq_hz,
            "band": freq_to_band(freq_hz),
            "mode": mode or None,
            "snr": snr,
        }
    except (ValueError, TypeError):
        return None


def store_spots(conn, spots: list[dict], target_grid: str) -> int:
    new_count = 0
    for s in spots:
        row = dict(s)
        row["target_grid"] = target_grid
        try:
            conn.execute(
                """INSERT OR IGNORE INTO spots
                   (flow_start, sender_callsign, receiver_callsign,
                    receiver_locator, frequency_hz, band, mode, snr, target_grid)
                   VALUES (:flow_start, :sender_callsign, :receiver_callsign,
                           :receiver_locator, :frequency_hz, :band, :mode, :snr, :target_grid)""",
                row,
            )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                new_count += 1
        except Exception as e:
            print(f"DB insert error for {s}: {e}", file=sys.stderr)
    conn.commit()
    return new_count


def log_fetch(conn, grid: str, found: int, new: int, error: str | None = None):
    conn.execute(
        "INSERT INTO fetch_log(grid, spots_found, spots_new, error) VALUES(?,?,?,?)",
        (grid, found, new, error),
    )
    conn.commit()


def run_grid(grid: str, db_path: Path, lookback: int):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[{ts}] Fetching spots for grid {grid}...")

    conn = get_conn(db_path)
    error_msg = None
    spots = []
    new_count = 0

    try:
        spots = fetch_spots(grid, lookback)
        print(f"  [{grid}] Received {len(spots)} spot(s)")
        new_count = store_spots(conn, spots, grid)
        print(f"  [{grid}] {new_count} new spot(s) stored")
    except requests.RequestException as e:
        error_msg = str(e)
        print(f"  [{grid}] Fetch error: {e}", file=sys.stderr)
    except Exception as e:
        error_msg = str(e)
        print(f"  [{grid}] Unexpected error: {e}", file=sys.stderr)
    finally:
        log_fetch(conn, grid, len(spots), new_count, error_msg)
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="HFWatch PSK Reporter collector")
    parser.add_argument("--grid",     default=None,            help="Grid(s) to fetch, comma-separated (overrides DB config)")
    parser.add_argument("--db",       default=str(DEFAULT_DB), help="Path to SQLite database")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_SECONDS,
                        help="Seconds of history to fetch (default: 1000)")
    parser.add_argument("--add-grid", default=None, metavar="GRID", help="Add a grid to the collection list")
    parser.add_argument("--remove-grid", default=None, metavar="GRID", help="Remove a grid from the collection list")
    parser.add_argument("--list-grids", action="store_true", help="List configured grids and exit")
    args = parser.parse_args()

    db_path = Path(args.db)
    init_db(db_path)

    with get_conn(db_path) as conn:
        # Handle grid management commands
        if args.list_grids:
            grids = get_grids(conn)
            print("Configured grids:", ", ".join(grids))
            return

        if args.add_grid:
            grids = get_grids(conn)
            new_grid = args.add_grid.upper().strip()
            if new_grid not in grids:
                grids.append(new_grid)
                set_grids(conn, grids)
                print(f"Added grid {new_grid}. Configured grids: {', '.join(grids)}")
            else:
                print(f"Grid {new_grid} already configured.")
            return

        if args.remove_grid:
            grids = get_grids(conn)
            rem_grid = args.remove_grid.upper().strip()
            if rem_grid in grids:
                grids.remove(rem_grid)
                set_grids(conn, grids)
                print(f"Removed grid {rem_grid}. Configured grids: {', '.join(grids)}")
            else:
                print(f"Grid {rem_grid} not found in configured grids.")
            return

        # Determine grids to fetch
        if args.grid:
            grids = [g.strip().upper() for g in args.grid.split(",") if g.strip()]
        else:
            grids = get_grids(conn)

    # Fetch each grid, with a small delay between requests to respect PSK Reporter
    for i, grid in enumerate(grids):
        if i > 0:
            time.sleep(10)  # 10s between grids to be polite to PSK Reporter
        run_grid(grid, db_path, args.lookback)


if __name__ == "__main__":
    main()
