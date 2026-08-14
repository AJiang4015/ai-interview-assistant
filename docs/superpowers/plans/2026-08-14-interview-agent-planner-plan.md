# 项目深挖 / RAG 评测 / Interview Agent 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地三个能力——从简历项目对抗式深挖、RAG 检索/生成质量评测、以及 Planner 驱动的 Interview Agent 编排。

**Architecture:** 三个独立阶段，按优先级先后交付。阶段一新增独立的「项目深挖」模式（复用 ResumeParser/LLMClient + 新增 DeepDiveService/Store）。阶段二新增 RAG 评测工具链（TestSetGenerator/Evaluator/StrategyRunner），复用现有 RAG 管线开关做策略对比。阶段三把现有 InterviewService 重构为显式 Planner 决策循环，将阶段一作为新动作接入。

**Tech Stack:** Python 3 + FastAPI + moto(SQLite) 已有；LLM 用现有 Qwen/Bailian client；FAISS + BM25 已有；前端原生 JS + 现有 CSS 变量体系；测试用 pytest + pytest-asyncio。

## Global Constraints

- 复用现有 `LLMClient.chat()` 作为所有 LLM 调用入口（不新增 LLM 提供商）。
- 复用现有 `ResumeParser` 解析简历，不重复实现 PDF 解析。
- 复用现有 RAG 管线组件（`FaissStore` / `EmbeddingService` / `HybridRetriever` / `RerankService`），不新建检索实现。
- 数据落库统一走 `app/storage/`，SQLite 文件沿用 `data/interviews.db`。
- 前端沿用现有 CSS 变量（`--bg-primary`/`--accent`/`--border` 等）与 `escapeHtml`/`showToast` 工具函数。
- 阶段三不得改变现有 API 对外契约（`/start`、`/answer`、`/end`、`/report`）。
- 所有 LLM 解析失败必须优雅降级，不抛异常中断流程。

---

## 阶段一：项目经历深挖（Deep Dive）

### 文件结构

| 文件 | 职责 |
|---|---|
| `app/storage/deep_dive_store.py` | SQLite 存储：深挖会话 + 追问链 |
| `app/services/deep_dive_service.py` | 深挖核心逻辑 + 恶劣面试官 Prompt + 状态机 |
| `app/api/deep_dive.py` | 深挖 API 端点 |
| `app/main.py` | 注册服务与路由 |
| `frontend/index.html` | 面试首屏新增「项目深挖」模式入口 + 深挖 UI |
| `frontend/js/app.js` | 深挖交互逻辑 |
| `frontend/css/style.css` | 深挖样式 |

### Task D1: DeepDiveStore 存储层

**Files:**
- Create: `app/storage/deep_dive_store.py`
- Test: `tests/storage/test_deep_dive_store.py`

**Interfaces:**
- Consumes: 无（新建）
- Produces:
  - `create_session(project_name, tech_point, description) -> dict`（含 `id`）
  - `add_question(session_id, round_num, question) -> dict`（含 `id`）
  - `update_answer(question_id, answer, score, judgment) -> None`
  - `get_session(session_id) -> dict | None`
  - `get_questions(session_id) -> list[dict]`
  - `complete_session(session_id, summary_text) -> None`

- [ ] **Step 1: 写失败测试**

```python
# tests/storage/test_deep_dive_store.py
import pytest
from app.storage.deep_dive_store import DeepDiveStore

@pytest.fixture
def store(tmp_path):
    return DeepDiveStore(db_path=str(tmp_path / "dd.db"))

def test_create_and_get_session(store):
    s = store.create_session("RAG知识库", "Rerank", "构建问答系统")
    got = store.get_session(s["id"])
    assert got["project_name"] == "RAG知识库"
    assert got["status"] == "in_progress"

def test_question_round_trip(store):
    s = store.create_session("P", "T", "d")
    q = store.add_question(s["id"], 1, "为什么不直接向量检索?")
    store.update_answer(q["id"], "因为要重排", 6.0, "{\"ok\": true}")
    qs = store.get_questions(s["id"])
    assert len(qs) == 1 and qs[0]["answer"] == "因为要重排"

def test_complete_session(store):
    s = store.create_session("P", "T", "d")
    store.complete_session(s["id"], "薄弱点: Rerank原理")
    assert store.get_session(s["id"])["status"] == "completed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/storage/test_deep_dive_store.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.storage.deep_dive_store'`

- [ ] **Step 3: 实现存储层**

```python
# app/storage/deep_dive_store.py
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)


class DeepDiveStore:
    """SQLite storage for project deep-dive sessions."""

    def __init__(self, db_path: str = "data/interviews.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS deep_dive_sessions (
                    id           TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    tech_point   TEXT NOT NULL,
                    description  TEXT DEFAULT '',
                    status       TEXT NOT NULL DEFAULT 'in_progress',
                    summary      TEXT DEFAULT '',
                    start_round  INTEGER DEFAULT 0,
                    created_at   TEXT
                );
                CREATE TABLE IF NOT EXISTS deep_dive_questions (
                    id         TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    round      INTEGER NOT NULL,
                    question   TEXT NOT NULL,
                    answer     TEXT DEFAULT '',
                    score      REAL DEFAULT 0,
                    judgment   TEXT DEFAULT '{}',
                    created_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES deep_dive_sessions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_ddq_session ON deep_dive_questions(session_id);
            """)

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_session(self, project_name: str, tech_point: str, description: str = "") -> dict:
        sid = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO deep_dive_sessions (id, project_name, tech_point, description, status, created_at)
                   VALUES (?, ?, ?, ?, 'in_progress', ?)""",
                (sid, project_name, tech_point, description, self._now()),
            )
        return {"id": sid, "project_name": project_name, "tech_point": tech_point,
                "description": description, "status": "in_progress"}

    def add_question(self, session_id: str, round_num: int, question: str) -> dict:
        qid = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO deep_dive_questions (id, session_id, round, question, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (qid, session_id, round_num, question, self._now()),
            )
            conn.execute("UPDATE deep_dive_sessions SET start_round = ? WHERE id = ?",
                         (round_num, session_id))
        return {"id": qid, "session_id": session_id, "round": round_num, "question": question}

    def update_answer(self, question_id: str, answer: str, score: float, judgment: dict):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE deep_dive_questions SET answer = ?, score = ?, judgment = ? WHERE id = ?",
                (answer, score, json.dumps(judgment, ensure_ascii=False), question_id),
            )

    def get_session(self, session_id: str) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM deep_dive_sessions WHERE id = ?",
                               (session_id,)).fetchone()
            return dict(row) if row else None

    def get_questions(self, session_id: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM deep_dive_questions WHERE session_id = ? ORDER BY round ASC",
                (session_id,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["judgment"] = json.loads(d.get("judgment") or "{}")
                out.append(d)
            return out

    def complete_session(self, session_id: str, summary_text: str):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE deep_dive_sessions SET status = 'completed', summary = ? WHERE id = ?",
                (summary_text, session_id),
            )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/storage/test_deep_dive_store.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add app/storage/deep_dive_store.py tests/storage/test_deep_dive_store.py
git commit -m "feat: DeepDiveStore 深挖会话/追问链存储"
```

