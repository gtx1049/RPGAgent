# api/routes/events.py - 动态世界事件 API
"""
GET  /events              - 获取世界事件系统概览（事件总数、已触发数、激活事件）
GET  /events/active       - 获取当前激活的事件列表
GET  /events/history      - 获取最近触发的事件记录
POST /events/evaluate     - 手动触发一次事件评估（返回将触发的事件，不实际触发）
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/events", tags=["events"])


def get_gm() -> "GameMaster":
    from rpgagent.api.game_manager import game_manager
    gm = game_manager.get_active_gm()
    if not gm:
        raise HTTPException(status_code=404, detail="当前无活跃游戏")
    return gm


@router.get("")
def world_events_overview():
    """获取世界事件系统总览"""
    gm = get_gm()
    if not gm.world_event_sys:
        raise HTTPException(status_code=404, detail="世界事件系统未启用")
    if not gm.world_event_sys.is_loaded():
        raise HTTPException(status_code=404, detail="当前剧本未配置世界事件")

    summary = gm.world_event_sys.get_event_summary()
    return {
        "message": "世界事件系统正常",
        **summary,
    }


@router.get("/active")
def active_events():
    """获取当前激活的事件列表"""
    gm = get_gm()
    if not gm.world_event_sys or not gm.world_event_sys.is_loaded():
        return {"active_events": [], "count": 0}

    active = gm.world_event_sys.get_active_events()
    return {
        "active_events": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.event_type,
                "brief_hint": e.brief_hint,
                "description": e.description,
                "inject_via": e.inject_via,
                "tags": e.tags,
            }
            for e in active
        ],
        "count": len(active),
    }


@router.get("/history")
def event_history(limit: int = 20):
    """获取最近触发的事件记录"""
    gm = get_gm()
    if not gm.world_event_sys or not gm.world_event_sys.is_loaded():
        return {"events": [], "total": 0}

    records = gm.world_event_sys.get_fired_records(limit=limit)
    return {
        "events": [
            {
                "event_id": r.event_id,
                "turn": r.turn,
                "scene_id": r.scene_id,
                "day": r.day,
                "period": r.period,
                "effects_summary": r.effects_summary,
            }
            for r in records
        ],
        "total": len(gm.world_event_sys._fired_ids),
    }


@router.post("/evaluate")
def evaluate_events():
    """
    手动触发一次事件评估。
    返回当前满足条件的事件列表（不实际触发，只评估）。
    """
    gm = get_gm()
    if not gm.world_event_sys or not gm.world_event_sys.is_loaded():
        raise HTTPException(status_code=404, detail="当前剧本未配置世界事件")

    fired = gm.world_event_sys.evaluate(
        day=gm.day_night_sys.get_day(),
        period=gm.day_night_sys.get_current_period(),
        turn=gm.session.turn_count,
        scene_id=gm.session.current_scene_id,
        hidden_values=gm.hidden_value_sys.get_snapshot() if gm.hidden_value_sys else {},
        factions=gm.faction_sys.get_all_reputations() if gm.faction_sys else {},
        flags=gm.session.flags,
    )

    return {
        "message": f"当前可触发 {len(fired)} 个事件",
        "events": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.event_type,
                "priority": e.priority,
                "description": e.description,
                "effects_count": len(e.effects),
            }
            for e in fired
        ],
        "current_state": {
            "day": gm.day_night_sys.get_day(),
            "period": gm.day_night_sys.get_current_period().value,
            "turn": gm.session.turn_count,
            "scene": gm.session.current_scene_id,
        },
    }
