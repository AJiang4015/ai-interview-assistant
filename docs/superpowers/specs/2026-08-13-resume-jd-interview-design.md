# 简历+JD → 自动生成面试 — 设计文档

## 1. 概述

在现有 AI 面试系统基础上，增加「简历上传 + JD 输入」的可选环节，实现从简历解析、JD 匹配到个性化面试题生成的端到端流程。

### 目标

- 用户上传简历（PDF）后，系统自动解析结构化信息
- 用户粘贴招聘 JD 后，系统自动提取岗位要求
- 系统自动做简历与 JD 的匹配分析（技能缺口、项目匹配度等）
- 将匹配分析结果注入面试出题 Prompt，生成针对性的面试题
- 保持与现有面试流程完全兼容（无简历/JD 时走原有流程）

## 2. 架构

```
面试准备页（新增简历上传+JD输入）
  ↓
POST /api/interview/start
  { position, resume_file(可选), jd_text(可选) }
  ↓
后端处理：
  1. 创建 session（写入 SQLite）
  2. 如有简历 → pypdf 提取文本 → LLM 结构化解析
  3. 如有 JD → LLM 结构化解析
  4. 如有两者 → LLM 做匹配分析
  5. 分析结果存入 interview_sessions 表
  6. 生成第一道题（分析结果注入 Prompt）
  ↓
前端：走现有面试流程（出题→回答→评价→下一题→报告）
```

## 3. 数据库扩展

### interview_sessions 表新增字段

| 字段名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| resume_text | TEXT | '' | 简历原始文本（PDF 提取后） |
| resume_analysis | TEXT | '{}' | LLM 解析后的结构化简历（JSON） |
| jd_text | TEXT | '' | JD 原始文本 |
| jd_analysis | TEXT | '{}' | LLM 解析后的结构化 JD（JSON） |
| match_analysis | TEXT | '{}' | 匹配分析结果（JSON） |

### 兼容性

现有数据行这些字段值为空，不影响原有流程。`create_session()` 方法新增可选参数。

## 4. 服务层

### app/services/resume_parser.py（新建）

```python
class ResumeParser:
    """简历/JD 解析与匹配分析服务"""

    async def extract_pdf_text(self, file_path: str) -> str
        # 使用 pypdf 提取 PDF 文本内容

    async def parse_resume(self, text: str) -> dict
        # LLM 提取结构化简历信息
        # 返回: { skills, projects, experience, education, ... }

    async def parse_jd(self, text: str) -> dict
        # LLM 提取结构化 JD 需求
        # 返回: { required_skills, preferred_skills, responsibilities, experience_required, ... }

    async def analyze_match(self, resume: dict, jd: dict) -> dict
        # LLM 做匹配分析
        # 返回: { matched_skills, missing_skills, project_match, risk_areas, strong_areas, ... }
```

### app/services/interview_service.py（修改）

`start()` 方法新增 `resume_file` 和 `jd_text` 可选参数：

```python
async def start(self, position: str,
                resume_file: Optional[UploadFile] = None,
                jd_text: Optional[str] = None) -> dict:
    # 1. 创建 session
    session = self.store.create_session(position)

    # 2. 如有简历，解析并存储
    resume_analysis = {}
    jd_analysis = {}
    match_analysis = {}
    if resume_file:
        text = await resume_parser.extract_pdf_text(resume_file)
        resume_analysis = await resume_parser.parse_resume(text)
        self.store.update_resume_analysis(session_id, text, resume_analysis)
    if jd_text:
        jd_analysis = await resume_parser.parse_jd(jd_text)
        self.store.update_jd_analysis(session_id, jd_text, jd_analysis)
    if resume_analysis and jd_analysis:
        match_analysis = await resume_parser.analyze_match(resume_analysis, jd_analysis)
        self.store.update_match_analysis(session_id, match_analysis)

    # 3. 生成第一道题（带个性化上下文）
    question_data = await self._generate_question(
        session["id"], position, round_num=1,
        match_analysis=match_analysis
    )
    return {"session_id": session["id"], "question": question_data}
```

### Prompt 注入

在 `QUESTION_PROMPT` 模板中增加条件插入块：

```
{personalized_context}

【简历与JD匹配分析】
岗位要求：{jd_summary}
你的简历匹配度：{match_summary}
技能缺口：{missing_skills}
项目经验匹配：{project_match}
高风险追问方向：{risk_areas}

请基于以上信息，针对候选人的简历短板和岗位核心要求出题。
```

无简历/JD 时 `personalized_context` 为空字符串，走原有流程。

## 5. API 层

### POST /api/interview/start

将现有 JSON Body 接口改为 `multipart/form-data`：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| position | str | 是 | 岗位方向 |
| resume_file | UploadFile | 否 | PDF 简历文件 |
| jd_text | str | 否 | 招聘 JD 文本 |

返回格式不变，与现有接口一致。

## 6. 前端 UI

### 面试准备页（#interview-ready）改动

在现有「选择岗位」下方新增「简历与岗位匹配（可选）」区域：

```
┌─────────────────────────────────────────────────┐
│                 🎯 AI 模拟面试                     │
│                                                   │
│  选择岗位  [Java后端] [AI应用开发]                  │
│                                                   │
│  ─── 简历与岗位匹配（可选） ───                    │
│  上传简历： [📄 选择文件]  简历.pdf ✓              │
│                                                   │
│  招聘JD：  ┌─────────────────────────────────┐    │
│            │ 粘贴招聘JD内容...                  │    │
│            └─────────────────────────────────┘    │
│                                                   │
│  [▶ 开始面试]                                     │
└─────────────────────────────────────────────────┘
```

- 上传简历支持拖拽 + 点击选择，仅接受 .pdf 格式
- 上传后显示文件名，支持删除重新上传
- JD 输入框为多行文本域
- 开始面试逻辑：仅选岗位 → 原有流程；选岗位+传简历+贴JD → 个性化流程

## 7. 文件清单

### 新增文件
- `app/services/resume_parser.py` — 简历/JD 解析与匹配分析

### 修改文件
- `app/storage/interview_store.py` — 新增字段和方法
- `app/services/interview_service.py` — start() 加入可选参数
- `app/api/interview.py` — 改为 multipart/form-data 接收
- `app/main.py` — 注入 ResumeParser 实例
- `frontend/index.html` — 面试准备页新增上传区域
- `frontend/js/app.js` — 新增简历上传、JD输入、个性化请求逻辑
- `frontend/css/style.css` — 新增上传区域样式

## 8. 不需要改动的部分

- 回答评价流程（`answer()` 方法）
- 面试报告生成流程（`_generate_report()` 方法）
- 面试历史查询（`history()` 方法）
- 强制结束面试（`end()` 方法）
- 其他所有 API 端点
- 知识库、RAG 管道、会话管理等无关模块