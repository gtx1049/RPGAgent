# api/routes/replay.py - 剧情回放 API
"""
GET  /replay              - 获取当前游戏回放概览
GET  /replay/sessions     - 列出所有回放会话
GET  /replay/{session_id} - 获取指定会话的完整回放
GET  /replay/{session_id}/turn/{n} - 获取第 N 回合快照
GET  /replay/{session_id}/export  - 导出为 Markdown
POST /replay/start        - 开始一段新录制
POST /replay/stop         - 结束当前录制
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/replay", tags=["replay"])


def get_gm() -> "GameMaster":
    from rpgagent.api.game_manager import get_manager
    gm = get_manager().get_active_gm()
    if not gm:
        raise HTTPException(status_code=404, detail="当前无活跃游戏")
    return gm


class StartRecordingRequest(BaseModel):
    session_id: str
    act_title: str = ""


class StopRecordingRequest(BaseModel):
    final_ending: str = ""


@router.post("/start")
def start_recording(req: StartRecordingRequest):
    """开始一段新录制（通常在游戏开始时调用）"""
    gm = get_gm()
    if not hasattr(gm, "replay_sys"):
        raise HTTPException(status_code=500, detail="当前游戏未启用回放系统")

    session = gm.replay_sys.start_recording(
        session_id=req.session_id,
        game_id=gm.game_id,
        act_title=req.act_title or getattr(gm.session, "current_scene_id", "冒险记录"),
    )
    return {
        "message": "开始录制",
        "session_id": session.session_id,
        "started_at": session.started_at,
    }


@router.post("/stop")
def stop_recording(req: StopRecordingRequest = None):
    """结束当前录制"""
    gm = get_gm()
    if not hasattr(gm, "replay_sys"):
        raise HTTPException(status_code=500, detail="回放系统未启用")

    session = gm.replay_sys.stop_recording(
        final_ending=req.final_ending if req else None
    )
    if not session:
        raise HTTPException(status_code=404, detail="当前无活跃录制")

    return {
        "message": "录制已结束",
        "session_id": session.session_id,
        "total_turns": session.total_turns,
        "ended_at": session.ended_at,
    }


@router.get("")
def replay_overview():
    """获取当前游戏回放概览（不含完整叙事）"""
    gm = get_gm()
    if not hasattr(gm, "replay_sys"):
        raise HTTPException(status_code=500, detail="当前游戏未启用回放系统")

    active = gm.replay_sys.get_active_session()
    if not active:
        return {"is_recording": False, "message": "当前无活跃录制"}

    return {
        "is_recording": True,
        "session_id": active.session_id,
        "act_title": active.act_title,
        "started_at": active.started_at,
        "total_turns": active.total_turns,
    }


@router.get("/sessions")
def list_sessions():
    """列出所有回放会话"""
    gm = get_gm()
    if not hasattr(gm, "replay_sys"):
        raise HTTPException(status_code=500, detail="回放系统未启用")

    sessions = gm.replay_sys.get_all_sessions()
    return {
        "count": len(sessions),
        "sessions": [
            {
                "session_id": s.session_id,
                "game_id": s.game_id,
                "act_title": s.act_title,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "final_ending": s.final_ending,
                "total_turns": s.total_turns,
                "is_active": s.is_active(),
            }
            for s in sessions
        ],
    }


@router.get("/{session_id}")
def get_replay(session_id: str):
    """获取指定会话的完整回放"""
    gm = get_gm()
    if not hasattr(gm, "replay_sys"):
        raise HTTPException(status_code=500, detail="回放系统未启用")

    session = gm.replay_sys.get_replay(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="未找到该回放会话")

    return session.to_dict()


@router.get("/{session_id}/turn/{turn_num}")
def get_turn_record(session_id: str, turn_num: int):
    """获取第 N 回合的完整快照"""
    gm = get_gm()
    if not hasattr(gm, "replay_sys"):
        raise HTTPException(status_code=500, detail="回放系统未启用")

    session = gm.replay_sys.get_replay(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="未找到该回放会话")

    record = session.get_turn(turn_num)
    if not record:
        raise HTTPException(status_code=404, detail=f"未找到第 {turn_num} 回合记录")

    return record.to_dict()


@router.get("/{session_id}/summary")
def get_replay_summary(session_id: str):
    """获取回放概览（不含完整叙事）"""
    gm = get_gm()
    if not hasattr(gm, "replay_sys"):
        raise HTTPException(status_code=500, detail="回放系统未启用")

    summary = gm.replay_sys.get_replay_summary(session_id)
    if not summary:
        raise HTTPException(status_code=404, detail="未找到该回放会话")

    return summary


@router.get("/{session_id}/export")
def export_replay_markdown(session_id: str):
    """导出为 Markdown 可分享格式"""
    gm = get_gm()
    if not hasattr(gm, "replay_sys"):
        raise HTTPException(status_code=500, detail="回放系统未启用")

    md = gm.replay_sys.export_markdown(session_id)
    if md is None:
        raise HTTPException(status_code=404, detail="未找到该回放会话")

    return {"markdown": md}
