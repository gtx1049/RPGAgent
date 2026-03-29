#!/bin/bash
cd /root/.openclaw/workspace/RPGAgent
source .env
exec ./venv/bin/uvicorn rpgagent.api.server:app --host 0.0.0.0 --port 8080
