# 部署镜像：RAG 知识库 / Java 程序员智能面试助手
# 单 worker 约束（AGENTS.md §3）：state 与 faiss/index 落盘假定单进程，禁用多 worker
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖，利用构建缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用源码与前端静态资源
COPY app/ app/
COPY frontend/ frontend/
# data（知识库/FAISS/BM25/SQLite）通过 compose volume 挂载，不在镜像内固化

EXPOSE 8000

# 单 worker 启动（--workers 1，不用 --reload）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]