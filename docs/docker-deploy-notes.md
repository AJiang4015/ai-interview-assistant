# Docker 部署知识笔记（基于本项目实际部署整理）

> 适用项目：RAG 知识库 / Java 程序员智能面试助手
> 来源：将本服务部署到虚拟机 `192.168.127.101` 的完整过程沉淀
> 定位：面向「只会 `docker run` 起服务的阶段」的读者，讲清 Docker 的核心概念、项目里的部署文件、实操命令与故障排查。

---

## 0. 一句话总结（先记住这个）

**代码 + 依赖 + 运行时被一起打成「镜像」；运行时由镜像创建出「容器」；`docker compose` 负责启动多个容器、用网络让它们互通、用健康检查控制启动顺序——各个容器各自隔离，但协作像一个整体。**

---

## 1. 核心概念

### 1.1 镜像（Image）与容器（Container）

| 概念 | 一句话 | 本项目的对应物 |
|---|---|---|
| **镜像 Image** | 只读的「模板 / 压缩包」，包含运行所需的一切 | `rag-app-rag-app`、`redis:7-alpine` |
| **容器 Container** | 由镜像创建出的「运行实例」，可启停删 | `rag-knowledge-assistant-app`、`-redis` |

- **镜像**：只读模板。不只是代码，而是 **代码 + Python 依赖 + Python 解释器 + 最小操作系统** 一层层叠起来（如图：`代码 → 依赖 → Python → 系统`）。它不运行。
- **容器**：由镜像 `docker run` 出来，正在运行的那个进程。同一镜像可启动多个容器，互不影响。
- 类比：镜像 = 软件安装包 / 光盘；容器 = 装上并运行的那个程序。
- **关键：单纯代码本身不能运行，靠的是镜像内部包含了完整环境。** 这就是「打包到 Docker 就能跑」的本质。

### 1.2 端口映射（ports）

容器有独立的网络，外部默认访问不进来，靠端口映射暴露：

```
"8000:8000"  →  把宿主的 8000 端口 转发到 容器内的 8000 端口
```

访问链路：`浏览器 → 192.168.127.101:8000 →(宿主 8000)→ 容器 8000 → uvicorn → 应用`。

### 1.3 数据卷（volume）

容器删除后内部文件系统会一起消失。重要数据（FAISS 索引、BM25、`.env` 密钥）绝不能随容器删除，所以用卷持久化：

```yaml
volumes:
  - ./data:/app/data    # VM 上的 ./data 挂载到容器里的 /app/data
```

容器读写 `/app/data` 实际是在读写 VM 真实磁盘。**容器删除、重建，数据仍在磁盘。**

### 1.4 网络（network）与 `depends_on`

多容器各自独立环境，靠 **Docker 内置虚拟网络**互通，用服务名代替 IP：

```yaml
depends_on:
  redis:
    condition: service_healthy   # 等 redis 健康后才启动应用
```

rag-app 容器里访问 `redis:6379`，会通过 Docker 内置 DNS 解析到 redis 容器——就像局域网里一台机器访问另一台。**每个容器环境仍隔离，只是网络互通。**

---

## 2. 本项目里的部署文件

| 文件 | 作用 | 关键点 |
|---|---|---|
| `Dockerfile` | 镜像的「菜谱」 | `FROM python:3.11-slim` → 基础镜像；`RUN pip install` → 装依赖；`COPY` → 拷代码；`CMD` → 启动命令 |
| `docker-compose.yml` | 多容器「总指挥」 | 定义 rag-app + redis 两个服务、端口、卷、启动顺序、健康检查 |
| `.dockerignore` | 构建排除项 | 排除 data/、.env、git、测试、docs 等，不固化进镜像 |

### 2.1 `Dockerfile` 关键行

```dockerfile
FROM python:3.11-slim           # 以官方 Python 3.11 镜像为底（需先从网上下载）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .          # 先装依赖，利用构建缓存
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/                   # 拷入代码
COPY frontend/ frontend/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
# --workers 1：符合项目「单进程约束」（state 与 faiss/index 落盘假定单进程）
```

### 2.2 `docker-compose.yml` 关键结构

