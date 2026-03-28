# api/routes/stats.py - 游戏统计面板 API
"""
GET /api/sessions/{session_id}/stats
    返回当前会话的完整统计数据面板

统计维度：
- 游戏概览（回合数、天数、时长）
- 战斗统计（战斗次数、胜率、伤害）
- 对话选择分布（战斗/外交/探索/其他）
- 道德债务变化曲线
- 阵营声望变化
- NPC关系分布
- 场景探索率
- 隐藏数值轨迹
- 队友状态
- 技能/装备获取时间线
- 成就进度
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any

router = APIRouter(prefix="/sessions", tags=["stats"])


# ─── 响应模型 ────────────────────────────────────────


class GameOverview(BaseModel):
    turn_count: int
    current_scene: str
    scene_title: str
    current_day: int
    current_period: str
    level: int
    gold: int


class CombatStats(BaseModel):
    battles_started: int = 0
    battles_won: int = 0
    battles_lost: int = 0
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    kills: int = 0
    deaths: int = 0
    win_rate: float = 0.0


class DialogueDistribution(BaseModel):
    combat_actions: int = 0
    diplomatic_actions: int = 0
    exploration_actions: int = 0
    other_actions: int = 0
    total: int = 0
    breakdown: dict[str, int] = {}


class MoralDebtHistory(BaseModel):
    current: int
    current_level: str
    peak: int
    events: list[dict] = []


class FactionReputationSummary(BaseModel):
    factions: list[dict]
    most_hostile: Optional[str] = None
    most_friendly: Optional[str] = None


class NPCRelationSummary(BaseModel):
    total_npcs: int
    allies: int = 0  # value >= 30
    neutral: int = 0  # -29 <= value <= 29
    hostile: int = 0  # value <= -30
    best_relation: Optional[dict] = None
    worst_relation: Optional[dict] = None


class SceneVisit(BaseModel):
    scene_id: str
    scene_title: str
    first_visited_turn: int = 0
    visits: int = 0


class ExplorationStats(BaseModel):
    total_scenes: int
    visited_scenes: int
    visit_rate: float = 0.0
    scenes: list[SceneVisit] = []


class HiddenValueTrajectory(BaseModel):
    id: str
    name: str
    current: int = 0
    peak: int = 0
    trough: int = 0
    history: list[dict] = []


class TeammateStats(BaseModel):
    recruited_count: int = 0
    current_count: int = 0
    members: list[dict] = []


class SkillAcquisition(BaseModel):
    total_skills: int
    total_skill_points_spent: int
    skills: list[dict] = []


class EquipmentHistory(BaseModel):
    total_equipped: int
    current_equipped: list[dict] = []


class AchievementStats(BaseModel):
    total: int
    unlocked: int
    unlock_rate: float = 0.0
    recently_unlocked: list[dict] = []


class GameStatsResponse(BaseModel):
    session_id: str
    game_id: str
    player_name: str
    overview: GameOverview
    combat: CombatStats
    dialogue: DialogueDistribution
    moral_debt: MoralDebtHistory
    factions: FactionReputationSummary
    npc_relations: NPCRelationSummary
    exploration: ExplorationStats
    hidden_values: list[HiddenValueTrajectory]
    teammates: TeammateStats
    skills: SkillAcquisition
    equipment: EquipmentHistory
    achievements: AchievementStats


# ─── 工具函数 ────────────────────────────────────────


def _classify_action(content: str) -> str:
    """根据行动内容关键词分类"""
    content_lower = content.lower()
    if any(k in content_lower for k in ["攻击", "战斗", "杀", "打", "砍", "揍", "打倒", "杀死", "combat", "fight", "kill", "attack"]):
        return "combat"
    if any(k in content_lower for k in ["说", "谈", "问", "答", "说服", "欺骗", "贿赂", "讨好", "谈", "聊", "dialogue", "talk", "ask", "persuade", "convince", "bribe", "flatter"]):
        return "diplomatic"
    if any(k in content_lower for k in ["找", "探索", "查看", "调查", "搜", "翻", "走", "探索", "explore", "search", "look", "find", "check", "investigate"]):
        return "exploration"
    return "other"


# ─── 路由 ────────────────────────────────────────


@router.get("/{session_id}/stats", response_model=GameStatsResponse)
async def get_game_stats(session_id: str):
    """
    返回当前会话的完整游戏统计数据。
    """
    from ...api.game_manager import get_manager

    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    gm = session.gm
    history = gm.session.history

    # ── 概览 ────────────────────────────────
    scene = gm.get_current_scene()
    stats = gm.stats_sys.get_snapshot()
    moral = gm.moral_sys.get_snapshot()
    overview = GameOverview(
        turn_count=gm.session.turn_count,
        current_scene=gm.session.current_scene_id,
        scene_title=scene.title if scene else "?",
        current_day=gm.day_night_sys.get_day(),
        current_period=gm.day_night_sys.get_current_period().value,
        level=stats.get("level", 1),
        gold=stats.get("gold", 0),
    )

    # ── 对话/行动分布（从 history 分析）─────────
    combat_count = 0
    diplomatic_count = 0
    exploration_count = 0
    other_count = 0
    for entry in history:
        if entry.get("role") == "player":
            content = entry.get("content", "")
            cat = _classify_action(content)
            if cat == "combat":
                combat_count += 1
            elif cat == "diplomatic":
                diplomatic_count += 1
            elif cat == "exploration":
                exploration_count += 1
            else:
                other_count += 1

    total_actions = combat_count + diplomatic_count + exploration_count + other_count
    dialogue_dist = DialogueDistribution(
        combat_actions=combat_count,
        diplomatic_actions=diplomatic_count,
        exploration_actions=exploration_count,
        other_actions=other_count,
        total=total_actions,
        breakdown={
            "combat": combat_count,
            "diplomatic": diplomatic_count,
            "exploration": exploration_count,
            "other": other_count,
        },
    )

    # ── 战斗统计（从 flags 累积）────────────────
    battles_started = gm.session.flags.get("_combat_count", 0)
    battles_won = gm.session.flags.get("_combat_wins", 0)
    battles_lost = gm.session.flags.get("_combat_losses", 0)
    total_damage_dealt = gm.session.flags.get("_total_damage_dealt", 0)
    total_damage_taken = gm.session.flags.get("_total_damage_taken", 0)
    kills = gm.session.flags.get("_kills", 0)
    deaths = gm.session.flags.get("_deaths", 0)
    win_rate = (battles_won / battles_started * 100) if battles_started > 0 else 0.0

    combat_stats = CombatStats(
        battles_started=battles_started,
        battles_won=battles_won,
        battles_lost=battles_lost,
        total_damage_dealt=total_damage_dealt,
        total_damage_taken=total_damage_taken,
        kills=kills,
        deaths=deaths,
        win_rate=round(win_rate, 1),
    )

    # ── 道德债务历史 ────────────────────────────
    moral_history = moral.get("history", []) if isinstance(moral, dict) else []
    debt_events = []
    peak_debt = 0
    for ev in moral_history[-20:]:
        amount = ev.get("amount", 0)
        if amount > 0:  # 正向为增加债务
            peak_debt = max(peak_debt, abs(amount))
        debt_events.append({
            "turn": ev.get("turn", 0),
            "amount": amount,
            "source": ev.get("source", ""),
            "description": ev.get("description", ""),
        })

    current_debt = moral.get("debt", 0) if isinstance(moral, dict) else 0
    current_level = moral.get("level", "无债") if isinstance(moral, dict) else "无债"
    moral_debt = MoralDebtHistory(
        current=current_debt,
        current_level=current_level,
        peak=peak_debt,
        events=debt_events,
    )

    # ── 阵营声望 ──────────────────────────────
    all_reps = gm.faction_sys.get_all_reputations()
    faction_list = []
    most_hostile = None
    most_friendly = None
    min_rep = 101
    max_rep = -101

    for fid, info in all_reps.items():
        faction_list.append(info)
        val = info.get("value", 0)
        if val < min_rep:
            min_rep = val
            most_hostile = fid
        if val > max_rep:
            max_rep = val
            most_friendly = fid

    factions_summary = FactionReputationSummary(
        factions=faction_list,
        most_hostile=most_hostile,
        most_friendly=most_friendly,
    )

    # ── NPC 关系分布 ───────────────────────────
    all_relations = gm.dialogue_sys.get_all_relations()
    allies = 0
    neutral = 0
    hostile = 0
    best_rel = None
    worst_rel = None
    best_val = -999
    worst_val = 999

    for npc_id, rel_data in all_relations.items():
        val = rel_data.get("value", 0)
        char = gm.game_loader.characters.get(npc_id)
        name = char.name if char else npc_id
        entry = {"npc_id": npc_id, "name": name, "value": val, "level": rel_data.get("level", "陌生")}
        if val >= 30:
            allies += 1
        elif val <= -30:
            hostile += 1
        else:
            neutral += 1
        if val > best_val:
            best_val = val
            best_rel = entry
        if val < worst_val:
            worst_val = val
            worst_rel = entry

    npc_relation_summary = NPCRelationSummary(
        total_npcs=len(all_relations),
        allies=allies,
        neutral=neutral,
        hostile=hostile,
        best_relation=best_rel,
        worst_relation=worst_rel,
    )

    # ── 场景探索 ───────────────────────────────
    visited = getattr(gm.session, "visited_scenes", set())
    visited.add(gm.session.current_scene_id)
    all_scenes = list(gm.game_loader.scenes.keys()) if hasattr(gm.game_loader, "scenes") else []
    visited_list = []
    for sid in visited:
        s = gm.game_loader.get_scene(sid)
        visited_list.append(SceneVisit(
            scene_id=sid,
            scene_title=s.title if s else sid,
            first_visited_turn=0,
            visits=1,
        ))

    exploration = ExplorationStats(
        total_scenes=len(all_scenes),
        visited_scenes=len(visited_list),
        visit_rate=round(len(visited_list) / max(len(all_scenes), 1) * 100, 1),
        scenes=visited_list,
    )

    # ── 隐藏数值轨迹 ───────────────────────────
    hv_trajectories = []
    if gm.hidden_value_sys:
        hv_snap = gm.hidden_value_sys.get_snapshot()
        for hv_id, hv_data in hv_snap.items():
            if isinstance(hv_data, dict):
                hv_trajectories.append(HiddenValueTrajectory(
                    id=hv_id,
                    name=hv_data.get("name", hv_id),
                    current=hv_data.get("current", hv_data.get("level_idx", 0)),
                    peak=hv_data.get("peak", 0),
                    trough=hv_data.get("trough", 0),
                    history=hv_data.get("recent_records", [])[-20:],
                ))

    # ── 队友统计 ───────────────────────────────
    tm_snap = gm.teammate_sys.get_snapshot()
    tm_members = tm_snap.get("members", [])
    teammate_stats = TeammateStats(
        recruited_count=tm_snap.get("recruited_count", 0),
        current_count=len(tm_members),
        members=tm_members,
    )

    # ── 技能获取 ───────────────────────────────
    learned = gm.skill_sys.learned
    skill_list = []
    total_spent = 0
    for skill_id, rank in learned.items():
        skill = gm.skill_sys.book.get(skill_id)
        if skill:
            skill_list.append({
                "id": skill_id,
                "name": skill.name,
                "rank": rank,
                "max_rank": skill.max_rank,
                "type": skill.type,
            })
            total_spent += rank

    skill_stats = SkillAcquisition(
        total_skills=len(skill_list),
        total_skill_points_spent=total_spent,
        skills=skill_list,
    )

    # ── 装备当前状态 ───────────────────────────
    equip_snap = gm.equipment_sys.get_snapshot()
    equipped = equip_snap.get("equipped", {})
    current_equipped = []
    for slot, item in equipped.items():
        if item:
            current_equipped.append({
                "slot": slot,
                "name": item.get("name", ""),
                "rarity": item.get("rarity", "common"),
            })

    equipment_stats = EquipmentHistory(
        total_equipped=len([v for v in equipped.values() if v]),
        current_equipped=current_equipped,
    )

    # ── 成就统计 ───────────────────────────────
    ach_unlocked = gm.achievement_sys.get_unlocked()
    total_ach = len(gm.achievement_sys._achievements)
    unlocked_ach = len(ach_unlocked)
    recent_ach = [
        {
            "id": u.achievement_id,
            "unlocked_at_turn": u.unlocked_at_turn,
            "scene_id": u.scene_id,
        }
        for u in ach_unlocked[-5:]
    ]
    achievement_stats = AchievementStats(
        total=total_ach,
        unlocked=unlocked_ach,
        unlock_rate=round(unlocked_ach / max(total_ach, 1) * 100, 1),
        recently_unlocked=recent_ach,
    )

    return GameStatsResponse(
        session_id=session_id,
        game_id=session.game_id,
        player_name=session.player_name,
        overview=overview,
        combat=combat_stats,
        dialogue=dialogue_dist,
        moral_debt=moral_debt,
        factions=factions_summary,
        npc_relations=npc_relation_summary,
        exploration=exploration,
        hidden_values=hv_trajectories,
        teammates=teammate_stats,
        skills=skill_stats,
        equipment=equipment_stats,
        achievements=achievement_stats,
    )


@router.get("/{session_id}/stats/overview")
async def get_stats_overview(session_id: str):
    """
    轻量版统计概览：单次请求返回核心指标（用于前端状态栏实时显示）
    """
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    gm = session.gm
    stats = gm.stats_sys.get_snapshot()
    moral = gm.moral_sys.get_snapshot()

    # 从 history 快速统计行动类型
    total = len([e for e in gm.session.history if e.get("role") == "player"])
    combat = len([e for e in gm.session.history if e.get("role") == "player" and _classify_action(e.get("content", "")) == "combat"])

    return {
        "session_id": session_id,
        "turn": gm.session.turn_count,
        "level": stats.get("level", 1),
        "hp": f"{stats.get('hp', 0)}/{stats.get('max_hp', 0)}",
        "action_power": f"{stats.get('action_power', 0)}/{stats.get('max_action_power', 0)}",
        "moral_debt_level": moral.get("level", "无债") if isinstance(moral, dict) else "无债",
        "moral_debt_value": moral.get("debt", 0) if isinstance(moral, dict) else 0,
        "gold": stats.get("gold", 0),
        "day": gm.day_night_sys.get_day(),
        "period": gm.day_night_sys.get_current_period().value,
        "combat_rate": round(combat / max(total, 1) * 100, 1),
        "scene": gm.get_current_scene().title if gm.get_current_scene() else "?",
    }
