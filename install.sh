#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# install.sh — HFWatch installer
# Works on Raspberry Pi OS (bookworm/bullseye) and Debian/Ubuntu cloud servers.
#
# Usage:
#   chmod +x install.sh
#   sudo ./install.sh [--user pi] [--install-dir /opt/hfwatch] [--data-dir /var/lib/hfwatch] [--port 5000]
# ─────────────────────────────────────────────────────────────────────────────

set -e

# ── Defaults ──────────────────────────────────────────────────────────────────
RUN_USER="pi"
INSTALL_DIR="/opt/hfwatch"
DATA_DIR="/var/lib/hfwatch"
PORT=5000

# ── Parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)        RUN_USER="$2"; shift 2 ;;
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    --data-dir)    DATA_DIR="$2"; shift 2 ;;
    --port)        PORT="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

DB_PATH="$DATA_DIR/hfwatch.db"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "════════════════════════════════════════════"
echo "  HFWatch installer"
echo "  Install dir : $INSTALL_DIR"
echo "  Data dir    : $DATA_DIR"
echo "  Run as user : $RUN_USER"
echo "  Port        : $PORT"
echo "════════════════════════════════════════════"

# ── System dependencies ───────────────────────────────────────────────────────
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv

# ── Create directories ────────────────────────────────────────────────────────
echo "[2/6] Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR"
chown "$RUN_USER":"$RUN_USER" "$DATA_DIR"

# ── Copy application files ────────────────────────────────────────────────────
echo "[3/6] Copying application files..."
cp "$SRC_DIR"/db.py        "$INSTALL_DIR/"
cp "$SRC_DIR"/collector.py "$INSTALL_DIR/"
cp "$SRC_DIR"/query.py     "$INSTALL_DIR/"
cp "$SRC_DIR"/server.py    "$INSTALL_DIR/"
cp "$SRC_DIR"/prune.py     "$INSTALL_DIR/"
cp "$SRC_DIR"/requirements.txt "$INSTALL_DIR/"
chown -R "$RUN_USER":"$RUN_USER" "$INSTALL_DIR"

# ── Python virtual environment ────────────────────────────────────────────────
echo "[4/6] Setting up Python virtual environment..."
VENV="$INSTALL_DIR/venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
chown -R "$RUN_USER":"$RUN_USER" "$VENV"

PYTHON="$VENV/bin/python3"

# ── Initialise database ───────────────────────────────────────────────────────
echo "[5/6] Initialising database..."
sudo -u "$RUN_USER" "$PYTHON" "$INSTALL_DIR/db.py" --db "$DB_PATH" 2>/dev/null || \
  sudo -u "$RUN_USER" "$PYTHON" "$INSTALL_DIR/db.py"

# ── Systemd units ─────────────────────────────────────────────────────────────
echo "[6/6] Installing systemd units..."

cat > /etc/systemd/system/hfwatch-collector.service << EOF
[Unit]
Description=HFWatch PSK Reporter collector (single run)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON $INSTALL_DIR/collector.py --db $DB_PATH
StandardOutput=journal
StandardError=journal
TimeoutStartSec=60
EOF

cat > /etc/systemd/system/hfwatch-collector.timer << EOF
[Unit]
Description=HFWatch PSK Reporter collector — every 15 minutes
Requires=hfwatch-collector.service

[Timer]
OnCalendar=*:0/15
Persistent=true
RandomizedDelaySec=30

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/hfwatch.service << EOF
[Unit]
Description=HFWatch band activity web dashboard
After=network.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON $INSTALL_DIR/server.py --db $DB_PATH --port $PORT --host 0.0.0.0
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/hfwatch-prune.service << EOF
[Unit]
Description=HFWatch database pruning
After=network.target

[Service]
Type=oneshot
User=$RUN_USER
ExecStart=$PYTHON $INSTALL_DIR/prune.py --db $DB_PATH
EOF

cat > /etc/systemd/system/hfwatch-prune.timer << EOF
[Unit]
Description=HFWatch daily database pruning
Requires=hfwatch-prune.service

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now hfwatch-collector.timer
systemctl enable --now hfwatch-prune.timer
systemctl enable --now hfwatch.service

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  Installation complete!"
echo ""
echo "  Dashboard : http://$(hostname -I | awk '{print $1}'):$PORT"
echo "  Database  : $DB_PATH"
echo "  Logs      : journalctl -u hfwatch -f"
echo "  Collector : journalctl -u hfwatch-collector -f"
echo ""
echo "  The first spots will arrive within 15 minutes."
echo "  Grid square defaults to CN87 (change in dashboard header)."
echo "════════════════════════════════════════════"
