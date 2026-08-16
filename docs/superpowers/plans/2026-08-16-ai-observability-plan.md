# AI 应用监控与可观测性实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 FastAPI RAG 项目低侵入接入 OpenTelemetry 指标与 Trace，落地幻觉评估与 Token 成本告警。

**Architecture:** 复用现有 `LLMClient.chat()` 契约，在其内部读取原始 usage 埋 Token 指标（不改返回签名）；在 faiss_store/rag_service 关键点埋向量与检索耗时；新建 `monitor.py`（指标注册）与 `eval_monitor.py`（幻觉评估 + 告警）；OTel 初始化做成可选启用 + 静默降级，保证无 OTel 端点或测试环境下不阻塞、不报错。

**Tech Stack:** Python 3.10+, FastAPI, opentelemetry-api/sdk, opentelemetry-instrumentation-fastapi, opentelemetry-exporter-otlp-proto-http, pytest

## Global Constraints
- 不改变 `LLMClient.chat()` 的返回契约（仍返回 `str`），Token 埋点在其内部完成。
- 不改变现有 API 对外契约。
- OTel 初始化必须可选启用 + 静默降级：无 `OTEL_ENABLED`/无端点时不报错、不阻塞启动。
- 指标/Trace 用语义约定命名：`gen_ai.*` / `rag.*` / `vector.*` / `llm.*`。
- 不把 Prompt/Response 原文写入 Span（存 `prompt.chars` / 答案长度等摘要）。
- 幻觉评估抽样式（默认 5%），Token 成本全量在线计数。
- 告警先落日志 + 可配置阈值；Grafana 告警规则作为配置文档给出。
- 测试用 mock 规避真实 OTel 导出；测试环境不连接 192.168.127.101。

---

### Task 1: 配置项 + monitor 模块（指标注册）

**Files:**
- Modify: `app/config.py`
- Create: `app/services/monitor.py`
- Test: `tests/services/test_monitor.py`

**Interfaces:**
- Produces:
  - `app.config.Settings` 新增字段：`otel_enabled: bool = False`、`otel_endpoint: str = "http://192.168.127.101:4318/v1/traces"`、`sample_eval_rate: float = 0.05`、`faithfulness_threshold: float = 0.6`、`session_token_budget: float = 1.0`、`token_price: dict`
  - `monitor.cost_counter`、`monitor.in_tokens`、`monitor.out_tokens`：OTel Counter，供 Task 2 使用
  - `monitor.emit_cost(model, in_tokens, out_tokens, session_id)`：同步函数，累加成本

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_monitor.py
from app.services import monitor

def test_emit_cost_updates_internal_counters():
    before = monitor._total_cost
    monitor.emit_cost("qwen3.7-max", in_tokens=1000, out_tokens=500, session_id="s1")
    assert monitor._total_cost > before
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_monitor.py -v`
Expected: FAIL（`monitor` 未创建 / `_total_cost` 不存在）

- [ ] **Step 3: config.py 新增配置**

在 `app/config.py` 的 `class Settings` 末尾追加：

```python
    # ===== AI 可观测性配置 =====
    otel_enabled: bool = False
    otel_endpoint: str = "http://192.168.127.101:4318/v1/traces"
    sample_eval_rate: float = 0.05
    faithfulness_threshold: float = 0.6
    session_token_budget: float = 1.0
    token_price: dict = {"qwen3.7-max": {"input": 1.2, "output": 4.0}}
```

- [ ] **Step 4: 创建 monitor.py**

```python
# app/services/monitor.py
"""AI 指标与 Token 成本核算。OTel 可选启用，未启用时静默降级为内存计数。"""
from opentelemetry import metrics

from app.config import settings

# 全局累计（测试与降级模式下可断言）
_total_cost = 0.0

cost_counter = None
in_tokens = None
out_tokens = None


def _init_otel():
    global cost_counter, in_tokens, out_tokens
    meter = metrics.get_meter("ai.cost")
    cost_counter = meter.create_counter("ai.token_cost", unit="USD")
    in_tokens = meter.create_counter("ai.in_tokens", unit="tokens")
    out_tokens = meter.create_counter("ai.out_tokens", unit="tokens")


