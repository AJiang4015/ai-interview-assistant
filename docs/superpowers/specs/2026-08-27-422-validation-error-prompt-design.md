# 后端 Pydantic 422 校验错误的前端提示缺失（Spec）

> 状态：待确认（风险点 1/2/3 待用户选择后进入实现）
> 日期：2026-08-27

## 1. 问题描述

- 后端注册接口 `POST /api/auth/register` 的请求体由 Pydantic schema `RegisterRequest` 校验（`app/api/schemas.py` L92-L95）：`username` 需 3–32 字符、`password` 需 6–64 字符、`display_name` 最长 64 字符。用户提交不满足约束的数据（如 2 个字符的用户名）时，FastAPI 返回 **422**，响应体形如：

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "username"],
      "msg": "String should have at least 3 characters",
      "ctx": { "min_length": 3 }
    }
  ]
}
```

- 前端 `frontend/js/app.js` 的 `handleAuthSubmit()`（约 L1414-L1417）用 `new Error(err.detail || '请求失败')` 抛出。`detail` 为字符串时正常，但 422 时是**数组**，`Error` 的 message 变成 `[object Object]`，toast 弹出的是无意义文本——用户不知道哪个字段、什么要求。
- 登录/注册模态框（`frontend/index.html` L584-L601）内没有任何表单级错误展示区域，仅靠全局 toast。
- 另外，Pydantic 原生错误消息是英文（"String should have at least 3 characters"），即使能显示，对中文用户也不友好。

## 2. 影响模块 / 文件

| 层 | 文件 | 说明 |
|---|---|---|
| 后端 | `app/api/schemas.py` | 422 的来源（`RegisterRequest` 约束），只读不动 |
| 后端（可选） | `app/main.py` | 若选择后端翻译方案，需注册 `RequestValidationError` 全局异常处理器 |
| 前端 | `frontend/js/app.js` `handleAuthSubmit()`（约 L1379-L1440） | 错误消费逻辑，需解析 422 数组并展示 |
| 前端 | `frontend/index.html` 登录模态框（约 L584-L601） | 需新增表单上方错误容器 |
| 前端 | `frontend/css/style.css` | 错误提示样式 |

不涉及数据库/数据表变更；不涉及新的 API 端点。

## 3. 预期行为（用户视角 + 前后端交互流程）

1. 用户在注册表单输入用户名 `ab`（2 字符）、密码 `123456`，点击「注册」。
2. 前端 POST `/api/auth/register` → 后端 Pydantic 校验失败，返回 422 + `detail` 数组。
3. 前端解析 `detail` 数组，在**模态框表单上方**显示错误信息（含字段名和原因），例如：`用户名长度至少 3 个字符`；同时可辅以 toast。用户名/密码多字段同时违规时，逐条列出。
4. 用户修改后重新提交，旧错误信息清除；成功后正常进入登录态（现有逻辑不变）。
5. 登录接口返回的 400/401（`detail` 为字符串，如「用户名或密码错误」）仍按现有 toast 逻辑展示，不回归。
6. 网络异常时显示「网络错误」类提示（现有行为保留）。

## 4. 技术方案概要

**核心：新增 422 错误解析 + 表单内错误展示，错误消息中文化。**

### 4.1 前端（必做）

1. **新增工具函数 `parseApiError(errJson, fallback)`**（放 `frontend/js/app.js`，供各调用点复用）：
   - `detail` 为字符串 → 直接返回（兼容现有 400/401）；
   - `detail` 为数组（422）→ 逐条取 `loc[1]`（字段名）+ `msg`/`ctx`，映射为中文（字段名映射：`username→用户名`、`password→密码`、`display_name→显示名称`；错误类型映射：`string_too_short→长度至少 N 个字符`、`string_too_long→长度不能超过 N 个字符` 等），返回错误信息列表；
   - 其他 → 返回 fallback（`HTTP {status}`）。
2. **`handleAuthSubmit()` 改造**：
   - 调用 `parseApiError` 得到错误列表；
   - 在模态框表单上方错误容器中渲染（多条时逐行显示），同时保留一条汇总 toast（与现有交互一致）；
   - 提交前/重新打开模态框/输入时清空旧错误。
3. **HTML**：登录模态框内新增 `<div id="auth-error" class="auth-error" style="display:none"></div>`，置于表单顶部（用户名输入框上方）。
4. **CSS**：新增 `.auth-error` 样式（红底/红字、圆角、小字号，与现有蓝紫色系风格协调）。

### 4.2 后端（可选增强，二选一，见风险点）

- **方案 A（纯前端，默认）**：仅做 4.1，中文映射在前端。
- **方案 B（后端兜底翻译）**：在 `app/main.py` 注册全局 `@app.exception_handler(RequestValidationError)`，将 422 的 `detail` 数组翻译为**中文字符串**（如 `"用户名长度至少 3 个字符；密码长度至少 6 个字符"`）。优点：所有 API 的 422（含 interview/deep_dive 的 answer 长度校验）一次性受益、OpenAPI 文档行为一致；前端只需 4.1 的字符串兼容分支即可。缺点：改动面稍大，需补测试。

## 5. 验收标准

- [ ] 注册时输入 2 字符用户名提交 → 表单上方显示含「用户名」字段名和长度要求的中文提示（如「用户名长度至少 3 个字符」），不再出现 `[object Object]` 或英文原文。
- [ ] 注册时输入 5 字符密码提交 → 显示「密码长度至少 6 个字符」。
- [ ] 用户名与密码同时违规 → 两条错误信息都展示（逐行）。
- [ ] `display_name` 超长（>64）→ 显示「显示名称」相关提示（注册模式下）。
- [ ] 错误出现后重新提交或修改输入 → 旧错误信息清除，不残留。
- [ ] 登录失败（401，`detail` 为字符串「用户名或密码错误」）→ 行为与现状一致（toast 展示原文），不回归。
- [ ] 网络错误 / 后端 500 → 显示兜底提示，不抛 JS 异常。
- [ ] 401 token 过期拦截逻辑（app.js 统一 fetch 守卫，`/api/auth/*` 排除）不受影响。
- [ ] 若采用方案 B：`python -m pytest tests/` 全部通过，且新增 422 处理器有对应单测。

## 6. 风险与未知点

1. **待确认：中文映射放前端（方案 A）还是后端（方案 B）？** 推荐 **B**（一次性覆盖全部接口的未来 422 场景），但 A 改动最小。请选择。
2. **待确认：错误展示位置**——本 Spec 按"表单上方错误区 + toast 汇总"设计；是否需要更细粒度的**字段下方**错误提示（每个 input 下红字）？后者实现稍多但体验更好。
3. **待确认：是否需要前端提交前本地预校验**（长度即时检查，避免一次无效请求）？属可选增强，默认不在本 Spec 范围。
4. **范围控制**：`frontend/js/app.js` 中其他消费 `errData.detail` 的位置（流式问答约 L646-L652、文件上传约 L1167、面试出题约 L1715 等）存在同样的数组未处理隐患，**本 Spec 仅处理 auth 表单**，其余是否统一收敛到 `parseApiError` 由用户后续决定。
5. **Pydantic v2 错误类型枚举较多**（`missing`、`string_type` 等），映射表先覆盖注册表单实际可触发的类型，未覆盖类型回退显示原始 `msg`，保证不丢信息。
