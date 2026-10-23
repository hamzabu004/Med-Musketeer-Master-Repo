# Raspberry Pi initial setup

`setup_pi.sh` prepares a Raspberry Pi running Raspberry Pi OS Bookworm or newer. It installs the I2C/OLED packages, enables I2C, installs and enables Tailscale, configures a WPA2 2.4 GHz hotspot with NetworkManager, and restarts the existing `netstat.service` Python service. It does not replace the service or its Python file.

The hotspot activation is delayed by 30 seconds because switching `wlan0` from client mode to access point mode can end the SSH connection. The script prompts for the hotspot name and password. The Pi uses `10.42.0.1` as the hotspot address.

## Copy and run over SSH

From this repository root, copy the setup script to the Pi, then run it in an interactive SSH session so you can enter the hotspot password:

```bash
scp tools/Fixed-Gateway-Setup/setup_pi.sh <user>@<pi-address>:/tmp/setup_pi.sh
ssh -t <user>@<pi-address> 'sudo bash /tmp/setup_pi.sh'
```

If the service has a different systemd unit name, pass it as an environment variable:

```bash
ssh -t <user>@<pi-address> 'sudo env NETSTAT_SERVICE=my-netstat.service bash /tmp/setup_pi.sh'
```

The Pi needs internet access during setup to install packages and Tailscale. After setup, authenticate Tailscale with `sudo tailscale up`; this prints a URL to open on another device. If SSH was using `wlan0`, connect the computer to the new hotspot after it starts, then reconnect to `10.42.0.1`.

The script assumes the existing service already has its Python script and OLED application logic installed. It only enables/restarts that service; the Pi itself was not reachable during preparation, so the unit path and OLED driver's requirements have not been inspected.

## Mosquitto broker

`setup_mosquitto.sh` installs Mosquitto and writes the two-listener configuration from `docs/decisions/mqtt-fixed-path-topics.md`: a mutual-TLS wearable listener on port 8883 (certificate CN as username, `wearables.acl`) and a loopback services listener on `127.0.0.1:1883` (`gw_services` password, `services.acl`). Deploy the gateway credentials with `mmca deploy` first; the script stops if `ca.crt`, `gateway.crt` or `gateway.key` is missing from `/etc/mosquitto/certs`. It prompts for the `gw_services` password when no password file exists.

```bash
scp tools/Fixed-Gateway-Setup/setup_mosquitto.sh <user>@<pi-address>:/tmp/setup_mosquitto.sh
ssh -t <user>@<pi-address> 'sudo bash /tmp/setup_mosquitto.sh'
```
