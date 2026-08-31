"""JSONL trace 记录器（impl-spec v2 附录 H）。

对应关系（spec → 本模块）：
- 附录 H 字段表      → :class:`TraceRecord` / :class:`ToolCallTrace`
- 附录 H 记录类型 7 类 → :data:`TRACE_EVENT_TYPES`
- 附录 H 文件路径    → `data/traces/{session_id}.jsonl`（目录/保留策略可配置）
- 附录 H 输入摘要脱敏截断 → record() 内对 input_summary / raw_output 截断

设计约束：
- 不导入 settings（运行期由调用方传 trace_dir/retention，来源 settings.agent_trace_*）
- 必填字段缺失或 event 类型非法 → ValueError（字段完整性）
- session_id 必须与 recorder 一致（防串写）
- close() 后继续写入 → RuntimeError（生命周期错误）
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

TRACE_SCHEMA_VERSION = "1.0"
TRACE_EVENT_TYPES = (
    "node_started",
    "node_finished",
    "transition",
    "tool_call",
    "fallback",
    "escape",
    "session_end",
)

# 输入摘要/原始输出截断上限（spec H：输入摘要截断 + 脱敏；脱敏逻辑随 roles 注入，W1 Day 2+）
_MAX_SUMMARY_CHARS = 500
_MAX_RAW_CHARS = 2000


@dataclass
class ToolCallTrace:
    """spec H tool_calls 单条记录。"""

    tool: str
    args_summary: str = ""
    latency_ms: Optional[int] = None
    ok: bool = True


@dataclass
class TraceRecord:
    """spec H 单条 trace 记录（字段顺序即 JSON 输出顺序）。"""

    schema_version: str = TRACE_SCHEMA_VERSION
    session_id: str = ""
    ts: str = ""
    event: str = ""
    state: str = ""
    node: Optional[str] = None
    role: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    input_summary: Optional[str] = None
    raw_output: Optional[str] = None
    validated: Optional[bool] = None
    retries: int = 0
    tool_calls: Optional[list[ToolCallTrace]] = None
    fallback_used: Optional[str] = None
    cost: float = 0.0
    latency_ms: Optional[int] = None

    def validate(self) -> None:
        """必填字段完整性 + event 类型白名单。非法即抛 ValueError。"""
        for name in ("session_id", "ts", "event", "state"):
            if not getattr(self, name):
                raise ValueError(f"TraceRecord missing required field: {name}")
        if self.event not in TRACE_EVENT_TYPES:
            raise ValueError(f"TraceRecord invalid event type: {self.event!r}")


class TraceRecorder:
    """每 session 一个 JSONL 文件；追加写入；超过 retention 清除最旧文件。

    用法（W1 Day 4 orchestrator 接线）：
        rec = TraceRecorder(session_id, trace_dir=settings.agent_trace_dir,
                            retention=settings.agent_trace_retention)
        rec.record(TraceRecord(...))
        rec.close()
    """

    def __init__(
        self,
        session_id: str,
        trace_dir: str | Path = "data/traces",
        retention: int = 200,
    ):
        self.session_id = session_id
        self._dir = Path(trace_dir)
        self._retention = max(1, retention)
        self._path = self._dir / f"{session_id}.jsonl"
        self._closed = False
        self._enforce_retention()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def closed(self) -> bool:
        return self._closed

    def record(self, record: TraceRecord) -> None:
        """校验 → 截断 → 追加 JSON 行 → 维护保留策略。"""
        if self._closed:
            raise RuntimeError("TraceRecorder closed")
        if record.session_id != self.session_id:
            raise ValueError(
                f"TraceRecord session_id {record.session_id!r} != recorder {self.session_id!r}"
            )
        record.validate()

        data = asdict(record)
        if data.get("input_summary"):
            data["input_summary"] = data["input_summary"][:_MAX_SUMMARY_CHARS]
        if data.get("raw_output"):
            data["raw_output"] = data["raw_output"][:_MAX_RAW_CHARS]

        self._dir.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        self._enforce_retention()

    def close(self) -> None:
        self._closed = True

    def _enforce_retention(self) -> None:
        """保留最近 N 个 trace 文件（按 mtime 升序删除最旧）。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self._dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        while len(files) > self._retention:
            files.pop(0).unlink(missing_ok=True)
