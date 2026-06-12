"""
query.py — HFWatch data query helpers
All queries accept a target_grid parameter to filter by grid.
"""

import time
from db import get_conn, BAND_ORDER, DEFAULT_DB


def get_heatmap(hours: int = 24, target_grid: str = "CN87", db_path=DEFAULT_DB) -> dict:
    """
    Returns band x UTC-hour spot counts for the last `hours` hours.
    """
    conn = get_conn(db_path)
    cutoff = int(time.time()) - (hours * 3600)

    rows = conn.execute(
        """SELECT band,
                  CAST(strftime('%H', datetime(flow_start, 'unixepoch')) AS INTEGER) AS hour,
                  COUNT(*) as cnt,
                  ROUND(AVG(CASE WHEN snr IS NOT NULL THEN snr END), 0) as avg_snr
           FROM spots
           WHERE flow_start >= ?
             AND band IS NOT NULL
             AND target_grid = ?
           GROUP BY band, hour
           ORDER BY band, hour""",
        (cutoff, target_grid),
    ).fetchall()

    totals = conn.execute(
        """SELECT band, COUNT(*) as cnt
           FROM spots
           WHERE flow_start >= ?
             AND band IS NOT NULL
             AND target_grid = ?
           GROUP BY band""",
        (cutoff, target_grid),
    ).fetchall()
    conn.close()

    matrix = {b: {h: 0 for h in range(24)} for b in BAND_ORDER}
    snr_matrix = {b: {h: None for h in range(24)} for b in BAND_ORDER}
    for row in rows:
        if row["band"] in matrix:
            matrix[row["band"]][row["hour"]] = row["cnt"]
            snr_matrix[row["band"]][row["hour"]] = row["avg_snr"]

    totals_map = {r["band"]: r["cnt"] for r in totals if r["band"] in BAND_ORDER}
    active_bands = [b for b in BAND_ORDER if totals_map.get(b, 0) > 0]
    peak = max((matrix[b][h] for b in active_bands for h in range(24)), default=1)

    return {
        "bands": active_bands,
        "hours": list(range(24)),
        "matrix": {b: matrix[b] for b in active_bands},
        "snr_matrix": {b: snr_matrix[b] for b in active_bands},
        "totals": totals_map,
        "peak": peak,
        "window_hours": hours,
        "from_ts": cutoff,
        "to_ts": int(time.time()),
        "target_grid": target_grid,
        "from_ts": cutoff,
        "to_ts": int(__import__("time").time()),
    }


def get_weekly_avg(target_grid: str = "CN87", db_path=DEFAULT_DB) -> dict:
    """
    Returns band x UTC-hour average spot counts over the last 7 days.
    """
    conn = get_conn(db_path)
    cutoff = int(time.time()) - (7 * 24 * 3600)

    rows = conn.execute(
        """SELECT band,
                  CAST(strftime('%H', datetime(flow_start, 'unixepoch')) AS INTEGER) AS hour,
                  COUNT(*) as cnt,
                  COUNT(DISTINCT strftime('%Y-%m-%d', datetime(flow_start, 'unixepoch'))) as days
           FROM spots
           WHERE flow_start >= ?
             AND band IS NOT NULL
             AND target_grid = ?
           GROUP BY band, hour""",
        (cutoff, target_grid),
    ).fetchall()

    totals = conn.execute(
        """SELECT band, COUNT(*) as cnt
           FROM spots
           WHERE flow_start >= ?
             AND band IS NOT NULL
             AND target_grid = ?
           GROUP BY band""",
        (cutoff, target_grid),
    ).fetchall()
    conn.close()

    matrix = {b: {h: 0 for h in range(24)} for b in BAND_ORDER}
    for row in rows:
        if row["band"] in matrix and row["days"] > 0:
            matrix[row["band"]][row["hour"]] = round(row["cnt"] / row["days"])

    totals_map = {r["band"]: r["cnt"] for r in totals if r["band"] in BAND_ORDER}
    active_bands = [b for b in BAND_ORDER if totals_map.get(b, 0) > 0]
    peak = max((matrix[b][h] for b in active_bands for h in range(24)), default=1)

    return {
        "bands": active_bands,
        "hours": list(range(24)),
        "matrix": {b: matrix[b] for b in active_bands},
        "totals": totals_map,
        "peak": peak,
        "window_hours": 168,
        "target_grid": target_grid,
        "from_ts": cutoff,
        "to_ts": int(__import__("time").time()),
    }


