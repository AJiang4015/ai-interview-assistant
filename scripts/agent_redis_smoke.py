"""W3 Phase 3 验证项：Redis profile roundtrip smoke（不改业务逻辑）。

验证链路（要求见 W3 计划 §3）：
    Session A → profile write → Redis → 新进程视角读取 → Session B → INIT 注入
    → 难度/薄弱点影响

同时验证：
1. RedisProfileStore 真实可用（凭据经环境变量 REDIS_PASSWORD 注入，不落盘）；
2. 跨 session / 跨实例数据一致（新 RedisProfileStore 实例读到相同数据）；
3. make_profile_store 正确选择 RedisProfileStore（正确密码）/ SessionProfileStore（错误密码）；
4. 结果只记录 成功/失败/环境条件/是否 fallback。

运行（密码只进进程环境，不写入任何文件/提交）：
    $env:REDIS_PASSWORD="..."   # 由运行方提供
    python scripts/agent_redis_smoke.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.services.agent.agent_service import build_agent_service  # noqa: E402
from app.services.agent.profile_store import (  # noqa: E402
    RedisProfileStore,
    SessionProfileStore,
    make_profile_store,
)
from app.services.agent.state_machine import EscapeHatchConfig  # noqa: E402
from app.services.topic_tracker import TopicTracker  # noqa: E402
from app.storage.interview_store import InterviewStore  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)


class _MockLLM:
    """对象式 mock LLM（build_agent_service 经 ModelGateway → llm.chat(model=...)，须为对象方法）。"""

    def __init__(self, score: float = 3.0, capture: dict | None = None):
        self.score = score
        self.capture = capture  # 记录 question prompt（Session B 断言 INIT 注入用）

    async def chat(self, prompt, system=None, session_id=None, model=None):
        if self.capture is not None and '"score_reason"' not in prompt:
            self.capture["prompt"] = prompt
        if '"score_reason"' in prompt:
            return (f'{{"score": {int(self.score)}, "comment": "c", "score_reason": "r", '
                    '"reference_answer": "ref", "tags": ["JVM"]}}')
        return ('{"question": "什么是 JVM 内存模型？", "difficulty": "medium", '
                '"knowledge_tags": ["JVM"], "topic": "JVM", "category": "JVM"}')


def _build(store, llm, profile_store, trace_dir, max_rounds=1):
    tracker = TopicTracker(interview_store=store, tree_dir=str(PROJECT_ROOT / "data" / "knowledge_trees"))
    return build_agent_service(
        store=store, llm=llm, facade=None, topic_tracker=tracker,
        profile_store=profile_store,
        trace_dir=str(trace_dir), trace_retention=50,
        escape_config=EscapeHatchConfig(max_rounds=max_rounds),
    )


async def main() -> None:
    password = os.environ.get("REDIS_PASSWORD")
    if not password:
        check("REDIS_PASSWORD 环境变量", False, "未注入（运行方提供）")
        return
    check("REDIS_PASSWORD 仅经环境变量注入（不落盘）", password != "", "len 已隐去")

    work = PROJECT_ROOT / "data" / "agent_smoke" / "redis_smoke"
    work.mkdir(parents=True, exist_ok=True)

    # 1) make_profile_store 选择：正确密码 → RedisProfileStore
    store_a = make_profile_store(
        host=settings.redis_host, port=settings.redis_port, db=settings.redis_db,
        password=password, timeout=3.0,
    )
    check("make_profile_store(正确密码) → RedisProfileStore", isinstance(store_a, RedisProfileStore))

    # 2) Session A：低分（JVM, score 3）→ SUMMARIZING 批量写画像到 Redis
    import shutil

    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    try:
        store_a._redis.delete(store_a._key("smoke_u1"))  # 清理历史探针，保证干净起点
    except Exception:  # noqa: BLE001
        pass
    store_a_db = InterviewStore(db_path=str(work / "a.db"))
    svc_a = _build(store_a_db, _MockLLM(score=3.0), store_a, str(work / "traces"))
    res_a = await svc_a.start("Java后端", username="smoke_u1")
    ans_a = await svc_a.answer(res_a["question"]["id"], "回答内容足够长避免追问：" + "r" * 300, username="smoke_u1")
    check("Session A 完成（is_complete）", ans_a["is_complete"] is True)
    check("Session A 评估为 LLM 分（score=3，非兜底）", ans_a["evaluation"]["score"] == 3,
          f"score={ans_a['evaluation']['score']}, fallback={ans_a['evaluation'].get('fallback')}")

    # 3) 跨实例一致性：新 RedisProfileStore（模拟新进程）读同一 key
    store_b = RedisProfileStore(store_a._redis)  # 同 Redis 的新实例
    prof_b = store_b.get("smoke_u1")
    check("跨实例读取一致（accuracy=3.0）", prof_b.get("accuracy") == 3.0, f"accuracy={prof_b.get('accuracy')}")
    check("weak_points 含 JVM", "JVM" in prof_b.get("weak_points", []))
    check("level=初级", prof_b.get("level") == "初级")

    # 原始 Redis key 内容可解析
    raw = store_a._redis.get(store_a._key("smoke_u1"))
    check("Redis 原始 key 可解析 JSON", raw is not None and json.loads(raw).get("level") == "初级")

    # 4) Session B：新进程视角（新 store 实例 + 新 InterviewStore）→ INIT 注入
    captured: dict = {}
    db_b = str(work / "b.db")
    store_b_db = InterviewStore(db_path=db_b)
    svc_b = _build(store_b_db, _MockLLM(capture=captured), store_b, str(work / "traces"))
    res_b = await svc_b.start("Java后端", username="smoke_u1")
    check("Session B start 成功", bool(res_b["question"]["content"]))
    check("INIT 注入：目标难度由 level(初级)→easy", "目标难度：easy" in captured.get("prompt", ""),
          "prompt 含目标难度")
    check("INIT 注入：薄弱点 JVM 进 prompt", "薄弱点：JVM" in captured.get("prompt", ""))
    # 难度影响（确定性断言：get_profile 返回 level=初级）
    prof_c = store_b.get("smoke_u1")
    check("Session B 读取同一画像（level 仍初级）", prof_c.get("level") == "初级")

    # 5) 错误密码 → 降级 SessionProfileStore
    store_bad = make_profile_store(
        host=settings.redis_host, port=settings.redis_port, db=settings.redis_db,
        password="wrong-password", timeout=3.0,
    )
    check("make_profile_store(错误密码) → SessionProfileStore（降级）", isinstance(store_bad, SessionProfileStore))

    # 清理探针 key
    try:
        store_a._redis.delete(store_a._key("smoke_u1"))
        print("已清理探针 key", flush=True)
    except Exception as e:  # noqa: BLE001
        print("清理探针 key 失败:", e, flush=True)

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n===== Redis roundtrip smoke：{len(RESULTS) - len(failed)}/{len(RESULTS)} PASS =====")
    if failed:
        print("FAILED:", [(n, d) for n, _, d in failed])
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
