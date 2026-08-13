# 简历+JD → 自动生成面试 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有AI面试系统中增加「简历上传+JD输入」的可选环节，实现简历解析、JD匹配到个性化面试题生成的端到端流程。

**Architecture:** 扩展现有POST /api/interview/start接口，新增resume_parser.py服务层，在interview_sessions表新增5个字段，将匹配分析结果注入出题Prompt。前端在面试准备页增加简历上传和JD输入区域。

**Tech Stack:** Python FastAPI, pypdf (PDF解析), LLM (百炼通义千问 for 结构化解析&匹配分析), SQLite, HTML/CSS/JS

## Global Constraints

- 无简历/JD时走现有流程，完全向后兼容
- 简历仅接受PDF格式，使用pypdf提取文本
- JD为用户粘贴的纯文本
- 匹配分析结果存储在SQLite的interview_sessions表
- 评价、报告等后续流程完全不变

---

### Task 1: Git分支准备

**Files:**
- Modify: 当前git工作区

**Interfaces:**
- Consumes: 当前feature/knowledge-tree分支（有未提交改动）
- Produces: 基于main的新分支feature/resume-jd-interview

- [ ] **Step 1: 暂存当前改动**

```bash
git stash push -m "feature/knowledge-tree uncommitted changes"
```

- [ ] **Step 2: 切换到main分支**

```bash
git checkout main
```

- [ ] **Step 3: 尝试拉取远程最新代码**

先清除代理，拉取后再恢复：

```bash
git config --global --unset http.proxy
git config --global --unset https.proxy
git pull origin main
```

如果远程拉取失败（网络问题），则使用本地main分支继续。

- [ ] **Step 4: 创建新分支**

```bash
git checkout -b feature/resume-jd-interview
```

---

### Task 2: 数据库扩展 — interview_store.py

**Files:**
- Modify: `app/storage/instrument_store.py`

**Interfaces:**
- Consumes: 现有InterviewStore类
- Produces: 新增字段和方法用于存储简历/JD/匹配分析

- [ ] **Step 1: 修改建表语句，增加5个字段**

在`_init_db()`的`interview_sessions`建表语句中增加：

```python
CREATE TABLE IF NOT EXISTS interview_sessions (
    id             TEXT PRIMARY KEY,
    position       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'in_progress',
    total_rounds   INTEGER DEFAULT 0,
    total_score    REAL DEFAULT 0,
    started_at     TEXT,
    completed_at   TEXT,
    report         TEXT,
    resume_text    TEXT DEFAULT '',
    resume_analysis TEXT DEFAULT '{}',
    jd_text        TEXT DEFAULT '',
    jd_analysis    TEXT DEFAULT '{}',
    match_analysis TEXT DEFAULT '{}'
);
```

- [ ] **Step 2: 修改create_session()方法**

增加可选参数，存储简历/JD/匹配分析数据：

```python
def create_session(self, position: str,
                   resume_text: str = "",
                   resume_analysis: str = "{}",
                   jd_text: str = "",
                   jd_analysis: str = "{}",
                   match_analysis: str = "{}") -> dict:
    session_id = str(uuid.uuid4())
    now = self._now()
    with self._get_conn() as conn:
        conn.execute(
            """INSERT INTO interview_sessions
               (id, position, status, started_at, resume_text, resume_analysis,
                jd_text, jd_analysis, match_analysis)
               VALUES (?, ?, 'in_progress', ?, ?, ?, ?, ?, ?)""",
            (session_id, position, now, resume_text, resume_analysis,
             jd_text, jd_analysis, match_analysis),
        )
    return {"id": session_id, "position": position, "status": "in_progress", "started_at": now}
```

- [ ] **Step 3: 新增update_analysis方法**

用于异步更新解析结果（start方法中先创建session，再解析，再更新）：

