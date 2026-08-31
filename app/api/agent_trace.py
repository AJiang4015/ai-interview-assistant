"""只读 trace 查看端点（W3 Demo 定位，非产品能力；DR-016 trace 只读不建查询服务层）。

- `GET /api/agent/traces/{session_id}`：直接读取 TraceRecorder 输出
  （`settings.agent_trace_dir/{session_id}.jsonl`），不建立新的 trace storage；
- 只读：不修改 / 不删除 trace 文件，不扩展 AgentService surface；
- 路径穿越防护：session_id 仅允许 `[A-Za-z0-9_-]`（uuid + 短横线下划线），
  其余一律 404（AGENTS.md 硬规则 5）；
- 无权限体系（W3 计划约束：Demo 展示入口，权限治理列入技术债 P1）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import settings

router = APIRouter(prefix="/api/agent/traces", tags=["agent-trace"])

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@router.get("/{session_id}")
def get_trace(session_id: str) -> dict:
    """返回某会话的 trace 记录列表（只读）。"""
    if not _SAFE_ID.fullmatch(session_id or ""):
        raise HTTPException(status_code=404, detail="trace not found")
    trace_file = Path(settings.agent_trace_dir) / f"{session_id}.jsonl"
    if not trace_file.exists():
        raise HTTPException(status_code=404, detail="trace not found")
    records: list[dict] = []
    try:
        for line in trace_file.read_text(encoding="utf-8").strip().splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"trace read failed: {e}") from e
    return {"session_id": session_id, "count": len(records), "events": records}