---

### Task D2: DeepDiveService 核心逻辑

**Files:**
- Create: `app/services/deep_dive_service.py`
- Test: `tests/services/test_deep_dive_service.py`

**Interfaces:**
- Consumes: `DeepDiveStore`（Task D1）、`LLMClient.chat(prompt, system)`、`ResumeParser.parse_resume(text)`
- Produces:
  - `extract_projects(resume_analysis: dict) -> list[dict]`（可测）
  - `async start(project_name, tech_point, description) -> dict`（返回 `{session_id, question}`）
  - `async answer(question_id, answer, action) -> dict`（`action` ∈ `continue|switch|end`；返回 `{judgment, next_question}` 或 `{judgment, summary, is_complete}`）
  - `async end(session_id) -> dict`（返回 `{summary}`）

- [ ] **Step 1: 写失败测试（纯逻辑部分）**

```python
# tests/services/test_deep_dive_service.py
import pytest
from app.services.deep_dive_service import DeepDiveService

class FakeLLM:
    async def chat(self, prompt, system=None):
        return '{"question": "为什么不直接向量检索?", "judgment": "ok", "score": 6, "can_answer": true}'

def make_service():
    # store 用临时内存 SQLite
    import tempfile, os
    from app.storage.deep_dive_store import DeepDiveStore
    tmp = tempfile.mktemp(suffix=".db")
    store = DeepDiveStore(db_path=tmp)
    return DeepDiveService(store=store, llm=FakeLLM())

def test_extract_projects_returns_technologies():
    svc = make_service()
    resume = {"projects": [
        {"name": "知识库问答", "technologies": ["RAG", "Rerank", "Redis"]}
    ]}
    projects = svc.extract_projects(resume)
    assert projects[0]["name"] == "知识库问答"
    assert "RAG" in projects[0]["technologies"]

async def test_start_returns_session_and_first_question():
    svc = make_service()
    res = await svc.start("知识库问答", "Rerank", "构建问答系统")
    assert "session_id" in res and "question" in res and "id" in res["question"]

async def test_answer_continue_returns_next_question():
    svc = make_service()
    s = await svc.start("知识库问答", "Rerank", "d")
    q1 = s["question"]
    res = await svc.answer(q1["id"], "因为要做相关性重排", "continue")
    assert res["is_complete"] is False
    assert "next_question" in res and res["next_question"]["round"] == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/services/test_deep_dive_service.py -v`
Expected: FAIL，`No module named 'app.services.deep_dive_service'`

- [ ] **Step 3: 实现服务（含恶劣面试官 Prompt）**

```python
# app/services/deep_dive_service.py
import json
import re

from app.storage.deep_dive_store import DeepDiveStore
from app.utils.logger import get_logger

logger = get_logger(__name__)

MAX_DEPTH = 5

SYSTEM_MEAN = (
    "你是一名极其严格、喜欢刨根问底的资深技术面试官。"
    "你的风格是：抓住候选人回答中每一个技术断言，连续追问，逼迫其讲清原理、必要性与边界。"
    "追问要单刀直入、一针见血，但语气专业克制，不进行人身攻击。"
    "你只问一个问题，不解释答案。"
)

FIRST_ASK_PROMPT = """候选人简历中有一个项目：{project_name}
技术点：{tech_points}
项目描述：{description}

你作为严格的面试官，针对这个项目和技术点，抛出第一个尖锐问题，要求候选人解释"为什么这么选/怎么实现"。
请以 JSON 输出：{{"question": "问题内容"}}
"""

FOLLOW_UP_PROMPT = """候选人正在接受你的项目深挖追问。
技术点：{tech_point}
项目：{project_name}
此前追问链：
{history}

候选人对上一个问题的回答是：{answer}

请针对这个回答，只问一个更深入或更尖锐的追问（质疑其选择、要求原理、升级规模、考察边界）。
请以 JSON 输出：{{"question": "追问内容"}}
"""

JUDGE_PROMPT = """判断候选人回答的质量，并决定是否继续追问。

问题：{question}
候选人的回答：{answer}

请以 JSON 输出：
{{
    "score": <1-10 整数>,
    "judgment": "一句话点评（指出候选人暴露的薄弱点）",
    "can_answer": <true/false，false 表示答不上来或明显错误>
}}
"""

SUMMARY_PROMPT = """请根据本次项目深挖的完整追问链，生成一份总结。
追问链：
{history}

请以 JSON 输出：
{{
    "weaknesses": ["候选人暴露的薄弱点1", "薄弱点2"],
    "key_points": ["该技术点应掌握的核心要点1", "要点2"],
    "overall": "整体评价（60字内）"
}}
"""


def _parse_json(text: str) -> dict | None:
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


class DeepDiveService:
    def __init__(self, store: DeepDiveStore, llm):
        self.store = store
        self.llm = llm

    def extract_projects(self, resume_analysis: dict) -> list[dict]:
        """从简历解析结果中提取项目及技术点。"""
        projects = resume_analysis.get("projects") or []
        out = []
        for p in projects:
            techs = p.get("technologies") or []
            out.append({
                "name": p.get("name", "未命名项目"),
                "description": p.get("description", ""),
                "technologies": techs,
            })
        return out

    async def start(self, project_name: str, tech_point: str, description: str = "") -> dict:
        session = self.store.create_session(project_name, tech_point, description)
        prompt = FIRST_ASK_PROMPT.format(
            project_name=project_name, tech_points=tech_point, description=description)
        text = await self.llm.chat(prompt, SYSTEM_MEAN)
        parsed = _parse_json(text) or {"question": f"请先解释一下你在项目 {project_name} 中使用 {tech_point} 的动机。"}
        q = self.store.add_question(session["id"], 1, parsed["question"])
        return {"session_id": session["id"], "question": self._qdict(q)}

    async def answer(self, question_id: str, answer: str, action: str = "continue") -> dict:
        questions = None
        # 定位当前问题与其会话
        for sid in self._all_session_ids():
            qs = self.store.get_questions(sid)
            for q in qs:
                if q["id"] == question_id:
                    questions = qs
                    session = self.store.get_session(sid)
                    break
            if questions is not None:
                break
        if questions is None:
            raise ValueError(f"Question not found: {question_id}")

        # 评价当前回答
        judge_text = await self.llm.chat(
            JUDGE_PROMPT.format(question=self._find(questions, question_id)["question"], answer=answer),
            SYSTEM_MEAN)
        judge = _parse_json(judge_text) or {"score": 5, "judgment": "", "can_answer": True}
        score = judge.get("score", 5)
        self.store.update_answer(question_id, answer, score, judge)

        # 结束：用户主动 end，或达最大深度，或答不上来
        depth = len([q for q in questions if q["answer"]])
        if action == "end" or depth >= MAX_DEPTH or judge.get("can_answer") is False:
            summary = await self._generate_summary(session["id"])
            return {"is_complete": True, "judgment": judge, "summary": summary}

        # 生成下一层追问
        follow_text = await self.llm.chat(
            FOLLOW_UP_PROMPT.format(
                tech_point=session["tech_point"], project_name=session["project_name"],
                history=self._fmt_history(questions), answer=answer),
            SYSTEM_MEAN)
        follow = _parse_json(follow_text) or {"question": "再说得具体一点，你当时是怎么实现的？"}
        next_round = depth + 1
        nq = self.store.add_question(session["id"], next_round, follow["question"])
        return {"is_complete": False, "judgment": judge, "next_question": self._qdict(nq)}

    async def end(self, session_id: str) -> dict:
        summary = await self._generate_summary(session_id)
        return {"summary": summary}

    async def _generate_summary(self, session_id: str) -> dict:
        questions = self.store.get_questions(session_id)
        session = self.store.get_session(session_id)
        history = "\n".join(f"Q: {q['question']}\nA: {q['answer']}" for q in questions)
        text = await self.llm.chat(SUMMARY_PROMPT.format(history=history))
        parsed = _parse_json(text) or {
            "weaknesses": [], "key_points": [], "overall": "深挖结束。"}
        self.store.complete_session(session_id, json.dumps(parsed, ensure_ascii=False))
        return parsed

    @staticmethod
    def _qdict(q) -> dict:
        return {"id": q["id"], "question": q["question"], "round": q["round"]}

    @staticmethod
    def _find(questions, qid):
        return next(q for q in questions if q["id"] == qid)

    @staticmethod
    def _fmt_history(questions) -> str:
        return "\n".join(f"Q: {q['question']}\nA: {q['answer']}" for q in questions if q["answer"])

    def _all_session_ids(self):
        # 简化：通过 store 提供会话列表（见下方补充方法）
        return self.store.list_sessions()
```

