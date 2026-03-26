# api/routes/logs.py - 冒险日志 REST API
"""
GET  /logs/{session_id}       - 列出当前剧本所有日志
GET  /logs/{session_id}/latest - 获取最新日志内容
GET  /logs/{session_id}/{filename} - 获取指定日志内容
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from config.settings import GAMES_DIR
import datetime

router = APIRouter(prefix="/logs", tags=["logs"])


class LogEntry(BaseModel):
    filename: str
    act_id: str
    act_title: str
    created_at: str
    path: str


class LogContent(BaseModel):
    filename: str
    content: str


def _get_log_dir(game_id: str) -> Path:
    return Path.home() / ".openclaw" / "RPGAgent" / "logs" / game_id


@router.get("/{session_id}", response_model=list[LogEntry])
async def list_logs(session_id: str):
    """列出当前剧本所有冒险日志"""
    from api.game_manager import get_manager

    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    log_dir = _get_log_dir(session.game_id)
    if not log_dir.exists():
        return []

    logs = []
    for f in sorted(log_dir.glob("act_*.md"), reverse=True):
        # 解析文件名: act_{act_id}_{timestamp}.md
        parts = f.stem.split("_")
        act_id = parts[1] if len(parts) > 1 else "?"
        act_title = " ".join(parts[2:]) if len(parts) > 2 else "冒险日志"

        # 读取文件前几行获取标题
        title_from_content = ""
        try:
            with open(f, "r", encoding="utf-8") as fh:
                first_line = fh.readline().strip()
                if first_line.startswith("#"):
                    title_from_content = first_line.lstrip("#").strip()
        except Exception:
            pass

        logs.append(LogEntry(
            filename=f.name,
            act_id=act_id,
            act_title=title_from_content or act_title,
            created_at=datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            path=str(f),
        ))

    return logs


@router.get("/{session_id}/latest", response_model=LogContent)
async def get_latest_log(session_id: str):
    """获取最新生成的冒险日志"""
    from api.game_manager import get_manager

    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    log_dir = _get_log_dir(session.game_id)
    if not log_dir.exists():
        raise HTTPException(status_code=404, detail="尚无冒险日志")

    files = sorted(log_dir.glob("act_*.md"), reverse=True)
    if not files:
        raise HTTPException(status_code=404, detail="尚无冒险日志")

    latest = files[0]
    try:
        with open(latest, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志失败: {e}")

    return LogContent(filename=latest.name, content=content)


@router.get("/{session_id}/{filename}", response_model=LogContent)
async def get_log(session_id: str, filename: str):
    """获取指定日志文件内容"""
    from api.game_manager import get_manager

    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 安全检查：禁止路径遍历
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    log_path = _get_log_dir(session.game_id) / filename
    if not log_path.exists() or not log_path.is_file():
        raise HTTPException(status_code=404, detail="日志文件不存在")

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志失败: {e}")

    return LogContent(filename=filename, content=content)
