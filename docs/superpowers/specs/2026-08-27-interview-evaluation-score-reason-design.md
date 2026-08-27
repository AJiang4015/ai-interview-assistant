# Spec：面试评价展示评分原因与参考答案

## 1. 问题描述

面试流程中，用户提交回答后只能看到 **1-10 的评分**及一段 50-100 字的简短评语，无法看到：

- **评分原因**：为什么得这个分、哪些点答对了、哪些关键点遗漏或答错了；
- **该题的正确回答（参考答案）**：这道题的理想回答应该覆盖什么。

复盘场景同样缺失：面试报告的 `score_breakdown` 每题只有 `round/题目截断80字/score/tags`；历史记录详情页只有总分与等级。用户答完一题后无法针对性改进，复盘价值受限。

## 2. 影响模块/文件

| 文件 | 改动性质 |
|------|----------|
| `app/services/interview_service.py` | 修改 `EVALUATE_PROMPT` 输出结构（新增字段）、`answer()` 解析透传、`_generate_report()` 的 `q_details`/`REPORT_PROMPT` |
| `app/storage/interview_store.py` | **无需改表**（`evaluation` 列为 JSON 文本，天然兼容新增字段） |
| `frontend/index.html` | `evaluation-area` 区块新增“评分原因”“参考答案”展示元素（约 L414-440） |
| `frontend/js/app.js` | `showEvaluation()`（L1931）、报告渲染（L1956 起）增加新字段渲染与判空降级 |
| API 层 | **无新增端点**，复用 `/api/interview/answer` 与 `/api/interview/report/{id}`，仅响应结构扩展 |

不涉及：深挖模式（`deep_dive_service.py` 的 judgment 流程）、RAG 问答主链路。

## 3. 预期行为（用户视角）

1. 用户在面试中提交回答 → 评价区依次展示：**评分 → 评分原因（得分点/失分点拆解）→ 参考答案 → 知识点标签**，之后仍可点“下一题 / 再答一次 / 结束面试”；
2. 点击“再答一次”重新提交后，新评价（含新的原因与参考答案）覆盖旧内容；
3. 面试结束后查看报告、以及在“复习→面试记录”里回看历史报告时，每道题都能看到当时的评分原因与参考答案；
4. 评价生成失败或旧数据缺字段时，对应区块隐藏，不出现空白框、不报错。

## 4. 技术方案概要

**后端（`interview_service.py`）**

- `EVALUATE_PROMPT` 的 JSON 输出新增两个字段：
  - `"score_reason"`：评分依据，按条列出「答对的部分 / 遗漏或错误的部分」，约 100-200 字；
  - `"reference_answer"`：参考答案要点（结构化的标准回答，约 150-300 字）；
  - 现有 `comment` 保留为一句摘要（前端评分旁展示），`tags/next_difficulty/should_end` 不变；
- `answer()` 中 `_parse_json` 失败的 fallback dict 同步补默认空值；
- `_generate_report()`：`q_details`（喂给 `REPORT_PROMPT` 及 `score_breakdown`）新增 `comment/score_reason/reference_answer` 字段，同时把 `question` 截断从 80 字放宽（或报告里携带完整题目），保证报告可独立复盘。

**前端**

- `index.html`：`evaluation-area` 内新增两个区块（复用 `evaluation-comment` 样式风格），参考答案默认**折叠**、点击展开；
- `app.js`：`showEvaluation(evaluation)` 用 `textContent`/`escapeHtml` 渲染新字段并判空；报告渲染函数中 `score_breakdown` 每题条目追加展示；

**存储**

- 无表结构变更；旧记录 `evaluation` JSON 缺新字段 → 前端判空跳过；已生成的历史报告 JSON 不回填（仅新生成报告含新字段）。

## 5. 验收标准

- [ ] 提交回答后，评价区可见：评分、一句话评语、**评分原因**（含得分点/失分点）、**参考答案**（默认折叠，可展开）、知识点标签
- [ ] 点击“再答一次”重新提交后，展示的是**新**评价内容（不残留旧原因/旧答案）
- [ ] 参考答案展开/折叠交互正常，切换题目后重置为折叠态
- [ ] 面试报告 `score_breakdown` 每题展示评分原因与参考答案，题目不再被截断到无法理解
- [ ] “复习→面试记录”打开历史报告，能看到每题的原因与参考答案（仅限新产生的面试数据）
- [ ] 旧数据（`evaluation` 无新字段、旧报告无新字段）下页面正常，无空白区块、无 JS 报错
- [ ] 后端 LLM 返回的 JSON 缺失新字段时，接口不 500，返回空值由前端降级
- [ ] 新增内容全部经 `textContent` 或 `escapeHtml` 注入，无 XSS 风险
- [ ] `python -m pytest tests/` 全部通过；为 prompt 解析新字段补 1-2 个单测（含缺字段容错）

## 6. 风险与未知点

1. **【需确认】参考答案的显示时机**：评价后立即展示参考答案，用户点“再答一次”时可能照抄。方案 A：默认折叠+“查看参考答案”按钮（推荐）；方案 B：直接展示。请选择。
2. **【需确认】报告页范围**：报告 `score_breakdown` 是否也要展示完整的原因/参考答案（会让报告变长），还是仅在答题阶段展示、报告只保留分数与标签？
3. **Token 成本与耗时**：评价 prompt 输出 token 显著增加（约 +200-400 字），单次评价响应时间会变长。是否接受？备选：参考答案改由知识库检索内容裁剪生成，减少 LLM 生成量（但知识库无相关内容时质量下降）。
4. **`comment` 与 `score_reason` 的关系**：按「comment=一句话摘要（评分旁）+ score_reason=详细拆解（正文）」设计，若觉得冗余可合并为一个字段。
5. **深挖模式**（`deep_dive_service.py`，judgment 而非 score）默认不在本 spec 范围，如需一并增强请说明。