def get_stats(db_path=DEFAULT_DB) -> dict:
    """
    Returns summary statistics for the database, across all grids.
    """
    conn = get_conn(db_path)

    total = conn.execute("SELECT COUNT(*) as cnt FROM spots").fetchone()["cnt"]
    oldest = conn.execute("SELECT MIN(flow_start) as t FROM spots").fetchone()["t"]
    latest = conn.execute("SELECT MAX(flow_start) as t FROM spots").fetchone()["t"]
    last_fetch = conn.execute(
        "SELECT fetched_at, spots_new, grid FROM fetch_log ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    config = conn.execute("SELECT key, value FROM config").fetchall()
    active_grids = conn.execute(
        "SELECT DISTINCT target_grid FROM spots ORDER BY target_grid"
    ).fetchall()

    conn.close()

    cfg = {r["key"]: r["value"] for r in config}
    return {
        "total_spots": total,
        "oldest_spot": oldest,
        "latest_spot": latest,
        "last_fetch_at": last_fetch["fetched_at"] if last_fetch else None,
        "last_fetch_new": last_fetch["spots_new"] if last_fetch else 0,
        "last_fetch_grid": last_fetch["grid"] if last_fetch else None,
        "grid": cfg.get("grid", "CN87"),
        "grids": cfg.get("grids", "CN87"),
        "active_grids": [r["target_grid"] for r in active_grids],
    }


def get_timeseries(hours: int = 24, resolution_minutes: int = 30,
                   target_grid: str = "CN87", snap_to_utc_day: bool = False,
                   db_path=DEFAULT_DB) -> dict:
    """
    Returns spot counts per band in time buckets of resolution_minutes.
    Filters by target_grid. Used for the time-series line chart.

    If snap_to_utc_day is True, from_ts is anchored to UTC midnight
    ceil(hours/24) days ago instead of a rolling now-hours window.
    This keeps the chart aligned with the heatmap's hour-of-day view.
    """
    import math
    from datetime import datetime, timezone, timedelta
    now_ts = int(time.time())
    if snap_to_utc_day:
        today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        days_back = math.ceil(hours / 24) - 1
        from_dt = today_utc - timedelta(days=days_back)
        from_ts = int(from_dt.timestamp())
    else:
        from_ts = now_ts - (hours * 3600)
    bucket_seconds = resolution_minutes * 60

    conn = get_conn(db_path)
    rows = conn.execute(
        """
        SELECT band,
               (flow_start / :bucket * :bucket) AS bucket,
               COUNT(*) AS cnt
        FROM   spots
        WHERE  flow_start >= :from_ts
          AND  band IS NOT NULL
          AND  target_grid = :grid
        GROUP  BY band, bucket
        ORDER  BY bucket
        """,
        {"bucket": bucket_seconds, "from_ts": from_ts, "grid": target_grid},
    ).fetchall()
    conn.close()

    first_bucket = (from_ts // bucket_seconds) * bucket_seconds
    if snap_to_utc_day:
        # Extend to 23:59 UTC of the final day so the full day frame is always shown
        from datetime import datetime, timezone, timedelta
        final_day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day_ts = int((final_day_start + timedelta(days=1)).timestamp()) - 1
        last_bucket = (end_of_day_ts // bucket_seconds) * bucket_seconds
    else:
        last_bucket = (now_ts // bucket_seconds) * bucket_seconds
    buckets = list(range(first_bucket, last_bucket + bucket_seconds, bucket_seconds))

    lookup = {}
    for row in rows:
        b = row["band"]
        if b not in lookup:
            lookup[b] = {}
        lookup[b][row["bucket"]] = row["cnt"]

    active_bands = [b for b in BAND_ORDER if b in lookup]
    series = {b: [lookup[b].get(bkt, 0) for bkt in buckets] for b in active_bands}

    return {
        "bands":              active_bands,
        "buckets":            buckets,
        "series":             series,
        "resolution_minutes": resolution_minutes,
        "lookback_hours":     hours,
        "target_grid":        target_grid,
        "snap_to_utc_day":    snap_to_utc_day,
    }
