#!/usr/bin/env bash
# MedMusketeer - gateway uplink setup on the fixed gateway (Raspberry Pi). Run with sudo, after
# setup_mosquitto.sh and `mmca deploy` (the uplink uses the same gateway certificate).
# Usage: sudo ./setup_uplink.sh CLOUD_HOST [path/to/gateway/uplink]
#   CLOUD_HOST: the cloud Pi's Tailscale address (the cloud is verified by name, not address).
# Installs gateway/uplink into /opt/medmusketeer/uplink, writes /etc/medmusketeer/uplink.toml and
# the systemd unit medmusketeer-uplink (runs as mosquitto; see docs/iterations/iteration-4-revocation-sync.md).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }
CLOUD_HOST=${1:?usage: setup_uplink.sh CLOUD_HOST [uplink source dir]}
SOURCE=${2:-"$(cd "$(dirname "$0")/../../gateway/uplink" && pwd)"}
[[ "$CLOUD_HOST" =~ ^[A-Za-z0-9.:-]+$ ]] || { echo "CLOUD_HOST must be a host name or address"; exit 1; }
[ -f "$SOURCE/pyproject.toml" ] || { echo "No uplink source at $SOURCE"; exit 1; }
VENV=/opt/medmusketeer/uplink
CONF=/etc/medmusketeer/uplink.toml
UNIT=/etc/systemd/system/medmusketeer-uplink.service

echo "[1/5] Checking Mosquitto"
[ -f /var/lib/medmusketeer/wearables.acl ] || { echo "Run setup_mosquitto.sh first"; exit 1; }
if ! grep -qs '^pid_file /run/mosquitto/mosquitto.pid' /etc/mosquitto/mosquitto.conf; then
  echo "  WARNING: /etc/mosquitto/mosquitto.conf has no 'pid_file /run/mosquitto/mosquitto.pid';"
  echo "  set mosquitto_pid_file or reload_command in $CONF, or the uplink cannot reload the broker."
fi

echo "[2/5] Installing the uplink into $VENV"
apt-get install -y python3-venv
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "$SOURCE"

echo "[3/5] Writing $CONF"
install -d -m 755 /etc/medmusketeer
if [ ! -f "$CONF" ]; then
  sed "s/CLOUD_HOST/$CLOUD_HOST/" "$SOURCE/deploy/uplink.toml.example" > "$CONF"
else
  echo "  $CONF exists, leaving it alone"
fi
chown root:mosquitto "$CONF"
chmod 640 "$CONF"

echo "[4/5] Installing the systemd unit"
install -m 644 "$SOURCE/deploy/medmusketeer-uplink.service" "$UNIT"
systemctl daemon-reload

echo "[5/5] Starting the uplink"
systemctl enable medmusketeer-uplink
systemctl restart medmusketeer-uplink
sleep 3
if systemctl is-active --quiet medmusketeer-uplink; then
  echo "Uplink running. Logs: journalctl -u medmusketeer-uplink -f"
else
  echo "Uplink failed to start. Check: journalctl -u medmusketeer-uplink -n 50"
  exit 1
fi
