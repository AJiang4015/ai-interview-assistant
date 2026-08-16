import asyncio

from app.services.eval_monitor import _parse_json, EvalMonitor


class FakeLLM:
    def __init__(self, text='{"score": 0.3}'):
        self.text = text

    async def chat(self, prompt, system=None):
        return self.text


def test_maybe_eval_low_score_returns_alert():
    m = EvalMonitor(FakeLLM(), sample_rate=1.0, threshold=0.6)
    assert m._evaluate_score('{"score": 0.3}') is True


def test_maybe_eval_high_score_no_alert():
    m = EvalMonitor(FakeLLM('{"score": 0.9}'), sample_rate=1.0, threshold=0.6)
    assert m._evaluate_score('{"score": 0.9}') is False


def test_evaluate_score_boundary_equal_threshold():
    m = EvalMonitor(FakeLLM(), sample_rate=1.0, threshold=0.6)
    # 等于阈值不告警
    assert m._evaluate_score('{"score": 0.6}') is False


def test_evaluate_score_clamps_out_of_range():
    m = EvalMonitor(FakeLLM(), sample_rate=1.0, threshold=0.6)
    assert m._evaluate_score('{"score": 1.5}') is False
    assert m._evaluate_score('{"score": -0.5}') is True


def test_evaluate_score_invalid_json_no_alert():
    m = EvalMonitor(FakeLLM(), sample_rate=1.0, threshold=0.6)
    assert m._evaluate_score("not json") is False


def test_evaluate_score_non_numeric_score_returns_false():
    m = EvalMonitor(FakeLLM(), sample_rate=1.0, threshold=0.6)
    assert m._evaluate_score('{"score": "abc"}') is False


def test_evaluate_score_fenced_json():
    m = EvalMonitor(FakeLLM(), sample_rate=1.0, threshold=0.6)
    assert _parse_json("```json\n{\"score\": 0.3}\n```") == {"score": 0.3}
    assert m._evaluate_score("Answer:\n```json\n{\"score\": 0.2}\n```") is True


def test_parse_json_none():
    assert _parse_json("") is None
    assert _parse_json("nothing here") is None


def test_maybe_eval_scores():
    m = EvalMonitor(FakeLLM('{"score": 0.3}'), sample_rate=1.0, threshold=0.6)
    score = asyncio.run(m.maybe_eval("q", "ctx", "ans"))
    assert score is not None


def test_maybe_eval_skipped_when_not_sampled():
    m = EvalMonitor(FakeLLM('{"score": 0.9}'), sample_rate=0.0, threshold=0.6)
    score = asyncio.run(m.maybe_eval("q", "ctx", "ans"))
    assert score is None


def test_maybe_eval_handles_llm_failure():
    class FailLLM:
        async def chat(self, prompt, system=None):
            raise RuntimeError("timeout")
    m = EvalMonitor(FailLLM(), sample_rate=1.0, threshold=0.6)
    score = asyncio.run(m.maybe_eval("q", "ctx", "ans"))
    assert score is None