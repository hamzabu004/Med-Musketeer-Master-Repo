"""Unit tests: the generated ACL file and its reload (stack.md, Slice 0 mechanism)."""
import re
import uuid
from pathlib import Path

from mm_uplink.enforce import PATTERNS, Enforcer, render
from tests.test_revocations import listing

REPO = Path(__file__).resolve().parents[3]


def test_setup_mosquitto_writes_the_same_patterns():
    script = (REPO / "tools" / "Fixed-Gateway-Setup" / "setup_mosquitto.sh").read_text()
    first_acl = re.search(r'cat > "\$WEARABLES_ACL" <<\'EOF\'\n(.*?)EOF\n', script, re.S).group(1)
    assert first_acl == PATTERNS


def test_render_adds_one_deny_block_per_listed_wearable():
    a, b = sorted(str(uuid.uuid4()) for _ in range(2))
    text = render(listing(7, b, a, certificates=(str(uuid.uuid4()),)))
    assert text.startswith(PATTERNS)
    assert "version 7" in text
    assert text.endswith(f"\nuser {a}\ntopic deny #\n\nuser {b}\ntopic deny #\n")  # sorted; certificates not here
    assert render(None) == PATTERNS


class Reloads:
    def __init__(self):
        self.count = 0
        self.fail = False

    def __call__(self):
        if self.fail:
            raise OSError("no such process")
        self.count += 1


def test_the_broker_is_reloaded_only_when_the_file_changes_and_failures_are_retried(tmp_path):
    acl = tmp_path / "wearables.acl"
    acl.write_text(PATTERNS)
    reloads = Reloads()
    enforcer = Enforcer(acl, reloads)
    assert enforcer.apply(None) and reloads.count == 0  # already in line: no reload
    device = str(uuid.uuid4())

    reloads.fail = True
    assert not enforcer.apply(listing(2, device))
    assert enforcer.pending and enforcer.enforced_version is None
    assert f"user {device}" in acl.read_text()  # written; the reload is what failed

    reloads.fail = False
    assert enforcer.apply(listing(2, device))  # same file, but the reload is still owed
    assert reloads.count == 1 and not enforcer.pending and enforcer.enforced_version == 2
    assert enforcer.apply(listing(3, device)) and reloads.count == 2  # version line changed
    assert oct(acl.stat().st_mode & 0o777) == "0o600"
