class RAGSystemError(Exception):
    """系统基础异常"""


class IndexNotFoundError(RAGSystemError):
    """索引不存在"""


class EmbeddingAPIError(RAGSystemError):
    """Embedding API 调用失败"""


class LLMAPIError(RAGSystemError):
    """LLM API 调用失败"""


class IndexBuildError(RAGSystemError):
    """索引构建失败"""


class AuthorizationError(Exception):
    """数据归属授权失败：登录用户不可访问某个资源（映射 HTTP 403）。"""