- [ ] **Step 4: 补充存储会话列表方法**

在 `app/storage/deep_dive_store.py` 追加：

```python
    def list_sessions(self, limit: int = 50) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM deep_dive_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
            return [dict(r) for r in rows]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/services/test_deep_dive_service.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 提交**

```bash
git add app/services/deep_dive_service.py app/storage/deep_dive_store.py tests/services/test_deep_dive_service.py
git commit -m "feat: DeepDiveService 恶劣面试官深挖逻辑"
```

---

### Task D3: 深挖 API + 服务注册

**Files:**
- Create: `app/api/deep_dive.py`
- Modify: `app/main.py:44-50,131-142`

**Interfaces:**
- Consumes: `DeepDiveService`（Task D2）、`ResumeParser`（现有）
- Produces: 端点供前端调用：
  - `POST /api/deepdive/analyze`（FormData: `resume_file`）→ `{projects: [...]}`
  - `POST /api/deepdive/start`（JSON: `{project_name, tech_point, description?}`）→ `{session_id, question}`
  - `POST /api/deepdive/answer`（JSON: `{question_id, answer, action}`）→ 见 Task D2
  - `POST /api/deepdive/end`（JSON: `{session_id}`）→ `{summary}`

- [ ] **Step 1: 实现 API**

```python
# app/api/deep_dive.py
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.api.schemas import BaseModel, Field


class DeepDiveStartRequest(BaseModel):
    project_name: str
    tech_point: str
    description: str = ""


class DeepDiveAnswerRequest(BaseModel):
    question_id: str
    answer: str = Field(..., min_length=1, max_length=10000)
    action: str = "continue"  # continue | switch | end


class DeepDiveEndRequest(BaseModel):
    session_id: str


router = APIRouter(prefix="/api/deepdive")


def _get_service():
    from app.main import deep_dive_service
    if deep_dive_service is None:
        raise HTTPException(status_code=503, detail="Deep dive service not initialized")
    return deep_dive_service


