import json
import uuid

from mmca.cli import main


def test_cli_ca_issue_and_audit_workflow(tmp_path, monkeypatch, capsys):
    answers = iter(["first-test-passphrase", "first-test-passphrase",
                    "y", "first-test-passphrase"])
    monkeypatch.setattr("mmca.cli.getpass.getpass", lambda _prompt: next(answers))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    root = tmp_path / "mmca"
    assert main(["--root", str(root), "init-ca"]) == 0
    device_id = str(uuid.uuid4())
    assert main(["--root", str(root), "issue", "wearable", "--device-id", device_id]) == 0
    assert main(["--root", str(root), "audit", "--device-id", device_id]) == 0
    output = capsys.readouterr().out
    assert "Certificate to be signed" in output
    assert "issue" in output
    audit = [json.loads(line) for line in (root / "audit.log.jsonl").read_text().splitlines()]
    assert [record["action"] for record in audit] == ["init_ca", "issue"]
