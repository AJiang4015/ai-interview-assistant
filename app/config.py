from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    bailian_api_key: str
    bailian_model: str = "qwen3.7-max"
    siliconflow_api_key: str
    siliconflow_model: str = "Qwen/Qwen3-Embedding-4B"
    knowledge_base_dir: str = "data/knowledge_base"
    # 单进程约束：state 与 faiss/index 落盘假定单 worker，多 worker 部署需自行加进程级文件锁或换外部存储
    index_path: str = "data/faiss_index"
    top_k: int = 5
    chunk_size: int = 1000
    chunk_overlap: int = 200
    chunk_min_size: int = 100

    # ===== 大规模 RAG 检索配置 =====
    vector_index_type: str = "hnsw"      # flat | hnsw | ivf
    hnsw_m: int = 16
    hnsw_ef_construction: int = 200
    hnsw_ef_search: int = 64
    ivf_nlist: int = 200
    sparse_backend: str = "auto"          # memory | whoosh | sqlite_fts | auto
    concurrent_batches: int = 4
    enable_parent_expansion: bool = True
    # 单进程约束：state 与 faiss/index 落盘假定单 worker，多 worker 部署需自行加进程级文件锁或换外部存储
    ingest_state_path: str = "data/ingest_state.json"
    llm_temperature: float = 0.7
    request_timeout: int = 30

    # Redis configuration
    redis_host: str = "192.168.127.101"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    session_ttl: int = 3600
    max_history_turns: int = 20
    # 长期记忆持久化：开启时会话历史自 Redis 过期后可从 SQLite 恢复（按用户隔离）；关闭则只走 Redis
    enable_history_persistence: bool = True

# RAG pipeline 配置
    rerank_top_k: int = 5
    rerank_model: str = "Qwen/Qwen3-Reranker-4B"
    enable_query_rewrite: bool = True
    enable_hybrid_search: bool = True
    enable_rerank: bool = True
    enable_cache: bool = True
    bm25_index_path: str = "data/bm25_index.pkl"
    cache_ttl: int = 3600

    # ===== AI 可观测性配置 =====
    otel_enabled: bool = False
    otel_endpoint: str = "http://192.168.127.101:4318/v1/traces"
    sample_eval_rate: float = 0.05
    faithfulness_threshold: float = 0.6
    session_token_budget: float = 1.0
    token_price: dict = {"qwen3.7-max": {"input": 1.2, "output": 4.0}}

    # ===== 面试/复习画像 =====
    # 今日一题在用户无历史数据、也无此前面试岗位记录时回退的全局默认岗位
    default_interview_position: str = "Java后端"
    # 存量旧面试数据的归属账号：启动时把 username='' 的场次认领到该账号；
    # 留空表示旧数据不被任何用户认领（对任何登录用户访问均返回 403）
    legacy_data_owner: str = ""

    # ===== 认证与跨域 =====
    # JWT 签名密钥：生产必须通过 .env 提供（JWT_SECRET），缺失则拒绝启动，避免可预测的默认值
    jwt_secret: str
    # 允许跨域访问的前端来源白名单（JSON 数组字符串），生产按实际部署域名收紧
    cors_origins: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    # 问答/流式接口限流：每来源 IP 每分钟允许的最大请求数（按 IP 计，宽容值兼顾同 NAT 内多人）
    ratelimit_per_minute: int = 120

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def kb_path(self) -> Path:
        return PROJECT_ROOT / self.knowledge_base_dir

    @property
    def idx_path(self) -> Path:
        return PROJECT_ROOT / self.index_path


settings = Settings()