@router.post("/analyze")
async def analyze_resume(resume_file: UploadFile = File(...)):
    """解析简历，返回项目与技术点列表。"""
    try:
        from app.main import resume_parser
        text = await resume_parser.extract_pdf_text(resume_file)
        analysis = await resume_parser.parse_resume(text)
        service = _get_service()
        projects = service.extract_projects(analysis)
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_dive(req: DeepDiveStartRequest):
    try:
        return await _get_service().start(req.project_name, req.tech_point, req.description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/answer")
async def answer_dive(req: DeepDiveAnswerRequest):
    try:
        return await _get_service().answer(req.question_id, req.answer, req.action)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/end")
async def end_dive(req: DeepDiveEndRequest):
    try:
        return await _get_service().end(req.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 2: 注册服务与路由**

在 `app/main.py`：

```python
# 顶部导入区追加
from app.api.deep_dive import router as deep_dive_router
from app.services.deep_dive_service import DeepDiveService
from app.storage.deep_dive_store import DeepDiveStore

# 模块级全局变量追加
deep_dive_service: DeepDiveService | None = None

# lifespan() 内、interview_service 之后追加
global deep_dive_service
deep_dive_service = DeepDiveService(store=DeepDiveStore(), llm=llm_client)

# app.include_router(interview_router) 之后追加
app.include_router(deep_dive_router)
```

- [ ] **Step 3: 启动验证**

Run: 重启 uvicorn 后 `Invoke-WebRequest -Method Post -Uri http://localhost:8000/api/deepdive/start -ContentType 'application/json' -Body '{"project_name":"知识库问答","tech_point":"Rerank","description":"构建问答系统"}'`
Expected: 返回含 `session_id` 与 `question` 的 JSON

- [ ] **Step 4: 提交**

```bash
git add app/api/deep_dive.py app/main.py
git commit -m "feat: 深挖 API 端点与服务注册"
```

---

### Task D4: 深挖前端

**Files:**
- Modify: `frontend/index.html`、`frontend/js/app.js`、`frontend/css/style.css`

**Interfaces:**
- Consumes: Task D3 端点
- Produces: 面试首屏「项目深挖」模式，复用现有面试进度/回答/评价 UI

- [ ] **Step 1: 面试首屏新增模式入口**

在 `frontend/index.html` 的 `#interview-ready` 内、岗位选择下方追加：

```html
<div class="deepdive-mode">
    <div class="resume-jd-divider"><span>项目深挖（可选）</span></div>
    <p class="deepdive-hint">上传简历，识别项目技术点，由"恶劣面试官"逐层追问，检验真实掌握程度。</p>
    <label class="resume-jd-label">上传简历</label>
    <div class="resume-upload-zone" id="dd-resume-zone">
        <div class="resume-upload-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 16V4m0 0L8 8m4-4l4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></div>
        <p class="resume-upload-text">拖拽PDF简历到此处，或 <span class="resume-upload-link">点击选择文件</span></p>
        <input type="file" id="dd-resume-input" hidden accept=".pdf">
    </div>
    <div class="dd-project-select" id="dd-project-select" style="display:none;">
        <label class="resume-jd-label">选择项目</label>
        <div class="position-options" id="dd-project-options"></div>
        <label class="resume-jd-label" style="margin-top:10px;">选择技术点</label>
        <div class="position-options" id="dd-tech-options"></div>
        <button class="btn-primary" id="btn-start-deepdive" disabled>开始深挖</button>
    </div>
</div>
```

在面试进行中区域，深挖复用现有 `#interview-progress`，但追加「继续追问 / 换个技术点 / 结束」按钮到评价区（复用 `#evaluation-actions`，追加一个深挖按钮容器）：

```html
<div class="evaluation-actions" id="dd-actions" style="display:none;">
    <button class="btn-primary" id="btn-dd-continue">继续追问</button>
    <button class="btn-secondary" id="btn-dd-switch">换个技术点</button>
    <button class="btn-secondary" id="btn-dd-end">结束深挖</button>
</div>
```

- [ ] **Step 2: 实现交互逻辑**

在 `frontend/js/app.js` 追加：

```javascript
// ============ Deep Dive Module ============
const ddState = { projects: [], techPoint: '', sessionId: null, currentQuestionId: null, round: 0, mode: false };
const ddEls = {
    zone: document.getElementById('dd-resume-zone'),
    input: document.getElementById('dd-resume-input'),
    projectSelect: document.getElementById('dd-project-select'),
    projectOptions: document.getElementById('dd-project-options'),
    techOptions: document.getElementById('dd-tech-options'),
    btnStart: document.getElementById('btn-start-deepdive'),
    actions: document.getElementById('dd-actions'),
    btnContinue: document.getElementById('btn-dd-continue'),
    btnSwitch: document.getElementById('btn-dd-switch'),
    btnEnd: document.getElementById('btn-dd-end'),
};

function initDeepDive() {
    ddEls.zone.addEventListener('click', () => ddEls.input.click());
    ddEls.zone.addEventListener('dragover', e => { e.preventDefault(); ddEls.zone.classList.add('dragover'); });
    ddEls.zone.addEventListener('dragleave', () => ddEls.zone.classList.remove('dragover'));
    ddEls.zone.addEventListener('drop', e => { e.preventDefault(); ddEls.zone.classList.remove('dragover'); handleDDUpload(e.dataTransfer.files[0]); });
    ddEls.input.addEventListener('change', e => { handleDDUpload(e.target.files[0]); e.target.value = ''; });
    ddEls.btnStart.addEventListener('click', startDeepDive);
    ddEls.btnContinue.addEventListener('click', submitDeepDiveAnswer('continue'));
    ddEls.btnSwitch.addEventListener('click', () => { ddState.mode = false; showInterviewReady(); });
    ddEls.btnEnd.addEventListener('click', endDeepDive);
}

async function handleDDUpload(file) { /* 上传到 /api/deepdive/analyze，填充项目列表 */ }
async function startDeepDive() { /* POST /api/deepdive/start，进入深挖进度 */ }
function submitDeepDiveAnswer(action) { /* POST answer，渲染追问或总结 */ }
async function endDeepDive() { /* POST /api/deepdive/end，展示总结 */ }
```

> **实现要点**（implementer 遵循）：`handleDDUpload` 用 FormData 上传文件到 `/api/deepdive/analyze`，把返回的 `projects` 渲染进 `#dd-project-options`；点击项目后用其 `technologies` 填充 `#dd-tech-options`；选中技术点后启用 `btnStart`。`startDeepDive` 调用 `/start` 后，将 `ddState.mode=true` 并复用 `showInterviewProgress` 展示题目，隐藏普通「提交回答」、显示 `#dd-actions`。`submitDeepDiveAnswer` 读取 `#answer-input`，POST `/answer`，`is_complete` 时渲染返回的 `summary`（weaknesses/key_points/overall），否则展示下一层追问。

- [ ] **Step 3: 样式**

在 `frontend/css/style.css` 末尾追加最小样式：

```css
/* ============ Deep Dive ============ */
.deepdive-mode { width: 100%; max-width: 520px; margin-top: 8px; }
.deepdive-hint { font-size: 12px; color: var(--text-tertiary); margin: 0 0 10px; }
#dd-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
```

- [ ] **Step 4: 浏览器验证**

Run: 打开 `http://localhost:8000/`，进入 AI面试 → 上传简历 → 选择项目/技术点 → 开始深挖，逐层回答并验证「继续追问/换个技术点/结束」按钮、答不上来或达层数自动收尾，结束展示总结。
Expected: 全流程可用，无控制台报错

- [ ] **Step 5: 提交**

```bash
git add frontend/index.html frontend/js/app.js frontend/css/style.css
git commit -m "feat: 项目深挖前端交互"
```

---

## 阶段二：RAG Evaluation

### 文件结构

| 文件 | 职责 |
|---|---|
| `app/services/evaluation_service.py` | 测试集生成 + 指标计算 + 策略对比 |
| `app/api/evaluation.py` | 评测 API |
| `app/main.py` | 注册服务与路由 |
| `frontend/js/app.js` + `frontend/index.html` | 「RAG 评测」板块 |

### Task E1: 指标计算（纯逻辑）

**Files:**
- Create: `app/services/eval_metrics.py`
- Test: `tests/services/test_eval_metrics.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `hit_rate(ranked_sources: list[str], expected_sources: set, k: int) -> float`
  - `recall_at_k(ranked_sources, expected_sources, k) -> float`
  - `mrr(ranked_sources, expected_sources, k) -> float`

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_eval_metrics.py
from app.services.eval_metrics import hit_rate, recall_at_k, mrr

def test_hit_rate_hit():
    assert hit_rate(["a.py", "b.py"], {"a.py"}, k=2) == 1.0

def test_hit_rate_miss():
    assert hit_rate(["a.py", "b.py"], {"c.py"}, k=2) == 0.0

def test_recall_at_k():
    assert recall_at_k(["a.py", "b.py"], {"a.py", "b.py", "c.py"}, k=2) == 2 / 3

def test_mrr_first_hit():
    assert mrr(["b.py", "a.py"], {"a.py"}, k=3) == 0.5

def test_mrr_no_hit():
    assert mrr(["a.py"], {"x.py"}, k=3) == 0.0
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/services/test_eval_metrics.py -v`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现**

```python
# app/services/eval_metrics.py
def hit_rate(ranked_sources, expected_sources, k):
    """期望来源是否出现在 top-k，逐条看是否命中（0 或 1，取均值由调用方处理）。"""
    top = ranked_sources[:k]
    return 1.0 if any(s in expected_sources for s in top) else 0.0


def recall_at_k(ranked_sources, expected_sources, k):
    """top-k 中命中的期望来源数 / 期望来源总数。"""
    if not expected_sources:
        return 0.0
    top = ranked_sources[:k]
    hit = sum(1 for s in expected_sources if s in top)
    return hit / len(expected_sources)


def mrr(ranked_sources, expected_sources, k):
    """第一个命中期望来源的倒数排名。"""
    for i, s in enumerate(ranked_sources[:k], start=1):
        if s in expected_sources:
            return 1.0 / i
    return 0.0
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/services/test_eval_metrics.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 提交**

```bash
git add app/services/eval_metrics.py tests/services/test_eval_metrics.py
git commit -m "feat: RAG 评测指标 hit_rate/recall/mrr"
```

---

### Task E2: 测试集生成器

**Files:**
- Create: `app/services/eval_testset.py`
- Test: `tests/services/test_eval_testset.py`

**Interfaces:**
- Consumes: `FaissStore` / `DocStore`（读取 chunk 与来源）、`LLMClient`
- Produces:
  - `async generate(limit=None) -> dict`（`{total, created}`）
  - `load() -> list[dict]`
  - `clear() -> None`

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_eval_testset.py
import json
import pytest
from app.services.eval_testset import TestSetGenerator

class FakeLLM:
    async def chat(self, prompt, system=None):
        return '{"question": "什么是RAG?"}'

def test_load_empty_returns_list(tmp_path):
    path = tmp_path / "testset.json"
    gen = TestSetGenerator(llm=FakeLLM(), testset_path=str(path),
                           chunks=[{"content": "chunk1", "source": "a.md", "index": 0}])
    assert gen.load() == []
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/services/test_eval_testset.py -v`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现**

```python
# app/services/eval_testset.py
import json
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)

GEN_PROMPT = """你正在为 RAG 知识库构建评测集。请根据下面这段文档内容，生成一个用户可能提出的问题。
文档来源：{source}
文档内容：{chunk}

请只以 JSON 输出：{{"question": "问题"}}
"""


class TestSetGenerator:
    def __init__(self, llm, testset_path: str = "data/eval_testset.json",
                 chunks: list | None = None, evaluate_every: int = 1):
        self.llm = llm
        self.testset_path = Path(testset_path)
        self.chunks = chunks or []
        self.evaluate_every = evaluate_every

    def load(self):
        if not self.testset_path.exists():
            return []
        with open(self.testset_path, encoding="utf-8") as f:
            return json.load(f)

    def clear(self):
        if self.testset_path.exists():
            self.testset_path.unlink()

    async def generate(self, limit: int | None = None):
        existing = self.load()
        seen_sources = {e["source_file"] for e in existing}
        created = 0
        for chunk in self.chunks:
            if limit is not None and created >= limit:
                break
            src = chunk.get("source") or chunk.get("source_file") or "unknown"
            if src in seen_sources:
                continue
            prompt = GEN_PROMPT.format(source=src, chunk=chunk["content"])
            try:
                text = await self.llm.chat(prompt)
                parsed = json.loads(text) if text.strip().startswith("{") else {}
                question = parsed.get("question", "")
            except Exception as e:
                logger.warning(f"Testset gen failed for {src}: {e}")
                question = ""
            if not question:
                continue
            existing.append({
                "question": question,
                "expected_answer": chunk["content"],
                "expected_source": src,
                "source_file": src,
            })
            seen_sources.add(src)
            created += 1
        with open(self.testset_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        return {"total": len(existing), "created": created}
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/services/test_eval_testset.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/eval_testset.py tests/services/test_eval_testset.py
git commit -m "feat: RAG 测试集自动生成"
```

---

### Task E3: 评测服务（策略对比 + 指标 + LLM judge）

**Files:**
- Create: `app/services/evaluation_service.py`
- Test: `tests/services/test_evaluation_service.py`

**Interfaces:**
- Consumes: `eval_metrics`（Task E1）、`TestSetGenerator`（Task E2）、`EmbeddingService`/`FaissStore`/`HybridRetriever`/`RerankService`/`LLMClient`
- Produces:
  - `async run(configs: list[dict]) -> dict`（返回各策略 Retrieval/Generation 指标与对比）
  - `list_reports() -> list[str]`
  - `get_report(name) -> dict`

- [ ] **Step 1: 写失败测试（先生成指标聚合逻辑）**

```python
# tests/services/test_evaluation_service.py
from app.services.evaluation_service import _aggregate_retrieval

def test_aggregate_retrieval():
    metrics = [
        {"hit": 1.0, "recall": 0.5, "mrr": 1.0},
        {"hit": 0.0, "recall": 0.25, "mrr": 0.5},
    ]
    agg = _aggregate_retrieval(metrics)
    assert agg["hit_rate"] == 0.5
    assert agg["recall"] == 0.375
    assert agg["mrr"] == 0.75
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/services/test_evaluation_service.py -v`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现评测服务**

```python
# app/services/evaluation_service.py
import json
import time
from pathlib import Path

from app.services.eval_metrics import hit_rate, recall_at_k, mrr
from app.utils.logger import get_logger

logger = get_logger(__name__)

REPORT_DIR = Path("data/eval_reports")

# LLM-as-judge 提示词
FAITHFULNESS_PROMPT = """根据上下文，判断回答是否忠于检索内容（无幻觉）。
上下文：{context}
回答：{answer}
请以 JSON 输出：{{"score": <0.0-1.0>}}
"""
ANSWER_RELEVANCE_PROMPT = """判断回答与问题的相关程度。
问题：{question}
回答：{answer}
请以 JSON 输出：{{"score": <0.0-1.0>}}
"""
CONTEXT_RELEVANCE_PROMPT = """判断检索上下文与问题的相关程度。
问题：{question}
上下文：{context}
请以 JSON 输出：{{"score": <0.0-1.0>}}
"""


def _aggregate_retrieval(metrics: list[dict]) -> dict:
    n = max(len(metrics), 1)
    return {
        "hit_rate": round(sum(m["hit"] for m in metrics) / n, 4),
        "recall": round(sum(m["recall"] for m in metrics) / n, 4),
        "mrr": round(sum(m["mrr"] for m in metrics) / n, 4),
        "samples": len(metrics),
    }


class EvaluationService:
    def __init__(self, llm, embedding, faiss, hybrid_retriever, reranker,
                 testset_path: str = "data/eval_testset.json", top_k: int = 5):
        self.llm = llm
        self.embedding = embedding
        self.faiss = faiss
        self.hybrid = hybrid_retriever
        self.reranker = reranker
        self.testset_path = Path(testset_path)
        self.top_k = top_k
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def _retrieve(self, query: str, use_hybrid: bool, use_rerank: bool) -> list[str]:
        """按配置检索，返回按相关性排序的来源文件列表。"""
        if use_hybrid and self.hybrid and self.hybrid.enabled:
            results = __import__("asyncio").get_event_loop().run_until_complete(
                self.hybrid.retrieve(query, top_k=20))
        else:
            import asyncio
            vec = asyncio.get_event_loop().run_until_complete(self.embedding.encode([query]))
            results = self.faiss.search(vec[0], 20)
        if use_rerank and self.reranker and self.reranker.enabled:
            docs = [r.content for r in results]
            reranked = __import__("asyncio").get_event_loop().run_until_complete(
                self.reranker.rerank(query, docs, top_k=self.top_k))
            content_idx = {r.content: r for r in results}
            ordered = [content_idx[rr.content] for rr in reranked if rr.content in content_idx]
        else:
            ordered = list(results)[:self.top_k]
        return [r.source_file for r in ordered]

    async def _judge(self, prompt) -> float:
        try:
            text = await self.llm.chat(prompt)
            data = json.loads(text)
            return max(0.0, min(1.0, float(data.get("score", 0))))
        except Exception as e:
            logger.warning(f"Judge failed: {e}")
            return 0.0

    async def run(self, configs: list[dict] | None = None) -> dict:
        testset = self._load_testset()
        if not testset:
            return {"error": "测试集为空，请先生成测试集"}
        default_cfgs = [
            {"name": "hybrid_rerank", "use_hybrid": True, "use_rerank": True},
            {"name": "dense_only", "use_hybrid": False, "use_rerank": False},
            {"name": "no_rerank", "use_hybrid": True, "use_rerank": False},
        ]
        configs = configs or default_cfgs
        report = {"timestamp": time.strftime("%Y%m%d_%H%M%S"), "configs": [], "total_questions": len(testset)}
        for cfg in configs:
            retrieval_metrics = []
            gen_faithfulness = gen_relevance = gen_context = []
            for item in testset:
                ranked = self._retrieve(item["question"], cfg["use_hybrid"], cfg["use_rerank"])
                expected = {item["expected_source"]}
                retrieval_metrics.append({
                    "hit": hit_rate(ranked, expected, self.top_k),
                    "recall": recall_at_k(ranked, expected, self.top_k),
                    "mrr": mrr(ranked, expected, self.top_k),
                })
                # 生成质量：用检索到的上下文让 LLM 生成回答，再 judge
                context = self._context_text(ranked)
                answer = await self._generate_answer(item["question"], context)
                gen_faithfulness.append(await self._judge(
                    FAITHFULNESS_PROMPT.format(context=context, answer=answer)))
                gen_relevance.append(await self._judge(
                    ANSWER_RELEVANCE_PROMPT.format(question=item["question"], answer=answer)))
                gen_context.append(await self._judge(
                    CONTEXT_RELEVANCE_PROMPT.format(question=item["question"], context=context)))
            report["configs"].append({
                "name": cfg["name"],
                "retrieval": _aggregate_retrieval(retrieval_metrics),
                "generation": {
                    "faithfulness": self._avg(gen_faithfulness),
                    "answer_relevance": self._avg(gen_relevance),
                    "context_relevance": self._avg(gen_context),
                },
            })
        self._save_report(report)
        return report

    def _load_testset(self):
        if not self.testset_path.exists():
            return []
        with open(self.testset_path, encoding="utf-8") as f:
            return json.load(f)

    async def _generate_answer(self, question, context):
        try:
            text = await self.llm.chat(f"参考资料：\n{context}\n\n问题：{question}")
            return text
        except Exception:
            return ""

    def _context_text(self, ranked_sources):
        # 简化：来源文件列表作为上下文占位；真实实现应取 chunk 内容
        return "\n".join(ranked_sources[:self.top_k])

    @staticmethod
    def _avg(values):
        return round(sum(values) / len(values), 4) if values else 0.0

    def _save_report(self, report):
        name = report["timestamp"] + ".json"
        with open(REPORT_DIR / name, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    def list_reports(self):
        return sorted(p.name for p in REPORT_DIR.glob("*.json"))

    def get_report(self, name):
        path = REPORT_DIR / name
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
```

> **Note for implementer**：`_retrieve` 中的 `run_until_complete` 是同步桥接，若评估在 async 上下文运行，建议改为把 `_retrieve` 改造成 async 并使用 `await`。保持 `run()` 为 async，让 `_retrieve` 也 async 更干净。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/services/test_evaluation_service.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 提交**

```bash
git add app/services/evaluation_service.py tests/services/test_evaluation_service.py
git commit -m "feat: RAG 评测服务（策略对比+LLM judge）"
```

---

### Task E4: 评测 API + 前端板块

**Files:**
- Create: `app/api/evaluation.py`
- Modify: `app/main.py`、`frontend/index.html`、`frontend/js/app.js`

**Interfaces:**
- Consumes: `EvaluationService`、`TestSetGenerator`
- Produces: 端点：
  - `POST /api/eval/generate-testset`（`{limit?}`）→ `{total, created}`
  - `POST /api/eval/run`（`{configs?}`）→ report
  - `GET /api/eval/reports` → `{reports: []}`
  - `GET /api/eval/reports/{name}` → report

- [ ] **Step 1: 实现 API**

```python
# app/api/evaluation.py
from fastapi import APIRouter, HTTPException

from app.api.schemas import BaseModel, Field


class GenTestsetRequest(BaseModel):
    limit: int | None = None


class RunEvalRequest(BaseModel):
    configs: list[dict] | None = None


router = APIRouter(prefix="/api/eval")


def _get_eval_service():
    from app.main import evaluation_service
    if evaluation_service is None:
        raise HTTPException(status_code=503, detail="Evaluation service not initialized")
    return evaluation_service


@router.post("/generate-testset")
async def generate_testset(req: GenTestsetRequest):
    try:
        from app.main import testset_generator
        return await testset_generator.generate(limit=req.limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_eval(req: RunEvalRequest):
    try:
        return await _get_eval_service().run(req.configs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports")
async def list_reports():
    return {"reports": _get_eval_service().list_reports()}


@router.get("/reports/{name}")
async def get_report(name: str):
    report = _get_eval_service().get_report(name)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
```

- [ ] **Step 2: 注册**

在 `app/main.py`：
- 导入 `from app.api.evaluation import router as evaluation_router`
- 导入 `from app.services.evaluation_service import EvaluationService`、`from app.services.eval_testset import TestSetGenerator`
- 全局变量 `evaluation_service`、`testset_generator`
- lifespan 内（`doc_store`/`embedding_service` 就绪后）：
```python
testset_generator = TestSetGenerator(
    llm=llm_client,
    chunks=doc_store.get_all_chunks() if hasattr(doc_store, "get_all_chunks") else [],
)
evaluation_service = EvaluationService(
    llm=llm_client, embedding=embedding_service, faiss=faiss_store,
    hybrid_retriever=hybrid_retriever, reranker=rerank_service)
```
- `app.include_router(evaluation_router)`

> **Note**：若 `DocStore` 无 `get_all_chunks`，则改为从 FAISS 索引读取 chunk + source（见 Task E5 的 `_load_chunks`）。

- [ ] **Step 3: 前端「RAG 评测」板块**

在 `frontend/index.html` 的设置页 `#view-index` 内追加一个卡片：

```html
<div class="card eval-card">
    <div class="card-header"><h3>RAG 评测</h3></div>
    <div class="card-body">
        <p class="card-desc">基于固定测试集量化检索与生成质量，对比不同检索策略。</p>
        <div class="button-group">
            <button class="btn-secondary" id="btn-gen-testset">生成测试集</button>
            <button class="btn-primary" id="btn-run-eval">运行评测</button>
        </div>
        <div class="eval-result" id="eval-result" style="display:none;"></div>
    </div>
</div>
```

在 `frontend/js/app.js` 追加：

```javascript
// ============ RAG Evaluation Module ============
const evalEls = {
    btnGen: document.getElementById('btn-gen-testset'),
    btnRun: document.getElementById('btn-run-eval'),
    result: document.getElementById('eval-result'),
};

if (evalEls.btnGen) {
    evalEls.btnGen.addEventListener('click', async () => {
        showToast('正在生成测试集...', 'info');
        const res = await fetch('/api/eval/generate-testset', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const data = await res.json();
        showToast(`测试集生成完成：${data.total} 条`, 'success');
    });
    evalEls.btnRun.addEventListener('click', async () => {
        evalEls.btnRun.disabled = true; evalEls.btnRun.textContent = '评测中...';
        try {
            const res = await fetch('/api/eval/run', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            const data = await res.json();
            renderEvalResult(data);
        } catch (e) { showToast('评测失败: ' + e.message, 'error'); }
        finally { evalEls.btnRun.disabled = false; evalEls.btnRun.textContent = '运行评测'; }
    });
}

function renderEvalResult(data) {
    if (data.error) { showToast(data.error, 'error'); return; }
    const rows = (data.configs || []).map(c => `
        <tr>
            <td>${c.name}</td>
            <td>${c.retrieval.hit_rate}</td><td>${c.retrieval.recall}</td><td>${c.retrieval.mrr}</td>
            <td>${c.generation.faithfulness}</td><td>${c.generation.answer_relevance}</td><td>${c.generation.context_relevance}</td>
        </tr>`).join('');
    evalEls.result.innerHTML = `
        <table class="eval-table"><thead><tr>
            <th>策略</th><th>Hit Rate</th><th>Recall</th><th>MRR</th>
            <th>Faithfulness</th><th>Answer Rel.</th><th>Context Rel.</th>
        </tr></thead><tbody>${rows}</tbody></table>`;
    evalEls.result.style.display = 'block';
}
```

追加样式 `.eval-table`（间距、边框、表头底色）到 `frontend/css/style.css`。

- [ ] **Step 4: 浏览器验证**

Run: 打开设置页 → 生成测试集 → 运行评测，查看对比表。
Expected: 评测运行并展示各策略指标

- [ ] **Step 5: 提交**

```bash
git add app/api/evaluation.py app/main.py frontend/index.html frontend/js/app.js frontend/css/style.css
git commit -m "feat: RAG 评测 API 与前端板块"
```

---

### Task E5: 补全 chunk 来源读取（评测上下文）

**Files:**
- Modify: `app/storage/faiss_store.py`（若已有 chunk 读取则跳过）、`app/services/evaluation_service.py`

**Interfaces:**
- Consumes: 现有 `FaissStore`
- Produces: `evaluation_service` 可读取 `(content, source_file)` 列表，用于测试集 chunk 与生成上下文

- [ ] **Step 1: 确认 FaissStore 是否暴露 chunk 列表**

Run: `Grep` `def ` in `app/storage/faiss_store.py`
若已有返回全部 chunk+source 的方法则直接复用；否则在 `evaluation_service.py` 增加：

```python
def _load_chunks(self):
    """从 FAISS 索引读取 (content, source_file)。"""
    chunks = []
    for i in range(self.faiss.size):
        r = self.faiss.get(i)
        if r:
            chunks.append({"content": r.content, "source": r.source_file})
    return chunks
```

- [ ] **Step 2: 将 `_load_chunks` 接入测试集生成**

把 `app/main.py` 中 `testset_generator` 的 `chunks` 改为 `evaluation_service._load_chunks()`（或等价实现）。

- [ ] **Step 3: 验证**

Run: 重新生成测试集，确认 `expected_source`/`source_file` 正确填充。
Expected: 测试集条目含真实来源文件

- [ ] **Step 4: 提交**

```bash
git add app/services/evaluation_service.py app/main.py app/storage/faiss_store.py
git commit -m "feat: 评测上下文chunk来源读取"
```

---

## 阶段三：Interview Agent（Planner 重构）

### 文件结构

| 文件 | 职责 |
|---|---|
| `app/services/interview_agent.py` | Agent 编排 + Planner 决策 + 工具接入 |
| `app/services/interview_service.py` | 重构为调用 Agent（保持 API 契约） |
| `app/services/deep_dive_service.py` | 作为 `ask_question` 的 deep_dive 分支被 Agent 调用 |

### Task A1: InterviewPlanner 决策器

**Files:**
- Create: `app/services/interview_agent.py`
- Test: `tests/services/test_interview_agent.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `PlannerContext` dataclass（`mode`、`total_answered`、`max_rounds`、`should_end`、`last_evaluation`）
  - `InterviewPlanner.decide(ctx) -> str`（`ask_question` / `evaluate_answer` / `retrieve_knowledge` / `generate_report`）

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_interview_agent.py
from app.services.interview_agent import InterviewPlanner, PlannerContext

def test_decide_ask_after_start():
    p = InterviewPlanner()
    ctx = PlannerContext(mode="interview", total_answered=0, max_rounds=15, should_end=False, last_evaluation=None)
    assert p.decide(ctx) == "ask_question"

def test_decide_report_when_last_should_end():
    p = InterviewPlanner()
    ctx = PlannerContext(mode="interview", total_answered=3, max_rounds=15,
                         should_end=True, last_evaluation={"should_end": True})
    assert p.decide(ctx) == "generate_report"

def test_decide_evaluate_after_answer():
    p = InterviewPlanner()
    ctx = PlannerContext(mode="interview", total_answered=1, max_rounds=15, should_end=False,
                         last_evaluation=None, pending_evaluation=True)
    assert p.decide(ctx) == "evaluate_answer"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/services/test_interview_agent.py -v`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现**

```python
# app/services/interview_agent.py
from dataclasses import dataclass, field


@dataclass
class PlannerContext:
    mode: str = "interview"          # interview | deep_dive
    total_answered: int = 0
    max_rounds: int = 15
    should_end: bool = False
    last_evaluation: dict | None = None
    pending_evaluation: bool = False  # 刚提交回答待评价


class InterviewPlanner:
    """根据当前状态决策下一个动作。"""

    def decide(self, ctx: PlannerContext) -> str:
        if ctx.pending_evaluation:
            return "evaluate_answer"
        if ctx.should_end or (ctx.last_evaluation and ctx.last_evaluation.get("should_end")):
            return "generate_report"
        if ctx.total_answered < ctx.max_rounds:
            return "ask_question"
        return "generate_report"
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/services/test_interview_agent.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add app/services/interview_agent.py tests/services/test_interview_agent.py
git commit -m "feat: InterviewPlanner 决策器"
```

---

### Task A2: InterviewAgent 编排层

**Files:**
- Create: `app/services/interview_agent.py`（追加 Agent 类）
- Test: `tests/services/test_interview_agent.py`

**Interfaces:**
- Consumes: `InterviewPlanner`、`InterviewService`、`DeepDiveService`（作为工具）
- Produces:
  - `InterviewAgent(context_builder, planner, tools)` 
  - `async step(ctx) -> dict`（执行决策动作，返回输出）

- [ ] **Step 1: 写失败测试**

```python
def test_agent_step_routes_to_ask():
    class FakeToolBox:
        def ask(self): return {"kind": "ask", "question_id": "q1"}
        def evaluate(self): return {"kind": "evaluate"}
        def retrieve(self): return {"kind": "retrieve"}
        def report(self): return {"kind": "report"}
    from app.services.interview_agent import InterviewAgent
    agent = InterviewAgent(tools=FakeToolBox())
    out = agent.run_action("ask_question")
    assert out["kind"] == "ask"
```

- [ ] **Step 2: 运行确认失败**

Expected: FAIL，`InterviewAgent` 不存在

- [ ] **Step 3: 实现 Agent 编排**

```python
# 追加到 app/services/interview_agent.py
class InterviewAgent:
    """顶层编排：汇聚上下文 → Planner 决策 → 执行工具。"""

    def __init__(self, planner=None, tools=None, context_builder=None):
        self.planner = planner or InterviewPlanner()
        self.tools = tools or {}
        self.context_builder = context_builder

    def run_action(self, action: str):
        """根据动作分派到对应工具。tools 为 {action: callable}。"""
        handler = self.tools.get(action)
        if handler is None:
            raise ValueError(f"No handler for action: {action}")
        return handler()

    async def step(self, ctx: PlannerContext) -> dict:
        action = self.planner.decide(ctx)
        return await self.run_action(action)

    def build_context(self, **kwargs) -> PlannerContext:
        if self.context_builder:
            return self.context_builder(**kwargs)
        return PlannerContext(**kwargs)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/services/test_interview_agent.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 提交**

```bash
git add app/services/interview_agent.py tests/services/test_interview_agent.py
git commit -m "feat: InterviewAgent 编排层"
```

---

### Task A3: 重构 InterviewService 接入 Planner（保持 API 契约）

**Files:**
- Modify: `app/services/interview_service.py`
- Test: `tests/services/test_interview_service.py`（新增回归）

**Interfaces:**
- Consumes: `InterviewAgent`（Task A2）
- Produces: 维持现有 `start`/`answer`/`end`/`get_report` 签名不变，内部用 Planner 决策，deep_dive 分支委派 `DeepDiveService`

- [ ] **Step 1: 写回归测试（现有契约不回退）**

```python
# tests/services/test_interview_service.py
import pytest
from app.services.interview_agent import InterviewPlanner, PlannerContext

def test_planner_wiring_keeps_contract():
    p = InterviewPlanner()
    # 模拟完成够题数但未达结束标志 → 仍出题
    ctx = PlannerContext(total_answered=5, max_rounds=15, should_end=False)
    assert p.decide(ctx) == "ask_question"
    # 达上限 → 报告
    ctx2 = PlannerContext(total_answered=15, max_rounds=15, should_end=False)
    assert p.decide(ctx2) == "generate_report"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/services/test_interview_service.py -v`
Expected: PASS（该测试本就应通过，作为契约锚点）

- [ ] **Step 3: 重构 InterviewService**

将 `InterviewService.start/answer/end` 改为内部持有 `self.agent`，在关键决策点调用 `self._decide_action(...)`：

```python
# interview_service.py 内新增
from app.services.interview_agent import InterviewAgent, InterviewPlanner, PlannerContext

def _build_agent(self):
    return InterviewAgent(
        planner=InterviewPlanner(),
        tools={
            "ask_question": self._tool_ask_question,
            "evaluate_answer": self._tool_evaluate_answer,
            "retrieve_knowledge": self._tool_retrieve_knowledge,
            "generate_report": self._tool_generate_report,
        },
    )

def _decide_action(self, mode, total_answered):
    ctx = PlannerContext(
        mode=mode, total_answered=total_answered,
        max_rounds=self.max_rounds, should_end=False,
        pending_evaluation=total_answered >= 1,
    )
    return self.agent.planner.decide(ctx)
```

> **实现原则**：`answer()` 内部在提交回答后先调用 `_decide_action("interview", total_rounds)`；若决策为 `generate_report` 则走 `_generate_report`；否则走 `_generate_question`。`generate_next` 逻辑保持不变。deep_dive 场景下 `start` 若 `mode="deep_dive"` 则把 `_generate_question` 替换为委托 `DeepDiveService` 的追问逻辑。保持对外 `answer` 返回结构不变。

- [ ] **Step 4: 运行回归**

Run: `python -m pytest tests/services/test_interview_service.py tests/services/test_interview_agent.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 端到端回归**

Run: 重启 uvicorn，走一遍普通面试 `start→answer→end→report`，确认行为与重构前一致。
Expected: 流程正常，报告可生成

- [ ] **Step 6: 提交**

```bash
git add app/services/interview_service.py app/services/interview_agent.py tests/services/test_interview_service.py
git commit -m "refactor: InterviewService 接入 Planner 编排"
```

---

## 自检对照

**Spec 覆盖：**
- 功能一（深挖）：D1 存储、D2 服务/状态机/恶劣面试官 prompt、D3 API、D4 前端、D5 兜底收尾 ✓
- 功能二（评测）：E1 指标、E2 测试集、E3 策略对比+LLM judge、E4 API+前端、E5 chunk 来源 ✓
- 功能三（Agent）：A1 Planner、A2 Agent、A3 重构保持契约、deep_dive 接入 ✓

**边界：** 阶段三是最大重构面，A3 明确"保持 API 契约 + 回归测试锚点"，避免破坏现有前端。

若执行中发现某阶段独立可交付性不足，可将阶段拆为独立计划文件再执行。