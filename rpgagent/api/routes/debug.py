# api/routes/debug.py - 开发者调试模式 API
"""
GET /games/{session_id}/debug
返回完整的调试状态：隐藏数值、行动点、骰点记录、场景触发、NPC关系等。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any

from ..game_manager import get_manager

router = APIRouter(prefix="/games", tags=["debug"])


class HiddenValueDebug(BaseModel):
    id: str
    name: str
    direction: str
    raw_value: int
    level_idx: int
    current_effect: dict
    trigger_fired: bool
    thresholds: list


class RecentRollDebug(BaseModel):
    attribute: str
    roll: int
    threshold: int
    modifier: int
    success: bool
    critical: bool
    fumble: bool
    tier: str
    description: str


class DebugResponse(BaseModel):
    session_id: str
    scene_id: str
    turn: int
    # 基础属性
    stats: dict
    # 隐藏数值
    hidden_values: dict[str, HiddenValueDebug]
    # 行动点
    action_power: int
    max_action_power: int
    # 最近骰点记录（存疑）
    recent_roll: Optional[dict] = None
    # 待触发场景
    pending_triggered_scenes: list[str]
    # NPC关系
    npc_relations: dict[str, dict]
    # 技能
    skills: list[dict]
    # 装备
    equipped: dict[str, Optional[dict]]
    # 标记
    flags: dict[str, Any]


@router.get("/{session_id}/debug", response_model=DebugResponse)
async def get_debug_info(session_id: str):
    """获取完整的调试状态（供开发者调试模式使用）"""
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    gm = session.gm

    # ── 隐藏数值 ───────────────────────────────────
    hidden_values = {}
    if gm.hidden_value_sys and gm.hidden_value_sys.values:
        for vid, hv in gm.hidden_value_sys.values.items():
            eff = hv.current_effect
            hidden_values[vid] = HiddenValueDebug(
                id=hv.id,
                name=hv.name,
                direction=hv.direction,
                raw_value=hv._compute_raw_value() if hasattr(hv, '_compute_raw_value') else 0,
                level_idx=hv.level_idx,
                current_effect={
                    "locked_options": eff.locked_options if eff else [],
                    "narrative_tone": eff.narrative_tone if eff else "",
                    "trigger_scene": eff.trigger_scene if eff else "",
                },
                trigger_fired=eff.trigger_fired if eff else False,
                thresholds=hv.thresholds,
            )

    # ── 最近骰点记录 ────────────────────────────────
    # 从 roll_sys 取最近的判定结果
    recent_roll = None
    if hasattr(gm.roll_sys, "_last_result") and gm.roll_sys._last_result:
        r = gm.roll_sys._last_result
        recent_roll = {
            "attribute": getattr(r, 'attribute_key', 'unknown'),
            "roll": r.roll,
            "threshold": r.threshold,
            "modifier": r.modifier,
            "success": r.success,
            "critical": r.critical,
            "fumble": r.fumble,
            "tier": r.tier.value if hasattr(r.tier, 'value') else str(r.tier),
            "description": r.description,
        }

    # ── 待触发场景 ─────────────────────────────────
    pending = []
    if gm.hidden_value_sys:
        pending = list(gm.hidden_value_sys.get_pending_triggered_scenes().keys())

    # ── NPC关系 ───────────────────────────────────
    npc_relations = {}
    for npc_id, rel_value in gm.dialogue_sys.relations.items():
        char = gm.game_loader.characters.get(npc_id)
        npc_relations[npc_id] = {
            "name": char.name if char else npc_id,
            "value": rel_value,
            "level": gm.dialogue_sys.get_relation_level(npc_id),
        }

    # ── 技能 ─────────────────────────────────────
    skills = gm.skill_sys.list_learned()

    # ── 装备 ──────────────────────────────────────
    equipped = gm.equipment_sys.get_equipped()

    # ── 标记 ──────────────────────────────────────
    flags = dict(session.flags) if hasattr(session, "flags") else {}

    stats = gm.stats_sys.get_snapshot()

    scene = gm.get_current_scene()

    return DebugResponse(
        session_id=session_id,
        scene_id=scene.id if scene else "unknown",
        turn=session.turn_count,
        stats=stats,
        hidden_values=hidden_values,
        action_power=stats.get("action_power", 0),
        max_action_power=stats.get("max_action_power", 3),
        recent_roll=recent_roll,
        pending_triggered_scenes=pending,
        npc_relations=npc_relations,
        skills=skills,
        equipped=equipped,
        flags=flags,
    )
