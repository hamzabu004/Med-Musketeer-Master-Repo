from __future__ import annotations

import argparse
import getpass
import json
import sys
import uuid
from pathlib import Path

from .core.audit import read_events
from .core.ca import (REPLACE_PHRASE, cert_preview, init_ca, issue_cloud, issue_device)
from .core.config import ensure_layout, load_settings
from .core.errors import MMCAError
from .core.flash import ESP_ERASE_TARGETS, erase_esp, flash_device
from .core.ssh import deploy_gateway, erase_gateway_credentials


def _positive_days(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1 or number > 36500:
        raise argparse.ArgumentTypeError("must be between 1 and 36500")
    return number


def _port_number(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("must be between 1 and 65535")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mmca", description="MedMusketeer local CA and provisioning tool")
    parser.add_argument("--root", type=Path, help="CA tool data directory (default: ~/medmusketeer-ca)")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init-ca", help="create the private MedMusketeer CA")
    init.add_argument("--cn", default="MedMusketeer CA")
    init.add_argument("--validity-days", type=_positive_days, default=3650)
    replace = sub.add_parser("replace-ca", help="replace an existing CA after an explicit confirmation")
    replace.add_argument("--cn", default="MedMusketeer CA")
    replace.add_argument("--validity-days", type=_positive_days, default=3650)
    replace.add_argument("--confirm-phrase", required=True)
    issue = sub.add_parser("issue", help="issue a wearable, gateway or cloud server TLS certificate")
    issue.add_argument("profile", choices=("wearable", "gateway", "cloud"))
    issue.add_argument("--device-id", help="UUIDv4; generated when omitted (not for cloud)")
    issue.add_argument("--key-type", choices=("ec_p256", "rsa_2048"), default=None)
    issue.add_argument("--validity-days", type=_positive_days, default=None)
    issue.add_argument("--replace", action="store_true",
                       help="cloud only: replace the existing cloud certificate")
    flash = sub.add_parser("flash", help="write a wearable identity to its ESP32-S3 creds partition")
    flash.add_argument("--device-id", required=True)
    flash.add_argument("--port")
    deploy = sub.add_parser("deploy", help="deploy gateway credentials to Mosquitto over SSH")
    deploy.add_argument("--device-id", required=True)
    deploy.add_argument("--host")
    deploy.add_argument("--port", type=_port_number)
    deploy.add_argument("--user")
    deploy.add_argument("--remote-cert-dir")
    deploy.add_argument("--restart", action="store_true")
    erase = sub.add_parser("erase", help="erase provisioned TLS credentials from a device or gateway")
    erase_sub = erase.add_subparsers(dest="erase_target", required=True)
    erase_esp = erase_sub.add_parser("esp", help="erase ESP32-S3 TLS credentials and/or network settings over serial")
    erase_esp.add_argument("scope", choices=ESP_ERASE_TARGETS,
                           help="tls: creds partition; network: Wi-Fi, MQTT broker, and BLE bonds "
                                "(application nvs partition); all: both")
    erase_esp.add_argument("--device-id", required=True)
    erase_esp.add_argument("--port")
    erase_gateway = erase_sub.add_parser("gateway", help="erase deployed Mosquitto TLS credentials over SSH")
    erase_gateway.add_argument("--device-id", required=True)
    erase_gateway.add_argument("--host")
    erase_gateway.add_argument("--port", type=_port_number)
    erase_gateway.add_argument("--user")
    erase_gateway.add_argument("--remote-cert-dir")
    audit = sub.add_parser("audit", help="show the local append-only audit log")
    audit.add_argument("--device-id")
    return parser


def _confirm_issue(preview: dict) -> bool:
    print("Certificate to be signed:")
    print(f"  Profile:   {preview['profile']}")
    print(f"  CN:        {preview['cn']}")
    print(f"  SAN:       {', '.join(preview['san'])}")
    print(f"  EKU:       {', '.join(preview['eku'])}")
    print(f"  Key type:  {preview['key_type']}")
    print(f"  Validity:  {preview['validity_days']} days")
    return input("Sign this certificate? [y/N] ").strip().lower() == "y"


def _passphrase() -> str:
    value = getpass.getpass("CA key passphrase: ")
    if not value:
        raise MMCAError("Passphrase cannot be empty")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.root)
        if args.command == "init-ca":
            first = getpass.getpass("New CA passphrase: ")
            second = getpass.getpass("Confirm CA passphrase: ")
            if not first or first != second:
                raise MMCAError("Passphrases were empty or did not match")
            fingerprint = init_ca(settings, args.cn, args.validity_days, first)
            print(f"CA created. SHA-256 fingerprint: {fingerprint}")
        elif args.command == "replace-ca":
            if args.confirm_phrase != REPLACE_PHRASE:
                raise MMCAError(f"Type exactly: {REPLACE_PHRASE}")
            print("Replacing this CA invalidates every certificate it issued.")
            if input(f"Type '{REPLACE_PHRASE}' again to continue: ").strip() != REPLACE_PHRASE:
                raise MMCAError("CA replacement cancelled")
            first = getpass.getpass("New CA passphrase: ")
            second = getpass.getpass("Confirm CA passphrase: ")
            if not first or first != second:
                raise MMCAError("Passphrases were empty or did not match")
            fingerprint = init_ca(settings, args.cn, args.validity_days, first, replace_existing=True)
            print(f"New CA created. SHA-256 fingerprint: {fingerprint}")
        elif args.command == "issue" and args.profile == "cloud":
            ensure_layout(settings)
            if args.device_id:
                raise MMCAError("The cloud certificate has no device_id")
            preview = cert_preview("cloud", "", args.key_type or "ec_p256",
                                   args.validity_days or settings.leaf_validity_days)
            if not _confirm_issue(preview):
                raise MMCAError("Issuance cancelled")
            passphrase = _passphrase()
            fingerprint, output_dir = issue_cloud(settings, preview["validity_days"], passphrase,
                confirm=lambda _preview: True, replace=args.replace)
            print(f"Issued the cloud server certificate for {preview['cn']}.")
            print(f"SHA-256 fingerprint: {fingerprint}")
            print(f"Files: {output_dir} (install with cloud/scripts/install-emqx-certs.sh)")
        elif args.command == "issue":
            if args.replace:
                raise MMCAError("--replace applies to the cloud certificate only")
            ensure_layout(settings)
            device_id = args.device_id or str(uuid.uuid4())
            key_type = args.key_type or settings.default_key_type
            validity = args.validity_days or settings.leaf_validity_days
            preview = cert_preview(args.profile, device_id, key_type, validity)
            if not _confirm_issue(preview):
                raise MMCAError("Issuance cancelled")
            passphrase = _passphrase()
            fingerprint, output_dir = issue_device(settings, args.profile, device_id, key_type,
                validity, passphrase, confirm=lambda _preview: True)
            print(f"Issued {args.profile} certificate for {preview['cn']}.")
            print(f"SHA-256 fingerprint: {fingerprint}")
            print(f"Files: {output_dir}")
        elif args.command == "flash":
            ensure_layout(settings)
            result = flash_device(settings, args.device_id, args.port)
            print(f"Flash verified on {result['port']} at 0x{result['partition_offset']:X}.")
            print("The local device private-key file was removed after verification.")
        elif args.command == "deploy":
            ensure_layout(settings)
            host = args.host or settings.gateway_host
            if not host:
                raise MMCAError("Provide --host or set gateway_ssh.host in config.toml")
            result = deploy_gateway(settings, args.device_id, host,
                port=args.port or settings.gateway_port,
                username=args.user or settings.gateway_user,
                remote_cert_dir=args.remote_cert_dir or settings.remote_cert_dir,
                restart=args.restart)
            print(f"Gateway credentials deployed to {result['host']}.")
            if args.restart:
                print("Mosquitto restarted and reported active.")
        elif args.command == "erase" and args.erase_target == "esp":
            ensure_layout(settings)
            result = erase_esp(settings, args.device_id, args.port, target=args.scope)
            for partition in result["partitions"]:
                print(f"Erased and verified the ESP {partition['name']} partition at 0x{partition['offset']:X}.")
            if args.scope == "tls":
                print("Wi-Fi and MQTT broker settings were left untouched.")
            if args.scope == "network":
                print("TLS credentials were left untouched.")
            if args.scope in ("tls", "all"):
                print("Run 'mmca flash' with a new wearable identity before MQTT can connect.")
            if args.scope in ("network", "all"):
                print("Remove the old gateway pairing on the phone, then provision Wi-Fi again over BLE.")
        elif args.command == "erase" and args.erase_target == "gateway":
            ensure_layout(settings)
            host = args.host or settings.gateway_host
            if not host:
                raise MMCAError("Provide --host or set gateway_ssh.host in config.toml")
            result = erase_gateway_credentials(settings, args.device_id, host,
                port=args.port or settings.gateway_port,
                username=args.user or settings.gateway_user,
                remote_cert_dir=args.remote_cert_dir or settings.remote_cert_dir)
            print(f"Erased gateway TLS credential files from {result['host']}.")
            print("Mosquitto was stopped if it was running; provision new gateway credentials before restarting it.")
        elif args.command == "audit":
            events = read_events(settings.audit_path, args.device_id)
            if not events:
                print("No audit records.")
            else:
                print(json.dumps(events, indent=2, sort_keys=True))
        return 0
    except (MMCAError, OSError, ValueError) as exc:
        print(f"mmca: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
