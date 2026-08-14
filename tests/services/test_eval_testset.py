import json
import pytest
from app.services.eval_testset import TestSetGenerator

class FakeLLM:
    async def chat(self, prompt, system=None):
        return '{"question": "什么是RAG?"}'

def make_gen(tmp_path):
    path = tmp_path / "testset.json"
    chunks = [
        {"content": "RAG通过检索增强生成", "source": "a.md"},
        {"content": "重排序提升相关性", "source": "b.md"},
    ]
    return TestSetGenerator(llm=FakeLLM(), testset_path=str(path), chunks=chunks)

def test_load_empty_returns_list(tmp_path):
    gen = make_gen(tmp_path)
    assert gen.load() == []

@pytest.mark.asyncio
async def test_generate_creates_entries(tmp_path):
    gen = make_gen(tmp_path)
    res = await gen.generate()
    assert res["created"] == 2
    assert res["total"] == 2
    items = gen.load()
    assert items[0]["expected_source"] == "a.md"
    assert items[0]["expected_answer"] == "RAG通过检索增强生成"
    assert items[0]["question"] == "什么是RAG?"

@pytest.mark.asyncio
async def test_generate_is_idempotent(tmp_path):
    gen = make_gen(tmp_path)
    await gen.generate()
    res = await gen.generate()  # 第二次应因 source 去重不新增
    assert res["created"] == 0
    assert res["total"] == 2

@pytest.mark.asyncio
async def test_generate_handles_llm_failure(tmp_path):
    class FailLLM:
        async def chat(self, prompt, system=None):
            raise RuntimeError("timeout")
    path = tmp_path / "t.json"
    gen = TestSetGenerator(llm=FailLLM(), testset_path=str(path),
                           chunks=[{"content": "c1", "source": "a.md"}])
    res = await gen.generate()
    assert res["created"] == 0 and res["total"] == 0

@pytest.mark.asyncio
async def test_generate_handles_fenced_json(tmp_path):
    class FenceLLM:
        async def chat(self, prompt, system=None):
            return '```json\n{"question": "什么是围栏JSON?"}\n```'
    path = tmp_path / "t.json"
    gen = TestSetGenerator(llm=FenceLLM(), testset_path=str(path),
                           chunks=[{"content": "c1", "source": "a.md"}])
    res = await gen.generate()
    assert res["created"] == 1
    items = gen.load()
    assert items[0]["question"] == "什么是围栏JSON?"

def test_clear(tmp_path):
    gen = make_gen(tmp_path)
    gen.clear()
    assert gen.load() == []