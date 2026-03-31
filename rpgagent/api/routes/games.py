# api/routes/games.py - 游戏管理路由
from typing import Optional
from fastapi import APIRouter, HTTPException
from ..models import (
    StartGameRequest, GameInfo, ActionResponse,
    PlayerStatus, NPCCard, NarrativeEvent, SaveInfo,
    PlayerActionRequest, RestartGameRequest,
)
from ..game_manager import get_manager
from ...core.context_loader import ContextLoader
from ...data.database import Database
from ...config.settings import GAMES_DIR, USER_GAMES_DIR, API_KEY

router = APIRouter(prefix="/games", tags=["games"])


def _build_loader() -> ContextLoader:
    """构建加载器，同时扫描内置目录和用户安装目录"""
    loader = ContextLoader()
    if GAMES_DIR.exists():
        for game_dir in GAMES_DIR.iterdir():
            if game_dir.is_dir():
                loader.register_game(game_dir.name, game_dir)
    if USER_GAMES_DIR.exists():
        for game_dir in USER_GAMES_DIR.iterdir():
            if game_dir.is_dir():
                loader.register_game(game_dir.name, game_dir)
    return loader


# ─── 列出剧本 ──────────────────────────────────────

@router.get("", response_model=list[GameInfo])
async def list_games():
    loader = _build_loader()
    games = loader.list_games()
    return [
        GameInfo(
            id=g["id"],
            name=g["name"],
            summary=g["summary"],
            tags=g["tags"],
            version="1.0",
            author="unknown",
        )
        for g in games
    ]


# ─── 开始游戏 ──────────────────────────────────────

@router.post("/{game_id}/start", response_model=dict)
async def start_game(game_id: str, req: StartGameRequest):
    """创建新游戏会话，返回 session_id"""
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API 密钥未配置。请设置 OPENAI_API_KEY 或 RPG_API_KEY 环境变量后重启服务器。",
        )
    loader = _build_loader()
    game_loader = loader.get_loader(game_id)
    if not game_loader:
        raise HTTPException(status_code=404, detail=f"剧本不存在: {game_id}")

    db = Database(game_id=game_id)
    manager = get_manager()

    session = await manager.start_game(
        game_id=game_id,
        player_name=req.player_name,
        game_loader=loader,
        db=db,
    )

    scene = session.gm.get_current_scene()
    scene_info = {
        "session_id": session.session_id,
        "game_id": game_id,
        "player_name": req.player_name,
        "scene": {
            "id": scene.id if scene else "unknown",
            "title": scene.title if scene else "未知场景",
            "content": scene.content[:500] if scene else "",
        },
        "turn": 0,
    }

    # 写入DB
    db.insert_event(
        turn=0,
        scene_id=scene.id if scene else "start",
        summary=f"开始游戏：{req.player_name}",
        tags=["game_start"],
    )

    return scene_info


# ─── 玩家行动 ──────────────────────────────────────

@router.post("/action", response_model=ActionResponse)
async def player_action(req: PlayerActionRequest):
    manager = get_manager()
    session = manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API 密钥未配置。请设置 OPENAI_API_KEY 或 RPG_API_KEY 环境变量后重启服务器。",
        )

    narrative, cmd = await manager.process_action(req.session_id, req.action)

    # 更新DB
    scene = session.gm.get_current_scene()
    session.db.insert_event(
        turn=session.turn,
        scene_id=scene.id if scene else "unknown",
        summary=narrative[:100],
        tags=["player_action"],
    )

    # CG 路径（若有新生成）
    scene_cg_url = None
    if session.gm.session.scene_cg_generated and session.gm.session.scene_cg_path:
        # 返回相对路径，前端拼接 BASE_URL
        scene_cg_url = session.gm.session.scene_cg_path

    # 获取当前状态（解决P2：action响应缺状态字段）
    stats = session.gm.stats_sys.get_snapshot()
    hp = stats.get("hp", 0)
    max_hp = stats.get("max_hp", 0)
    stamina = stats.get("stamina", 0)
    max_stamina = stats.get("max_stamina", 0)
    action_power = stats.get("action_power", 0)
    max_action_power = stats.get("max_action_power", 0)

    return ActionResponse(
        session_id=req.session_id,
        narrative=narrative,
        options=[],  # 从cmd解析
        hidden_value_changes={},
        relation_changes={},
        hp=hp,
        max_hp=max_hp,
        stamina=stamina,
        max_stamina=max_stamina,
        action_power=action_power,
        max_action_power=max_action_power,
        turn=session.turn,
        scene_change=scene.id if scene else None,
        command=cmd,
        scene_cg=scene_cg_url,
    )


