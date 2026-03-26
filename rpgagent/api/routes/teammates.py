# api/routes/teammates.py - 队友系统 API 路由
from fastapi import HTTPException
from ..models import (
    TeammateProfile,
    TeammateState,
    TeammateRecruitRequest,
    TeammateDismissRequest,
    TeammateLoyaltyRequest,
    TeammateActionRequest,
)
from ..game_manager import get_manager

router = __import__("fastapi", fromlist=["APIRouter"]).APIRouter(prefix="/teammates", tags=["teammates"])


def _get_gm(session_id: str):
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return session.gm


# ─── 列出可招募队友 ─────────────────────────────────

@router.get("/{session_id}/available", response_model=list[TeammateProfile])
async def list_available_teammates(session_id: str):
    """返回当前剧本中所有可招募的队友配置（来自 recruitable=True 的 NPC）"""
    gm = _get_gm(session_id)
    profiles = gm.teammate_sys.list_profiles()
    return [TeammateProfile(**p) for p in profiles]


# ─── 列出当前队友 ─────────────────────────────────

@router.get("/{session_id}/active", response_model=list[TeammateState])
async def list_active_teammates(session_id: str):
    """返回当前已在队伍中的队友状态列表"""
    gm = _get_gm(session_id)
    active = gm.teammate_sys.list_active()
    return [TeammateState(**s) for s in active]


# ─── 招募队友 ─────────────────────────────────

@router.post("/{session_id}/recruit")
async def recruit_teammate(session_id: str, req: TeammateRecruitRequest):
    """
    招募一个可招募的 NPC 为队友。
    通过 GM_COMMAND 指令让 DM 在叙事中呈现招募结果。
    """
    gm = _get_gm(session_id)
    result = gm.teammate_sys.recruit(req.teammate_id)

    # 将招募结果写入 session flags，供前端感知
    gm.session.flags["_teammate_recruit"] = result

    # 同步到数据库
    gm._sync_session()

    if result["ok"]:
        return {
            "ok": True,
            "message": result["message"],
            "profile": result.get("profile"),
        }
    else:
        raise HTTPException(status_code=400, detail=result["message"])


# ─── 解散队友 ─────────────────────────────────

@router.post("/{session_id}/dismiss")
async def dismiss_teammate(session_id: str, req: TeammateDismissRequest):
    """
    主动解散队友（忠诚度-20，降至0则永久离队）。
    """
    gm = _get_gm(session_id)
    dismissed = gm.teammate_sys.dismiss(req.teammate_id)
    profile = gm.teammate_sys.get_profile(req.teammate_id)
    name = profile.name if profile else req.teammate_id

    result = {
        "teammate_id": req.teammate_id,
        "permanently_left": dismissed,
        "message": f"「{name}」离队了。" if dismissed else f"「{name}」的忠诚度下降了。",
    }
    gm.session.flags["_teammate_dismiss"] = result
    gm._sync_session()

    return result


# ─── 修改忠诚度 ─────────────────────────────────

@router.post("/{session_id}/loyalty")
async def modify_loyalty(session_id: str, req: TeammateLoyaltyRequest):
    """增减队友忠诚度（delta 可正可负）"""
    gm = _get_gm(session_id)
    new_val = gm.teammate_sys.modify_loyalty(req.teammate_id, req.delta)
    profile = gm.teammate_sys.get_profile(req.teammate_id)
    name = profile.name if profile else req.teammate_id
    gm.session.flags["_teammate_loyalty_msg"] = f"「{name}」忠诚度变为 {new_val}/100"
    gm._sync_session()
    return {"ok": True, "teammate_id": req.teammate_id, "name": name, "loyalty": new_val}


# ─── 队友回合行动 ─────────────────────────────────

@router.post("/{session_id}/act")
async def teammate_turn_act(session_id: str, req: TeammateActionRequest):
    """
    触发所有存活队友执行一回合行动。
    返回各队友的行动描述列表，供 DM 注入叙事。
    """
    gm = _get_gm(session_id)

    # 构造战场上下文
    combat_context = {
        "scene_id": gm.session.current_scene_id,
        "turn": gm.session.turn_count,
        "player_hp": gm.stats_sys.get("hp"),
        "player_max_hp": gm.stats_sys.get("max_hp"),
        "active_teammate_count": gm.teammate_sys.count_active(),
    }

    results = gm.teammate_sys.act_all(combat_context)

    # 刷新所有队友 AP（每个玩家回合只触发一次）
    gm.teammate_sys.refresh_all_ap()

    # 收集行动描述
    action_narratives = []
    for r in results:
        action = r["action"]
        state = r["state_snapshot"]
        # 构建行动描述
        desc = action.description if hasattr(action, "description") else str(action)
        dmg_info = ""
        if hasattr(action, "damage_dealt") and action.damage_dealt > 0:
            dmg_info = f"（造成 {action.damage_dealt} 点伤害）"
        elif hasattr(action, "stat_delta") and action.stat_delta:
            for k, v in action.stat_delta.items():
                if k == "heal_ally":
                    dmg_info = f"（为队友恢复 {v} HP）"

        action_narratives.append({
            "teammate_id": r["teammate_id"],
            "teammate_name": r["teammate_name"],
            "action_type": action.action_type if hasattr(action, "action_type") else "unknown",
            "description": desc,
            "damage_dealt": dmg_info,
            "state": state,
        })

    gm._sync_session()
    return {"ok": True, "actions": action_narratives}


# ─── 队友状态快照（用于存档） ─────────────────────────────────

@router.get("/{session_id}/snapshot")
async def get_teammate_snapshot(session_id: str):
    """获取所有队友状态快照，用于存档"""
    gm = _get_gm(session_id)
    return gm.teammate_sys.get_snapshot()
