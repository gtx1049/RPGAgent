# api/routes/games.py - 游戏管理路由
from fastapi import APIRouter, HTTPException
from api.models import (
    StartGameRequest, GameInfo, ActionResponse,
    PlayerStatus, NPCCard, NarrativeEvent, SaveInfo,
    PlayerActionRequest,
)
from api.game_manager import get_manager
from core.context_loader import ContextLoader
from data.database import Database
from config.settings import GAMES_DIR
import uuid

router = APIRouter(prefix="/games", tags=["games"])


_loader = ContextLoader()
for game_dir in GAMES_DIR.iterdir():
    if game_dir.is_dir():
        _loader.register_game(game_dir.name, game_dir)


# ─── 列出剧本 ──────────────────────────────────────

@router.get("", response_model=list[GameInfo])
async def list_games():
    games = _loader.list_games()
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
    loader = _loader.get_loader(game_id)
    if not loader:
        raise HTTPException(status_code=404, detail=f"剧本不存在: {game_id}")

    db = Database(game_id=game_id)
    manager = get_manager()

    session = await manager.start_game(
        game_id=game_id,
        player_name=req.player_name,
        game_loader=_loader,
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

    narrative, cmd = await manager.process_action(req.session_id, req.action)

    # 更新DB
    scene = session.gm.get_current_scene()
    session.db.insert_event(
        turn=session.turn,
        scene_id=scene.id if scene else "unknown",
        summary=narrative[:100],
        tags=["player_action"],
    )

    return ActionResponse(
        session_id=req.session_id,
        narrative=narrative,
        options=[],  # 从cmd解析
        hidden_value_changes={},
        relation_changes={},
        scene_change=scene.id if scene else None,
        command=cmd,
    )


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

    return PlayerStatus(
        session_id=session_id,
        scene_id=scene.id if scene else "unknown",
        turn=session.turn,
        hp=stats.get("hp", 0),
        max_hp=stats.get("max_hp", 0),
        stamina=stats.get("stamina", 0),
        max_stamina=stats.get("max_stamina", 0),
        strength=stats.get("strength", 0),
        agility=stats.get("agility", 0),
        intelligence=stats.get("intelligence", 0),
        charisma=stats.get("charisma", 0),
        hidden_values={"moral_debt": moral},
        inventory=inv.get("items", []),
        relations=rels,
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
    from core.session import GameState
    state = GameState(**snapshot_data)
    session._apply_state(state)

    # 恢复当前场景
    if state.scene_id:
        session.gm.current_scene = session.gm.game_loader.get_scene(state.scene_id)

    return {
        "ok": True,
        "save_id": save_id,
        "scene_id": state.scene_id,
        "turn": state.turn_count,
    }
