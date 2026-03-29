# api/routes/endings.py - 多结局系统 API
"""
GET  /endings              - 获取所有结局列表及当前达成状态
GET  /endings/progress     - 获取结局达成进度摘要
POST /endings/evaluate     - 手动触发结局评估（返回当前最优先满足的结局）
GET  /endings/current      - 获取当前终局结果（如已触发）
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/endings", tags=["endings"])


def get_gm() -> "GameMaster":
    from rpgagent.api.game_manager import get_manager
    gm = get_manager().get_active_gm()
    if not gm:
        raise HTTPException(status_code=404, detail="当前无活跃游戏")
    return gm


@router.get("")
def list_endings():
    """获取所有结局及其达成状态"""
    gm = get_gm()
    if not gm.ending_sys.is_loaded():
        raise HTTPException(status_code=404, detail="当前剧本未配置多结局系统")

    endings = gm.ending_sys.get_all_endings()
    final = gm.ending_sys.get_final_ending()

    return {
        "total": len(endings),
        "reached_count": len(gm.ending_sys.get_reached_endings()),
        "is_finished": gm.ending_sys.is_finished(),
        "final_ending": {
            "id": final.id,
            "name": final.name,
            "type": final.ending_type,
            "description": final.description,
            "scene_id": final.scene_id,
        } if final else None,
        "endings": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.ending_type,
                "description": e.description,
                "scene_id": e.scene_id,
                "required": e.required,
                "reached": e.reached,
                "reached_at_turn": e.reached_at_turn if e.reached else None,
                "reached_in_scene": e.reached_in_scene if e.reached else None,
                "conditions_count": len(e.conditions) + (1 if e.condition_expr else 0),
            }
            for e in endings
        ],
    }


@router.get("/progress")
def ending_progress():
    """获取各类型结局的达成进度"""
    gm = get_gm()
    return gm.ending_sys.get_progress_summary()


@router.post("/evaluate")
def evaluate_ending():
    """
    手动触发结局评估。
    返回当前满足条件的最高优先级结局（不含隐藏结局）。
    不会触发终局，只返回评估结果。
    """
    gm = get_gm()
    if not gm.ending_sys.is_loaded():
        raise HTTPException(status_code=404, detail="当前剧本未配置多结局系统")
    if gm.ending_sys.is_finished():
        final = gm.ending_sys.get_final_ending()
        return {
            "message": "终局已触发",
            "ending": {
                "id": final.id,
                "name": final.name,
                "type": final.ending_type,
            } if final else None,
        }

    result = gm.ending_sys.evaluate(game_master=gm)
    if not result:
        return {
            "message": "当前无满足条件的结局",
            "available": gm.ending_sys.get_available_endings(),
        }

    return {
        "message": f"评估完成：满足「{result.ending.name}」条件",
        "ending": {
            "id": result.ending.id,
            "name": result.ending.name,
            "type": result.ending.ending_type,
            "description": result.ending.description,
            "scene_id": result.ending.scene_id,
            "satisfied_conditions": result.satisfied_conditions,
            "unsatisfied_conditions": result.unsatisfied_conditions,
        },
        "available": gm.ending_sys.get_available_endings(),
    }


@router.get("/hidden")
def list_hidden_endings():
    """获取隐藏结局的达成状态（不透露未达成结局的具体条件）"""
    gm = get_gm()
    if not gm.ending_sys.is_loaded():
        raise HTTPException(status_code=404, detail="当前剧本未配置多结局系统")

    all_endings = gm.ending_sys.get_all_endings()
    hidden = [e for e in all_endings if not e.required]

    return {
        "hidden_endings": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.ending_type,
                "reached": e.reached,
                # 不暴露未达成的隐藏结局的描述和条件
                "description": e.description if e.reached else None,
            }
            for e in hidden
        ],
        "hidden_reached_count": len([e for e in hidden if e.reached]),
        "hidden_total": len(hidden),
    }
