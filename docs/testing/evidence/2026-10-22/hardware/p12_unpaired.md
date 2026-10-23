ID:            TC-P12 (write without pairing)
Date/time:     2026-10-22, about 09:47 UTC
Tester:        automated from the laptop (scripts/ble_p12.py), observed by serial log
Firmware:      as found on the board; BLE name MM-GW-DA7EEC
Steps run:     Laptop not paired or bonded with the board (bluetoothctl: Paired no, Bonded no).
               Scan, connect, write {"ssid":"P12-UNPAIRED-TEST",...} with response to
               7a2e0002-2b3c-4d5e-8f90-123456789abc.
Observed:      Serial log (p12_unpaired_serial.txt; the logger reset the board at t=0):
               20.9 s  "BLE passkey displayed on OLED"  (pairing demanded by the write)
               51.0 s  advertising restarted (link dropped after the 30 s pairing timeout)
               No "Rejected invalid BLE provisioning payload" and no settings-saved message:
               the write never reached the application. The host script was stopped at 60 s
               while BlueZ waited for a passkey, so it wrote no JSON record.
               nvs partition read afterwards: byte-identical to the pre-test backup;
               "P12-UNPAIRED-TEST" not present. BlueZ afterwards: Paired no, Bonded no.
Result:        Pass — the unauthenticated write was refused and nothing was stored.
