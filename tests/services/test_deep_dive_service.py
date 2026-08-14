# tests/services/test_deep_dive_service.py
import pytest
from app.services.deep_dive_service import DeepDiveService

class FakeLLM:
    async def chat(self, prompt, system=None):
        return '{"question": "为什么不直接向量检索?", "score": 6, "can_answer": true}'

def make_service():
    import tempfile
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

@pytest.mark.asyncio
async def test_start_returns_session_and_first_question():
    svc = make_service()
    res = await svc.start("知识库问答", "Rerank", "构建问答系统")
    assert "session_id" in res and "question" in res and "id" in res["question"]

@pytest.mark.asyncio
async def test_answer_continue_returns_next_question():
    svc = make_service()
    s = await svc.start("知识库问答", "Rerank", "d")
    q1 = s["question"]
    res = await svc.answer(q1["id"], "因为要做相关性重排", "continue")
    assert res["is_complete"] is False
    assert "next_question" in res and res["next_question"]["round"] == 2

@pytest.mark.asyncio
async def test_answer_end_returns_summary():
    svc = make_service()
    s = await svc.start("P", "T", "d")
    res = await svc.answer(s["question"]["id"], "回答", "end")
    assert res["is_complete"] is True
    assert "summary" in res