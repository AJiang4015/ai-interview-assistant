from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    bailian_api_key: str
    bailian_model: str = "qwen-turbo"
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
    token_price: dict = {"qwen-turbo": {"input": 0.3, "output": 0.6},
                         "qwen-plus": {"input": 0.8, "output": 2.0}}  # 单价（元/百万tokens），按百炼刊例，上线前核实

    # ===== 面试/复习画像 =====
    # 今日一题在用户无历史数据、也无此前面试岗位记录时回退的全局默认岗位
    default_interview_position: str = "Java后端"
    # 面试追问环节（最多 5 层）默认不触发真实检索，仅用会话内已检索上下文；
    # 置 True 时追问层也走真实检索（供实验对比，受成本约束）。见 Part B spec §5.2
    enable_interview_followup_retrieval: bool = False
    # 存量旧面试数据的归属账号：启动时把 username='' 的场次认领到该账号；
    # 留空表示旧数据不被任何用户认领（对任何登录用户访问均返回 403）
    legacy_data_owner: str = ""

    # ===== Agent 编排（agent-dev，见 2026-08-31-agent-orchestration-refactor-impl-spec.md）=====
    # 面试实现选择：legacy（存量 InterviewService，默认）| agent（确定性编排 Agent）
    interview_mode: str = "legacy"
    # 附录 C 全局逃生舱上限（默认值 = spec §14 / 附录 C）
    agent_max_rounds: int = 15
    agent_max_structured_retries: int = 3
    agent_max_consecutive_failures: int = 3
    agent_max_total_fallbacks: int = 5
    agent_node_timeout_sec: int = 60
    agent_max_transitions: int = 200
    agent_max_reask_per_topic: int = 1
    # 附录 B 门禁参数
    agent_followup_enabled: bool = True
    agent_max_followup_depth: int = 1
    agent_max_answer_chars: int = 2000
    agent_max_context_chars: int = 4000
    # 附录 H trace
    agent_trace_dir: str = "data/traces"
    agent_trace_retention: int = 200
    # 附录 E5 模型分级（light→turbo / heavy→plus）
    agent_light_model: str = "qwen-turbo"
    agent_heavy_model: str = "qwen-plus"
    # 附录 A5 编排侧多方案并行（默认关）
    agent_parallel_candidates: bool = False

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