```python
def update_analysis(self, session_id: str,
                    resume_text: str = None,
                    resume_analysis: str = None,
                    jd_text: str = None,
                    jd_analysis: str = None,
                    match_analysis: str = None):
    updates = []
    values = []
    if resume_text is not None:
        updates.append("resume_text = ?")
        values.append(resume_text)
    if resume_analysis is not None:
        updates.append("resume_analysis = ?")
        values.append(resume_analysis)
    if jd_text is not None:
        updates.append("jd_text = ?")
        values.append(jd_text)
    if jd_analysis is not None:
        updates.append("jd_analysis = ?")
        values.append(jd_analysis)
    if match_analysis is not None:
        updates.append("match_analysis = ?")
        values.append(match_analysis)
    if not updates:
        return
    values.append(session_id)
    with self._get_conn() as conn:
        conn.execute(
            f"UPDATE interview_sessions SET {', '.join(updates)} WHERE id = ?",
            values,
        )
```

---

### Task 3: 新建服务层 — resume_parser.py

**Files:**
- Create: `app/services/resume_parser.py`

**Interfaces:**
- Consumes: LLMClient, pypdf
- Produces: ResumeParser类（含extract_pdf_text, parse_resume, parse_jd, analyze_match四个方法）

- [ ] **Step 1: 创建resume_parser.py文件**

```python
"""Resume/JD parsing and matching analysis service.

Parses PDF resumes, extracts structured info from JD text,
and performs matching analysis using LLM.
"""

import json
import re
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

# --- Prompt templates ---

RESUME_PARSE_PROMPT = """请从以下简历文本中提取结构化信息，以JSON格式输出（不要包含其他内容）：

{resume_text}

请按以下JSON格式输出：
{{
    "skills": ["Java", "Spring", ...],
    "projects": [
        {{
            "name": "项目名称",
            "description": "项目简介",
            "technologies": ["技术栈1", "技术栈2"]
        }}
    ],
    "experience": [
        {{
            "company": "公司名",
            "role": "职位",
            "duration": "时间范围",
            "description": "工作内容简述"
        }}
    ],
    "education": [
        {{
            "school": "学校名",
            "major": "专业",
            "degree": "学历",
            "year": "毕业年份"
        }}
    ],
    "summary": "候选人整体背景总结（30字以内）"
}}
"""

JD_PARSE_PROMPT = """请从以下招聘JD文本中提取结构化需求，以JSON格式输出（不要包含其他内容）：

{jd_text}

请按以下JSON格式输出：
{{
    "required_skills": ["Java", "Spring", ...],
    "preferred_skills": ["Redis", "Docker", ...],
    "responsibilities": ["负责XXX开发", ...],
    "experience_required": "3-5年",
    "education_required": "本科及以上",
    "key_requirements": ["核心要求1", "核心要求2"],
    "summary": "岗位整体要求总结（30字以内）"
}}
"""

MATCH_ANALYSIS_PROMPT = """请根据以下候选人的简历信息和招聘JD需求，进行详细的匹配分析，以JSON格式输出。

【简历信息】
{resume_json}

【JD需求】
{jd_json}

请按以下JSON格式输出：
{{
    "matched_skills": ["JD要求且候选人具备的技能1", "技能2"],
    "missing_skills": ["JD要求但候选人缺失的技能1", "技能2"],
    "partial_skills": ["JD要求但候选人仅部分具备的技能"],
    "project_match": "项目经验与岗位职责的匹配度评价（30字以内）",
    "experience_match": "工作年限/经验匹配度评价（20字以内）",
    "strong_areas": ["候选人具备的突出优势1", "优势2"],
    "risk_areas": ["高风险追问方向1", "方向2"],
    "overall_match": "high/medium/low",
    "interview_focus": "面试中应重点考察的方向（50字以内）"
}}
"""


def _parse_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


class ResumeParser:
    """Resume/JD parsing and matching analysis service."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def extract_pdf_text(self, file: UploadFile) -> str:
        """Extract text from a PDF file using pypdf."""
        try:
            from pypdf import PdfReader

            # Save uploaded file to temp location
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name

            try:
                reader = PdfReader(tmp_path)
                text_parts = []
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                return "\n".join(text_parts)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
            return ""

    async def parse_resume(self, text: str) -> dict:
        """Parse resume text into structured info using LLM."""
        if not text.strip():
            return {}
        prompt = RESUME_PARSE_PROMPT.format(resume_text=text[:4000])
        result = await self.llm.chat(prompt)
        parsed = _parse_json(result)
        if not parsed:
            logger.warning(f"Failed to parse resume JSON, raw: {result[:200]}")
            return {"skills": [], "projects": [], "experience": [], "summary": text[:100]}
        return parsed

    async def parse_jd(self, text: str) -> dict:
        """Parse JD text into structured requirements using LLM."""
        if not text.strip():
            return {}
        prompt = JD_PARSE_PROMPT.format(jd_text=text[:3000])
        result = await self.llm.chat(prompt)
        parsed = _parse_json(result)
        if not parsed:
            logger.warning(f"Failed to parse JD JSON, raw: {result[:200]}")
            return {"required_skills": [], "key_requirements": [], "summary": text[:100]}
        return parsed

    async def analyze_match(self, resume: dict, jd: dict) -> dict:
        """Analyze match between resume and JD using LLM."""
        if not resume or not jd:
            return {}
        prompt = MATCH_ANALYSIS_PROMPT.format(
            resume_json=json.dumps(resume, ensure_ascii=False, indent=2),
            jd_json=json.dumps(jd, ensure_ascii=False, indent=2),
        )
        result = await self.llm.chat(prompt)
        parsed = _parse_json(result)
        if not parsed:
            logger.warning(f"Failed to parse match analysis JSON, raw: {result[:200]}")
            return {"matched_skills": [], "missing_skills": [], "overall_match": "unknown"}
        return parsed
```