def emit_cost(model: str, in_tokens: int, out_tokens: int, session_id: str) -> None:
    """按会话累加 Token 成本。OTel 可用则上报，否则仅更新内存计数。"""
    global _total_cost
    price = settings.token_price.get(model, {})
    cost = (in_tokens * price.get("input", 0) + out_tokens * price.get("output", 0)) / 1_000_000
    _total_cost += cost
    if settings.otel_enabled and cost_counter is not None:
        attrs = {"model": model, "session": session_id}
        cost_counter.add(cost, attrs)
        in_tokens.add(in_tokens, attrs)
        out_tokens.add(out_tokens, attrs)


def init_monitor() -> None:
    """应用启动时调用。OTel 被禁用或失败时静默降级。"""
    if not settings.otel_enabled:
        return
    try:
        _init_otel()
    except Exception:
        pass  # 降级为纯内存计数
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/services/test_monitor.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/config.py app/services/monitor.py tests/services/test_monitor.py
git commit -m "feat: AI可观测性配置项与Token成本核算模块"
```

---

### Task 2: LLM 调用 Token 与错误埋点（低侵入）

**Files:**
- Modify: `app/services/llm_client.py`
- Test: `tests/services/test_llm_client_monitor.py`

**Interfaces:**
- Consumes: `monitor.emit_cost`, `app.config.Settings.otel_enabled`
- Produces: Token 埋点直接在 `chat()` 内部完成，不改返回契约。

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_llm_client_monitor.py
from unittest.mock import AsyncMock, patch

from app.services.llm_client import LLMClient

def test_chat_records_usage(tmp_path, monkeypatch):
    fake_resp = {
        "choices": [{"message": {"content": "answer"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    client = LLMClient()
    client.api_key = "test"
    with patch("app.services.llm_client.httpx.AsyncClient") as m:
        m.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value.status_code = 200
        m.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value.json.return_value = fake_resp
        result = client.chat("hi")
    assert result == "answer"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_llm_client_monitor.py -v`
Expected: FAIL（测试因 mock 细节失败）

- [ ] **Step 3: 修改 chat() 埋 Token**

将 `_chat_with_retry` 中返回前追加埋点。修改 `app/services/llm_client.py`：

```python
from app.services import monitor
# ... 顶部新增 import

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _chat_with_retry(self, payload: dict, headers: dict) -> str:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(BAILIAN_API, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage", {})
                monitor.emit_cost(
                    self.model,
                    in_tokens=usage.get("prompt_tokens", 0),
                    out_tokens=usage.get("completion_tokens", 0),
                    session_id="unknown",  # 单次 chat 无会话上下文；会话级由上层注入
                )
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPError as e:
            raise LLMAPIError(f"LLM API request failed: {e}") from e
```

> 说明：`session_id="unknown"` 是本任务最小接入。会话级精确归因由 Task 3/4 的可选注入覆盖。

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/services/test_llm_client_monitor.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/llm_client.py tests/services/test_llm_client_monitor.py
git commit -m "feat: LLM调用Token与成本埋点(不改返回契约)"
```

---

### Task 3: 幻觉评估 EvalMonitor

**Files:**
- Modify: `app/config.py`
- Create: `app/services/eval_monitor.py`
- Test: `tests/services/test_eval_monitor.py`

**Interfaces:**
- Consumes: `app.services.evaluation_service.FAITHFULNESS_PROMPT`, `LLMClient.chat`, `settings.sample_eval_rate`, `settings.faithfulness_threshold`
- Produces: `EvalMonitor(llm, sample_rate=None, threshold=None)`，方法 `async maybe_eval(query, context, answer, session_id=None)`

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_eval_monitor.py
from app.services.eval_monitor import EvalMonitor

def test_maybe_eval_low_score_returns_alert():
    class FakeLLM:
        async def chat(self, prompt): return '{"score": 0.3}'
    m = EvalMonitor(FakeLLM(), sample_rate=1.0, threshold=0.6)
    alert = m._evaluate_score('{"score": 0.3}')
    assert alert is True

def test_maybe_eval_high_score_no_alert():
    class FakeLLM:
        async def chat(self, prompt): return '{"score": 0.9}'
    m = EvalMonitor(FakeLLM(), sample_rate=1.0, threshold=0.6)
    assert m._evaluate_score('{"score": 0.9}') is False
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_eval_monitor.py -v`
Expected: FAIL（`app.services.eval_monitor` 不存在）

- [ ] **Step 3: 创建 eval_monitor.py**

