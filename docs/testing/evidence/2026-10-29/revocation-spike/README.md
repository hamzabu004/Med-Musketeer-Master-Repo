# Iteration 4, Slice 0: revocation enforcement spike (2026-10-29)

Plan and conclusions: `docs/iterations/iteration-4-revocation-sync.md`, Slice 0. This is a spike, not a report test case: Slices 1 and 2 turn the chosen mechanisms into TC-C28 to TC-C32 and TC-B05 to TC-B08.

## Mosquitto: `spike_mosquitto.py`

```
tools/ca-tool/.venv/bin/python docs/testing/evidence/2026-10-29/revocation-spike/spike_mosquitto.py
```

- **Needs:** podman, plus `eclipse-mosquitto:2.0.21` (the Pi's version, from the 2026-10-22 hardware evidence) and `eclipse-mosquitto:2` (2.1.2).
- **Material:** issues a throwaway CA, one gateway and three wearables with `mmca` in a temporary directory; none of it is kept. The services password in the script is a test constant.
- **Broker:** configured as `tools/Fixed-Gateway-Setup/setup_mosquitto.sh`. The containers run as the image's `mosquitto` user so that the entrypoint does not take over the mounted directory.

| File | Content |
|---|---|
| `results.json` | Every check, per image and mechanism |
| `broker-A-<version>.txt`, `broker-B-<version>.txt` | Broker log (`log_type all`) for mechanism A (ACL deny + SIGHUP) and B (dynamic security) |
| `client-A-<version>-*.txt` | Services-listener monitor, and the open wearable connections of mechanism A. The `-d` output of the long-running clients is partly buffered; the monitor and the broker log are the record. |

## EMQX: `spike_emqx.py`

```
python3 docs/testing/evidence/2026-10-29/revocation-spike/spike_emqx.py
```

- **Needs:** Docker with `emqx/emqx:6.3.2` (the pinned image), and podman with `eclipse-mosquitto:2` for the MQTT clients.
- **Configuration:** EMQX runs standalone, with:
  - an API key from `api_key.bootstrap_file`;
  - file authorisation that allows only subscribing (`no_match = deny`, cache off);
  - once with the retainer in RAM (the default) and once on disc.

  The key and secret in the script are test constants.

| File | Content |
|---|---|
| `emqx-results.json` | Every check, per retainer storage type |
| `emqx-ram.txt`, `emqx-disc.txt` | EMQX log of the second (recreated) container of each run |

## Results in short
- **Mosquitto, ACL deny + SIGHUP (chosen):**
  - a listed wearable's publishes are refused (PUBACK 0x87) and nothing is delivered to it, on an open connection too;
  - the connection stays open;
  - other wearables are unaffected;
  - lifting the deny restores it.
- **Mosquitto, dynamic security plugin (rejected):** it does not authenticate certificate identities, and `disableClient` neither drops nor refuses the client.
- **EMQX:**
  - the bootstrapped key works;
  - a REST retained publish passes authorisation that denies every publish, and clients cannot overwrite it;
  - clients are found by username and disconnected (0x98);
  - the retained message survives a container recreate only with `storage_type = disc`.