---

### Task 4: 修改面试服务层 — interview_service.py

**Files:**
- Modify: `app/services/interview_service.py`

**Interfaces:**
- Consumes: ResumeParser, 修改后的InterviewStore
- Produces: start()方法支持可选resume_file和jd_text参数，生成的question包含个性化上下文

- [ ] **Step 1: 导入ResumeParser**

在文件顶部import中增加：

```python
from app.services.resume_parser import ResumeParser
from fastapi import UploadFile
```

- [ ] **Step 2: 修改__init__方法**

增加resume_parser参数：

```python
def __init__(
    self,
    store: InterviewStore,
    llm: LLMClient,
    faiss: Optional[FaissStore] = None,
    embedding: Optional[EmbeddingService] = None,
    topic_tracker: Optional[TopicTracker] = None,
    resume_parser: Optional[ResumeParser] = None,
):
    # ... existing code ...
    self.resume_parser = resume_parser
```

- [ ] **Step 3: 修改start()方法**

增加resume_file和jd_text可选参数：

```python
async def start(
    self,
    position: str,
    resume_file: Optional[UploadFile] = None,
    jd_text: Optional[str] = None,
) -> dict:
    """Start a new interview session, optionally with resume+JD analysis."""
    # Create session with empty analysis first
    session = self.store.create_session(position)

    # Parse resume and JD if provided
    resume_analysis = {}
    jd_analysis = {}
    match_analysis = {}
    resume_raw = ""
    jd_raw = ""

    if resume_file and self.resume_parser:
        try:
            resume_raw = await self.resume_parser.extract_pdf_text(resume_file)
            if resume_raw:
                resume_analysis = await self.resume_parser.parse_resume(resume_raw)
        except Exception as e:
            logger.warning(f"Resume parsing failed: {e}")

    if jd_text and self.resume_parser:
        try:
            jd_raw = jd_text
            jd_analysis = await self.resume_parser.parse_jd(jd_text)
        except Exception as e:
            logger.warning(f"JD parsing failed: {e}")

    # Perform matching analysis if both resume and JD are available
    if resume_analysis and jd_analysis:
        try:
            match_analysis = await self.resume_parser.analyze_match(resume_analysis, jd_analysis)
        except Exception as e:
            logger.warning(f"Match analysis failed: {e}")

    # Store analysis results
    self.store.update_analysis(
        session["id"],
        resume_text=resume_raw[:5000] if resume_raw else None,
        resume_analysis=json.dumps(resume_analysis, ensure_ascii=False) if resume_analysis else None,
        jd_text=jd_raw[:3000] if jd_raw else None,
        jd_analysis=json.dumps(jd_analysis, ensure_ascii=False) if jd_analysis else None,
        match_analysis=json.dumps(match_analysis, ensure_ascii=False) if match_analysis else None,
    )

    # Generate first question with personalized context
    question_data = await self._generate_question(
        session["id"], position, round_num=1,
        match_analysis=match_analysis,
        resume_analysis=resume_analysis,
        jd_analysis=jd_analysis,
    )

    return {
        "session_id": session["id"],
        "question": question_data,
    }
```

