#!/usr/bin/env bash
set -Eeuo pipefail

# Initial Raspberry Pi setup for the MedMusketeer gateway.
# Run on Raspberry Pi OS Bookworm or newer with NetworkManager enabled.

readonly HOTSPOT_PROFILE="MM-Gateway-Hotspot"
readonly HOTSPOT_INTERFACE="wlan0"
readonly HOTSPOT_ADDRESS="10.42.0.1/24"
readonly NETSTAT_SERVICE="${NETSTAT_SERVICE:-netstat.service}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ ${EUID} -eq 0 ]] || fail "Run with sudo: sudo bash $0"
command -v nmcli >/dev/null || fail "NetworkManager/nmcli is required (Raspberry Pi OS Bookworm or newer)."
systemctl is-active --quiet NetworkManager || fail "NetworkManager is not active. This setup expects Raspberry Pi OS Bookworm or newer."
systemctl cat "$NETSTAT_SERVICE" >/dev/null 2>&1 || fail "Could not find $NETSTAT_SERVICE. Set NETSTAT_SERVICE if the unit has a different name."
nmcli device status | awk -v dev="$HOTSPOT_INTERFACE" '$1 == dev { found = 1 } END { exit !found }' \
    || fail "Wi-Fi interface $HOTSPOT_INTERFACE was not found."

printf 'Installing NetworkManager, I2C/OLED packages, and prerequisites...\n'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    curl i2c-tools python3-pil python3-smbus python3-luma.oled

if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_i2c 0
else
    printf 'WARNING: raspi-config not found; enable I2C manually before using the OLED.\n' >&2
fi

if ! command -v tailscale >/dev/null 2>&1; then
    printf 'Installing Tailscale...\n'
    curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable --now tailscaled

read -r -p 'Hotspot SSID [MedMusketeer-Setup]: ' HOTSPOT_SSID
HOTSPOT_SSID=${HOTSPOT_SSID:-MedMusketeer-Setup}
[[ ${#HOTSPOT_SSID} -ge 1 && ${#HOTSPOT_SSID} -le 32 ]] || fail "SSID must be 1-32 characters."
read -r -s -p 'Hotspot WPA2 password (8-63 characters): ' HOTSPOT_PASSWORD
printf '\n'
[[ ${#HOTSPOT_PASSWORD} -ge 8 && ${#HOTSPOT_PASSWORD} -le 63 ]] || fail "Password must be 8-63 characters."

if nmcli -t -f NAME connection show | grep -Fxq "$HOTSPOT_PROFILE"; then
    nmcli connection modify "$HOTSPOT_PROFILE" \
        connection.interface-name "$HOTSPOT_INTERFACE" \
        connection.autoconnect yes \
        802-11-wireless.ssid "$HOTSPOT_SSID" \
        802-11-wireless.mode ap \
        802-11-wireless.band bg \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.proto rsn \
        wifi-sec.pairwise ccmp \
        wifi-sec.psk "$HOTSPOT_PASSWORD" \
        ipv4.method shared \
        ipv4.addresses "$HOTSPOT_ADDRESS" \
        ipv6.method disabled
else
    nmcli connection add type wifi ifname "$HOTSPOT_INTERFACE" \
        con-name "$HOTSPOT_PROFILE" ssid "$HOTSPOT_SSID" \
        802-11-wireless.mode ap \
        802-11-wireless.band bg \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.proto rsn \
        wifi-sec.pairwise ccmp \
        wifi-sec.psk "$HOTSPOT_PASSWORD" \
        ipv4.method shared \
        ipv4.addresses "$HOTSPOT_ADDRESS" \
        ipv6.method disabled
    nmcli connection modify "$HOTSPOT_PROFILE" connection.autoconnect yes
fi
unset HOTSPOT_PASSWORD

printf 'Restarting existing %s service...\n' "$NETSTAT_SERVICE"
systemctl enable "$NETSTAT_SERVICE"
systemctl restart "$NETSTAT_SERVICE"

# Starting an AP on wlan0 can disconnect this SSH session. Delay activation so
# the script can finish and the operator can note the new SSID first.
systemd-run --quiet --unit=mm-hotspot-activate --on-active=30s \
    /usr/bin/nmcli connection up "$HOTSPOT_PROFILE"

cat <<EOF

Setup complete.
- The $NETSTAT_SERVICE service is enabled and restarted.
- I2C is enabled; reboot the Pi once to ensure the OLED interface is active.
- Tailscale is installed and tailscaled is enabled. Authenticate it after
  confirming the Pi has an internet uplink: sudo tailscale up
- The WPA2 2.4 GHz hotspot will start in 30 seconds: $HOTSPOT_SSID
- Hotspot address: $HOTSPOT_ADDRESS

If your SSH session uses wlan0, it will disconnect when the hotspot starts.
Reconnect your computer to the hotspot, then SSH to 10.42.0.1.
EOF
