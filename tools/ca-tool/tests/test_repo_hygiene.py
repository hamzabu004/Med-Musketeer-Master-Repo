"""TC-P11: no private key or certificate is tracked, or about to be tracked, in the repository."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SECRET_SUFFIXES = (".key", ".pem", ".crt", ".csr", ".srl", ".p12", ".pfx", ".der", ".jks",
                   ".keystore", ".passphrase", ".passwd")
SECRET_CONTENT = re.compile(rb"-----BEGIN (?:[A-Z]+ )?(?:PRIVATE KEY|CERTIFICATE)-----")

pytestmark = pytest.mark.skipif(shutil.which("git") is None or not (REPO_ROOT / ".git").exists(),
                                reason="not inside the master repository")


def _git_files(*args):
    output = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "-z", *args],
                            check=True, capture_output=True).stdout
    return [name for name in output.decode().split("\0") if name]


@pytest.mark.parametrize("scope", ["tracked", "untracked-not-ignored"])
def test_tc_p11_no_key_or_certificate_files(scope):
    files = _git_files() if scope == "tracked" else _git_files("--others", "--exclude-standard")
    by_name = [name for name in files if name.lower().endswith(SECRET_SUFFIXES)
               or Path(name).name in {".env", "passwd"}]
    by_content = []
    for name in files:
        path = REPO_ROOT / name
        if path.is_file() and path.stat().st_size < 5_000_000 and SECRET_CONTENT.search(path.read_bytes()):
            by_content.append(name)
    assert by_name == [], f"secret-like file names: {by_name}"
    assert by_content == [], f"PEM key or certificate content in: {by_content}"


def test_tc_p11_gitignore_covers_ca_output():
    for sample in ("ca/ca.key", "issued/x/device.key", "x/device.crt", "certs/gateway.key"):
        result = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", "-q", sample])
        assert result.returncode == 0, f"{sample} is not ignored"
