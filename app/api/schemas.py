from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, description="Session ID for multi-turn dialogue")


class SourceInfo(BaseModel):
    file: str
    chunk_index: int
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]
    retrieved_chunks: list[str]
    session_id: str | None = None


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
    redis_status: str = "disconnected"


# Session-related schemas

class CreateSessionRequest(BaseModel):
    session_id: str | None = Field(default=None, description="Custom session ID, auto-generated if not provided")


class SessionResponse(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    turn_count: int
    title: str | None = None


class SessionListResponse(BaseModel):
    total_sessions: int
    sessions: list[SessionResponse]


class MessageInfo(BaseModel):
    role: str
    content: str
    timestamp: str
    sources: list[dict] | None = None
    metadata: dict | None = None


class SessionHistoryResponse(BaseModel):
    session_id: str
    history: list[MessageInfo]
    total_turns: int


class DeleteSessionResponse(BaseModel):
    success: bool
    session_id: str


class ClearSessionsResponse(BaseModel):
    success: bool
    deleted_count: int


# ==================== Auth Schemas ====================

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)
    display_name: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    user: dict


class UserResponse(BaseModel):
    username: str
    display_name: str
    created_at: str | None = None


# ==================== File Management Schemas ====================

class FileInfo(BaseModel):
    filename: str
    size: int
    modified_time: str
    file_type: str


class FileListResponse(BaseModel):
    total_files: int
    files: list[FileInfo]


class FileUploadResponse(BaseModel):
    success: bool
    filename: str
    message: str
    index_rebuilt: bool = False
    total_chunks: int = 0


class FileDeleteResponse(BaseModel):
    success: bool
    filename: str
    message: str
    index_rebuilt: bool = False
    total_chunks: int = 0


# ==================== Search Schemas ====================

class SearchResultItem(BaseModel):
    session_id: str
    title: str | None = None
    role: str
    content: str
    content_snippet: str
    created_at: str | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResultItem]