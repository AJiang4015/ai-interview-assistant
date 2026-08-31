"""agent 测试共享 fixture：工作区内临时目录（避免 DSH 沙箱与 pytest tmp 机制冲突）。"""

import shutil
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def env_dir():
    d = REPO_ROOT / ".pytest_local_tmp" / f"agent_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