```yaml
services:
  rag-app:
    build: .                     # 用当前目录 Dockerfile 构建镜像
    ports: ["8000:8000"]         # 端口映射
    volumes: ["./data:/app/data"] # 数据持久化
    env_file: [.env]             # 注入 API Key 等密钥
    depends_on:
      redis: { condition: service_healthy }
    healthcheck:                 # 容器自身健康检查（请求 /api/health）
      test: ["CMD", "python", "-c", "..."]

  redis:
    image: redis:7-alpine        # 直接用现成镜像，不构建
    command: ["redis-server", "--appendonly", "yes"]
    healthcheck:                 # 用 redis-cli ping
      test: ["CMD", "redis-cli", "ping"]
```

---

## 3. 部署到 192.168.127.101 的具体命令

### 第 1 步：本机（Windows / PowerShell）打包并传输

```powershell
cd e:\CodeField\RAGKonwLedge

# 打包：代码 + 数据(data) + 密钥(.env)，排除 git/测试/缓存
tar --exclude=.git --exclude=__pycache__ --exclude=*.pyc `
    --exclude=tests --exclude=docs --exclude=*.md `
    -czf rag-app.tar.gz app frontend data requirements.txt Dockerfile docker-compose.yml .dockerignore .env

# 传输到 VM（提示输入 root 密码）
scp rag-app.tar.gz root@192.168.127.101:/root/
```

> PowerShell 续行符是反引号 `` ` ``；也可以写在一行里。

### 第 2 步：登录 VM 并解压

```bash
ssh root@192.168.127.101
mkdir -p /root/rag-app
tar -xzf /root/rag-app.tar.gz -C /root/rag-app
ls /root/rag-app     # 确认有 app / data / frontend / Dockerfile / .env
```

### 第 3 步：构建并启动

```bash
cd /root/rag-app
docker compose up -d --build
```

### 第 4 步：验证

```bash
docker compose ps                                          # 两个容器：Up (healthy)
curl http://127.0.0.1:8000/api/health                      # 返回 status:ok 全绿
```
本机浏览器访问 `http://192.168.127.101:8000`。

### 重新部署 / 彻底重来

```bash
cd /root/rag-app
docker compose up -d --build    # 改代码后重新构建 + 热替换
docker compose down             # 停容器（data 卷仍在，不丢数据）
docker compose up -d --build    # 彻底重来后的再拉起
```

---

## 4. `docker compose` 子命令背后的底层逻辑

| compose 子命令 | 真正调用 | 作用 |
|---|---|---|
| `--build` | `docker build` | 执行 Dockerfile 构建镜像 |
| `up` | `docker run` 等 | 创建启动容器、建网络、挂卷 |
| `-d` | — | 后台运行，不霸占终端 |
| `ps` | `docker ps` | 查看容器状态 |
| `logs` | `docker logs` | 查看容器日志 |

**不用 compose 的「手工等价」**：

```bash
docker network create rag-net
docker run --network rag-net --name redis redis:7-alpine
docker run --network rag-net -p 8000:8000 -v ./data:/app/data rag-app-rag-app
```

compose 只是把这些命令写进 YAML，一条命令自动化。两个容器之间**不是"同一个环境"，而是"同一个网络"**。

---

## 5. 上线后报错排查（分层定位，别瞎猜）

**铁律：报错先看日志，后改代码；定位到根因再动手。**

### 排查决策流

```
服务报错
  ├─ 第1步 docker compose ps
  ├─ 第2步 容器 healthy?
  │    ├─ 否 → docker compose logs（找启动报错/崩溃）
  │    │        → 改代码/配置 → docker compose up -d --build
  │    │
  │    └─ 是 → 浏览器 / curl 访问接口（500?404?超时?）
  │            → docker compose logs -f（看运行时错误堆栈）
  │            → 定位根因 → 修复 → 回到第1步验证
```

### 场景 A：容器起不来 / 崩溃（Exit / Restarting）

```bash
cd /root/rag-app
docker compose ps                          # 看 STATUS 是否 Exit / Restarting / Unhealthy
docker compose logs --tail=100 rag-app     # 关键一步：看启动报错
```

