# api/server.py - FastAPI 主服务器 + WebSocket
"""
RPGAgent API 服务器
启动：python -m api.server
默认：http://localhost:7860
"""

import asyncio
import json
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

# 确保项目路径在 sys.path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from api.game_manager import get_manager
from api.routes import games
from config.settings import HOST, PORT

_static_dir = _project_root / "static"


# ─── 启动/关闭 ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[RPGAgent] 服务器启动中...")
    yield
    print(f"[RPGAgent] 服务器关闭")


# ─── FastAPI 应用 ──────────────────────────────────

app = FastAPI(
    title="RPGAgent API",
    description="RPG 游戏引擎接口",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games.router, prefix="/api")


# ─── 静态首页 ───────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(str(_static_dir / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(get_manager().list_active_sessions())}


# ─── WebSocket 实时叙事流 ──────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    manager = get_manager()
    session = manager.get_session(session_id)

    if not session:
        await websocket.accept()
        await websocket.send_json({"type": "error", "content": "会话不存在或已过期"})
        await websocket.close(code=4000)
        return

    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "无效的 JSON 格式"})
                continue

            action = msg.get("action", "")

            if action == "ping":
                await websocket.send_json({"type": "pong", "content": ""})
                continue

            if action == "player_input":
                content = msg.get("content", "").strip()
                if not content:
                    continue

                narrative, cmd = await manager.process_action(session_id, content)

                options = []
                if cmd and cmd.get("action") == "choice":
                    options = cmd.get("options", "").split("|")

                await websocket.send_json({
                    "type": "narrative",
                    "content": narrative,
                    "options": options,
                })

                stats = session.gm.stats_sys.get_snapshot()
                moral = session.gm.moral_sys.get_snapshot()
                await websocket.send_json({
                    "type": "status_update",
                    "content": "",
                    "extra": {
                        "hp": stats.get("hp", 0),
                        "max_hp": stats.get("max_hp", 0),
                        "stamina": stats.get("stamina", 0),
                        "max_stamina": stats.get("max_stamina", 0),
                        "moral_debt_level": moral.get("level", ""),
                        "moral_debt_value": moral.get("debt", 0),
                        "turn": session.turn,
                    },
                })

                if cmd and cmd.get("next_scene"):
                    await websocket.send_json({
                        "type": "scene_change",
                        "content": cmd.get("next_scene", ""),
                    })

            elif action == "get_status":
                stats = session.gm.stats_sys.get_snapshot()
                moral = session.gm.moral_sys.get_snapshot()
                await websocket.send_json({
                    "type": "status_update",
                    "content": "",
                    "extra": {
                        "hp": stats.get("hp", 0),
                        "max_hp": stats.get("max_hp", 0),
                        "stamina": stats.get("stamina", 0),
                        "max_stamina": stats.get("max_stamina", 0),
                        "moral_debt_level": moral.get("level", ""),
                        "moral_debt_value": moral.get("debt", 0),
                        "turn": session.turn,
                    },
                })

    except WebSocketDisconnect:
        pass


# ─── 启动 ──────────────────────────────────────────

def run(host: str = HOST, port: int = PORT):
    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