# ─── 当前状态 ──────────────────────────────────────

# ─── CG 配图 ─────────────────────────────────────

@router.get("/scenes/{scene_id}/cg")
async def get_scene_cg(scene_id: str):
    """
    获取指定场景的 CG 配图（从本地缓存返回）。
    按 scene_id 匹配 ~/.cache/rpgagent/cg/{scene_id}_*.png
    """
    from ...config.settings import IMAGE_GENERATOR_CACHE_DIR
    import os

    cache_dir = IMAGE_GENERATOR_CACHE_DIR
    if not cache_dir.exists():
        return {"scene_id": scene_id, "cg_url": None}

    # 查找该场景的 CG 文件
    matches = list(cache_dir.glob(f"{scene_id}_*.png"))
    if not matches:
        return {"scene_id": scene_id, "cg_url": None}

    # 取最新的一个
    latest = max(matches, key=lambda f: f.stat().st_mtime)
    filename = latest.name
    return {
        "scene_id": scene_id,
        "cg_url": f"/cg_cache/{filename}",
        "generated_at": latest.stat().st_mtime,
    }


@router.post("/scenes/{scene_id}/cg/generate")
async def generate_scene_cg(
    scene_id: str,
    session_id: str,
    style: str = "fantasy illustration, dark atmosphere, high quality",
    characters: Optional[list[dict]] = None,
):
    """
    为指定场景异步生成 CG 配图。
    通过 GameMaster 的 generate_scene_cg GMS 工具实现（异步调用 DM）。
    返回生成的图片 URL。
    """
    import os, asyncio
    from ...config.settings import IMAGE_GENERATOR_CACHE_DIR, IMAGE_GENERATOR_ENABLED

    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if not IMAGE_GENERATOR_ENABLED:
        return {"scene_id": scene_id, "cg_url": None, "reason": "TONGYI_API_KEY not configured"}

    # 复用 session 中已生成的 CG（如有）
    cache_dir = IMAGE_GENERATOR_CACHE_DIR
    existing = list(cache_dir.glob(f"{scene_id}_*.png")) if cache_dir.exists() else []
    if existing:
        latest = max(existing, key=lambda f: f.stat().st_mtime)
        return {
            "scene_id": scene_id,
            "cg_url": f"/cg_cache/{latest.name}",
            "cached": True,
        }

    # 获取场景内容
    scene = session.gm.game_loader.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"场景不存在: {scene_id}")

    api_key = os.getenv("TONGYI_API_KEY", "")
    from rpgagent.systems.image_generator import make_generator
    gen = make_generator(provider="tongyi", api_key=api_key)
    img_path = await gen.generate(
        scene_id=scene_id,
        scene_content=scene.content,
        characters=characters or [],
        style=style,
    )
    await gen.close()

    filename = os.path.basename(img_path)
    return {
        "scene_id": scene_id,
        "cg_url": f"/cg_cache/{filename}",
        "cached": False,
    }


# ─── NPC 列表 ─────────────────────────────────────

