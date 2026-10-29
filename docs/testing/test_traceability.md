# Test traceability: report test cases to tests and evidence

Report tables: `tab:tc-prov` (TC-P), `tab:tc-ca` (TC-A, TC-B01 to B04) in Chapter 8 of the FYP-1 mid report. TC-B05 to B08 (the gateway uplink, Iteration 4) live in `gateway/uplink/tests/`; run them with `gateway/uplink/run_uplink_tests.sh` (evidence in `docs/testing/evidence/<date>/uplink/`).
Automated tests live in `tools/ca-tool/tests/`. Run them with `tools/ca-tool/run_report_tests.sh`;
it writes `environment.txt`, `pytest.txt`, `junit.xml`, `coverage.xml`, and `broker/` (Mosquitto log,
config, ACLs, and every client command with its output) to `docs/testing/evidence/<date>/`.

Kinds: **A** automated on the development machine; **A-mock** automated with esptool or SSH replaced
by a fake (shows the tool's logic, not the device); **A-container** automated against Mosquitto in a
container that stands in for the Pi; **H** needs the ESP32-S3, phone, or Pi (see
`hardware_test_procedures.md`).

| ID | Kind | Tests | Notes |
|---|---|---|---|
| TC-P01 | A | `test_report_cases::test_tc_p01_cli_creates_ca_in_designated_location` | Through the CLI. |
| TC-P02 | A | `test_report_cases::test_tc_p02_cli_issued_certificate_verifies_against_ca[*]` | Verified independently with `openssl verify`. |
| TC-P03 | A-mock + H | `test_flash::test_flash_builds_nvs_writes_verifies_then_removes_key` | Real flash: procedure H-P03. |
| TC-P04 | A-mock + H | `test_ssh::test_deploy_approves_new_host_uploads_and_verifies_gateway_files` | Real Pi: procedure H-P04. |
| TC-P05 to TC-P10, TC-P12 | H | — | Firmware on the board and the phone app (`apps/provisioner/`). |
| TC-P11 | A | `test_repo_hygiene::*` | Tracked and untracked-not-ignored files; names and PEM content. |
| TC-A01 | A | `test_ca::test_ca_and_leaf_profiles_and_encrypted_ca_key`, `test_ca::test_gateway_profile_includes_role_san_and_both_ekus`, `test_report_cases::test_tc_a01_leaf_profiles_match_design[*]` | Both key types. |
| TC-A02 | A | `test_report_cases::test_tc_a02_chain_verification_and_foreign_ca_rejection` | `openssl verify` with purpose and role-name checks; foreign CA rejected. |
| TC-A03 | A | `test_ssh::test_gateway_material_preflight_checks_role_san_and_key_match`, `test_report_cases::test_tc_a03_*` | Mismatched key and open key permissions rejected. |
| TC-A04 | A | `test_ca::test_serials_are_unique_and_device_ids_are_uuid4`, `test_report_cases::test_tc_a04_many_certificates_have_unique_recorded_serials` | 50 certificates. |
| TC-A05 | A | `test_ca::test_ca_and_leaf_profiles_and_encrypted_ca_key` | Right passphrase loads; wrong one fails. |
| TC-A06 | A | `test_flash::test_partition_table_parser_reads_named_nvs_partition`, `test_report_cases::test_tc_a06_*` | Binary generated from `firmware/wearable/partitions.csv` with ESP-IDF `gen_esp32part.py`. |
| TC-A07 | A-mock + H | `test_flash::test_wrong_chip_stops_without_removing_private_key`, `test_flash::test_missing_partition_stops_without_removing_private_key`, `test_flash::test_readback_mismatch_retains_private_key_and_metadata` | Real board: procedure H-A07 (missing partition only). |
| TC-A08 | A-mock + H | `test_ssh::test_host_fingerprint_and_explicit_new_host_approval`, `test_ssh::test_new_host_rejection_does_not_save_key`, `test_ssh::test_deploy_stops_on_known_host_key_mismatch` | Real Pi: procedure H-A08. |
| TC-A09 | A-mock | `test_ca::test_audit_whitelists_details_and_never_records_secret_values`, `test_report_cases::test_tc_a10_audit_log_after_issue_flash_deploy_has_every_action_and_no_secret` | Full init, issue, flash, issue, deploy run. The test function keeps its pre-renumbering name (`tc_a10`) so it matches the 2026-10-22 evidence. |
| TC-B01 | A-container + H | `test_broker_interop::test_tc_b01_*` | Includes foreign CA, no certificate, and connecting without the role name. Pi: H-B, passed 2026-10-22. |
| TC-B02 | A-container + H | `test_broker_interop::test_tc_b02_*` | All four own publish topics and the own command subscription. |
| TC-B03 | A-container + H | `test_broker_interop::test_tc_b03_*` | Judged by a services-listener monitor and `Denied PUBLISH` in the broker log. |
| TC-B04 | A-container + H | `test_broker_interop::test_tc_b04_*` | The services username is a UUIDv4 so that a wearable CN can equal it. On the Pi it is `gw_services`, so H-B uses a scratch CA. TC-B02 to B04 on the Pi: blocked (Pi not available; after the CA replacement). |
| TC-B05 | A-container + H | `gateway/uplink/tests/test_interop.py::test_tc_b05_*` | Iteration 4 (D16). The uplink gets a list from a cloud stand-in and applies it within 10 s. On an open connection, the listed wearable's publishes are refused and commands no longer reach it; it stays connected; another wearable is unaffected; the version is reported to the cloud. Pi: H-B06. |
| TC-B06 | A-container + A | `test_interop::test_tc_b06_*`; `test_revocations::*` | Older, equal and invalid lists are ignored, and so is a device id that would inject an ACL line; the stored list and the ACL file stay as they were. |
| TC-B07 | A-container + A | `test_interop::test_tc_b07_*`; `test_revocations::test_only_newer_versions_are_kept_and_survive_a_restart`; `test_enforce::*` | A restarted uplink applies the stored list to a broker that lost it, before the cloud is reached (cloud down). The ACL file and the stored list are 0600. A failed reload is retried. |
| TC-B08 | A-container | `test_interop::test_tc_b08_*` | During a cloud outage the stored list holds: the listed wearable is refused and others are accepted. When the cloud returns with a newer list, the uplink reconnects by itself and enforces it: one wearable lifted, another listed. |

## Wearable firmware (Iteration 2)

Automated tests: `firmware/wearable/tools/test_check_capture.py`, run with the cloud backend's environment (`cloud/backend/.venv/bin/python -m pytest firmware/wearable/tools`) and in the `payload` job of `.github/workflows/firmware.yml`. **A-host**: the firmware's own C source built and run on the development machine with stand-ins for the ESP-IDF calls.

| ID | Kind | Tests | Notes |
|---|---|---|---|
| TC-W01 | A-host + H | `test_check_capture::test_tc_w01_*` | `main/alert.c` built on the host; its alerts pass alert-payload-v1 (`cloud/backend/app/contracts.py`) and fit the 4096-byte MQTT buffer. Pi: H-W01, blocked (Pi not available). |
| TC-W02 | H | H-W02 | Retained `online` on connect, Last Will `offline`. Blocked (Pi not available). |
| TC-W03 | H | H-W03 | A press while disconnected is dropped, not queued. Blocked (Pi not available). |
| TC-W04 | A | `test_check_capture::test_tc_w04_*` | The capture checker refuses what ingestion would (the old test alert, a wrong sample count, unknown topics), a wearable status with `revocation_version`, another device's topic, seq gaps, repeated `msg_id`, and `segment_start` after `sent_at`. A reboot's `seq` 0 is accepted. |

## Cloud backend (Iteration 3)

Tests live in `cloud/backend/tests/`. Run them with `cloud/run_cloud_tests.sh`; it writes `environment.txt`, `pytest.txt`, `junit.xml`, `coverage.xml`, and `stack/` (compose output, service states, `/healthz` response, the EMQX and API logs, and per-case records) to `docs/testing/evidence/<date>/cloud/`. Planned cases: `docs/iterations/iteration-3-cloud.md`.

Kinds: **A** automated, no containers; **A-db** automated against a throwaway TimescaleDB container (same image and init script as the stack), migrated as `mm_migrator`, with the API connecting as `mm_api`; **A-stack** automated against the full compose stack (Docker), brought up under its own project name and removed afterwards.

| ID | Kind | Tests | Notes |
|---|---|---|---|
| TC-C01 | A-stack | `test_stack::test_tc_c01_every_service_is_healthy`, `test_stack::test_tc_c01_healthz_reports_every_dependency_ok`, `test_stack::test_tc_c01_zitadel_serves_oidc_discovery_through_the_proxy` | From empty volumes. Evidence 2026-10-23. |
| TC-C02 | A | `test_app::test_tc_c02_api_refuses_to_start_without_required_setting[*]` | One case per required `MM_*` setting. |
| TC-C03 | A-db | `test_schema::test_tc_c03_migrations_go_down_and_up_on_an_empty_database`, `test_schema::test_tc_c03_the_api_login_can_change_rows_but_not_the_schema` | All 20 report tables plus `audit_log` (D11), both hypertables, the `ecg_chunks` retention job, no foreign key into `ecg_chunks`; `mm_api` cannot change the schema or change or delete audit entries. |
| TC-C04 | A-db | `test_schema::test_tc_c04_a_device_has_at_most_one_open_grant`; API: `test_registry::test_tc_c08_registry_round_trip` (409 on a second grant) | Partial unique index `device_grants_one_open`. |
| TC-C05 | A-db | `test_schema::test_tc_c05_one_active_wearable_per_patient_and_one_patient_per_wearable` | Both directions. |
| TC-C06 | A-db | `test_schema::test_tc_c06_one_active_doctor_per_patient` | |
| TC-C07 | A-db | `test_registry::test_tc_c07_revoking_a_grant_ends_the_open_assignment_and_session`, `test_registry::test_revoking_a_device_revokes_its_credentials_and_closes_its_grant` | |
| TC-C08 | A-db | `test_registry::test_tc_c08_registry_round_trip` and the 404/403/401 tests in `test_registry` | System admin only; the API refuses every request until authentication exists (Slice 3). |
| TC-C09 | A-db | `test_access::test_tc_c09_role_endpoint_matrix[*]` (every endpoint × every role), `test_access::test_tc_c09_the_matrix_covers_every_endpoint` | Allowed: 2xx on a target the role is entitled to; denied: 403. A fresh populated database per case (`tests/integration/world.py`). Endpoints: D9 in `docs/decisions/cloud-backend.md`. |
| TC-C10 | A-db | `test_access::test_tc_c10_*` | Other doctor's and other organisation's patients answer 404 and never appear in lists; a reassigned patient leaves the old doctor's reach; patients see only themselves; org admins stay inside their organisation and get no ECG, also not in exports. |
| TC-C11 | A-db | `test_access::test_tc_c11_the_system_admin_gets_no_patient_or_doctor_data` | Every `/admin` read searched for patient, doctor, segment and alert ids, pseudonyms and disorders after organisation-side actions; every non-admin endpoint refuses the system admin. |
| TC-C12 | A + A-db + A-stack | `test_tokens::test_tc_c12_*` (signature, key id, algorithm, issuer, audience, expiry), `test_auth::test_tc_c12_*` (registered user, role and organisation must match), `test_stack::test_tc_c12_a_real_zitadel_token_works_once_the_user_is_registered` | Unit tests sign tokens with a local RSA key; the stack test uses a real ZITADEL machine user with a client-credentials token. |
| TC-C13 | A-stack (+ A-db, A) | `test_stack::test_tc_c13_account_creation_shows_up_in_zitadel_and_in_users`; with ZITADEL faked: `test_organisation::*` (rollback when ZITADEL or the database refuses); `test_zitadel::*` (the client's calls) | Real ZITADEL: organisation with the project granted, org admin, doctor and patient each in the right ZITADEL organisation with the right role and in `users`; a duplicate e-mail leaves no row; disabling deactivates the ZITADEL user. Record in `stack/tc_c13_accounts.json`. |
| TC-C14 | A-stack | `test_gateway::test_tc_c14_an_active_gateway_connects_and_its_messages_reach_ingestion` | A gateway registered through the API connects over mTLS, subscribes to commands, publishes an alert and a status; a monitor with the adapter's account receives both on `ingest/{gateway}/...` with the broker-attested username (D1). The monitor ignores the broker's connection events (`ingest/{gateway}/broker/...`, D15). |
| TC-C15 | A-stack + A-db | `test_gateway::test_tc_c15_a_revoked_credential_is_refused_on_the_next_connect`; `test_broker::test_tc_c15_*`, `test_broker::test_a_revoked_certificate_is_refused_while_the_gateways_new_one_works` | Revoked credential refused at once on reconnect; a new certificate for the same gateway works while the old stays refused; a suspended device is refused; the API logs reason and check time. |
| TC-C16 | A-stack + A-db | `test_gateway::test_tc_c16_foreign_missing_and_wearable_certificates_are_refused`; `test_broker::test_tc_c15_c16_refused_gateways[*]` | Foreign CA (even with its fingerprint registered) and no certificate: refused in the TLS handshake; wearable and unregistered gateway certificates: refused by the API. |
| TC-C17 | A-stack + A + A-db | `test_gateway::test_tc_c17_publish_and_subscribe_outside_the_acl_are_denied`; `test_broker_rules::*`; `test_broker::test_tc_c17_topic_access_also_needs_an_active_gateway` | MQTT 5 reason code "Not authorized" for each denied publish and subscription; the adapter monitor receives only the allowed sentinel; EMQX logs each denial (`emqx.log`). |
| TC-C18 | A-stack + A | `test_gateway::test_tc_c18_the_gateway_verifies_the_cloud_by_its_pinned_name`; CA tool `test_ca::test_cloud_profile_*`, `test_ca::test_certificates_carry_key_identifiers_*` | The listener presents CN/SAN `cloud.medmusketeer.local`; a client pinning another name or trusting another CA refuses it. The gateway's own uplink (Iteration 4) has to apply the same pin. |
| TC-C19 | A-stack + A-db + A | `test_stack::test_tc_c19_seeded_accounts_sign_in_to_the_dashboard_and_get_their_role`; `test_directory::*`; `test_app::test_cors_*`, `test_app::test_auth_config_*`; `test_zitadel_bootstrap::*`; `test_zitadel::test_profiles_*`; `test_access::*` (row `GET /directory`) | The bootstrap's dashboard app is a PKCE browser app with JWT access tokens; `GET /auth/config` gives its client id; seeded accounts of all four roles sign in with authorization code + PKCE (the browser's steps, scripted) and `/me` returns their role, with CORS for the dashboard origin; `/directory` returns names from ZITADEL per role (D14). Record in `stack/tc_c19_dashboard_sign_in.json`. |
| TC-C20 | A-stack + A-db + A | `test_ingestion::test_tc_c20_c22_an_alert_from_a_gateway_is_stored_once_with_the_brokers_attestation`; `test_ingest::test_tc_c20_an_alert_for_an_issued_wearable_lands_in_every_table`; `test_contracts::*`, `test_adapter::test_an_alert_is_attested_by_the_gateway_in_the_topic` | Through EMQX, the adapter and the API: session, segment, chunk (`attested_by` = the publishing gateway, `x509_mtls`), the wearable's classification, the alert, the hop times in `ingested_messages`. At the API: `NOTIFY mm_alerts`, presence fields, and the doctor reading the samples back through `/segments/{id}`. Record in `stack/tc_c20_c26_ingestion.json`. |
| TC-C21 | A-stack + A-db | `test_ingestion::test_tc_c21_c23_unissued_and_malformed_alerts_are_rejected_and_logged`; `test_ingest::test_tc_c21_*` | An alert for a granted but unissued wearable is rejected; the API logs `ingest rejected … reason=the wearable is not issued to a patient` and writes nothing. At the API, also: unknown, suspended and ungranted wearables, an inactive or missing attesting gateway, an unauthenticated message, a gateway reporting for another. |
| TC-C22 | A-stack + A-db | `test_ingestion::test_tc_c20_c22_*`; `test_ingest::test_tc_c22_a_redelivered_message_is_stored_once`, `test_ingest::test_message_ids_are_per_device` | The same alert published twice is stored once (`ingest duplicate` in the API log); message ids are scoped to the device. |
| TC-C23 | A-stack + A-db + A | `test_ingestion::test_tc_c21_c23_*`; `test_ingest::test_tc_c23_a_malformed_message_is_rejected[*]`; `test_contracts::test_tc_c23_*`, `test_adapter::test_tc_c23_*` | The adapter drops payloads that fail their contract (logged `adapter dropped`), e.g. `fs_hz` 0 or not JSON; the API rejects them again if posted (sample count, unknown field, version, message type, missing envelope field, future `segment_start`). |
| TC-C24 | A-stack + A-db + A | `test_ingestion::test_tc_c24_an_ids_event_is_stored_as_the_publishing_gateways`; `test_ingest::test_tc_c24_*`; `test_contracts::test_ids_mode_does_not_act` | Stored in `security_events` with `gateway_id` = the publishing gateway and `event_id` = `msg_id`; a redelivery is stored once; an unknown device in the event is rejected. |
| TC-C25 | A-db | `test_ingest::test_tc_c25_reassigning_a_wearable_ends_the_session_and_later_data_goes_to_the_new_patient`, `test_ingest::test_a_session_left_open_for_another_patient_is_ended_by_ingestion` | Returning the wearable ends its session, and alerts are then rejected; issued to another patient, its next alert opens a new session for them, and the first patient's segments stay theirs. |
| TC-C26 | A-stack + A-db | `test_ingestion::test_tc_c26_when_the_gateway_disconnects_its_wearables_become_unknown`; `test_ingest::test_tc_c26_*`, `test_ingest::test_a_wearable_reported_offline_is_unknown_and_detached_from_its_gateway` | After a gateway disconnects (EMQX's event, rule `mm_presence`), its wearable is `unknown`, not offline, still via that gateway; it is `fixed` again once the gateway forwards its status; a stale disconnect is ignored. Also: messages wait in EMQX while the adapter is stopped (`test_ingestion::test_messages_wait_in_the_broker_while_the_adapter_is_down`). |
| TC-C28 | A-db + A | `test_revocation::test_tc_c28_*`; `test_contracts::test_revocation_list_v1`; `test_broker_rules::test_a_gateway_subscribes_only_to_commands_and_the_revocation_list` | Iteration 4 (D16). The wearable revocation list follows each registry transition, with a new version only when its contents change; expired certificates drop off; gateways are disconnected, not listed; a change commits while EMQX is down and is published by the reconciler later. EMQX is a fake here. |
| TC-C29 | A-stack | `test_revocation_stack::test_tc_c29_*` | Through the real EMQX: a gateway gets the retained list on subscribing and a new version within 10 s of a revocation; another gateway's publish to the topic is refused (0x87); the retained list survives EMQX being recreated (disc storage, not republished in between). |
| TC-C30 | A-stack + A-db | `test_revocation_stack::test_tc_c30_*`; `test_revocation::test_tc_c28_gateways_are_disconnected_not_listed` | A gateway whose credential is revoked, or which is suspended or revoked, is disconnected within 5 s (reason 0x98), and its reconnect is refused. |
| TC-C31 | A-db + A | `test_revocation::test_tc_c31_*`; `test_contracts::test_a_gateway_status_may_carry_its_revocation_version` | A gateway's reported list version is stored (a stale report ignored); `GET /admin/revocation` lists active gateways behind the published version; a wearable's status cannot carry one. |

## Dashboard (Iteration 6)

Tests live in `web/dashboard/`:
- unit tests: `src/**/*.test.ts(x)`, run with `npm test`;
- sample-mode browser tests: `e2e/mock/`, run with `npm run test:e2e`, desktop and phone;
- API-mode browser tests: `e2e/api/`, run with `scripts/api-e2e.sh`.

Screens and rules: `docs/iterations/iteration-6-dashboard.md`. Evidence: `docs/testing/evidence/2026-10-26/dashboard*/` (`checks.txt`, `e2e-mock.txt`, `e2e-api.txt`).

Kinds:
- **A**: Vitest, no browser.
- **A-browser**: Playwright in sample mode, desktop and phone.
- **A-stack-browser**: Playwright against the cloud compose stack, signing in through ZITADEL's real login.

| ID | Kind | Tests | Notes |
|---|---|---|---|
| TC-D01 | A + A-browser + A-stack-browser | `roles.test`, `role-guard.test`, `navigation.test`; `e2e/mock/sign-in.spec` (each role lands in its area and is kept out of the others; signed-out visitors go to sign-in); `e2e/api/sign-in.spec` (each seeded role signs in through ZITADEL and lands by the role `/me` reports) | |
| TC-D02 | A + A-stack-browser | `http.test` (renew and retry once on 401, one renewal shared between requests, give up with the 401 when the token cannot be renewed); `e2e/api/sign-in.spec` (tokens not in `localStorage`; sign-out ends the ZITADEL session) | |
| TC-D03 | A | `api.test` (every call matches a path and method of the cloud's OpenAPI document; unserved capabilities refused without a call); `mock-data-source.test` (sample data answers 403/404 and 409/422 as the API does, including suspension); `errors.test` | Keeps sample mode honest to the API. |
| TC-D04 | A-browser + A-stack-browser | `e2e/mock/system-admin.spec`; `e2e/api/system-admin.spec` | Organisation and admin; device registration, credential, activation, grant; security events; audit trail of each step. |
| TC-D05 | A-browser + A-stack-browser | `e2e/mock/system-admin.spec`, `e2e/mock/org-admin.spec` (code gone after confirmation); `e2e/api/system-admin.spec`, `e2e/api/org-admin.spec` (the new org admin and the new patient redeem their codes in ZITADEL's login and land in their areas) | Closes the redemption gap of D12. |
| TC-D06 | A + A-browser + A-stack-browser | `org.test`; `e2e/mock/org-admin.spec`; `e2e/api/org-admin.spec` | Create, disable with consequences, assign doctor, issue/return wearable, disorder, export with download, history. |
| TC-D07 | A-browser + A-stack-browser | `e2e/mock/doctor-patient.spec` (doctor); `e2e/api/doctor-patient.spec` | Alert → ECG → acknowledge; the acknowledgement survives a reload against the API; another doctor's patient reads "not found". |
| TC-D08 | A-browser + A-stack-browser | `e2e/mock/doctor-patient.spec` (patient); `e2e/api/doctor-patient.spec` | Own alerts read-only with who acknowledged, their doctor's name, their ECG. |
| TC-D09 | A | `ecg.test` (int16le-base64 decoding, stitching by `seq`); `care.test` (strip at 25 mm/s and 10 mm/mV, whole large squares) | |
| TC-D10 | A-browser + A-stack-browser | `e2e/api/system-admin.spec` (attack tests unavailable), `e2e/api/doctor-patient.spec` (on-demand recording unavailable); `e2e/mock/doctor-patient.spec`, `mock-data-source.test` (sample recording contract) | Unbuilt capabilities said plainly in API mode. |
| TC-D11 | A-browser | `expectFitsViewport` in every sample-mode spec | Every page at phone width (Pixel 7) without horizontal page scroll. |
| TC-D12 | A + A-browser + A-stack-browser | `care.test` (each alert marked once; `backlog` flag); `e2e/mock/doctor-patient.spec`, `e2e/api/doctor-patient.spec` (one mark per alert drawn) | "Dashboard render" checkpoint of the latency methodology. |
| TC-D13 | A + A-browser | `revocation-list.test`; `mock-data-source.test` ("the wearable revocation list"); `e2e/mock/system-admin.spec` ("flags gateways behind the wearable revocation list") | Iteration 4 (D16). A gateway's list state, as the API's `stale_gateways`: current, behind, not reported; none before a list is published or for inactive gateways. Sample data raises the version as the API does. The dashboard, devices list and device page show it, and a suspension makes the gateways behind. The API-mode spec does not cover it yet. |
