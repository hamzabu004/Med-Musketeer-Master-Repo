# Iteration 5 — ECG from the sensor, and live ECG on request

- **Owner:** Hamza Tariq (M2 firmware, M5 gateway, M7 cloud, M8 dashboard)
- **Status:** Planned (2026-11-06). Slice 2 built on 2026-11-26 for the ADS1292, with the on-device model (Slice 2b): compiled for the ESP32-S3 and tested on the host; not yet run on the board.
- **Scope change (2026-11-06):** `scope.md` listed ECG evaluation, the edge model, the gateway classifier and IDS/IPS under Iteration 5. They move to **Iteration 7**, which runs in parallel with its own owners (D-0). This iteration is ECG acquisition and on-demand live ECG.
- **Scope change (2026-11-26):** the ADS1292 arrived. It replaces the AD8232, which is dropped. The on-device model (a 1D-CNN from the model owners) moves from Iteration 7 into this iteration and raises alerts (D-13 to D-15). ECG evaluation, the gateway classifier and IDS/IPS stay in Iteration 7.
- **Depends on:**
  - the uplink bridge (`gateway/uplink/mm_uplink/bridge.py`, Iteration 4), merged before Slice 4;
  - `cloud-backend.md` D1, D5, D6, D9, D15, D16;
  - `mqtt-fixed-path-topics.md` §1 to §6;
  - `shared/contracts/`;
  - the wearable pin layout: OLED SDA 9 / SCL 3, button 21 (2026-11-06); ADS1292 SCLK 12, DIN 11, DOUT 13, CS 10, DRDY 4, START 5, PWDN/RESET 6 (D-16, 2026-11-26).

## Goal

The wearable reads real ECG from the ADS1292 and classifies every beat on the device. A doctor presses Start on a patient's page. The command goes dashboard → API → EMQX → the gateway uplink → the gateway's Mosquitto → the wearable. The wearable streams 1-second chunks back the same way. The doctor, and the patient on their own page, watch the strip build up about 2 to 3 s behind live. The doctor stops it, or it stops when its duration runs out. The stream is stored as a `recording` segment.

The alert keeps its contract (alert-payload-v1), but since 2026-11-26 the on-device model raises it when abnormal beats recur, and it carries the last 10 s of real ECG (D-13 to D-15). The button stays as a manual alert. The sensor sits behind a driver interface, so the stream, the contracts and the cloud do not depend on it.

## Decisions

Confirmed by the owner on 2026-11-06: D-0, D-1, D-3, D-8 and the patient part of D-10; on 2026-11-26: the changes to D-0 and D-8, and D-13 to D-16. The rest are proposals, checked in Slice 0 or confirmed before the slice that needs them.

