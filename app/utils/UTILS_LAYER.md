# UTILS_LAYER.md — 工具层契约 / 边界（Layer Contract）

> **Layer Contract / Layer Boundary**，不是代码使用说明。回答：这一层负责什么、不能负责什么。
> 适用目录：`app/utils/`。变更纪律（DoD）见 `SERVICES_LAYER.md` 头部，同理适用本契约。

## 1. Responsibility（职责）
- 纯函数 / 无副作用通用工具：文本切分、日志等。
- 可被 api / services / storage 各层安全复用，不承载业务规则。

## 2. Input contract（输入契约）
- 普通数据类型（文本、参数），不接收也从不出领域依赖对象。

## 3. Output contract（输出契约）
- 纯函数返回值；不产生 I/O 副作用（日志工具除外，专司日志）。

## 4. Decision ownership（决策所有权）
- 拥有：切分策略（供 chunker 复用）、日志格式化。
- 不拥有：业务决策、持久化、HTTP。

## 5. Allowed dependencies（允许依赖）
- 仅标准库 / 第三方普通库；`app/config.py` 可选（如需日志级别等配置）。

## 6. Forbidden dependencies（禁止依赖）
- **禁止依赖 `app/api/*`、`app/services/*`、`app/storage/*`**（工具层不得反向依赖业务/存储/接口）。

## 7. Invariants（不变量）
- 保持无状态：不持有全局可变状态、不做缓存、不修改入参。
- 同一输入同一输出（纯函数）。

## 8. Failure ownership（失败归属）
- 工具失败由调用方层负责；工具本身不做业务级降级决策。

## 9. Testing expectations（测试期望）
- 覆盖在所属服务测试中（如 `tests/services/test_chunker.py` 覆盖 `text_splitter`）。

## 10. Typical changes allowed here（允许在此的改动）
- 新增通用纯函数、修正切分边界、调整日志格式。

## 11. Changes that must be implemented elsewhere（必须改在别处的改动）
- 带状态 / 带存储 / 带 I/O 的工具 → 提升为 service 或归入 storage。
- 业务规则相关逻辑 → `app/services/`。