# HFWatch — HF Band Activity Monitor

HFWatch polls [PSK Reporter](https://pskreporter.info) every 15 minutes, stores reception spots in a local SQLite database, and serves a web dashboard that shows when each amateur radio band is active at your location.

The core view is a **band × UTC-hour heatmap**: rows are HF bands (160m through 6m), columns are hours of the day (00–23 UTC), and color intensity reflects spot count. After a few days of collection you have a reliable picture of your local propagation windows without having to be at the radio.

Built with Python, Flask, and SQLite. Runs well on a Raspberry Pi or any Debian/Ubuntu box.

<img width="1739" height="1125" alt="HFWatch" src="https://github.com/user-attachments/assets/6157d8de-4e04-40ce-8a24-daf657538b6e" />

---

## Features

- **Heatmap view** — band × UTC-hour spot density, color-scaled per window
- **SNR overlay** — toggle to show average signal-to-noise ratio instead of spot count
- **Data table view** — numeric spot counts for the same matrix, useful for exporting
- **Time-series chart** — per-band line chart with configurable resolution and time window
- **7-day average** — smoothed heatmap averaged across the past week, good for identifying recurring propagation patterns
- **Multi-grid support** — collect data for multiple Maidenhead grid squares simultaneously; switch between them in the dashboard
- **Time window controls** — 24h, 48h, 72h, 7-day rolling, or 7-day average
- **Automatic pruning** — nightly systemd timer deletes spots older than 90 days (configurable)
- **Dual UTC/local time axes** — heatmap and table show both UTC and your browser's local time
- **Live clock** in the dashboard header

---

## What it does not do

- It does not transmit anything. HFWatch is receive-only, pulling data from PSK Reporter's public API.
- It does not decode signals. The spot data comes from other stations who have reported hearing callsigns in your grid square.
- It is not a real-time bandscope. The 15-minute poll interval is intentional — PSK Reporter rate-limits frequent requests, and this interval produces a smooth picture without hammering their servers.

---

## Requirements

- Python 3.11 or later
- A Debian or Ubuntu system (Raspberry Pi OS works fine)
- Internet access to reach `retrieve.pskreporter.info`
- Port of your choice open on the local network (default: 5000)

No amateur radio license is required to run HFWatch. You do not need a callsign or a radio — only internet access.

---

## Quick install

```bash
git clone https://github.com/EtherHamRadio/hfwatch.git
cd hfwatch
chmod +x install.sh
sudo ./install.sh
```

The installer creates a Python virtual environment, installs dependencies, writes systemd unit files, and starts the services. The dashboard will be available at:

```
http://<your-host-ip>:5000
```

The first spots arrive within 15 minutes of the collector's first run.

### Install options

```bash
sudo ./install.sh \
  --user pi \                    # system user to run services as (default: pi)
  --install-dir /opt/hfwatch \   # where code lives (default: /opt/hfwatch)
  --data-dir /var/lib/hfwatch \  # where the database lives (default: /var/lib/hfwatch)
  --port 4000                    # dashboard port (default: 5000)
```

---

## Manual / development install

```bash
git clone https://github.com/EtherHamRadio/hfwatch.git
cd hfwatch

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Initialize the database
python3 db.py

# Run a one-off collection pass
python3 collector.py --grid CN87

# Start the dashboard
python3 server.py --port 5000
```

Open `http://localhost:5000` in a browser.

---

## File layout

```
hfwatch/
├── db.py               Band map, schema, SQLite helpers, migration logic
├── collector.py        PSK Reporter fetcher — run via systemd timer
├── query.py            Heatmap, weekly average, time-series, and stats queries
├── server.py           Flask dashboard and JSON API
├── prune.py            Deletes spots older than prune_days (called by systemd timer)
├── requirements.txt    Python dependencies (flask, requests)
├── install.sh          One-shot installer for Debian/Pi OS
└── systemd-units.conf  Reference copies of all unit files
```

---

## Systemd services

The installer creates four units:

| Unit | Type | Purpose |
|------|------|---------|
| `hfwatch.service` | service | Flask dashboard, runs continuously |
| `hfwatch-collector.service` | oneshot | Single collection pass |
| `hfwatch-collector.timer` | timer | Triggers collector every 15 minutes |
| `hfwatch-prune.service` | oneshot | Deletes spots older than `prune_days` |
| `hfwatch-prune.timer` | timer | Triggers prune nightly at 03:00 local |

Useful commands:

```bash
# Check dashboard status
sudo systemctl status hfwatch

# Watch live collector output
journalctl -u hfwatch-collector -f

# Restart the dashboard after a code change
sudo systemctl restart hfwatch

# Check timer schedule
systemctl list-timers hfwatch*
```

---

## Managing grid squares

HFWatch can collect data for more than one Maidenhead grid square. The dashboard lets you switch between grids that have data; collection targets are managed from the command line.

```bash
# See what grids are currently configured
python3 collector.py --list-grids

# Add a grid
python3 collector.py --add-grid IO85

# Remove a grid
python3 collector.py --remove-grid IO85

# One-off fetch for a specific grid (does not change config)
python3 collector.py --grid EM73
```

A newly added grid will not appear in the dashboard dropdown until after its first collection run completes (data must be present in the database).

Grid squares can be 4-character (e.g. `CN87`) or 6-character (e.g. `CN87ul`). PSK Reporter accepts both.

---

## JSON API

The dashboard is driven by a small JSON API. You can query it directly or use it to build your own front end.

| Endpoint | Parameters | Description |
|----------|------------|-------------|
| `GET /api/heatmap` | `hours` (1–168), `grid` | Band × hour spot counts |
| `GET /api/weekly` | `grid` | 7-day average band × hour matrix |
| `GET /api/timeseries` | `hours`, `res` (minutes), `grid`, `snap` (0/1) | Per-band spot counts in time buckets |
| `GET /api/grids` | — | List of grids with spot data |
| `GET /api/stats` | — | Database summary (total spots, oldest/newest, last fetch) |
| `GET /api/config` | — | Current configuration values |
| `POST /api/config` | JSON body `{"grid": "CN87"}` | Update active display grid |

Example:

```bash
curl "http://localhost:5000/api/heatmap?hours=48&grid=CN87"
```

---

## Database

HFWatch uses SQLite. The database file lives at `/var/lib/hfwatch/hfwatch.db` by default.

Schema overview:

- **spots** — one row per unique reception report (sender callsign, receiver callsign, timestamp, frequency, band, mode, SNR, target grid)
- **fetch_log** — one row per collection run (grid, spot count, new count, any error)
- **config** — key/value pairs (active grid(s), fetch interval, prune window)

The `init_db()` function in `db.py` handles schema creation and migration. If you upgrade from an older single-grid version, the migration adds the `target_grid` column automatically on first run.

### Backup

```bash
sqlite3 /var/lib/hfwatch/hfwatch.db ".backup /home/youruser/hfwatch-backup.db"
```

---

## Configuration

Most settings live in the `config` table and can be inspected via `/api/config`. The pruning window can be adjusted:

```bash
# Change retention to 60 days (takes effect on next prune run)
sqlite3 /var/lib/hfwatch/hfwatch.db \
  "UPDATE config SET value='60' WHERE key='prune_days';"
```

---

## Notes on PSK Reporter etiquette

PSK Reporter is a community resource. HFWatch is designed to be a polite client:

- Polls once every 15 minutes per grid square
- Waits 10 seconds between requests when collecting multiple grids
- Sends a descriptive `User-Agent` header identifying itself
- Uses `rronly=1` to fetch only reception reports (not transmission reports), which reduces response size

Please do not reduce the collection interval significantly or run many simultaneous instances against the same grids.

---

## Troubleshooting

**No data after 15 minutes**
- Check the collector log: `journalctl -u hfwatch-collector -f`
- Confirm the host has internet access: `curl https://retrieve.pskreporter.info/query?rronly=1&receiverLocator=CN87&flowStartSeconds=-900`
- PSK Reporter occasionally returns empty results for grids with low activity. This is normal — the database will populate as spots arrive.

**Dashboard shows "No data for this window"**
- The selected grid may have no spots yet. Check `/api/grids` to see which grids have data.
- Try a wider time window (48h or 7D).

**`target_grid` migration message on startup**
- Expected on first run after upgrading from a single-grid version. The message confirms the schema was updated successfully.

**Port conflict**
- If something else is already on port 5000, reinstall with `--port 4000` (or any open port).

---

## License

MIT License. See [LICENSE](LICENSE) for full text.

---

## About

HFWatch was built as a personal tool for band-opening planning from grid square CN87 (Pacific Northwest). It grew out of the observation that existing tools show *current* activity but nothing that answers "when is 17 meters usually open in the morning?" The heatmap view fills that gap using accumulated data from your own location.

Source and discussion at [EtherHam.com](https://etherham.com).
