# api/routes/exploration.py - 藏宝图/探索系统 API 路由
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/exploration", tags=["exploration"])


class ExplorationResultResponse(BaseModel):
    site_id: str
    site_name: str
    success: bool
    roll: int
    modifier: int
    total: int
    dc: int
    rewards: List[Dict[str, Any]]
    has_new_clue: bool


class ClueResponse(BaseModel):
    id: str
    name: str
    clue_text: str
    location_hint: str


@router.get("/{session_id}/clues")
async def get_player_clues(session_id: str) -> List[ClueResponse]:
    """返回玩家当前持有的所有藏宝线索"""
    from ..game_manager import get_manager
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    clues = session.gm.explore_sys.get_player_clues()
    return [
        ClueResponse(
            id=s.id,
            name=s.name,
            clue_text=s.clue_text,
            location_hint=s.location_hint,
        )
        for s in clues
    ]


@router.get("/{session_id}/summary")
async def get_exploration_summary(session_id: str) -> Dict[str, Any]:
    """获取探索系统状态摘要"""
    from ..game_manager import get_manager
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return session.gm.explore_sys.get_exploration_summary()


@router.post("/{session_id}/explore/{site_id}")
async def explore_treasure(
    session_id: str,
    site_id: str,
) -> ExplorationResultResponse:
    """
    对指定宝藏进行探索（骰点判定）。
    直接触发探索判定，返回结果（含奖励发放）。
    """
    from ..game_manager import get_manager
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    site = session.gm.explore_sys.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"找不到宝藏：{site_id}")

    result = session.gm.explore_sys.explore(
        site_id=site_id,
        stats_sys=session.gm.stats_sys,
        skill_sys=session.gm.skill_sys,
        turn=session.gm.session.turn_count,
    )

    # 发放奖励
    if result.success:
        for reward in result.rewards_given:
            if reward.type == "gold":
                session.gm.stats_sys.modify("gold", reward.quantity)
            elif reward.type == "equipment" and reward.id:
                from rpgagent.systems.equipment_system import get_template_equipment
                equip = get_template_equipment(reward.id)
                if equip:
                    session.gm.acquisition_sys.grant_equipment(equip)
                    current_eq = session.gm.equipment_sys.equipped.get(equip.slot)
                    if current_eq is None:
                        session.gm.equipment_sys.equip(equip)
            elif reward.type == "intel" and reward.id:
                session.gm.explore_sys.grant_clue(reward.id)

    return ExplorationResultResponse(
        site_id=site_id,
        site_name=result.site.name if result.site else site_id,
        success=result.success,
        roll=result.roll,
        modifier=result.modifier,
        total=result.total,
        dc=result.dc,
        rewards=[
            {"type": r.type, "name": r.name, "quantity": r.quantity}
            for r in result.rewards_given
        ],
        has_new_clue=result.new_clue is not None,
    )


@router.get("/{session_id}/sites")
async def list_treasure_sites(
    session_id: str,
    include_excavated: bool = False,
) -> List[Dict[str, Any]]:
    """列出所有宝藏地点状态"""
    from ..game_manager import get_manager
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    sites = session.gm.explore_sys.get_all_sites(include_excavated=include_excavated)
    return [
        {
            "id": s.id,
            "name": s.name,
            "difficulty": s.difficulty,
            "difficulty_label": s.get_difficulty_label(),
            "attribute_key": s.attribute_key,
            "discovered": s.discovered,
            "excavated": s.excavated,
        }
        for s in sites
    ]
