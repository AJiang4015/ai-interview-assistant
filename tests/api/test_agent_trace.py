"""W3 Phase 1：只读 trace 端点单测（app/api/agent_trace.py）。

覆盖：读取成功 / 缺失 404 / 路径穿越防护（非法 session_id 一律 404）/ 只读不建新存储。
"""

import json

import pytest
from fastapi import HTTPException

from app.config import settings


def _write_trace(d, session_id="sess-0001", n=3):
    (d / f"{session_id}.jsonl").write_text(
        "\n".join(json.dumps({"event": "transition", "state": "awaiting_answer", "session_id": session_id}) for _ in range(n)),
        encoding="utf-8",
    )
    return session_id


def test_get_trace_ok(env_dir, monkeypatch):
    sid = _write_trace(env_dir)
    monkeypatch.setattr(settings, "agent_trace_dir", str(env_dir))
    from app.api.agent_trace import get_trace

    res = get_trace(sid)
    assert res["session_id"] == sid
    assert res["count"] == 3
    assert res["events"][0]["state"] == "awaiting_answer"


def test_get_trace_missing_404(env_dir, monkeypatch):
    monkeypatch.setattr(settings, "agent_trace_dir", str(env_dir))
    from app.api.agent_trace import get_trace

    with pytest.raises(HTTPException) as ei:
        get_trace("no-such-session")
    assert ei.value.status_code == 404


def test_get_trace_path_traversal_rejected(env_dir, monkeypatch):
    monkeypatch.setattr(settings, "agent_trace_dir", str(env_dir))
    from app.api.agent_trace import get_trace

    for bad in ("../secret", "..\\secret", "a/b", "a b", "", "..", "session.jsonl"):
        with pytest.raises(HTTPException) as ei:
            get_trace(bad)
        assert ei.value.status_code == 404, f"session_id={bad!r} should be rejected"


def test_trace_file_not_modified(env_dir, monkeypatch):
    sid = _write_trace(env_dir, n=2)
    monkeypatch.setattr(settings, "agent_trace_dir", str(env_dir))
    from app.api.agent_trace import get_trace

    before = (env_dir / f"{sid}.jsonl").read_text(encoding="utf-8")
    get_trace(sid)
    after = (env_dir / f"{sid}.jsonl").read_text(encoding="utf-8")
    assert before == after  # 只读，不修改