- [ ] **Step 4: 修改_generate_question()方法**

增加match_analysis、resume_analysis、jd_analysis参数，构建个性化上下文注入Prompt：

```python
async def _generate_question(
    self,
    session_id: str,
    position: str,
    round_num: int,
    difficulty: str = "medium",
    last_answer: str = "",
    last_evaluation: Optional[dict] = None,
    match_analysis: Optional[dict] = None,
    resume_analysis: Optional[dict] = None,
    jd_analysis: Optional[dict] = None,
) -> dict:
    """Generate a question, optionally with personalized context."""
    questions = self.store.get_questions(session_id)
    history_count = len(questions)
    difficulty_history = ", ".join([_difficulty_label(q.get("difficulty", "medium")) for q in questions]) or "暂无"
    last_eval_summary = ""
    if last_evaluation:
        last_eval_summary = f"得分：{last_evaluation.get('score', '?')}，评语：{last_evaluation.get('comment', '')[:50]}"

    kb_context = await self._retrieve_context(f"{position} 技术面试题 {difficulty}")

    # Build personalized context if match analysis is available
    personalized_context = ""
    if match_analysis and match_analysis.get("matched_skills"):
        jd_summary = jd_analysis.get("summary", "") if jd_analysis else ""
        resume_summary = resume_analysis.get("summary", "") if resume_analysis else ""
        missing = ", ".join(match_analysis.get("missing_skills", []))
        matched = ", ".join(match_analysis.get("matched_skills", []))
        risk = ", ".join(match_analysis.get("risk_areas", []))
        focus = match_analysis.get("interview_focus", "")

        personalized_context = f"""
【简历与JD匹配分析】
岗位要求：{jd_summary}
候选人背景：{resume_summary}
已匹配技能：{matched}
技能缺口：{missing}
高风险追问方向：{risk}
面试重点：{focus}

请基于以上分析，针对候选人的简历短板和岗位核心要求出题。
"""

    # --- Knowledge tree integration (unchanged) ---
    coverage_text = ""
    tree_text = ""
    suggestion_text = ""
    suggested_category = ""
    if self.topic_tracker:
        tree = self.topic_tracker.get_tree(position)
        if tree:
            coverage_text = self.topic_tracker.get_coverage_summary_text(session_id, position)
            tree_text = self.topic_tracker.get_tree_structure_text(position)
            suggestion = self.topic_tracker.get_next_suggestion(session_id, position)
            if suggestion.get("topic"):
                suggested_category = suggestion.get("category", "")
                suggestion_text = (
                    f"建议优先出题方向：{suggested_category} - {suggestion['topic']}\n"
                    f"原因：{suggestion['reason']}"
                )

    prompt = QUESTION_PROMPT.format(
        position=position,
        round=round_num,
        history_count=history_count,
        difficulty_history=difficulty_history,
        last_evaluation_summary=last_eval_summary,
        knowledge_context=kb_context + personalized_context,
        难度提示=_difficulty_label(difficulty),
        coverage_summary=coverage_text,
        knowledge_tree_structure=tree_text,
        suggested_topic=suggestion_text,
        suggested_category=suggested_category,
    )

    text = await self.llm.chat(prompt, SYSTEM_START)
    # ... rest of the method (unchanged) ...
```

