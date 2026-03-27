# RPGAgent Dockerfile
# 方案 C：Docker 一键部署
#
# 用法:
#   docker build -t rpgagent/agent:latest .
#   docker run -d -p 7860:7860 \
#       -v ~/.config/rpgagent:/root/.local/share/rpgagent \
#       rpgagent/agent:latest
#
# 或使用 docker-compose（见 docker-compose.yml）

FROM python:3.11-slim

LABEL maintainer="RPGAgent Team"
LABEL description="LLM-driven RPG game engine with hidden stat system"

# 安装系统依赖（curl 用于健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件
COPY pyproject.toml requirements.txt ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -e .

# 复制项目文件（仅运行时需要的部分）
COPY rpgagent/ rpgagent/
COPY static/ static/
COPY games/ games/

# 预创建数据目录
ENV RPGAGENT_BASE=/app
RUN mkdir -p ${RPGAGENT_BASE}/games ${RPGAGENT_BASE}/user_games

# 暴露端口
EXPOSE 7860

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# 默认启动命令（Web 服务器）
CMD ["python", "-m", "rpgagent.api.server"]
