# api/routes/cg.py - CG 配图 API
"""
GET /api/sessions/{session_id}/cg
    返回当前会话的 CG 历史列表

GET /api/sessions/{session_id}/cg/latest
    返回最新生成的 CG（含 URL）
"""
import os
import hashlib
from fastapi import APIRouter, HTTPException
from ...config.settings import IMAGE_GENERATOR_CACHE_DIR
from ...api.game_manager import get_manager

router = APIRouter(prefix="/sessions", tags=["cg"])


def _cg_to_url(cg_path: str, base_url: str = "") -> str:
    """将本地 CG 路径转换为可访问的 URL"""
    if not cg_path:
        return ""
    filename = os.path.basename(cg_path)
    return f"{base_url}/cg/{filename}"


@router.get("/{session_id}/cg")
async def get_cg_history(session_id: str):
    """返回当前会话的 CG 历史"""
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    history = session.gm.session.cg_history or []
    result = []
    for item in history:
        cg_path = item.get("cg_path", "")
        result.append({
            "scene_id": item.get("scene_id", ""),
            "scene_title": item.get("scene_title", ""),
            "cg_path": cg_path,
            "cg_url": _cg_to_url(cg_path),
            "trigger": item.get("trigger", "unknown"),
        })
    return {
        "count": len(result),
        "cg_list": result,
    }


@router.get("/{session_id}/cg/latest")
async def get_latest_cg(session_id: str):
    """返回最新生成的 CG"""
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    cg_path = session.gm.session.scene_cg_path
    if not cg_path or not os.path.exists(cg_path):
        return {"has_cg": False}

    history = session.gm.session.cg_history or []
    latest = history[-1] if history else {}

    return {
        "has_cg": True,
        "cg_path": cg_path,
        "cg_url": _cg_to_url(cg_path),
        "scene_id": latest.get("scene_id", ""),
        "scene_title": latest.get("scene_title", ""),
    }
