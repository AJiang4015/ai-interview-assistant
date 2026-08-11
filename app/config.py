from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    bailian_api_key: str
    bailian_model: str = "qwen3.7-max-2026-05-20"
    siliconflow_api_key: str
    siliconflow_model: str = "Qwen/Qwen3-Embedding-4B"
    knowledge_base_dir: str = "data/knowledge_base"
    index_path: str = "data/faiss_index"
    top_k: int = 5
    chunk_size: int = 1000
    chunk_overlap: int = 200
    llm_temperature: float = 0.7
    request_timeout: int = 30

    # Redis configuration
    redis_host: str = "192.168.127.101"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    session_ttl: int = 3600
    max_history_turns: int = 20

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def kb_path(self) -> Path:
        return PROJECT_ROOT / self.knowledge_base_dir

    @property
    def idx_path(self) -> Path:
        return PROJECT_ROOT / self.index_path


settings = Settings()