@router.get("/{session_id}/npcs", response_model=list[NPCCard])
async def list_npcs(session_id: str):
    """
    返回当前剧本场景中所有 NPC 的信息卡片（含关系值）。
    用于前端展示 NPC 关系面板。
    """
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    relations = session.gm.dialogue_sys.get_all_relations()
    cards = []
    for npc_id, rel_data in relations.items():
        char = session.gm.game_loader.characters.get(npc_id)
        if not char:
            continue
        cards.append(NPCCard(
            id=npc_id,
            name=char.name,
            role=char.role,
            description=char.description[:200] if char.description else "",
            relation_level=rel_data.get("level", "陌生"),
            relation_value=rel_data.get("value", 0),
        ))
    return cards


# ─── 当前状态 ──────────────────────────────────────

@router.get("/{session_id}/status", response_model=PlayerStatus)
async def get_status(session_id: str):
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    stats = session.gm.stats_sys.get_snapshot()
    moral = session.gm.moral_sys.get_snapshot()
    inv = session.gm.inv_sys.get_snapshot()
    rels = session.gm.dialogue_sys.get_all_relations()
    scene = session.gm.get_current_scene()
    skills = session.gm.skill_sys.list_learned()
    equip = session.gm.equipment_sys.get_snapshot()
    bonus = equip.get("total_bonus", {})
    s = stats
    ab = s.get("ability", {})

    return PlayerStatus(
        session_id=session_id,
        scene_id=scene.id if scene else "unknown",
        turn=session.turn,
        hp=s.get("hp", 0),
        max_hp=s.get("max_hp", 0),
        stamina=s.get("stamina", 0),
        max_stamina=s.get("max_stamina", 0),
        action_power=s.get("action_power", 0),
        max_action_power=s.get("max_action_power", 0),
        level=s.get("level", 1),
        exp=s.get("exp", 0),
        exp_to_level=s.get("exp_to_level", 100),
        gold=s.get("gold", 0),
        strength=ab.get("strength", 10),
        agility=ab.get("dexterity", 10),
        constitution=ab.get("constitution", 10),
        intelligence=ab.get("intelligence", 10),
        wisdom=ab.get("wisdom", 10),
        charisma=ab.get("charisma", 10),
        armor_class=bonus.get("armor_class", 0),
        attack_bonus=bonus.get("attack_bonus", 0),
        damage_bonus=bonus.get("damage_bonus", 0),
        skill_points=stats.get("skill_points", 0),
        hidden_values={"moral_debt": moral},
        factions=session.gm.faction_sys.get_all_reputations(),
        inventory=inv.get("items", []),
        relations=rels,
        equipped=equip.get("equipped", {}),
        skills=skills,
    )


# ─── 存档 ──────────────────────────────────────

@router.get("/{session_id}/saves", response_model=list[SaveInfo])
async def list_saves(session_id: str):
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    saves = session.db.list_saves()
    return [SaveInfo(id=s["id"], slot=s["slot"], created_at=s["created_at"]) for s in saves]


@router.post("/{session_id}/saves/{save_id}")
async def save_game(session_id: str, save_id: str):
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    snapshot = session.gm.session.get_snapshot()
    session.db.save_snapshot(save_id, snapshot.__dict__, slot=0)
    return {"ok": True, "save_id": save_id}


@router.get("/{session_id}/saves/{save_id}/load")
async def load_game(session_id: str, save_id: str):
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    snapshot_data = session.db.load_snapshot(save_id)
    if not snapshot_data:
        raise HTTPException(status_code=404, detail="存档不存在")

    # 从数据库恢复 HiddenValueSystem 状态（records + effects）
    if session.gm.hidden_value_sys:
        session.gm.hidden_value_sys.load_from_db(session.db)

    # 重建 GameState 并恢复到 session
    from rpgagent.core.session import GameState
    state = GameState(**snapshot_data)
    session.gm.session._apply_state(state)

    # 恢复探索系统状态
    exploration_snapshot = session.gm.session.flags.get("_exploration", {})
    if exploration_snapshot and session.gm.explore_sys:
        session.gm.explore_sys.load_snapshot(exploration_snapshot)

    # 恢复当前场景
    if state.scene_id:
        session.gm.current_scene = session.gm.game_loader.get_scene(state.scene_id)

    return {
        "ok": True,
        "save_id": save_id,
        "scene_id": state.scene_id,
        "turn": state.turn_count,
    }