| # | Question | Decision | Why |
|---|---|---|---|
| D-0 | Where the old Iteration 5 work goes | **Confirmed:** ECG evaluation, the edge model, the gateway classifier and IDS/IPS move to a parallel **Iteration 7 — models and IDS/IPS**. The attack-test module goes with IDS/IPS. **Changed 2026-11-26:** the edge model came back once the model owners delivered it (D-13); its training and evaluation stay in Iteration 7. | They have other owners and do not depend on this work. **Risk:** `scope.md` says FYP-1 Final needs IDS/IPS. Iteration 7 has to finish by then, or the milestone moves (`gaps.md`). |
| D-1 | Sampling rate | **Confirmed: 500 SPS** | The ADS1292 supports 500 SPS natively, but not 360. 500 SPS is usual for diagnostic ECG. The model takes 128 Hz; the firmware resamples (D-13). |
| D-2 | How samples are read | **Changed 2026-11-26 (ADS1292):** SPI2 at 1 MHz, mode 1; continuous read (RDATAC) with the DRDY falling edge waking the sampler, one 9-byte frame per sample. Internal 2.42 V reference, PGA gain 6, channel 1 only, right-leg drive from channel 1, DC lead-off on IN1P and IN1N. The driver checks the chip ID and reads every register back at boot. | The chip's own clock paces the samples, so Wi-Fi load cannot change the rate. The ADS1292 has no FIFO, so a late read loses a frame; the driver counts them (H-W04). Was: ADC continuous mode on the AD8232. |
| D-3 | Sampler duty | **Confirmed: always on.** START is driven high at boot, and a 12 s ring (6000 samples) is filled all the time. A stream, the model and alerts read from it. | The model needs continuous samples, and the DC blocker (D-4) takes a few seconds to settle after a lead reconnect. Was 10 s; 12 s leaves room to copy a 10 s alert segment while sampling goes on. |
| D-4 | Units | int16 samples at a stated `counts_per_mv`: **200** (5 µV per count). The firmware turns a 24-bit code into µV (`code × 2 × VREF / gain / 2²⁴`, about 0.048 µV), removes the electrode offset with a 0.5 Hz first-order DC blocker, then scales and clamps to int16. | Keeps the dashboard's 200 counts/mV (`ecg-waveform.tsx` `DEFAULT_COUNTS_PER_MV`) correct. The ADS1292 is DC-coupled and an electrode offset of a few hundred mV would clamp int16 (±163 mV) without the blocker. Closes "gain is not stored with segments" (`gaps.md`). |
| D-5 | Start and stop | Start carries `duration_s` (10–300, default 60) and ends on its own after that time. `ecg_stop` ends it early. Commands carry `expires_at` (sent time + 15 s). One open recording per wearable. | Closes the start/stop item in `mqtt-fixed-path-topics.md` §6 and `gaps.md`. The limit means a closed browser tab cannot leave a wearable streaming. |
| D-6 | Telemetry QoS | QoS 1, not retained. A chunk is skipped (a visible `seq` gap) when the ESP-MQTT outbox is over about 8 KB. | Recordings are stored, so completeness matters. At one message a second, QoS 1 costs little. |
| D-7 | Encoding | JSON with int16le-base64, as in alert-payload-v1 | A 1 s chunk at 500 SPS is 1000 bytes, about 1.7 KB as base64 in JSON, well under the 4096-byte `MQTT_BUFFER_SIZE` (`fixed_path.c`). Reuses `check_capture.py`, `contracts.py` and the dashboard's `decodeSamples`. |
| D-8 | What the alert carries | **Confirmed: alert-payload-v1 is kept unchanged.** **Changed 2026-11-26:** an alert carries the last 10 s of real ECG at 500 SPS (D-15). The synthetic 3 s trace (`lead` `SYNTH`, `button-stub-0`) is only sent by a button press before 10 s of ECG exist. A live stream is still never attached to an alert. | No contract change: alert-payload-v1 already takes any `fs_hz`, `lead` and `screening`, and `samples` allows far more than 5000 samples. |
| D-9 | How the dashboard gets the data | Poll once a second while a recording is open: `GET /recordings/{id}?after_seq=N`. SSE is a stretch goal. | Same pattern as alerts (D15 chose polling; `use-polling.ts`). Bearer tokens in `sessionStorage` do not work with `EventSource` unless the token goes in the query string. |
| D-10 | Who may do what | **Start and stop:** the patient's current doctor (D9 row "Request on-demand ECG"). **Watch live and read recordings:** that doctor, and **the patient for their own recordings (confirmed)**. **Org admin and system admin:** no access. | Follows D9. Proposal: patients watch but cannot start. Confirm before Slice 5. |
| D-11 | Which commands a gateway receives | The uplink subscribes on EMQX to `mm/fixed/{w}/command` for each wearable whose local status is `online`, not to `mm/fixed/+/command`. The bridge also drops commands for wearables it has not seen. | With `+` (allowed by D5 today), every gateway would get every organisation's commands. Optional: EMQX authorisation allows the subscription only where `devices.current_gateway_id` is that gateway. |
| D-12 | Retention and records | Recording chunks use the `ecg_chunks` retention (90-day placeholder). The `commands` row records who started and who stopped a recording; no separate `audit_log` entry. | Same hypertable. The retention period itself is still open (`gaps.md`). Confirm the audit choice before Slice 5. |
| D-13 | On-device model | **Confirmed 2026-11-26:** the INT8 1D-CNN `p1_best` (Farag 2023, 1,267 parameters, 10.6 KB; N/S/V on MIT-BIH MLII; `firmware/wearable/model/`) runs on the wearable with TensorFlow Lite Micro. The firmware reproduces its preprocessing: 500 → 128 Hz, Pan-Tompkins R peaks, a 64-sample window at the R peak, RR features over the last 80 and 400 beats. | The model owners delivered it; its DS2 result is 97.34 % accuracy and 89.45 % macro-F1. On the beats the firmware's pipeline finds, it scores 97.45 % and 89.78 % (TC-W08), so the on-device preprocessing matches training. |
| D-14 | When the model alerts | **Confirmed 2026-11-26:** at least **3 of the last 10** beats S or V, at most once every **60 s** (Kconfig). The label is the more frequent of S and V (`V` on a tie), the confidence the mean probability of that class. The button stays as a manual alert (`abnormal`, `button-0`). | A single S beat is right only about two times in three (PPV S 67 %), so one beat would alarm too often. The labels `S` and `V` are the dashboard's beat classes (`labels.ts`). |
| D-15 | The alert's ECG | **Confirmed 2026-11-26:** the last 10 s at 500 SPS, lead II, from the ring: 5000 samples, about 13.8 KB of JSON. The ESP-MQTT output buffer grows from 4 to 16 KB; the input buffer stays at 4 KB. | Enough context for the doctor to see the abnormal beats and the rhythm around them. Mosquitto and EMQX take messages this size by default. |
| D-16 | ADS1292 pins and lead | **Confirmed 2026-11-26:** SCLK 12, DIN 11, DOUT 13, CS 10 (SPI2's IO MUX pins), DRDY 4, START 5, PWDN/RESET 6. Lead II on channel 1 (IN1N right arm, IN1P left leg, RLD right leg); channel 2 powered down. | Free pins that avoid the strapping pins, USB, the flash and octal PSRAM, and UART0; GPIO 4 and 5 were freed by the old button and the AD8232. Lead II is the closest to MIT-BIH MLII, which the model was trained on. |

## Design

### Firmware (`firmware/wearable/main/`)

**Front-end interface** (`ecg_frontend.h`):

```c
typedef struct {
    const char *sensor;          /* "ADS1292", "SYNTH" */
    const char *lead;            /* Kconfig WEARABLE_ECG_LEAD, default "II" */
    uint16_t fs_hz;              /* 500 */
    uint16_t counts_per_mv;      /* 200 */
    esp_err_t (*init)(void);
    esp_err_t (*start)(void);
    esp_err_t (*stop)(void);
    /* Blocks up to timeout; fills out[] and one leads-off flag per sample. */
    size_t (*read)(int16_t *out, uint8_t *leads_off, size_t max, TickType_t timeout);
    uint32_t (*take_lost)(void); /* samples lost since the last call; NULL if none can be */
} ecg_frontend_t;
const ecg_frontend_t *ecg_frontend(void);  /* chosen by Kconfig */
```

- **Kconfig** (`Kconfig.projbuild`): a choice `WEARABLE_ECG_FRONTEND`:
  - `_ADS1292`, the default, with the menu **ADS1292 pins** (`WEARABLE_ECG_SPI_{SCLK,MOSI,MISO,CS}_GPIO`, `WEARABLE_ECG_{DRDY,START,PWDN}_GPIO`; D-16);
  - `_SYNTH`, a generated waveform for bench runs without electrodes.

  Also `WEARABLE_ECG_LEAD` (default `II`), `WEARABLE_EDGE_MODEL` (default y) and the alert rule's `WEARABLE_EDGE_ALERT_{WINDOW_BEATS,MIN_ABNORMAL,COOLDOWN_S}` (10, 3, 60). The AD8232 options are gone.
- **`ecg_ads1292.c`** (D-2): SPI2 with CS held by hand across multi-byte commands; power-on wait, reset pulse, `SDATAC`, ID check (0x53), one `WREG` of CONFIG1 to RESP2 and a read-back; then `RDATAC` and START high. DRDY's falling edge gives a counting semaphore; `read` fetches one frame per DRDY and counts the frames overwritten before they were read.
- **`ecg_convert.c`** (no ESP-IDF, host-tested): frame parsing, lead-off bits, code to µV, the DC blocker, µV to int16 (D-4). The blocker is primed by the first sample and again when the electrodes come back on, so the offset does not start as a slowly decaying step.
- **`ecg_sampler.c`:**
  - a task at priority 6, above the network (5) and the alert task (4);
  - writes a ring of 6000 int16 samples, with their leads-off flags, a 64-bit running sample index, and the wall-clock time of sample 0;
  - a sample's time is `t0 + index / fs`, and `t0` is refreshed on SNTP sync. No per-chunk timestamps, so no jitter.
- **On-device model** (Slice 2b, D-13 to D-15):
  - `ecg_beats.c` (no ESP-IDF, host-tested): the polyphase resampler (32/125, Blackman-windowed sinc, 57.5 Hz cut-off), Pan-Tompkins at 128 Hz (5–15 Hz biquads, five-point derivative, 150 ms window, thresholds learned over 2 s, a 200 ms refractory period, a T-wave check within 360 ms, search-back after 1.66 RR, thresholds halved after 3 s without a beat), the R peak placed on the largest deflection 1 to 30 samples before the window's peak, and the beat's window and RR features. A leads-off sample resets detection and the RR history.
  - `ecg_model/` holds the export's C files: the model array, its quantisation constants and `ecg_classifier.cpp`, which z-scores, differentiates, quantises and runs the model.
  - `edge_rule.c` (no ESP-IDF, host-tested): the 3-of-10 rule with its cooldown (D-14).
  - `edge_model.c`: a task at priority 3 that reads the ring every 100 ms, classifies each beat and hands an alert to `fixed_path.c`, which publishes it on the alert task with the last 10 s of ECG. It logs a summary once a minute: beats per class, mean heart rate, the slowest inference, the free heap.
- **`ecg_stream.c`:** handles commands and the stream.
  - **Subscribing:** `MQTT_EVENT_CONNECTED` (`fixed_path.c`) also subscribes to `mm/fixed/{id}/command` at QoS 1. The topic is built next to `alert_topic`.
  - **Receiving:** `MQTT_EVENT_DATA` copies the topic and payload into a queue. Payloads over 512 B or fragmented (`total_data_len != data_len`) are refused. No other work is done on the MQTT task.
  - **Checks, in this order:**
    1. `v == 1`, a known `type`, and `command_id` is a UUID.
    2. The clock is valid (`CLOCK_VALID_AFTER`).
    3. `expires_at` is after now; otherwise `rejected/expired`.
    4. `command_id` is not among the last 8 seen. A repeat gets the same ack again, so a QoS 1 redelivery is harmless and a replay starts nothing.
    5. `duration_s` is in 10..300.
    6. For `ecg_start`, no recording is running; otherwise `rejected/busy`.
    7. For `ecg_stop`, `recording_id` is the current one.
  - **Streaming:**
    - after an `accepted` ack, the task publishes the next 500 samples from the ring every second as telemetry-v1, under `mqtt_client_mutex`, as `alert_publish_task` does;
    - a chunk is skipped when `esp_mqtt_client_get_outbox_size()` is over the limit (D-6);
    - the last chunk has `final: true` and an `end_reason`: `stop_command`, `duration` or `sensor_error`.
  - **Disconnect:** the recording ends quietly. The cloud closes it on the LWT `offline`, or after 15 s with no chunk. The session is clean, so a command sent while the wearable is offline is lost; `expires_at` covers that case.
- **Alert:** `alert.c` does not change (D-8). The button still works during a recording.
- **OLED** (`display_show_text`, at most one redraw a second):
  - when idle: `WIFI CONNECTED` / `MQTT REACHABLE` / `ECG READY` or `LEADS OFF`;
  - while streaming: `STREAMING ECG` / `23 / 60 S` / `LEADS OK` or `LEADS OFF` / `SEQ 22`;
  - at the end: `ECG STOPPED` and the reason, then back to idle.

  Alert screens work as they do today, including the return to the connection screen after 3 s.
- `CMakeLists.txt` `REQUIRES` gains `esp_driver_spi`, `esp_timer` and `esp-tflite-micro` (`espressif/esp-tflite-micro` ^1.4.3 in `idf_component.yml`). The firmware README describes the sampling, the model and the stream.

### Contracts (generated by `cloud/backend/app/contracts.py` into `shared/contracts/`)

| File | Topic | Sent by | Payload |
|---|---|---|---|
| `command-v1` | `mm/fixed/{w}/command` | the cloud (EMQX REST), republished by the gateway | `{"v":1,"command_id":uuid,"type":"ecg_start","duration_s":60,"issued_at":t,"expires_at":t}`, or `{"v":1,"command_id":uuid,"type":"ecg_stop","recording_id":uuid,"issued_at":t,"expires_at":t}` (a union on `type`) |
| `command-ack-v1` | `mm/fixed/{w}/command_ack` | the wearable | `{"v":1,"command_id":uuid,"status":"accepted"\|"rejected","reason"?:"busy"\|"expired"\|"invalid"\|"unsupported"\|"not_ready","sent_at"?}` |
| `telemetry-v1` | `mm/fixed/{w}/telemetry` | the wearable | `{"v":1,"recording_id":uuid,"seq":0,"recording_start":t,"first_sample":0,"fs_hz":500,"lead":"II","sensor":"ADS1292","counts_per_mv":200,"n_samples":500,"encoding":"int16le-base64","samples":"…","leads_off":0,"final":false,"end_reason"?,"sent_at"?}` |

- **Telemetry rules:**
  - `recording_id` is the start command's `command_id`;
  - `samples` must decode to 2 × `n_samples` bytes, with `n_samples` at most 2000;
  - `leads_off` counts the samples in the chunk taken with leads off;
  - `end_reason` appears only when `final` is true;
  - `recording_start` may be ahead of the broker's clock by at most `MAX_CLOCK_SKEW`.
- A chunk has no `msg_id`: `(recording_id, seq)` identifies it, which avoids one `ingested_messages` row per second.
- **Wiring:**
  - `MESSAGES["wearable"]` gains `telemetry` and `command_ack`, and `Ingest.msg_type` widens to match. This is done in place: ingest-v1 is internal, and both of its ends are in one package.
  - `cloud/backend/tests/messages.py` gains `telemetry_payload()` and `command_ack_payload()`.
  - `firmware/wearable/tools/check_capture.py` checks each recording: `seq` goes up by 1 (gaps reported), `first_sample` agrees with `seq`, nothing comes after `final`, and the recording matches an `accepted` ack.

### Gateway (`gateway/uplink`, `tools/Fixed-Gateway-Setup`)

- **`services.acl`, user `gw_uplink`:** gains `topic read mm/fixed/+/telemetry`, `topic read mm/fixed/+/command_ack` and `topic write mm/fixed/+/command`.
  - `setup_mosquitto.sh` writes these lines.
  - `setup_uplink.sh:81` skips the block once `user gw_uplink` exists, so the Pi that is already set up would never get them. It must rewrite the block every time.
  - `wearables.acl` already allows the wearable to write telemetry and command_ack and to read command.
- **`bridge.py`, upstream:** `telemetry` and `command_ack` are forwarded like `alert` and `status`: ack after the cloud's PUBACK, and nothing from listed wearables. The module docstring is updated.
- **`bridge.py`, downstream:** a new `deliver_command(topic, payload)`, called from `Uplink._on_message` (`service.py`).
  - It validates the command against `command-v1`, shipped in `mm_uplink/schemas/` like `revocation-list-v1`.
  - It drops the command if the wearable is listed (`RevocationStore.listed`), the command has expired, or the wearable is not online locally.
  - Otherwise it publishes the command on the local broker at QoS 1, not retained.
- **Subscriptions (D-11):** when a wearable's status arrives as `online`, subscribe on the cloud session to `mm/fixed/{w}/command`; on `offline`, unsubscribe. In `cloud_connected()`, subscribe again for every wearable that is online.

### Cloud (`cloud/backend`, `cloud/emqx`)

- **EMQX rule (fix first):** `mm_ingest` (`emqx.conf.template:102`) reads from `"mm/fixed/#"`. A command the API publishes over REST would loop back into ingestion. Add `WHERE NOT (topic =~ 'mm/fixed/+/command')`.
- **`emqx_api.py`:** add `publish(topic, payload, qos=1, retain=False, expiry_s=15)` next to `publish_retained`, with the message expiry in `properties.message_expiry_interval`. Check it in Slice 0.
- **Migration `0006_recordings.py`:**
  - `commands` gains `patient_id`, `params jsonb`, `expires_at`, `ref_command_id`, `reason`, `ended_at`, `end_reason` and `stopped_by`, and its status check allows `rejected`;
  - `ecg_segments` gains `counts_per_mv smallint NULL` (NULL means 200), `sensor text NULL`, and a unique index on `(command_id) WHERE kind = 'recording'`;
  - `mm_api` gets the grants it needs.
- **New `app/recordings.py`:**

| Endpoint | Who | Behaviour |
|---|---|---|
| `POST /patients/{id}/recordings` `{duration_s}` | Doctor | Needs `patient_in_scope`, and a wearable that is issued, active and granted. The wearable must be on the fixed path, with a `current_gateway_id` whose newest connectivity event is online; otherwise 409, "not reachable on the fixed path" (the mobile path is not built). An open recording also gives 409. Inserts the command, commits, then publishes command-v1 over REST. If the publish fails, the command is marked `expired` with reason `not_delivered`. Returns 201. |
| `GET /patients/{id}/recordings` | Doctor, patient (self) | Newest first, at most 50 |
| `GET /recordings/{id}[?after_seq=N]` | Doctor, patient (self) | State (`requested`, `streaming`, `ended`, `rejected`, `expired`), `segment_id`, `fs_hz`, `counts_per_mv`, elapsed time, `end_reason`. With `after_seq`, also the chunks after N, in the `Chunk` model from `care.py`. |
| `POST /recordings/{id}/stop` | Doctor | Inserts an `ecg_stop` command (`ref_command_id`), publishes it, and records `stopped_by`. 409 if the recording is not open. |

- **Ingestion** (`ingest.py`, `adapter.py`); `telemetry` and `command_ack` leave `NOT_INGESTED`:
  - **`command_ack`:** the command must belong to the device named in the topic, or the ack is rejected. The command moves from `sent` to `acked` or `rejected`, idempotently.
  - **`telemetry`:**
    - the recording must be this device's open `ecg_start`, and the wearable must still be issued to that patient;
    - the first chunk also counts as the ack, and creates the `recording` segment in the current session, with `fs_hz`, lead, `counts_per_mv` and sensor;
    - each chunk is inserted with `ts = recording_start + first_sample / fs` and `ON CONFLICT DO NOTHING`;
    - a chunk past `duration_s + 5 s`, or with a changed `fs_hz`, is rejected;
    - `final` sets `ended_at` and `end_reason`.
  - **Wearable `offline` status:** ends any open recording (`wearable_offline`).
- **Sweeper,** started in `main.py`'s lifespan next to the revocation reconciler, runs every 5 s:
  - a `sent` command past its `expires_at` becomes `expired`;
  - a stream with no chunk for 15 s ends as `lost`;
  - a stream past `duration_s + 30 s` ends as `duration`.
- **D9:** rows for the four endpoints, so TC-C09 (`test_access.py`) covers them.

### Dashboard (`web/dashboard`)

- **Feature flag:** `config/capabilities.ts` sets `ecgRequests: true` once Slice 5 is deployed.
- **Types:** `services/contracts.ts` `RecordingRequest` gains `state`, `ended_at`, `end_reason`, `reason`, `stopped_by`, `segment_id`, `fs_hz` and `counts_per_mv`, and `status` gains `rejected`. `DataSource.recordings` gains `get(id, afterSeq)` and `stop(id)`.
- **API client:** `services/api.ts` replaces the `notServed` stubs, and `api/openapi.json` and `schema.d.ts` are regenerated.
- **Sample mode:** `mock-data-source.ts` produces synthetic chunks over time, with the API's states and 409 rules.
- **Doctor's live panel** (`features/care/recording-panel.tsx`):
  - a duration choice (30 s, 1 min, 2 min, 5 min) and Start;
  - the states shown: Sent → Streaming (elapsed / duration) → Ended (reason), or No answer, or Rejected (reason);
  - Stop, with a confirmation.
- **Live strip:** a new `live-ecg.tsx`.
  - It keeps a growing `Int16Array` (decoded with `lib/ecg.ts` `decodeSamples`) and draws the last 10 s with `ECGWaveform`, using the recording's `counts_per_mv`.
  - Leads-off stretches are shaded, with a "Leads off" banner, and `seq` gaps are drawn as breaks.
  - It polls once a second (`usePolling`) only while the recording is open.
- **Patient:** the ECG Recordings page shows an open recording with the same live strip, read-only (D-10).
- **Alert page:** "Request live ECG" for button alerts.
- **Long strips:** a 5-minute recording at 500 SPS is 150,000 samples. The segment viewer splits `kind = 'recording'` segments into rows or pages.

## Slices

| # | Slice | Size | Depends on |
|---|---|---|---|
| 0 | **Spike and remaining decisions.** On the bench: ADC continuous at 2000 Hz on GPIO 2 with Wi-Fi and MQTT running (sample count against the wall clock over 60 s; noise floor); the AD8232's gain and reference; how LO± behave (done on 2026-11-06 for the AD8232, since dropped; the ADS1292's rate and noise are checked in H-W04). EMQX: a REST publish with message expiry, and the rule exclusion. ESP-MQTT: subscribing from the event handler; the outbox-size call. Evidence in `docs/testing/evidence/<date>/ecg-spike/`. | S | — |
| 1 | **Contracts:** models, schemas, `tests/messages.py`, `check_capture.py` | S | 0 |
| 2 | **Firmware sampler:** `ecg_frontend.h`, `ecg_ads1292.c`, `ecg_convert.c`, `ecg_synth.c`, `ecg_sampler.c`, Kconfig, the OLED's idle line. **Built 2026-11-26.** | M | 0 (in parallel with 1) |
| 2b | **On-device model (added 2026-11-26):** `ecg_beats.c`, `ecg_model/`, `edge_rule.c`, `edge_model.c`, the model alert and the 10 s segment in `fixed_path.c` and `alert.c`, TC-W08 and TC-W09. **Built 2026-11-26.** | M | 2 |
| 3 | **Firmware commands and stream:** subscribing, the parser, acks, chunks, the automatic stop, the replay guard, the OLED stream screens | M | 1, 2 |
| 4 | **Gateway:** ACLs in both setup scripts, the bridge in both directions, per-wearable command subscriptions, tests | M | 1, the bridge merged |
| 5 | **Cloud:** migration 0006, `recordings.py`, ingestion, the adapter, the EMQX rule, `emqx_api.publish`, the sweeper, D9 rows | L | 1 (in parallel with 2–4; tests use a test gateway client) |
| 6 | **Dashboard:** contracts, API, sample mode, the doctor's live panel, the patient's live view, the alert-page link, long strips | M | 1 (sample mode); 5 (API mode) |
| 7 | **Hardware and docs:** H-W04 to H-W07 on the Pi and the deployed stack. Docs: `scope.md`, `stack.md`, `cloud-backend.md` (new D19), `mqtt-fixed-path-topics.md` §5 and §6, `gaps.md`, `test_traceability.md`, `hardware_test_procedures.md`, change log. | M | 3–6 |

