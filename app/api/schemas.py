from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class SourceInfo(BaseModel):
    file: str
    chunk_index: int
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]
    retrieved_chunks: list[str]


class BuildIndexRequest(BaseModel):
    rebuild: bool = False


class BuildIndexResponse(BaseModel):
    status: str
    total_chunks: int
    files_processed: int


class IndexStatusResponse(BaseModel):
    index_exists: bool
    total_chunks: int
    last_build_time: str | None
    knowledge_base_files: list[str]


class HealthResponse(BaseModel):
    status: str
    faiss_index: str
    embedding_service: str
    llm_service: str