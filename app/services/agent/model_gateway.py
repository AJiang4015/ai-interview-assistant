"""统一模型接入层（impl-spec v2 附录 E5 model_gateway；JD1-7；W2 上）。

职责（冻结约束，W0 OPEN-2 / B5）：
- 只负责：TaskSpec / light-heavy 分级策略 / qwen-turbo / qwen-plus 分级 / plus→turbo 降级链；
- **必须继续通过 LLMClient**（不引入第二套 HTTP 请求逻辑）；
- 使用 LLMClient 的 `chat(..., model=None)` 最小扩展（OPEN-2 冻结）；
- 成本经 `monitor.emit_cost` 在 LLMClient 内部按**实际模型名**记录；
- 跨供应商只保留 :class:`ProviderAdapter` 接口，不实现完整第二供应商（B5）。

对应关系（spec → 本模块）：
- 附录 E5 分级策略表：light（追问/出题）→ `qwen-turbo`；heavy（评估/报告）→ `qwen-plus`；
- 附录 E5 降级链：`qwen-plus` → `qwen-turbo` →（第三供应商接口预留）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol

from app.exceptions import LLMAPIError

LEVEL_LIGHT = "light"
LEVEL_HEAVY = "heavy"


@dataclass(frozen=True)
class TaskSpec:
    """一次模型调用规格（role_level 决定分级；schema 供结构化输出方使用，网关透传不消费）。"""

    role_level: str  # "light" | "heavy"
    prompt: str
    system: Optional[str] = None
    schema: Optional[dict] = None
    session_id: Optional[str] = None


@dataclass
class GenerationResult:
    """网关返回：文本 + 实际使用模型 + 降级次数 + 延迟。成本由 monitor/session_cost 记录。"""

    text: str
    model: str
    retries: int = 0
    latency_ms: int = 0
    cost: float = 0.0


class ProviderAdapter(Protocol):
    """供应商适配器接口（跨供应商仅预留接口，不实现完整第二供应商）。"""

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str: ...


class BailianAdapter:
    """Bailian 唯一实现：直接包装 LLMClient（复用其 retry / 成本 / 错误处理链路）。"""

    def __init__(self, llm_client: object):
        self._llm = llm_client

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        return await self._llm.chat(prompt, system=system, session_id=session_id, model=model)


class ModelGateway:
    """分级调用 + 降级链（light→turbo；heavy→plus→turbo）。"""

    def __init__(
        self,
        llm_client: object,
        *,
        light_model: str = "qwen-turbo",
        heavy_model: str = "qwen-plus",
        adapter: Optional[ProviderAdapter] = None,
        fallback_enabled: bool = True,
    ):
        self._adapter = adapter or BailianAdapter(llm_client)
        self._light_model = light_model
        self._heavy_model = heavy_model
        self._fallback_enabled = fallback_enabled

    def _chain(self, role_level: str) -> list[str]:
        """降级链：heavy=plus→turbo；light=turbo（已是链底）。"""
        if role_level == LEVEL_LIGHT:
            return [self._light_model]
        if self._fallback_enabled:
            return [self._heavy_model, self._light_model]
        return [self._heavy_model]

    async def generate(self, spec: TaskSpec) -> GenerationResult:
        """按分级链依次尝试；全部失败 → LLMAPIError（由上层走节点确定性兜底）。"""
        started = time.monotonic()
        chain = self._chain(spec.role_level)
        last_err: Optional[BaseException] = None
        for idx, model in enumerate(chain):
            try:
                text = await self._adapter.chat(
                    spec.prompt, system=spec.system, session_id=spec.session_id, model=model,
                )
                return GenerationResult(
                    text=text, model=model, retries=idx,
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            except Exception as e:  # noqa: BLE001 —— 降级链：失败继续尝试下一级
                last_err = e
        raise LLMAPIError(
            f"model gateway exhausted chain {chain} for level {spec.role_level}: {last_err}"
        ) from last_err
