# AI 应用监控与可观测性方案设计（LLM + RAG）

> 日期：2026-08-16
> 落地范围：本项目（Python + FastAPI 的 RAG 智能客服/面试助手）

## 1. 背景与目标

系统上线后出现三类问题：偶发响应超时、Token 成本超标、回答质量下降（幻觉）。
传统 APM（Redis/Prometheus 监控 HTTP 延迟与错误率）无法深入 AI 特有链路，故设计本方案。

**核心目标：**
- 在传统 RED 之外，补充 LLM 与 RAG 链路特有指标。
- 低侵入地在 FastAPI 中用 OpenTelemetry 实现全链路 Trace 埋点。
- 针对"幻觉"与"Token 成本超标"设计自动化评估与告警。

**落地原则：** 指标与 Trace 用 OpenTelemetry SDK 采集并导出到 192.168.127.101 监控栈；
幻觉评估做抽样式离线，Token 成本全量在线计数；告警分内置即时 + Grafana Alerting 两层。

---

## 2. 总体架构

```
FastAPI 应用 (本项目)
   │
   ├─ OTel SDK (opentelemetry-python)
   │    ├─ Metrics: 计数 / 直方图（Token、耗时、评估分）
   │    └─ Trace:   一次问答 = 1 root span → 子 span（检索/重排/向量库/LLM）
   │         │
   │         └─ OTLP 导出 ──► 192.168.127.101:4318 (OpenTelemetry Collector)
   │                              │
   │                 ┌────────────┴────────────┐
   │         Prometheus(指标)       Tempo(Trace) / Loki(日志)
   │                              │
   │                            Grafana 面板
   │
   └─ 应用内评估与告警（代码）
        ├─ EvalMonitor：幻觉(Faithfulness)抽样式评估 + 运行时告警
        └─ Monitor：Token 全量在线成本核算 → 成本超标告警
```

**技术选型（Python 侧）：**

| 类别 | 技术 | 说明 |
|---|---|---|
| 指标/Trace SDK | `opentelemetry-api/sdk` | 阿里：OTel 协议与 Spring 题设一致 |
| HTTP 入口自动埋点 | `opentelemetry-instrumentation-fastapi` | 自动生成 root span |
| 出站调用自动埋点 | `opentelemetry-instrumentation-httpx` | 自动捕获 LLM/向量库 HTTP 调用 |
| 导出 | `opentelemetry-exporter-otlp-proto-http` | 走 4318 到 Collector |
| 展示栈 | Prometheus + Tempo + Grafana | 部署于 192.168.127.101 |

---

## 3. 功能一：LLM + RAG 特有指标设计

在传统 RED（Rate/Errors/Duration）之上，新增三大类。

### 3.1 LLM 调用指标

| 指标 | 类型 | 用途/告警 |
|---|---|---|
| `llm_in_tokens` / `llm_out_tokens` | Counter | Token 消耗总量 |
| `llm_token_cost` | Counter(USD) | token × 单价，成本核算 |
| `llm_ttft_ms` | Histogram | 首字延迟，用户可感速度 |
| `llm_token_throughput` | Histogram(tokens/s) | 生成效率 |
| `llm_error_total` | Counter(by status) | 超时/限流/4xx/5xx 拆分 |
| `llm_prompt_char_len` | Histogram | 上下文膨胀监控 |

### 3.2 RAG 链路指标（含向量库）

| 指标 | 类型 | 用途 |
|---|---|---|
| `vector_query_duration_ms` | Histogram | 向量查询链路全程 |
| `vector_exec_duration_ms` | Histogram | 仅向量库**检索执行**耗时 |
| `vector_queue_wait_ms` | Histogram | 高并发排队等待时长 |
| `vector_query_total` | Counter(含 error 维度) | 向量查询次数 |
| `vector_recall_count` | Histogram | 每次召回 chunk 数 |
| `rag_retrieve_duration_ms` | Histogram | 检索全链路耗时 |
| `rag_empty_result_total` | Counter | 0 chunk 占比（幻觉前兆） |
| `rag_cache_hit_total` | Counter(hit/miss) | 检索缓存命中率 |

### 3.3 质量与成本治理指标

| 指标 | 类型 | 用途 |
|---|---|---|
| `eval_faithfulness_score` | Gauge | 回答忠于检索上下文（幻觉） |
| `eval_answer_relevance` | Gauge | 回答相关性 |
| `eval_context_relevance` | Gauge | 检索上下文相关性 |
| `cost_per_session_total` | Gauge | 会话级累计成本 |
| `cost_per_request_avg` | Gauge | 单位请求成本环比 |

**设计要点：**
- TTFT 与检索耗时拆开 —— 分得清"慢在检索还是生成"。
- 空结果率是第一信号 —— 检索无召回 → 模型只能"编"，作为低成本前置告警。
- 向量库执行/排队/查询三段拆分 —— 定位瓶颈在哪一段。
- Token 成本分"请求"与"会话"两个粒度 —— 请求抓单次异常，会话抓累计超标。

---

## 4. 功能二：OpenTelemetry 全链路 Trace 埋点

**低侵入**：自动埋点为主 + 少量手动 Span，不改散业务代码。

### 4.1 初始化（`app/main.py` lifespan）
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXInstrumentor

OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://192.168.127.101:4318/v1/traces")

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT)))
trace.set_tracer_provider(provider)

FastAPIInstrumentor.instrument_app(app)   # HTTP 入口自动 root span
HTTPXInstrumentor().instrument()          # 自动捕获所有 httpx 出站调用
```

### 4.2 Span 结构（一次问答）
```
POST /api/{query}      root span (SERVER)
 ├── rag.rewrite       INTERNAL  查询改写
 ├── rag.retrieve      INTERNAL  混合检索
 │    └── vector.store CLIENT    向量库查询(FAISS)
 ├── rag.rerank        INTERNAL  重排序
 └── rag.llm_call      CLIENT    LLM 调用
```
- 向量库 Span 承载 `vector.exec_ms` / `vector.queue_ms` / `vector.recall_count`。
- LLM Span 承载 `llm.in_tokens` / `llm.out_tokens` / `llm.total_tokens`（从 usage 读取）。

### 4.3 关键属性语义
统一用 `gen_ai.*` / `rag.*` / `vector.*` 约定命名，Grafana 面板无需自定义解析。
**不把 Prompt/Response 原文写入 Span**（过长 + 敏感）——存 `prompt.chars`、答案长度等摘要；原文走日志/审计。

### 4.4 题设（Spring）→ 本项目（Python）映射

| Java/Spring 题设 | FastAPI/Python 落地 |
|---|---|
| AOP `@Around` | `tracer.start_as_current_span` 上下文管理器 |
| HandlerInterceptor | `@app.middleware("http")` 中间件 |
| Micrometer + OTel javaagent | OTel Python SDK + Instrumentation |
| 手动 Span 织入 Service | 关键点手动 `start_as_current_span` |

---

## 5. 功能三：幻觉评估 + Token 成本告警

### 5.1 触发策略

| 评估项 | 触发方式 | 理由 |
|---|---|---|
| 幻觉质量评估 | 抽样式（5%~10%）+ 离线 | 全量 LLM 判断翻倍成本 |
| Token 成本 | 全量在线计数 | 纯计数零额外成本 |

### 5.2 幻觉评估（Faithfulness）—— `app/services/eval_monitor.py`
```python
import random
from app.services.evaluation_service import FAITHFULNESS_PROMPT

class EvalMonitor:
    def __init__(self, llm, sample_rate=0.05, faithfulness_threshold=0.6):
        self.llm, self.sample_rate, self.threshold = llm, sample_rate, faithfulness_threshold

    async def maybe_eval(self, query, context, answer):
        if random.random() > self.sample_rate:
            return
        score = await self._judge(FAITHFULNESS_PROMPT.format(context=context, answer=answer))
        self._emit_gauge("eval.faithfulness", score)
        if score < self.threshold:
            await self._fire_alert("hallucination", query, score)
```
- 前置检测：检索空结果 → 直接高幻觉风险告警。
- 结合 `context_relevance` 区分"答非所问"与"胡编乱造"。

### 5.3 Token 成本核算 —— `app/services/monitor.py`
```python
from opentelemetry import metrics
TOKEN_PRICE = {"qwen3.7-max": {"input": 1.2, "output": 4.0}}  # $/1M tokens

async def record_tokens(model, usage, session_id):
    price = TOKEN_PRICE.get(model, {})
    cost = usage["in"]*price.get("input",0)/1e6 + usage["out"]*price.get("output",0)/1e6
    cost_counter.add(cost, {"model": model, "session": session_id})
```

### 5.4 告警两层
**内置即时（代码内）**：单条 Faithfulness 低于阈值、会话累计超预算 → 日志 + Webhook。
**Grafana Alerting（周期批量）**：
```yaml
- alert: 幻觉率过高
  expr: histogram_quantile(0.5, eval_faithfulness_bucket) < 0.6
  for: 5m
- alert: 会话成本超标
  expr: sum by(session)(ai_token_cost) > 5USD
  for: 10m
- alert: 向量检索空结果激增
  expr: sum(rate(vector_query_total{error="empty"}[5m])) > 10
```

### 5.5 复盘闭环
周粒度报告：横轴按模型/策略对比 Faithfulness 与单请求成本，辅助判断降级模型/收紧采样/扩容向量池。

---

## 6. 部署（192.168.127.101 监控栈）

采用 Docker Compose 部署最小栈（需在该主机上执行）：
```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports: ["4318:4318"]
  prometheus:
    image: prom/prometheus
    ports: ["9090:9090"]
  tempo:                      # Trace 存储
    image: grafana/tempo:latest
    ports: ["3200:3200"]
  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]
```
OTel Collector 接收 `4318`（OTLP HTTP），把 metrics 转发给 Prometheus、traces 给 Tempo。

---

## 7. 明确不在本期范围
- 不引入新的 LLM 提供商（复用现有 QQ 百炼/Bailian 与硅基 embedding）。
- 不改变现有 API 对外契约。
- 不做自动重试/熔断（仅监控，不干预业务流程）。

## 8. 验收
- 指标：`/api/health` 正常，Grafana 能看到上述指标与告警。
- Trace：一次问答在 Grafana/Tempo 呈现完整 Span 瀑布。
- 幻觉告警：人为制造空检索或低相关性回答，能触发告警。
- 成本告警：设置低预算阈值，高 Token 请求能触发告警。