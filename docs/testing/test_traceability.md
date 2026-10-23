# Test traceability: report test cases to tests and evidence

Report tables: `tab:tc-prov` (TC-P), `tab:tc-ca` (TC-A, TC-B) in Chapter 8 of the FYP-1 mid report.
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
| TC-B01 | A-container + H | `test_broker_interop::test_tc_b01_*` | Includes foreign CA, no certificate, and connecting without the role name. Pi: H-B. |
| TC-B02 | A-container + H | `test_broker_interop::test_tc_b02_*` | All four own publish topics and the own command subscription. |
| TC-B03 | A-container + H | `test_broker_interop::test_tc_b03_*` | Judged by a services-listener monitor and `Denied PUBLISH` in the broker log. |
| TC-B04 | A-container + H | `test_broker_interop::test_tc_b04_*` | The services username is a UUIDv4 so that a wearable CN can equal it. |

## Cloud backend (Iteration 3)

Tests live in `cloud/backend/tests/`. Run them with `cloud/run_cloud_tests.sh`; it writes `environment.txt`, `pytest.txt`, `junit.xml`, `coverage.xml`, and `stack/` (compose output, service states, `/healthz` response) to `docs/testing/evidence/<date>/cloud/`. Planned cases: `docs/iterations/iteration-3-cloud.md`.

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
