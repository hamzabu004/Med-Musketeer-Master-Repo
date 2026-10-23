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