注意：`_generate_question()`调用的地方需要更新。在`_generate_question()`内部，`self._generate_question(session_id, position, round_num=1)`调用现在需要传入match_analysis等参数。但`_generate_question`在`answer()`方法中也有调用（第233行），那里不需要个性化上下文，传空值即可。

- [ ] **Step 5: 修改answer()方法中_generate_question的调用**

在`answer()`方法中，调用`_generate_question()`时增加空参数：

```python
next_q = await self._generate_question(
    session_id, session["position"], next_round, next_difficulty,
    question["answer"], evaluation,
    match_analysis=None, resume_analysis=None, jd_analysis=None,
)
```

---

### Task 5: 修改API层 — interview.py

**Files:**
- Modify: `app/api/interview.py`

**Interfaces:**
- Consumes: 修改后的InterviewService
- Produces: POST /api/interview/start 支持multipart/form-data，接收resume_file和jd_text

- [ ] **Step 1: 修改start_interview接口**

改为接收 `multipart/form-data` 格式：

```python
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

@router.post("/start")
async def start_interview(
    position: str = Form(...),
    resume_file: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
):
    """Start a new interview session, optionally with resume+JD analysis."""
    try:
        service = _get_service()
        # Validate file type
        if resume_file and not resume_file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="仅支持PDF格式的简历文件")
        result = await service.start(position, resume_file=resume_file, jd_text=jd_text)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 2: 清理StartInterviewRequest类**

由于改为form-data方式，不再需要`StartInterviewRequest`的JSON schema，可以删除或保留（不影响）。

---

### Task 6: 修改main.py — 注入ResumeParser

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: 添加全局变量和导入**

```python
from app.services.resume_parser import ResumeParser

# 在全局变量区域增加
resume_parser: ResumeParser | None = None
```

- [ ] **Step 2: 在lifespan中初始化**

在`interview_service`初始化之前：

```python
# Initialize resume parser
resume_parser = ResumeParser(llm=llm_client)

# 修改interview_service初始化，注入resume_parser
interview_service = InterviewService(
    interview_store, llm_client, faiss_store, embedding_service,
    topic_tracker=topic_tracker,
    resume_parser=resume_parser,
)
```

---

### Task 7: 前端 — HTML修改

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: 在面试准备页增加简历上传和JD输入区域**

在`#interview-ready`的`position-select`下方、`btn-start-interview`上方增加：

```html
<div class="resume-jd-section">
    <div class="resume-jd-divider">
        <span>简历与岗位匹配（可选）</span>
    </div>

    <!-- 简历上传 -->
    <div class="resume-upload-area">
        <label class="resume-jd-label">上传简历</label>
        <div class="resume-upload-zone" id="resume-upload-zone">
            <div class="resume-upload-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M12 16V4m0 0L8 8m4-4l4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </div>
            <p class="resume-upload-text">拖拽PDF简历到此处，或 <span class="resume-upload-link">点击选择文件</span></p>
            <p class="resume-upload-hint">仅支持 .pdf 格式</p>
            <input type="file" id="resume-file-input" hidden accept=".pdf">
        </div>
        <div class="resume-file-info" id="resume-file-info" style="display:none;">
            <span class="resume-file-name" id="resume-file-name"></span>
            <button class="resume-file-remove" id="resume-file-remove" title="移除文件">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" stroke-width="1.5"/></svg>
            </button>
        </div>
    </div>

    <!-- JD输入 -->
    <div class="jd-input-area">
        <label class="resume-jd-label">招聘JD</label>
        <textarea id="jd-input" class="jd-textarea" placeholder="粘贴招聘JD内容..." rows="4"></textarea>
    </div>
</div>
```

