# api/routes/compression.py - 上下文压缩 API
"""
上下文压缩相关接口。

POST /sessions/{session_id}/compress   手动触发压缩
GET  /sessions/{session_id}/context-stats  查询上下文状态
"""

from typing import Optional
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/sessions", tags=["compression"])


@router.post("/{session_id}/compress")
async def trigger_compression(
    session_id: str,
    mode: str = "auto",
    keep_recent: int = 10,
) -> dict:
    """
    手动触发上下文压缩。

    - mode: 压缩模式
        - "auto": 自动检测，选择合适强度
        - "scene": 幕间完整压缩，生成章节回顾
        - "aggressive": 激进压缩
        - "light": 轻度压缩，保留更多历史
    - keep_recent: 保留最近 N 轮完整对话（仅 light/scene 模式）
    """
    from ..game_manager import game_manager

    gs = game_manager.get_session(session_id)
    if gs is None:
        raise HTTPException(status_code=404, detail="Session not found")

    compressor = getattr(gs.gm, "compressor", None)
    if compressor is None:
        raise HTTPException(status_code=500, detail="Compressor not initialized")

    core_session = gs.gm.session
    history = getattr(core_session, "history", [])
    if not history:
        return {"status": "noop", "message": "No history to compress"}

    valid_modes = {"auto", "scene", "aggressive", "light"}
    if mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode. Must be one of: {valid_modes}",
        )

    actual_keep = keep_recent
    if mode == "aggressive":
        actual_keep = 5
    elif mode == "scene":
        actual_keep = len(history)

    compressed = compressor.compress_history(
        history=history,
        keep_recent=actual_keep,
        mode=mode,
    )

    core_session.history = compressed["recent"]

    return {
        "status": "ok",
        "mode": mode,
        "original_length": compressed["compression_info"]["original_length"],
        "compressed_turns": compressed["compression_info"]["compressed_turns"],
        "kept_recent": compressed["compression_info"]["kept_recent"],
        "summary_tokens": len(compressed["summary"]),
        "compression_turn": compressed["compression_info"]["compression_turn"],
        "summary_preview": (
            compressed["summary"][:200] + "..."
            if len(compressed["summary"]) > 200
            else compressed["summary"]
        ),
    }


@router.get("/{session_id}/context-stats")
async def get_context_stats(session_id: str) -> dict:
    """
    查询当前上下文状态。
    """
    from ..game_manager import game_manager

    gs = game_manager.get_session(session_id)
    if gs is None:
        raise HTTPException(status_code=404, detail="Session not found")

    core_session = gs.gm.session
    history = getattr(core_session, "history", [])
    compressor = getattr(gs.gm, "compressor", None)

    if compressor is None:
        return {
            "turn_count": gs.turn,
            "history_length": len(history),
            "token_estimate": 0,
            "compression_ratio": 0.0,
            "can_continue": True,
            "warning_level": "ok",
            "compressor_enabled": False,
        }

    stats = compressor.get_stats(history=history)
    return {
        "turn_count": stats.turn_count,
        "history_length": stats.history_length,
        "token_estimate": stats.token_estimate,
        "compression_ratio": stats.compression_ratio,
        "compression_triggered": stats.compression_triggered,
        "last_compression_turn": stats.last_compression_turn,
        "can_continue": stats.can_continue,
        "warning_level": stats.warning_level,
        "compressor_enabled": True,
    }


@router.post("/{session_id}/compress/act-review")
async def generate_act_review(
    session_id: str,
    act_number: int = 1,
    act_history: Optional[list] = None,
) -> dict:
    """
    生成幕间回顾。
    """
    from ..game_manager import game_manager

    gs = game_manager.get_session(session_id)
    if gs is None:
        raise HTTPException(status_code=404, detail="Session not found")

    compressor = getattr(gs.gm, "compressor", None)
    if compressor is None:
        raise HTTPException(status_code=500, detail="Compressor not initialized")

    core_session = gs.gm.session
    history = act_history if act_history is not None else getattr(core_session, "history", [])

    hidden_values = {}
    hv_sys = getattr(gs.gm, "hidden_value_sys", None)
    if hv_sys:
        hidden_values = hv_sys.get_snapshot()

    npc_relations = {}
    dialogue_sys = getattr(gs.gm, "dialogue_sys", None)
    if dialogue_sys:
        npc_relations = dialogue_sys.get_all_relations()

    review = compressor.generate_act_review(
        act_history=history,
        act_number=act_number,
        hidden_values=hidden_values,
        npc_relations=npc_relations,
        pending_quests=getattr(core_session, "pending_quests", []),
    )

    return {
        "act_review": review,
        "act_number": act_number,
        "history_length": len(history),
    }


@router.post("/{session_id}/compress/rebuild-prompt")
async def rebuild_compressed_prompt(
    session_id: str,
    mode: str = "scene",
) -> dict:
    """
    压缩 history 并重建 system prompt（调试/预览用）。
    """
    from ..game_manager import game_manager

    gs = game_manager.get_session(session_id)
    if gs is None:
        raise HTTPException(status_code=404, detail="Session not found")

    compressor = getattr(gs.gm, "compressor", None)
    if compressor is None:
        raise HTTPException(status_code=500, detail="Compressor not initialized")

    core_session = gs.gm.session
    history = getattr(core_session, "history", [])
    if not history:
        raise HTTPException(status_code=400, detail="No history to compress")

    compressed = compressor.compress_history(
        history=history,
        keep_recent=len(history),
        mode=mode,
    )

    original_prompt = getattr(core_session, "_original_system_prompt", "")

    hidden_values = {}
    hv_sys = getattr(gs.gm, "hidden_value_sys", None)
    if hv_sys:
        hidden_values = hv_sys.get_snapshot()

    npc_relations = {}
    dialogue_sys = getattr(gs.gm, "dialogue_sys", None)
    if dialogue_sys:
        npc_relations = dialogue_sys.get_all_relations()

    new_prompt = compressor.build_compressed_system_prompt(
        original_system_prompt=original_prompt,
        compressed_data=compressed,
        hidden_values_snapshot=hidden_values,
        pending_quests=getattr(core_session, "pending_quests", []),
        npc_relations=npc_relations,
    )

    return {
        "original_length": len(original_prompt),
        "compressed_length": len(new_prompt),
        "saved_tokens": len(original_prompt) - len(new_prompt),
        "prompt_preview": (
            new_prompt[:500] + "..."
            if len(new_prompt) > 500
            else new_prompt
        ),
    }