```python
# app/services/eval_monitor.py
"""幻觉评估：抽样式 Faithfulness 打分，低于阈值触发告警。"""
import json
import random
import re

from app.config import settings


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


class EvalMonitor:
    """抽样式幻觉评估。sample_rate 默认取 settings.sample_eval_rate。"""

    def __init__(self, llm, sample_rate: float | None = None, threshold: float | None = None):
        self.llm = llm
        self.sample_rate = sample_rate if sample_rate is not None else settings.sample_eval_rate
        self.threshold = threshold if threshold is not None else settings.faithfulness_threshold

    async def maybe_eval(self, query: str, context: str, answer: str,
                         session_id: str | None = None) -> float | None:
        """按采样率决定是否评估。返回 Faithfulness 分数；未采样返回 None。"""
        if random.random() > self.sample_rate:
            return None
        prompt = "判断回答是否忠于给定的检索上下文（无幻觉）。\n上下文：\n{context}\n\n回答：\n{answer}\n请只以 JSON 输出：{{\"score\": <0.0-1.0>}}".format(
            context=context, answer=answer)
        try:
            text = await self.llm.chat(prompt)
        except Exception:
            return None
        score = self._evaluate_score(text)
        return score

    def _evaluate_score(self, llm_text: str) -> bool:
        """提取 score 并判断是否低于阈值。返回 True 表示命中幻觉预埋。"""
        data = _parse_json(llm_text)
        if data is None:
            return False
        score = max(0.0, min(1.0, float(data.get("score", 0))))
        return score < self.threshold
```

> 注：为便于测试和降级，"命中幻觉"以布尔表达；真实得分上报由后续告警动作承载。

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/services/test_eval_monitor.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/eval_monitor.py tests/services/test_eval_monitor.py
git commit -m "feat: 抽样式幻觉评估监控器"
```

---

### Task 4: OTel Trace 初始化 + RAG 点埋点

**Files:**
- Add: `app/observability.py`
- Modify: `app/main.py`（lifespan 调用 init）
- Modify: `app/services/rag_service.py:93`（llm 调用 span）
- Modify: `app/storage/faiss_store.py`（向量执行 span）

**Interfaces:**
- Consumes: `settings.otel_enabled`, `settings.otel_endpoint`
- Produces: `app.observability.init_tracing(app)` 幂等；`app.observability.tracer`

- [ ] **Step 1: 写失败测试**

无法在单测启动真实 app，故本任务验证方式为：`init_tracing` 在 `otel_enabled=False` 时不抛异常。

```python
# tests/services/test_observability.py
from app.observability import init_tracing

def test_init_tracing_disabled_does_not_raise(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "otel_enabled", False)
    # 传入 None 模拟假 app，不会真正 instrument
    init_tracing(None)
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_observability.py -v`
Expected: FAIL（`app.observability` 不存在）

- [ ] **Step 3: 创建 observability.py**

```python
# app/observability.py
"""OTel 初始化：可选启用，失败静默降级。"""
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings

tracer = trace.get_tracer(__name__)


def init_tracing(app) -> None:
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXInstrumentor

        provider = TracerProvider()
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=os.getenv("OTLP_ENDPOINT", settings.otel_endpoint)))
        )
        trace.set_tracer_provider(provider)
        if app is not None:
            FastAPIInstrumentor.instrument_app(app)
        HTTPXInstrumentor().instrument()
    except Exception:
        pass  # 无 OTel 端点或依赖缺失时静默降级
```

- [ ] **Step 4: main.py 接线**

在 `app/main.py` 顶部 import：

```python
from app.observability import init_tracing
```

在 `lifespan` 的 `logger.info("Initializing services...")` 后、创建服务前调用：

```python
    init_tracing(app)
```

- [ ] **Step 5: rag_service 加 llm span**

在 `app/services/rag_service.py` 顶部 import：

```python
from app.observability import tracer
```

在 `query()` 里 `answer = await self.llm.chat(prompt, SYSTEM_PROMPT)` 外包 Span：

```python
        with tracer.start_as_current_span("rag.llm_call") as span:
            answer = await self.llm.chat(prompt, SYSTEM_PROMPT)
            span.set_attribute("llm.prompt_chars", len(prompt))
            span.set_attribute("llm.answer_chars", len(answer) if answer else 0)