常见原因与识别：
- `RedisError / MISCONF` → 连不上 Redis；检查 `.env` 的 `REDIS_HOST`、redis 容器是否 healthy。
- 报 JWT_SECRET 缺失 → 安全设计「密钥缺失拒绝启动」，补 `.env` 的 `JWT_SECRET`。
- `ImportError: No module named xxx` → 镜像依赖没装上，检查 `requirements.txt`。
- 反复 Restarting → 多为启动命令崩溃，看日志首条错误。

### 场景 B：容器 healthy 但接口 500 / 404

```bash
docker compose logs --tail=200 rag-app
```

`/api/health` 返回的字段可快速切分故障域：
- `redis_status: unavailable` → Redis 问题
- `embedding_service/llm_service: unavailable` → 外呼 API 失败（BAILIAN_API_KEY / SILICONFLOW_API_KEY 失效、额度）
- `faiss_index` 未加载 → 索引丢了，检查 `./data` 卷挂载与 `data/faiss_index`

### 场景 C：前端打不开 / 白屏

```bash
docker compose ps                    # 端口映射在否（0.0.0.0:8000->8000）
curl -I http://127.0.0.1:8000/       # VM 内部测；VM 通而本机不通 → 防火墙 / 端口占用
ss -tlnp | grep 8000
firewall-cmd --state                 # 部署后 firewall 需关或放行 8000
```

---

## 6. 上线后修改——改完如何生效

**核心区别：改的不是「正在跑的文件」，而是「镜像里的代码」。**

| 改什么 | 做法 | 是否重新构建 |
|---|---|---|
| 改 `.env` 配置 | 改 `.env` 后 `docker compose up -d`（环境变量重启即可） | **不必**（仅重启容器） |
| 改代码（app/ frontend/） | 本地改 → 传文件 → `docker compose up -d --build` | **必须**（代码打进镜像） |

规范做法：**本地改→重新传输→VM 重新 build**，避免在 VM 直接改导致和本地代码库不同步、改丢难找回。

```bash
# 改代码后
# 本机： scp app/services/xx.py root@192.168.127.101:/root/rag-app/app/services/
# VM：
cd /root/rag-app
docker compose up -d --build
```

### 进容器查看环境 / 文件（必要时）

```bash
docker exec -it rag-knowledge-assistant-app bash
ls /app                  # 看代码
echo $REDIS_HOST         # 看注入的环境变量
exit
```

---

## 7. 报错 → 处置速查表

| 现象 | 首要排查命令 | 最常见根因 |
|---|---|---|
| 容器 Exit / Restarting | `logs --tail=100` | 密钥缺失 / Redis 连不上 / 依赖没装 |
| 接口 500 | health 各字段 + logs | API Key 失效 / 索引损坏 |
| 前端白屏 | `curl -I /` | 端口映射丢失 / 防火墙 |
| 改了不生效 | 检查是否重新 build | 只传文件没重建镜像（改代码必 `--build`） |

---

## 8. 本次部署实际踩过的坑（经验）

1. **镜像下载慢 / 失败**：`python:3.11-slim` 拉取出现 `unexpected EOF`、反复 `Retrying`。原因是 VM 上 Docker 官方源不稳。解决办法：VM 已配置多个国内 `registry-mirrors`，**重试即可**；排查命令 `curl -s https://<mirror>/v2/library/python/manifests/3.11-slim`（返回 200 表示镜像源可用）。
2. **`.env` 必须真实存在**：缺失 `JWT_SECRET` 会拒绝启动；打包前确认含真实 API Key。
3. **compose 内置 Redis 不占宿主 6379**：redis 容器未映射宿主端口，与应用在同一个 Docker 网络内通信，与 VM 原有服务（如 Neo4j 的 7474/7687）无冲突。

---

## 9. 日常维护速记

```bash
cd /root/rag-app
docker compose ps             # 状态是否 Running / healthy
docker compose logs -f rag-app # 实时看应用日志（最常用）
docker compose up -d          # 重建镜像并启动
docker compose down           # 停止并移除容器（卷保留，数据不丢）
docker exec -it <容器名> bash  # 进入容器内部
```

---

> 建议：本文件为「部署 & 排障」知识沉淀，配合项目根 `AGENTS.md`（工程约定）与 `PROBLEM.md`（问题知识库）一并阅读。