from pathlib import Path

import pytest

from mmca.core.config import load_settings


@pytest.fixture
def settings(tmp_path: Path):
    return load_settings(tmp_path / "ca-root")