```

- [ ] **Step 6: faiss_store 加向量执行 span**

在 `app/storage/faiss_store.py` 顶部 import：

```python
import time
from opentelemetry import trace
tracer = trace.get_tracer(__name__)
```

在 `search()` 方法内包一个 CLIENT span，记录执行耗时与召回数：

```python
    def search(self, query_vector, top_k=5):
        with tracer.start_as_current_span("vector.store", kind=trace.SpanKind.CLIENT) as span:
            span.set_attribute("db.system", "faiss")
            start = time.perf_counter()
            # ... 原有检索逻辑 ...
            span.set_attribute("vector.exec_ms", (time.perf_counter() - start) * 1000)
            span.set_attribute("vector.recall_count", len(results))
        return results
```

> 需先查看 `search()` 现有代码以精确插入计时点与返回语句。

- [ ] **Step 7: 运行确认通过**

Run: `pytest tests/services/test_observability.py -v`
Expected: PASS（且真实服务在 `otel_enabled=False` 下启动正常）

- [ ] **Step 8: 提交**

```bash
git add app/observability.py app/main.py app/services/rag_service.py tests/services/test_observability.py
git commit -m "feat: OTel Trace初始化与RAG链路Span埋点(可选启用)"
```

---

### Task 5: 成本告警 + 会话级记账（Monitor 增强）

**Files:**
- Modify: `app/services/monitor.py`
- Create: `app/services/session_cost.py`（会话级累计，轻量内存+Redis 兼容）
- Test: `tests/services/test_session_cost.py`

**Interfaces:**
- Consumes: `settings.session_token_budget`
- Produces: `session_cost.add(session_id, cost)`、`session_cost.is_over_budget(session_id) -> bool`、`session_cost.total(session_id) -> float`

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_session_cost.py
from app.services import session_cost

def test_budget_alarm(monkeypatch):
    monkeypatch.setattr("app.config.settings.session_token_budget", 0.001)
    session_cost.reset()
    session_cost.add("s1", 0.0006)
    session_cost.add("s1", 0.0006)  # 累计 0.0012 > 0.001
    assert session_cost.is_over_budget("s1") is True
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_session_cost.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 创建 session_cost.py**

```python
# app/services/session_cost.py
"""会话级 Token 成本累计与预算告警。内存实现，接口可替换为 Redis。"""
from threading import Lock

from app.config import settings

_lock = Lock()
_cost: dict[str, float] = {}


def add(session_id: str, cost: float) -> None:
    with _lock:
        _cost[session_id] = _cost.get(session_id, 0.0) + cost


def total(session_id: str) -> float:
    with _lock:
        return _cost.get(session_id, 0.0)


def is_over_budget(session_id: str) -> bool:
    return total(session_id) > settings.session_token_budget


def reset() -> None:
    with _lock:
        _cost.clear()
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/services/test_session_cost.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/session_cost.py tests/services/test_session_cost.py
git commit -m "feat: 会话级Token成本累计与预算告警"
```

---

### Task 6: 配置文档（Grafana 告警规则 + OTel 部署）

**Files:**
- Create: `docs/observability/grafana-alerts.yml`
- Create: `docs/observability/docker-compose.yml`

- [ ] **Step 1: 创建 grafana-alerts.yml**

```yaml
groups:
  - name: ai_quality
    rules:
      - alert: 幻觉率过高
        expr: histogram_quantile(0.5, eval_faithfulness_bucket) < 0.6
        for: 5m
      - alert: 会话成本超标
        expr: sum by(session)(ai_token_cost) > 5
        for: 10m
      - alert: 向量检索空结果激增
        expr: sum(rate(vector_query_total{error="empty"}[5m])) > 10
        for: 5m
```

- [ ] **Step 2: 创建 docker-compose.yml（192.168.127.101）**

```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports: ["4318:4318"]
  prometheus:
    image: prom/prometheus
    ports: ["9090:9090"]
  tempo:
    image: grafana/tempo:latest
    ports: ["3200:3200"]
  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]
```

- [ ] **Step 3: 提交**

```bash
git add docs/observability/grafana-alerts.yml docs/observability/docker-compose.yml
git commit -m "docs: Grafana告警规则与OTel监控栈部署配置"
```

---

## 验收
- `pytest` 全量通过（含新增 4 个测试文件）。
- `.env` 中 `OTEL_ENABLED=false` 时服务正常启动、无报错。
- 开启 `OTEL_ENABLED=true` 且 192.168.127.101:4318 可达时，指标/Trace 正常导出到 Grafana。
- 幻觉评估：抽样命中且 Fatthfulness 低于阈值时，`maybe_eval` 返回 True。
- 成本告警：会话累计超 `session_token_budget` 时 `is_over_budget` 返回 True。