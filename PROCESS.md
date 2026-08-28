# PROCESS.md — 项目开发 / 修复 / 实验 / 验收标准流程

> 任务"应该怎么做"。描述流程与纪律，**不**解释"为什么这么设计"（那是 `ARCHITECTURE.md` / `DECISIONS.md` 的职责）。
> 适用项目：RAG 知识库 / Java 程序员智能面试助手（Interview RAG）。

---

## §0 铁序（固定执行顺序）

以下先后顺序是硬约束，任何一步不可跳级：

```text
Task A 先于 Task B
Problem 先于 Code
Evidence 先于 Root Cause
Real evaluation 先于结论
Unit/Integration 先于真实 LLM 调优
```

即：先复现/取证，再下根因；先写清问题与方案，再动代码；先过测试，再用真实 LLM 评估；评估数据出来后，才下"有效/无效"的结论。

---

## §1 主流程（新增功能 / 修复问题 / 实验）

```text
Problem          （明确要解决什么）
→ Evidence       （复现 / 日志 / 测试取证）
→ 分层归因        （见 SERVICES_LAYER 决策所有权：归到真正拥有该决策的层）
→ Spec           （落盘 docs/superpowers/specs/YYYY-MM-DD-<主题>-design.md）
→ Review         （评审通过后进入实现）
→ Implementation
→ Unit           （pytest tests/services tests/storage）
→ Integration
→ 真实 LLM evaluation   （必须真实调用 LLM，不能只靠单测）
→ Evaluation report     （落盘 docs/evaluation/，先报告后结论）
→ Decision       （如需长期决策 → DECISIONS.md 新增 DR；否则到此为止）
→ Commit         （一个行为问题一个独立 commit）
```

### 1.1 Spec 落盘要求（硬性）

- 凡新问题 / 新功能，必须先写 Spec：问题描述、影响模块 / 文件、预期行为、技术方案概要、验收标准、风险与未知点。
- 落盘 `docs/superpowers/specs/`，命名 `YYYY-MM-DD-<主题>-design.md`。
- **禁止**仅停留在对话中不落盘。

### 1.2 验收顺序（不可跳过）

1. `python -m pytest tests/`（services + storage + 规模化回归）须全绿；
2. 涉及真实调用的功能，必须跑一次真实 LLM / 真实 ingest 验证；
3. 通过后输出 Evaluation report，再据此决定是否调整方案 / 固化决策。

---

## §2 问题修复流程（PROBLEM.md 使用要求）

`PROBLEM.md` 是长期复用的事实来源，**开发与 Debug 前必读**。

1. **开发 / Debug 前先读 `PROBLEM.md`**：先看"第 0 节 Critical Do/Don't"与"第 1 节 Problem Index"，确认不踩已记录规则（缓存 key、SSE 会话、reranker 选型、单 worker 等）。
2. **按 Trigger 判断是否读具体记录**：遇到已记录现象（如"流式中切换会话输出中断""缓存总不命中""进程 OMP 崩溃"），用对应记录的 `3. Trigger` / `5. Investigation Path` 定位，再决定是否深入。
3. **解决非 trivial 问题后更新对应 Problem Record**：回到 `PROBLEM.md` 对应 `PXX` 记录追加 / 修订（不清空历史），无法映射则新建记录。
4. **不覆盖历史事实**：不得修改已确认的 Root Cause / Solution / commit / Status；新增证据用追加方式说明。
5. **resolved 问题复现先验证，不盲目重复修复**：再次出现时先检查旧方案是否被回退、环境 / 输入是否变化、是否有新 reproduction，再动手——不得直接照搬旧修复。
6. **禁止编造**：`investigating` 状态如实标注未确认根因；写 `resolved` 必须有证据（提交号 / 测试 / 复现）。

---

## §3 真实 LLM 实验纪律

涉及真实 LLM / 检索 / 评估的实验，必须严守以下变量控制：

1. **变量固定原则**：一次只改一个变量（单一开关 / 单一 prompt 版本 / 单一参数），其余全部冻结。多变量同改无法归因。
2. **fresh 原则**：评估用的测试集必须重新生成（`eval_testset`），不得复用调参期间已看过的集合，否则产生过拟合式假阳性。
3. **唯一变量 A/B**：两组对比除目标变量外，输入集、分块参数、检索参数、LLM 版本、温度等必须一致。
4. **先结果后结论**：真实评估的原始落盘（`docs/evaluation/`）出来之前，不得下"有效 / 无效 / 变差"结论。
5. **不要"边改配置边看效果"跳过测试**：unit / integration 全绿后才允许进入真实 LLM 调优环节。

---

## §4 归因与止损

- **归因到拥有决策的层**：失败先判断属于哪一类（见 SERVICES_LAYER 决策所有权表），归到真正拥有该决策的层，而不是"哪里方便就改哪里"。
- **不同类型故障 ≠**：解析 / 分块失败、索引构建失败、召回失败、重排失败、生成失败、缓存失败、会话 / 流式失败、前端渲染失败——相互独立，分别归因。
- **失败后停止继续修改**：同一问题连续修复两次仍未解决，停止改代码；回到 Problem 阶段重新取证（Regression / environment / input / reproduction），必要时在 `PROBLEM.md` 立项记录后再动手。

---

## §5 何时允许修改核心组件

以下组件属于"核心"，修改前面临更高门槛：

- **prompt / resolver / schema / 管线行为**（查询改写、混合检索、重排、缓存 key、SSE 事件语义）。

修改它们必须同时满足：
1. 有明确 Problem 与 Evidence（已在 Spec 描述）；
2. Unit / Integration 测试先行并通过；
3. 有真实 LLM 评估结果支持（涉及生成 / 检索质量判断时）；
4. 涉及缓存 key / 流式会话 / 重排选型 / 单 worker 的改动，必须遵循 `PROBLEM.md` 对应铁律与 `DECISIONS.md` DR-001~010。

---

## §6 Git / Commit 纪律

- **一个行为问题一个独立 commit**：不要把多个不相关问题塞进一个 commit，便于回滚与归因。
- commit message 遵循仓库现有风格（如 `feat(...)/fix(...)/docs`）。
- 涉及本地重型资源 / 缓存 key / 流式会话等高压线，commit 前自查是否误改（见 `AGENTS.md` 铁律与 `PROBLEM.md` 门禁 Door）。
- 推送前在本地跑一遍受影响测试。

---

## §7 环境准备与常用命令

```bash
# 配置环境变量
cp .env.example .env    # 填入 BAILIAN_API_KEY / SILICONFLOW_API_KEY 等
# 修改 .env / config.py 后需重启进程生效（Settings() 在 import 时一次性读取）

# 安装依赖
pip install -r requirements.txt

# 启动服务（开发，支持热重载）
uvicorn app.main:app --reload

# 运行测试
python -m pytest tests/            # 全部
python -m pytest tests/services/   # 仅服务层

# 构建索引（首次或文档变更后）
curl -X POST http://localhost:8000/api/index/build -H "Content-Type: application/json" -d '{"rebuild": true}'
```

外部服务依赖：Redis（`192.168.127.101:6379`）、百炼 LLM API、硅基流动 Embedding / Rerank API；可选 Grafana / OTel Collector。部署详见 `docs/docker-deploy-notes.md` 与 `ARCHITECTURE.md` §6。