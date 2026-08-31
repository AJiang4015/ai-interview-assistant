"""W1 Day 1：trace 单元测试（impl-spec v2 附录 H）。

先于实现编写（TDD）。覆盖：
- JSONL 写入与可解析性（schema_version / 字段）
- 必填字段完整性校验
- event 类型白名单（7 类）
- session_id 一致性
- input_summary / raw_output 截断
- 多记录追加
- 保留策略（超过 retention 清除最旧文件）

临时目录：使用工作区内自管理目录（`<repo>/.pytest_local_tmp/`），
不依赖 pytest 的 tmp_path/basetemp 机制（DSH 沙箱与 pytest tmp 清理冲突；
自管理目录在 CI 与本地同样可用）。
"""

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.agent.trace import (
    TRACE_EVENT_TYPES,
    TRACE_SCHEMA_VERSION,
    TraceRecorder,
    TraceRecord,
    ToolCallTrace,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def trace_tmp_dir():
    d = REPO_ROOT / ".pytest_local_tmp" / f"trace_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _record(session_id="s1", event="node_finished", **kw):
    base = dict(
        session_id=session_id,
        ts=datetime.now(timezone.utc).isoformat(),
        event=event,
        state="EVALUATING",
        node="evaluator",
        role="评估官",
        model="qwen-plus",
        prompt_version="roles.v1",
        input_summary="问题+回答摘要",
        raw_output='{"score": 7}',
        validated=True,
        retries=1,
        tool_calls=[ToolCallTrace(tool="kb_retrieve", args_summary="query", latency_ms=230, ok=True)],
        fallback_used=None,
        cost=0.0021,
        latency_ms=1850,
    )
    base.update(kw)
    return TraceRecord(**base)


def test_recorder_writes_jsonl_line(trace_tmp_dir):
    rec = TraceRecorder("s1", trace_tmp_dir)
    rec.record(_record())
    rec.close()
    lines = (trace_tmp_dir / "s1.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["schema_version"] == TRACE_SCHEMA_VERSION
    assert data["session_id"] == "s1"
    assert data["event"] == "node_finished"
    assert data["state"] == "EVALUATING"
    assert data["model"] == "qwen-plus"
    assert data["tool_calls"][0]["tool"] == "kb_retrieve"
    assert data["tool_calls"][0]["latency_ms"] == 230


def test_field_completeness_required_fields(trace_tmp_dir):
    rec = TraceRecorder("s1", trace_tmp_dir)
    bad1 = _record(event="")
    with pytest.raises(ValueError):
        rec.record(bad1)
    bad2 = _record(state=None)
    with pytest.raises(ValueError):
        rec.record(bad2)
    bad3 = _record(session_id="")
    with pytest.raises(ValueError):
        rec.record(bad3)
    bad4 = _record(ts="")
    with pytest.raises(ValueError):
        rec.record(bad4)


def test_event_type_whitelist(trace_tmp_dir):
    rec = TraceRecorder("s1", trace_tmp_dir)
    with pytest.raises(ValueError):
        rec.record(_record(event="bogus_event"))
    for ev in TRACE_EVENT_TYPES:
        rec.record(_record(event=ev))
    rec.close()
    lines = (trace_tmp_dir / "s1.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(TRACE_EVENT_TYPES)


def test_session_id_must_match_recorder(trace_tmp_dir):
    rec = TraceRecorder("s1", trace_tmp_dir)
    with pytest.raises(ValueError):
        rec.record(_record(session_id="other"))


def test_record_after_close_raises(trace_tmp_dir):
    rec = TraceRecorder("s1", trace_tmp_dir)
    rec.record(_record())
    rec.close()
    with pytest.raises(RuntimeError):
        rec.record(_record())


def test_input_summary_and_raw_output_truncated(trace_tmp_dir):
    rec = TraceRecorder("s1", trace_tmp_dir)
    rec.record(_record(input_summary="x" * 2000, raw_output="y" * 5000))
    rec.close()
    data = json.loads((trace_tmp_dir / "s1.jsonl").read_text(encoding="utf-8"))
    assert len(data["input_summary"]) <= 500
    assert len(data["raw_output"]) <= 2000


def test_append_multiple_records(trace_tmp_dir):
    rec = TraceRecorder("s1", trace_tmp_dir)
    rec.record(_record())
    rec.record(_record(event="transition", state="AWAITING_ANSWER"))
    rec.record(_record(event="session_end", state="END"))
    rec.close()
    lines = (trace_tmp_dir / "s1.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_retention_purges_oldest(trace_tmp_dir):
    for i in range(3):
        r = TraceRecorder(f"s{i}", trace_tmp_dir, retention=2)
        r.record(_record(session_id=f"s{i}"))
        r.close()
        # 显式控制 mtime，保证排序确定
        os.utime(trace_tmp_dir / f"s{i}.jsonl", (1_700_000_000 + i, 1_700_000_000 + i))
    files = sorted(trace_tmp_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    assert len(files) == 2
    assert files[0].name == "s1.jsonl"
    assert files[1].name == "s2.jsonl"


def test_retention_below_limit_keeps_all(trace_tmp_dir):
    for i in range(2):
        r = TraceRecorder(f"s{i}", trace_tmp_dir, retention=2)
        r.record(_record(session_id=f"s{i}"))
        r.close()
    assert len(list(trace_tmp_dir.glob("*.jsonl"))) == 2