---

### Task 8: 前端 — CSS样式

**Files:**
- Modify: `frontend/css/style.css`

- [ ] **Step 1: 添加简历上传和JD输入区域的样式**

在文件末尾增加：

```css
/* ============ Resume + JD Upload Section ============ */
.resume-jd-section {
    width: 100%;
    max-width: 520px;
    margin-top: 8px;
}

.resume-jd-divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 16px 0;
    color: var(--text-secondary, #888);
    font-size: 12px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.resume-jd-divider::before,
.resume-jd-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border-color, #333);
}

.resume-upload-area,
.jd-input-area {
    margin-bottom: 14px;
}

.resume-jd-label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary, #e0e0e0);
    margin-bottom: 6px;
}

.resume-upload-zone {
    border: 2px dashed var(--border-color, #444);
    border-radius: 8px;
    padding: 20px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s, background-color 0.2s;
}

.resume-upload-zone:hover {
    border-color: var(--primary, #6054F1);
    background: rgba(96, 84, 241, 0.05);
}

.resume-upload-zone.dragover {
    border-color: var(--primary, #6054F1);
    background: rgba(96, 84, 241, 0.1);
}

.resume-upload-icon {
    color: var(--text-secondary, #888);
    margin-bottom: 8px;
}

.resume-upload-text {
    font-size: 13px;
    color: var(--text-secondary, #888);
    margin: 0 0 4px;
}

.resume-upload-link {
    color: var(--primary, #6054F1);
    cursor: pointer;
    font-weight: 500;
}

.resume-upload-link:hover {
    text-decoration: underline;
}

.resume-upload-hint {
    font-size: 11px;
    color: var(--text-muted, #666);
    margin: 0;
}

.resume-file-info {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: rgba(96, 84, 241, 0.1);
    border: 1px solid rgba(96, 84, 241, 0.3);
    border-radius: 6px;
    margin-top: 8px;
}

.resume-file-name {
    flex: 1;
    font-size: 13px;
    color: var(--text-primary, #e0e0e0);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.resume-file-remove {
    background: none;
    border: none;
    color: var(--text-secondary, #888);
    cursor: pointer;
    padding: 2px;
    display: flex;
    align-items: center;
    border-radius: 4px;
    transition: color 0.2s;
}

.resume-file-remove:hover {
    color: #ff4444;
}

.jd-textarea {
    width: 100%;
    padding: 10px 12px;
    background: var(--input-bg, #1e1e1e);
    border: 1px solid var(--border-color, #444);
    border-radius: 8px;
    color: var(--text-primary, #e0e0e0);
    font-size: 13px;
    font-family: inherit;
    resize: vertical;
    min-height: 80px;
    transition: border-color 0.2s;
    box-sizing: border-box;
}

.jd-textarea:focus {
    outline: none;
    border-color: var(--primary, #6054F1);
    box-shadow: 0 0 0 2px rgba(96, 84, 241, 0.15);
}

.jd-textarea::placeholder {
    color: var(--text-muted, #555);
}
```

---

### Task 9: 前端 — JavaScript逻辑

**Files:**
- Modify: `frontend/js/app.js`

- [ ] **Step 1: 在interviewEls中增加新DOM元素引用**

在`interviewEls`对象中增加：

```javascript
const interviewEls = {
    // ... existing refs ...
    resumeUploadZone: document.getElementById('resume-upload-zone'),
    resumeFileInput: document.getElementById('resume-file-input'),
    resumeFileInfo: document.getElementById('resume-file-info'),
    resumeFileName: document.getElementById('resume-file-name'),
    resumeFileRemove: document.getElementById('resume-file-remove'),
    jdInput: document.getElementById('jd-input'),
};
```

- [ ] **Step 2: 在interviewState中增加文件状态**

```javascript
const interviewState = {
    // ... existing state ...
    resumeFile: null,  // File object or null
};
```

- [ ] **Step 3: 在initInterview()中初始化事件**