@router.get("/{session_id}/saves/autosave")
async def get_autosave(session_id: str):
    """获取当前会话的自动存档信息"""
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if not session.autosave_id:
        return {"has_autosave": False}

    snapshot_data = session.db.load_snapshot(session.autosave_id)
    if not snapshot_data:
        return {"has_autosave": False}

    return {
        "has_autosave": True,
        "save_id": session.autosave_id,
        "scene_id": snapshot_data.get("scene_id", ""),
        "turn_count": snapshot_data.get("turn_count", 0),
        "player_name": snapshot_data.get("player_name", ""),
    }


@router.post("/{session_id}/saves/autosave/load")
async def load_autosave(session_id: str):
    """从自动存档恢复游戏"""
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if not session.autosave_id:
        raise HTTPException(status_code=404, detail="无自动存档")

    snapshot_data = session.db.load_snapshot(session.autosave_id)
    if not snapshot_data:
        raise HTTPException(status_code=404, detail="自动存档不存在")

    if session.gm.hidden_value_sys:
        session.gm.hidden_value_sys.load_from_db(session.db)

    from rpgagent.core.session import GameState
    state = GameState(**snapshot_data)
    session.gm.session._apply_state(state)

    # 恢复探索系统状态
    exploration_snapshot = session.gm.session.flags.get("_exploration", {})
    if exploration_snapshot and session.gm.explore_sys:
        session.gm.explore_sys.load_snapshot(exploration_snapshot)

    if state.scene_id:
        session.gm.current_scene = session.gm.game_loader.get_scene(state.scene_id)

    return {
        "ok": True,
        "save_id": session.autosave_id,
        "scene_id": state.scene_id,
        "turn": state.turn_count,
    }


@router.get("/{session_id}/cg/history")
async def get_cg_history(session_id: str):
    """返回当前会话已生成的全部 CG 历史"""
    manager = get_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    history = session.cg_history or []
    result = []
    for entry in history:
        cg_path = entry.get("cg_path", "")
        filename = ""
        if cg_path:
            filename = cg_path if "/" not in cg_path else cg_path.rsplit("/", 1)[-1]
        result.append({
            "scene_id": entry.get("scene_id", ""),
            "scene_title": entry.get("scene_title", ""),
            "cg_url": f"/cg_cache/{filename}" if filename else None,
            "trigger": entry.get("trigger", ""),
        })
    return result


# ─── 成就（别名，兼容 /api/games/{id}/achievements 路径）─────────────

@router.get("/{session_id}/achievements")
async def get_game_achievements(session_id: str):
    """返回当前会话的所有成就（含解锁状态）- /api/games/{id}/achievements 别名"""
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
async def get_game_unlocked_achievements(session_id: str):
    """返回已解锁成就列表 - /api/games/{id}/achievements/unlocked 别名"""
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


# ─── 统计（别名，兼容 /api/games/{id}/stats 路径）─────────────────

@router.get("/{session_id}/stats")
async def get_game_stats_via_games(session_id: str):
    """返回当前会话的完整游戏统计数据 - /api/games/{id}/stats 别名"""
    # 复用 stats.py 的路由逻辑，避免重复代码
    from .stats import get_game_stats
    return await get_game_stats(session_id=session_id)


@router.get("/{session_id}/stats/overview")
async def get_stats_overview_via_games(session_id: str):
    """轻量版统计概览 - /api/games/{id}/stats/overview 别名"""
    from .stats import get_stats_overview
    return await get_stats_overview(session_id=session_id)
