# The wearable's alert screen returns to the connection status after 3 s

- **Date:** 2026-11-06
- **Type:** code
- **Module:** M2 firmware
- **Commits:** 151b40d (screen timeout, README, this entry); merged in 1cc61ed (PR #17)

## What changed
- After an alert press, `ALERT SENT` (or `ALERT DROPPED`) stays on the OLED for 3 s (`ALERT_SCREEN_MS` in `firmware/wearable/main/fixed_path.c`). The screen then returns to `WIFI CONNECTED` / `MQTT REACHABLE` if Wi-Fi and MQTT are still up. If the connection dropped meanwhile, the network handlers' status screen is left as it is.
- The timer is separate from the 2 s button cooldown, which is unchanged. A press between 2 s and 3 s sends a new alert and restarts the 3 s.
- The wearable README describes the screen timeout.

## Why
The alert result stayed on the OLED until something else redrew it, so the connection status disappeared after the first press.

## Evidence
On the bench, with the rebuilt firmware on the wearable:
- one boot with no abort, then CONNACK from the gateway broker;
- the user pressed the button and saw `ALERT SENT` for about 3 s, then `WIFI CONNECTED` / `MQTT REACHABLE`.

Serial logs were read in the session but not saved.
