# api/routes/achievements.py - 成就系统 API
"""
GET /api/sessions/{session_id}/achievements
    返回当前会话的成就列表（含已解锁/未解锁状态）

GET /api/sessions/{session_id}/achievements/unlocked
    仅返回已解锁成就列表
"""
from fastapi import APIRouter, HTTPException
from ...api.game_manager import get_manager

router = APIRouter(prefix="/sessions", tags=["achievements"])


@router.get("/{session_id}/achievements")
async def get_achievements(session_id: str):
    """返回当前会话的所有成就（含解锁状态）"""
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    ach_sys = session.gm.achievement_sys
    if not ach_sys:
        raise HTTPException(status_code=404, detail="成就系统未启用")

    return {
        "achievements": ach_sys.list_achievements(),
        "unlocked_count": len(ach_sys.get_unlocked()),
        "total_count": len(ach_sys._achievements),
    }


@router.get("/{session_id}/achievements/unlocked")
async def get_unlocked_achievements(session_id: str):
    """返回已解锁成就列表"""
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    ach_sys = session.gm.achievement_sys
    if not ach_sys:
        raise HTTPException(status_code=404, detail="成就系统未启用")

    unlocked = ach_sys.get_unlocked()
    return {
        "achievements": [
            {
                "id": u.achievement_id,
                "unlocked_at_turn": u.unlocked_at_turn,
                "scene_id": u.scene_id,
                "narrative": u.narrative,
            }
            for u in unlocked
        ],
        "count": len(unlocked),
    }
