import asyncio
import json
from app.services.eval_testset import TestSetGenerator, _normalize_question

SEED = {
    "question": "Redis 为什么是单线程却还能这么快？",
    "expected_answer": "内存存储 + 高效数据结构 + 单线程无锁 + IO 多路复用。",
    "expected_source": ["Redis.md", "操作系统.md"],
    "source_file": "Redis.md",
    "question_type": "a",
}

VARIANTS = [
    "你说说 Redis 单线程咋还能这么快呗？",
    "面试官：Redis 不是单线程吗，凭什么性能这么高？",
    "Redis 为什么是单线程却还能这么快？",
]


class StubLLM:
    """返回固定的同义扩展问法，第 3 条与种子完全相同，用于验证防照抄过滤。"""
    async def chat(self, prompt, system=None):
        return json.dumps({"questions": VARIANTS}, ensure_ascii=False)


class FailLLM:
    async def chat(self, prompt, system=None):
        raise RuntimeError("timeout")


def write_seed(tmp_path):
    path = tmp_path / "testset.json"
    path.write_text(json.dumps([SEED], ensure_ascii=False), encoding="utf-8")
    return str(path)


def make_gen(tmp_path, llm=None):
    return TestSetGenerator(
        llm=llm or StubLLM(),
        testset_path=write_seed(tmp_path),
        chunks=[{"content": "chunk 原文不应出现在问题里", "source": "a.md"}],
    )


def test_load_empty_returns_list(tmp_path):
    gen = TestSetGenerator(llm=StubLLM(), testset_path=str(tmp_path / "t.json"))
    assert gen.load() == []


def test_normalize_question_strips_punct_and_case():
    assert _normalize_question("Redis 为什么这么快？ ") == _normalize_question("redis为什么这么快")


def test_generate_creates_variants_from_seed(tmp_path):
    gen = make_gen(tmp_path)
    res = asyncio.run(gen.generate())
    # 3 个候选中 1 条照抄种子被丢弃，应只创建 2 条
    assert res["created"] == 2
    assert res["total"] == 3
    items = gen.load()
    new_items = [e for e in items if e.get("origin") == "llm_extension"]
    assert len(new_items) == 2
    for e in new_items:
        # 答案/来源/类型继承种子，不依赖 chunk 文本
        assert e["expected_answer"] == SEED["expected_answer"]
        assert e["expected_source"] == SEED["expected_source"]
        assert e["source_file"] == SEED["source_file"]
        assert e["question_type"] == "a"
        assert e["question"] != SEED["question"]
        assert "chunk 原文" not in e["question"]


def test_generate_is_idempotent(tmp_path):
    gen = make_gen(tmp_path)
    asyncio.run(gen.generate())
    # 第二次：扩展条目不作为种子，已有问法全部去重
    res = asyncio.run(gen.generate())
    assert res["created"] == 0
    assert res["total"] == 3


def test_generate_handles_llm_failure(tmp_path):
    gen = make_gen(tmp_path, llm=FailLLM())
    res = asyncio.run(gen.generate())
    assert res["created"] == 0
    assert res["total"] == 1  # 种子仍在，文件不被破坏


def test_generate_handles_fenced_json(tmp_path):
    class FenceLLM:
        async def chat(self, prompt, system=None):
            return '```json\n{"questions": ["围栏 JSON 问法一？", "围栏 JSON 问法二？"]}\n```'
    gen = make_gen(tmp_path, llm=FenceLLM())
    res = asyncio.run(gen.generate())
    assert res["created"] == 2
    items = gen.load()
    assert items[1]["question"] == "围栏 JSON 问法一？"


def test_generate_limit_controls_creation(tmp_path):
    gen = make_gen(tmp_path)
    res = asyncio.run(gen.generate(limit=1))
    assert res["created"] == 1
    assert res["total"] == 2


def test_generate_dry_run_never_calls_llm(tmp_path):
    class GuardLLM:
        async def chat(self, prompt, system=None):
            raise AssertionError("dry-run 不应调用 LLM")
    gen = make_gen(tmp_path, llm=GuardLLM())
    res = asyncio.run(gen.generate(limit=0))
    assert res == {"total": 1, "created": 0}


def test_clear(tmp_path):
    gen = make_gen(tmp_path)
    gen.clear()
    assert gen.load() == []
