from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

REWRITE_PROMPT = (
    "你是一个检索助手。请将以下面试问题改写为更完整、更利于检索的表述，"
    "包含相关技术关键词，直接输出改写结果，不要多余内容：\n\n{question}"
)


class QueryRewriteService:
    def __init__(self, llm: LLMClient, enabled: bool = True):
        self._llm = llm
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def rewrite(self, question: str) -> str:
        if not self._enabled:
            return question
        try:
            prompt = REWRITE_PROMPT.format(question=question)
            rewritten = await self._llm.chat(prompt)
            rewritten = rewritten.strip().strip('"\'')
            logger.info(f"Query rewritten: '{question[:30]}...' -> '{rewritten[:50]}...'")
            return rewritten if rewritten else question
        except Exception as e:
            logger.warning(f"Query rewrite failed, using original: {e}")
            return question