## Tests

**Firmware**

| ID | Kind | Checks |
|---|---|---|
| TC-W05 | A-host | The `ecg_stream.c` chunker, built on the host as `test_check_capture` builds `alert.c` and fed by the SYNTH front end: chunks pass telemetry-v1 and fit 4096 B; `seq` and `first_sample` are continuous; the final chunk has `end_reason`. |
| TC-W06 | A-host | The command parser accepts a valid start and stop. It rejects expired, oversize, fragmented and malformed commands, unknown types and an out-of-range duration. A second start gets `busy`. A redelivered `command_id` gets the same ack and starts no second stream. |
| TC-W07 | A-host | ADS1292 conversion: frame parsing and the status header, 24-bit sign extension, the channel 1 lead-off bits, codes to µV at 2.42 V and gain 6, the DC blocker (offset removed, 10 Hz passed, −3 dB at 0.5 Hz), µV to counts with rounding and the int16 clamp, the leads-off count. |
| TC-W08 | A-host | The beat pipeline (`ecg_beats.c`). Synthetic: every beat found within one 128 Hz sample of its R peak; the window equals the trace at 128 Hz (no resampler delay); the RR features match their definition through a changing rhythm; leads off resets detection, which resumes after learning; a flat signal gives no beats. MIT-BIH DS2 (when the database and numpy, scipy and `ai_edge_litert` are present): Se and PPV ≥ 99.5 %, ≥ 95 % of R peaks within one sample, and the INT8 model on the found beats ≥ 97 % accuracy and ≥ 88.5 % macro-F1. |
| TC-W09 | A-host | The alert rule (`edge_rule.c`): 3 of 10 alerts once and 2 of 10 does not; old beats leave the window; the 60 s cooldown; the label is the more frequent class; clearing forgets the window. |
| H-W04 | H | On the bench: 500 SPS ±0.5% over 60 s with no lost frames (`ecg_sampler` log); a visible ECG (electrodes or a simulator) with `ECG_DUMP`; pulling an electrode shows `LEADS OFF` on the OLED. |
| H-W08 | H | The model on the board: on a person at rest (or a simulator's normal sinus rhythm) the `edge_model` log shows beats at the right heart rate, nearly all N, and no alert over 5 minutes; the slowest inference and the lowest free heap are recorded. With a simulator's PVCs (or the SYNTH front end for the plumbing), an alert arrives with the 10 s segment and passes `check_capture.py`. |
| H-W05 | H | On the Pi, `mosquitto_pub` as `gw_services` sends a start, a stop, an expired command and a repeated command. The `mosquitto_sub -v` capture passes `check_capture.py`, and the stream stops on its own at the set duration. |
| H-W06 | H | The alert button during a stream: both the alert and the stream arrive. Wi-Fi dropped mid-stream: the recording ends, the LWT `offline` arrives, and the wearable does not crash. |
| H-W07 | H | End to end on `app.medmusketeer.site`: Start → live strip (for the doctor and the patient) → Stop. The times from command to ack to the first chunk on screen are recorded (a benchmark, not a pass mark). |

**Gateway** (`gateway/uplink/tests/`, Mosquitto 2.0.21 containers)

| ID | Checks |
|---|---|
| TC-B13 | `telemetry` and `command_ack` reach the cloud stand-in unchanged; listed wearables are dropped. |
| TC-B14 | A cloud command for wearable A reaches A and not B. A command for a listed or offline wearable, or an expired or invalid one, is dropped. |
| TC-B15 | The uplink subscribes to a wearable's command topic only while it is online, and again after a cloud reconnect. |
| TC-B16 | `gw_uplink` may read telemetry and command_ack and write command, but may not read command or write telemetry. `setup_uplink.sh` upgrades an existing `services.acl`. |

**Cloud** (`tests/integration/`, `tests/unit/`)

| ID | Checks |
|---|---|
| TC-C36 | The three new schemas are generated (`test_contracts.py`). Bad payloads are refused: a wrong sample count, `end_reason` without `final`, unknown fields. |
| TC-C37 | Start: the patient's doctor gets 201, and the command goes to the right topic with an expiry. Another doctor gets 404. Org admin, patient and system admin get 403. No wearable, an inactive wearable, the mobile or an unknown path, an offline gateway, or a recording already open give 409. |
| TC-C38 | Ingestion: the ack and telemetry build one recording segment, and a redelivery changes nothing. Rejected: another device's recording, a chunk past the duration, a future `recording_start`, a wearable reassigned during the recording. |
| TC-C39 | Stop publishes `ecg_stop`, and `final` ends the recording. The sweeper expires unanswered commands and ends silent streams. A wearable going offline ends its recording. |
| TC-C40 | Live read: `after_seq` returns only newer chunks, for the doctor and for the patient (self); another patient gets 404. D9 rows in TC-C09 and TC-C10. |
| TC-C41 | Full stack: commands are not ingested back (the rule exclusion). A test gateway receives the command on the gateway listener. A gateway publishing to a command topic gets 0x87. |

**Dashboard**

| ID | Checks |
|---|---|
| TC-D15 | Unit: appending chunks, gaps, leads-off shading, the state machine, `counts_per_mv`. |
| TC-D16 | Sample-mode browser test on desktop and phone: request, the strip grows, stop, and the ended view links to the segment. The patient watches the same recording live. The org admin sees no panel. |
| TC-D17 | API-mode browser test (`scripts/api-e2e.sh`), with a test gateway client acting as the wearable: it acks and publishes chunks. |

**Evidence:** under `docs/testing/evidence/<date>/`:
- `ecg-spike/`: the rate and noise measurements, and the gain;
- `firmware/`: host pytest;
- `hardware/`: serial logs, captures with `check_capture.py` output, OLED photos;
- `uplink/`: `run_uplink_tests.sh`;
- `cloud/`: `run_cloud_tests.sh`;
- `dashboard/`: `checks.txt`, `e2e-mock.txt`, `e2e-api.txt`;
- `e2e/`: the H-W07 timings and a screenshot of the live strip.

## Exit criteria

1. The wearable samples the ADS1292 at 500 SPS within ±0.5% and reports leads-off (H-W04).
2. The on-device model classifies beats on the board and raises an alert with the 10 s segment (H-W08); its host checks pass (TC-W08, TC-W09).
3. A doctor starts and stops a live ECG on the deployed dashboard and sees it within about 3 s. The patient sees the same recording live. It is stored as a `recording` segment (H-W07).
4. Expired, replayed and invalid commands start nothing, and every recording ends: on stop, at its duration, on disconnect, or by the sweeper.
5. Only the patient's doctor can start or stop. Only that doctor and the patient can watch or read (TC-C37, TC-C40).
6. Alerts still follow alert-payload-v1: the button's and the model's both pass TC-W01 and are ingested.
7. Every test has an ID in `test_traceability.md` and stored evidence.

## Out of scope

- ECG evaluation and training of the models, the gateway classifier (`result` stays unread), IDS/IPS and attack tests → Iteration 7 (D-0). The edge model itself is in scope since 2026-11-26 (D-13).
- On-demand ECG on the mobile path (the API answers 409).
- Patients starting a recording; SSE or WebSocket; an outage backlog for telemetry; resampling to 360 Hz.

## Risks

| Risk | Handling |
|---|---|
| The ADS1292 wiring or module differs (CLKSEL, 5 V module, swapped DIN/DOUT) | The driver checks the ID and reads every register back, and logs what it read; `ECG ERROR` on the OLED |
| Frames lost when the sampler is late (no FIFO) | Priority 6 on core 1; lost frames are counted and logged (H-W04) |
| The model sees a different signal than MIT-BIH MLII (electrode placement, motion, the 0.5 Hz blocker) | Lead II placement (D-16); the 3-of-10 rule; H-W08 on a person at rest; the window is z-scored and differentiated, so gain and baseline matter little |
| The heap is too small with Wi-Fi, BLE, TLS, the 16 KB MQTT buffer and a 13.8 KB alert | Static RAM 188 KB of 342 KB after this change (154 KB left for the heap); the alert's samples are encoded without copies; the free heap and its minimum are logged every minute (H-W08) |
| Every gateway receives every command (`+`) | Per-wearable subscriptions (D-11); optional cloud enforcement |
| The EMQX rule loops commands into ingestion | The rule exclusion; TC-C41 |
| The Pi that is already set up keeps an old ACL | `setup_uplink.sh` rewrites the block; TC-B16 |
| The clock is not synced on the Pi hotspot (`gaps.md`) | Commands are refused until the clock is valid (TLS needs it anyway); the `recording_start` skew check |
| The outbox grows on a slow link | Chunks are skipped at the limit and show as gaps |
| A 5-minute strip is slow to draw (150,000 points) | The viewer splits it into rows or pages |
| Iteration 7 slips and FYP-1 Final lacks IDS/IPS | Tracked in `gaps.md`; the milestone is reviewed when Iteration 7 is planned |

## Conflicts with other docs, resolved in Slice 7

1. `scope.md`'s architecture says alerts come "with the triggering segment". The button alert keeps its synthetic segment (D-8), so this still holds.
2. `stack.md:92` says the gateway "classifies and forwards" telemetry. In this iteration it only forwards.
3. `iteration-6-dashboard.md` and `contracts.ts` describe a fixed-length recording seen only afterwards (type `ecg_recording`, statuses sent, acked and expired). This iteration adds a live view, Stop and new states.
4. `cloud-backend.md` D5 lets a gateway subscribe to `mm/fixed/+/command` (D-11).
5. The `bridge.py` docstring and D15 say telemetry and command_ack are neither forwarded nor ingested.
6. `gaps.md` notes MIT-BIH is 360 Hz. The stream is 500 SPS; the firmware resamples to the model's 128 Hz (D-13).

## Still open

- Whether patients may also start a recording (proposal: no) — before Slice 5.
- `audit_log` entries for start and stop (proposal: no) — before Slice 5.
- The maximum duration (proposal: 300 s) — before Slice 3.
- The retention period (placeholder: 90 days) — `gaps.md`.
- Enforcing the gateway assignment for commands in EMQX authorisation now, or later (D-11).
