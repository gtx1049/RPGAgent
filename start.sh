#!/bin/bash
cd /root/.openclaw/workspace/RPGAgent

# 加载 .env 文件中的环境变量
set -a
source .env
set +a

exec ./venv/bin/uvicorn rpgagent.api.server:app --host 0.0.0.0 --port 8080
