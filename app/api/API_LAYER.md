# API_LAYER.md — API 层契约 / 边界（Layer Contract）

> **Layer Contract / Layer Boundary**，不是代码使用说明。回答：这一层负责什么、不能负责什么。
> 适用目录：`app/api/`。变更纪律（DoD）见 `SERVICES_LAYER.md` 头部，同理适用本契约。

## 1. Responsibility（职责）
- HTTP 出入口：路由定义、请求校验、响应序列化。
- 鉴权与用户隔离入口：`get_current_user` 解析 JWT → `username`，注入各端点。
- 统一异常 → HTTP 状态码映射（`app/exceptions.py`）。
- SSE 协议的**端点层**实现（会话/检索/token/done/error 事件的发送），事件内容由服务层编排产生。

## 2. Input contract（输入契约）
- 请求体经 Pydantic schema（`schemas.py` 或路由模块顶部）校验；非法请求返回 4xx。
- 鉴权端点依赖 `Depends(get_current_user)` 取得 `username`（JWT sub）。
- 文件上传限 md/pdf/docx、大小上限 50MB，`~$` 临时文件过滤。

## 3. Output contract（输出契约）
- JSON 响应 / SSE 事件流，结构稳定可被前端消费。
- 错误使用统一异常映射：认证 401 / 越权 404 / 参数 4xx / 5xx。

## 4. Decision ownership（决策所有权）
- 拥有：路由、schema、鉴权、错误映射、SSE 事件发送时序。
- 不拥有：RAG 业务决策、检索/重排/生成策略、存储写读细节。

## 5. Allowed dependencies（允许依赖）
- `app/services/*`（调用编排）、`app/config.py`、`app/exceptions.py`、`schemas.py`。

## 6. Forbidden dependencies（禁止依赖）
- **禁止 import `app/storage/*`**（持久化不在 API 层直接操作）。
- 禁止在端点内放业务 / 检索 / 生成逻辑。

## 7. Invariants（不变量）
- 所有会话/文件/搜索端点**必须按 `username` 隔离**，跨用户访问返回 404（DR-010）。
- 越权统一 404（不暴露资源存在性），不建议 403。
- SSE 事件中不得修改会话归属；流绑定发起时会话 ID。
- 文件删除后必须触发索引重建。

## 8. Failure ownership（失败归属）
- 捕获业务异常映射状态码；未捕获异常由 FastAPI 兜底为 500 并记录日志。
- 不吞掉降级信息——向前端暴露可用的降级提示。

## 9. Testing expectations（测试期望）
- 端点行为用例覆盖：鉴权、越权 404、参数校验、SSE 事件序列、文件类型/大小边界。

## 10. Typical changes allowed here（允许在此的改动）
- 新增 / 调整端点、request/response schema、鉴权依赖接线、错误码映射。

## 11. Changes that must be implemented elsewhere（必须改在别处的改动）
- 业务编排 / 检索 / 生成逻辑 → `app/services/`。
- 存储 schema 或连接 → `app/storage/`。
- 全局异常类型 → `app/exceptions.py`。