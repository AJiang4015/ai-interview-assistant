# 本地功能验收记录（RAG 问答 / 认证 / SSE 链路）

> 日期：2026-08-29
> 状态：**通过（本机功能验收）**
> 验收方式：本机 FastAPI（`uvicorn app.main:app --host 127.0.0.1 --port 8765`）+ 虚拟机 Redis（`192.168.127.101:6379`，密码） + 本机真实 API Key。
> 范围说明：**Docker compose 一键部署验收归后续轮次**，本文件只记录 RAG 功能链路验收。

---

## 一、验收目标与结果对照

| # | 目标 | 结果 | 证据 |
|---|------|------|------|
| 1 | 服务启动成功 | ✅ | lifespan 完成 `Application startup complete`，监听 127.0.0.1:8765 |
| 2 | health 检查通过 | ✅ | `status=ok; faiss_index=loaded; embedding=available; llm=available; redis=available` |
| 3 | Redis 连接正常 | ✅ | `session_store/user_store Connected to Redis at 192.168.127.101:6379` |
| 4 | 真实 RAG 问答 | ✅ | `POST /api/query` 返回 answer（994 字符）+ sources=5 |
| 5 | SSE 完整事件链 | ✅ | `session → retrieval → token(×106) → done` |
| 6 | 记录验收结果 | ✅ | 本文件 |

## 二、关键链路明细

### 认证（注册/登录/鉴权）
- `POST /api/auth/register` → 200，返回 JWT（token_len≈153）
- `POST /api/auth/login` → 200，返回 JWT
- `GET /api/auth/me`（Bearer token）→ 200，返回当前用户
- 结论：**注册/登录/JWT 鉴权链路正常**。

### 真实 RAG 问答（非流式）
- `POST /api/query`（`question`：HashMap 原理与 HashTable 区别）
- 响应：`answer`（长度 994）+ `sources`（5 条，含来源文件 / score / chunk 上下文）
- 检索：加载既有索引 **558 个向量**，稀疏后端 `sqlite_fts`，BM25 就绪。
- 结论：**检索 + 重排提示上下文 + 真实 LLM 生成端到端正常，命中知识库多文档来源**。

### SSE 流式（核心事件链）
- `POST /api/query/stream`，事件序列即 `session > retrieval > token… > done`
- `session`：返回 `session_id`
- `retrieval`：携带 `sources` 数组（file + chunk_index + score）与 `chunks` 上下文
- `token`：累计 106 条增量内容
- `done`：正常收尾（`event: done`）
- 结论：**SSE 事件类型与顺序完全符合 DR-005 约定**（session/retrieval/token/done），前端流式渲染所需的事件结构正确。

## 三、过程中发现并处置的环境问题（非业务代码缺陷）

1. **Redis 连接（lifespan 启动挂起根因）**
   - 现象：本机裸跑 `uvicorn` 卡在 `Initializing services...` 不进监听。
   - 根因：虚拟机 Redis 设置了密码（`12345678`），而 `app/config.py` 的 `redis_password` 默认空 → 连接 AUTH 失败被阻塞。
   - 处置：启动时以环境变量 `REDIS_PASSWORD=12345678` 注入，lifespan 立即完成。**属运行配置缺失，非代码 bug**；`config.py` 默认空密码在有密码 Redis 环境需显式配置。

2. **bcrypt / passlib 版本不兼容（认证失效）**
   - 现象：`register` 返回 400，detail 为误导性的 `password cannot be longer than 72 bytes`。
   - 根因：本机 pip 环境漂移到 **bcrypt 5.0.0**，与 `requirements.txt` 锁定的 **bcrypt==3.2.2** 不兼容（passlib 1.7.4 读取 `bcrypt.__about__.__version__` 失败）。
   - 处置：本机重装 `bcrypt==3.2.2`（与锁定版一致），认证恢复正常。
   - 提示：部署/复用环境应严格按 `requirements.txt` 安装，避免 bcrypt 5.x 漂移导致认证失效。

## 四、未做 / 待后续

- **Docker compose 一键部署验收**（`docker-compose.yml`）→ 归下一轮。
- 本次使用既有索引（558 vectors），未重新跑 `POST /api/index/build`；如需验证全新建库可后续进行。
- 尚未跑真实 LLM 的分阶段 SSE 中途断开/多会话切换场景（前端时序），本文件只覆盖服务端事件链。

## 五、结论

本机 **RAG 问答 + 认证 + SSE 事件链全链路功能验收通过**。服务可正常装配、检索、真实生成与流式推送；认证可用（修复本机 bcrypt 版本漂移后）。此结果为「可交付版本」在功能层提供依据；Docker 部署形态与生产环境验证列入下一步。