在`initInterview()`函数末尾增加：

```javascript
// Resume upload: click to select
interviewEls.resumeUploadZone.addEventListener('click', () => {
    interviewEls.resumeFileInput.click();
});

// Resume file selected
interviewEls.resumeFileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        interviewState.resumeFile = file;
        interviewEls.resumeFileName.textContent = file.name;
        interviewEls.resumeFileInfo.style.display = 'flex';
        interviewEls.resumeUploadZone.style.display = 'none';
    }
});

// Resume file remove
interviewEls.resumeFileRemove.addEventListener('click', () => {
    interviewState.resumeFile = null;
    interviewEls.resumeFileInput.value = '';
    interviewEls.resumeFileInfo.style.display = 'none';
    interviewEls.resumeUploadZone.style.display = 'block';
});

// Resume drag & drop
interviewEls.resumeUploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    interviewEls.resumeUploadZone.classList.add('dragover');
});
interviewEls.resumeUploadZone.addEventListener('dragleave', () => {
    interviewEls.resumeUploadZone.classList.remove('dragover');
});
interviewEls.resumeUploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    interviewEls.resumeUploadZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file && file.type === 'application/pdf') {
        interviewState.resumeFile = file;
        interviewEls.resumeFileName.textContent = file.name;
        interviewEls.resumeFileInfo.style.display = 'flex';
        interviewEls.resumeUploadZone.style.display = 'none';
    }
});
```

- [ ] **Step 4: 修改startInterview()函数**

使用FormData发送请求，包含可选的文件和JD文本：

```javascript
async function startInterview() {
    if (!interviewState.position) return;

    showInterviewLoading('AI 面试官正在出题...');
    interviewState.isComplete = false;

    try {
        const formData = new FormData();
        formData.append('position', interviewState.position);

        if (interviewState.resumeFile) {
            formData.append('resume_file', interviewState.resumeFile);
        }

        const jdText = interviewEls.jdInput.value.trim();
        if (jdText) {
            formData.append('jd_text', jdText);
        }

        const res = await fetch(`${API_BASE}/api/interview/start`, {
            method: 'POST',
            body: formData,
            // Note: No Content-Type header - browser sets multipart/form-data automatically
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '请求失败');
        }

        const data = await res.json();
        interviewState.sessionId = data.session_id;
        interviewState.currentQuestionId = data.question.id;
        interviewState.currentRound = data.question.round;

        showInterviewProgress(data.question);
    } catch (err) {
        showToast('error', '出题失败: ' + err.message);
        showInterviewReady();
    }
}
```

- [ ] **Step 5: 在resetInterview()中重置文件状态**

在`resetInterview()`函数中增加重置代码：

```javascript
function resetInterview() {
    // ... existing reset code ...
    // Reset resume + JD
    interviewState.resumeFile = null;
    interviewEls.resumeFileInput.value = '';
    interviewEls.resumeFileInfo.style.display = 'none';
    interviewEls.resumeUploadZone.style.display = 'block';
    interviewEls.jdInput.value = '';
}
```

---

### Task 10: 完整测试与合并

- [ ] **Step 1: 运行服务验证**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

验证：
1. 打开 http://localhost:8000 确认页面正常加载
2. 点击「AI面试」tab，确认准备页正确显示
3. 仅选择岗位 → 点击开始面试 → 确认走原有流程
4. 选择岗位 + 上传简历 + 粘贴JD → 点击开始面试 → 确认正常出题

- [ ] **Step 2: 提交代码**

```bash
git add -A
git status  # 确认只包含预期文件
git commit -m "feat: 简历+JD自动生成面试 - ResumeParser/匹配分析/前端上传"
```

- [ ] **Step 3: 合并到main**

```bash
git checkout main
git merge feature/resume-jd-interview
```

- [ ] **Step 4: 推送远程**

恢复代理后推送：

```bash
git config --global http.proxy http://127.0.0.1:7897
git push origin main
```