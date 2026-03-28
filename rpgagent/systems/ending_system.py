# systems/ending_system.py - 多结局系统
"""
多结局系统：根据玩家在游戏中的选择和隐藏数值状态，
在游戏终局时判定玩家获得哪种结局。

结局类型：
- hero（英雄结局）
- tragedy（悲剧结局）
- neutral（中立结局）
- hidden（隐藏结局）

每个剧本在 meta.json 中定义 endings 列表，
每个结局包含 conditions（条件表达式）和 scene（结局场景ID）。

条件支持：
- 隐藏数值阈值：revolutionary_spirit >= 80
- 属性值：hp > 0
- 阵营声望：faction_{id} >= 50
- 持有物品：has_{item_id}
- 场景访问：visited_{scene_id}
- 标志位：flag_{name}

条件组合：AND / OR

使用方式：
    gm.ending_sys.evaluate(game_id)
    # 或在到达终局场景时：
    result = gm.ending_sys.trigger_ending(ending_id)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
import re


# ─── 结局配置 ────────────────────────────────────────


@dataclass
class Ending:
    id: str
    name: str                          # 结局名称，如"英雄结局"
    ending_type: str                   # hero / tragedy / neutral / hidden
    description: str                   # 简短描述（不透露关键剧情）
    scene_id: str                       # 结局场景的 scene_id
    conditions: Dict[str, Any] = field(default_factory=dict)  # 触发条件
    condition_expr: str = ""           # 可选：自定义条件表达式字符串
    required: bool = True              # 是否为必然结局（false=隐藏结局）
    priority: int = 0                   # 优先级，数字越大越优先（满足多条件时）
    reached: bool = False              # 是否已达成
    reached_at_turn: int = 0          # 达成时的回合数
    reached_in_scene: str = ""         # 达成时的场景ID


@dataclass
class EndingResult:
    """一次结局评估的结果"""
    ending_id: str
    ending: Ending
    satisfied_conditions: List[str]     # 满足的条件列表
    unsatisfied_conditions: List[str]  # 未满足的条件列表
    is_hidden: bool


# ─── 条件表达式求值 ────────────────────────────────────────


OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
}


class EndingConditionEvaluator:
    """
    判定单个条件是否满足。
    支持格式：
      "revolutionary_spirit >= 80"
      "hp > 0"
      "has_iron_sword"
      "visited_daze_camp"
      "flag_final_battle"
    """

    def __init__(self, game_master):
        self.gm = game_master

    def evaluate_condition(self, cond: str) -> bool:
        cond = cond.strip()

        # 解析比较运算符
        for op in [">=", "<=", "==", "!=", ">", "<"]:
            if op in cond:
                parts = cond.split(op)
                if len(parts) == 2:
                    key = parts[0].strip()
                    raw_val = parts[1].strip()
                    return self._compare(key, op, raw_val)

        # has_ 前缀
        if cond.startswith("has_"):
            item_id = cond[4:].strip()
            inv = self.gm.inv_sys.get_snapshot()
            return item_id in [it.get("id", it.get("name", "")) for it in inv.get("items", [])]

        # visited_ 前缀
        if cond.startswith("visited_"):
            scene_id = cond[8:].strip()
            return scene_id in getattr(self.gm.session, "visited_scenes", set())

        # flag_ 前缀
        if cond.startswith("flag_"):
            flag_name = cond[4:].strip()
            return bool(self.gm.session.flags.get(f"flag_{flag_name}"))

        # 阵营声望：faction_{id} >= N
        fac_match = re.match(r"(faction_\w+)\s*(>=|<=|==|!=|>|<)\s*(-?\d+)", cond)
        if fac_match:
            faction_id = fac_match.group(1)
            op_sym = fac_match.group(2)
            threshold = int(fac_match.group(3))
            val = self.gm.faction_sys.get_reputation(faction_id)
            return OPS[op_sym](val, threshold)

        # 简单布尔值（flag_xxx 无值默认 True）
        if cond.startswith("flag_"):
            return True

        return False

    def _compare(self, key: str, op: str, raw_val: str) -> bool:
        val = self._get_value(key)
        if val is None:
            return False
        try:
            threshold = float(raw_val) if "." in raw_val else int(raw_val)
        except ValueError:
            threshold = raw_val.strip('"').strip("'")
            # 字符串比较
            return str(val) == threshold
        return OPS[op](float(val), threshold)

    def _get_value(self, key: str) -> Optional[float]:
        key = key.strip()
        # 隐藏数值
        if self.gm.hidden_value_sys:
            hv = self.gm.hidden_value_sys.get_hidden_value(key)
            if hv:
                return float(hv.get_value())
        # 属性
        stats = self.gm.stats_sys.get_snapshot()
        if key in stats:
            return float(stats[key])
        # 道德债务
        if key == "moral_debt":
            return float(self.gm.moral_sys.debt)
        return None

    def evaluate_expr(self, expr: str) -> bool:
        """
        求值条件表达式，支持 AND / OR。
        示例："revolutionary_spirit >= 80 AND moral_debt < 26"
        """
        expr = expr.strip()
        if " OR " in expr:
            return any(self.evaluate_expr(c.strip()) for c in expr.split(" OR "))
        if " AND " in expr:
            return all(self.evaluate_expr(c.strip()) for c in expr.split(" AND "))
        return self.evaluate_condition(expr)


# ─── EndingSystem ────────────────────────────────────────


class EndingSystem:
    """
    多结局管理器。

    每个剧本在 meta.json 的 endings 列表中定义结局。
    游戏过程中可随时查询哪些结局已达成、哪些接近满足。

    用法：
        # 游戏结束时
        result = gm.ending_sys.evaluate()
        if result:
            gm.ending_sys.trigger_ending(result.ending_id)

        # 查询可用结局
        available = gm.ending_sys.get_available_endings()
    """

    ENDING_TYPES = ["hero", "tragedy", "neutral", "hidden"]

    def __init__(self):
        # ending_id -> Ending
        self._endings: Dict[str, Ending] = {}
        # 游戏结束时触发的最终结局（只允许一个）
        self._final_ending: Optional[str] = None
        # 评估回调（当触发结局时调用，可用于触发特殊叙事）
        self._on_trigger: List[Callable[[Ending], None]] = []
        # 当前游戏的 meta（用于重载）
        self._game_id: str = ""

    # ── 加载配置 ────────────────────────────────

    def load_from_meta(self, meta: Any, game_id: str = "") -> None:
        """从 meta.json 的 endings 配置加载所有结局"""
        self._game_id = game_id
        self._endings.clear()
        self._final_ending = None

        endings_cfg = getattr(meta, "endings", []) or []
        for ec in endings_cfg:
            ending = Ending(
                id=ec["id"],
                name=ec.get("name", ec["id"]),
                ending_type=ec.get("type", "neutral"),
                description=ec.get("description", ""),
                scene_id=ec.get("scene", ec.get("scene_id", "")),
                conditions=ec.get("conditions", {}),
                condition_expr=ec.get("condition_expr", ""),
                required=ec.get("required", True),
                priority=ec.get("priority", 0),
            )
            self._endings[ending.id] = ending

    def is_loaded(self) -> bool:
        return bool(self._endings)

    # ── 评估 ────────────────────────────────

    def evaluate(self, game_master=None) -> Optional[EndingResult]:
        """
        评估所有非隐藏结局（required=True），返回最高优先级满足条件的 EndingResult。
        如果没有结局满足条件，返回 None。

        隐藏结局（required=False）由 evaluate_hidden() 单独评估。
        """
        if not self._endings:
            return None

        results: List[EndingResult] = []
        evaluator = EndingConditionEvaluator(game_master) if game_master else None

        for ending in self._endings.values():
            if not ending.required:
                continue

            sat, unsat = self._check_ending(ending, evaluator, game_master)
            if sat:
                results.append(EndingResult(
                    ending_id=ending.id,
                    ending=ending,
                    satisfied_conditions=sat,
                    unsatisfied_conditions=unsat,
                    is_hidden=False,
                ))

        if not results:
            return None

        # 按优先级排序，取最高
        results.sort(key=lambda r: r.ending.priority, reverse=True)
        return results[0]

    def evaluate_hidden(self, game_master=None) -> List[EndingResult]:
        """
        评估所有隐藏结局（required=False），返回满足条件的隐藏结局列表。
        """
        if not self._endings:
            return []

        evaluator = EndingConditionEvaluator(game_master) if game_master else None
        results: List[EndingResult] = []

        for ending in self._endings.values():
            if ending.required:
                continue
            sat, unsat = self._check_ending(ending, evaluator, game_master)
            if sat:
                ending.reached = True
                results.append(EndingResult(
                    ending_id=ending.id,
                    ending=ending,
                    satisfied_conditions=sat,
                    unsatisfied_conditions=unsat,
                    is_hidden=True,
                ))
        return results

    def _check_ending(
        self,
        ending: Ending,
        evaluator: Optional[EndingConditionEvaluator],
        game_master,
    ) -> tuple[List[str], List[str]]:
        """
        检查一个结局的条件是否满足。
        返回 (满足的条件列表, 未满足的条件列表)。
        """
        satisfied: List[str] = []
        unsatisfied: List[str] = []

        # 方式1：conditions 字典（key: 值 比较）
        if ending.conditions and evaluator:
            for key, condition in ending.conditions.items():
                # condition 可以是数字（直接比较）或 dict {">=": 80}
                if isinstance(condition, dict):
                    for op, threshold in condition.items():
                        raw_cond = f"{key} {op} {threshold}"
                        if evaluator.evaluate_condition(raw_cond):
                            satisfied.append(raw_cond)
                        else:
                            unsatisfied.append(raw_cond)
                else:
                    # 直接比较值
                    raw_cond = f"{key} == {condition}"
                    if evaluator.evaluate_condition(raw_cond):
                        satisfied.append(raw_cond)
                    else:
                        unsatisfied.append(raw_cond)

        # 方式2：condition_expr 字符串表达式
        if ending.condition_expr and evaluator:
            if evaluator.evaluate_expr(ending.condition_expr):
                satisfied.append(ending.condition_expr)
            else:
                unsatisfied.append(ending.condition_expr)

        return satisfied, unsatisfied

    # ── 结局触发 ────────────────────────────────

    def trigger_ending(
        self,
        ending_id: str,
        turn: int = 0,
        scene_id: str = "",
    ) -> Optional[Ending]:
        """
        触发指定结局，返回 Ending 对象。
        终局只能触发一次（覆盖）。
        """
        ending = self._endings.get(ending_id)
        if not ending:
            return None

        self._final_ending = ending_id
        ending.reached = True
        ending.reached_at_turn = turn
        ending.reached_in_scene = scene_id

        for cb in self._on_trigger:
            try:
                cb(ending)
            except Exception:
                pass

        return ending

    def get_final_ending(self) -> Optional[Ending]:
        """获取已触发的最终结局"""
        if not self._final_ending:
            return None
        return self._endings.get(self._final_ending)

    def is_finished(self) -> bool:
        """游戏是否已触发终局"""
        return self._final_ending is not None

    # ── 查询 ────────────────────────────────

    def get_all_endings(self) -> List[Ending]:
        """获取所有结局（含已达成的状态）"""
        return list(self._endings.values())

    def get_reached_endings(self) -> List[Ending]:
        """获取已达成的结局列表"""
        return [e for e in self._endings.values() if e.reached]

    def get_ending(self, ending_id: str) -> Optional[Ending]:
        return self._endings.get(ending_id)

    def get_available_endings(self) -> List[Dict[str, Any]]:
        """
        获取当前状态下可用的结局列表。
        隐藏结局（required=False）只展示名称，不展示描述和条件。
        """
        evaluator = None
        if hasattr(self, '_gm') and self._gm:
            evaluator = EndingConditionEvaluator(self._gm)

        available = []
        for ending in self._endings.values():
            info = {
                "id": ending.id,
                "name": ending.name,
                "type": ending.ending_type,
                "reached": ending.reached,
            }
            if ending.required or ending.reached:
                info["description"] = ending.description
                info["scene_id"] = ending.scene_id
                info["conditions_count"] = len(ending.conditions) + (1 if ending.condition_expr else 0)
            available.append(info)
        return available

    def get_progress_summary(self) -> Dict[str, Any]:
        """
        获取结局达成进度摘要。
        """
        all_endings = list(self._endings.values())
        reached = [e for e in all_endings if e.reached]
        hero = [e for e in all_endings if e.ending_type == "hero"]
        tragedy = [e for e in all_endings if e.ending_type == "tragedy"]
        neutral = [e for e in all_endings if e.ending_type == "neutral"]
        hidden = [e for e in all_endings if e.ending_type == "hidden"]

        return {
            "total": len(all_endings),
            "reached_count": len(reached),
            "by_type": {
                "hero": {"total": len(hero), "reached": len([e for e in hero if e.reached])},
                "tragedy": {"total": len(tragedy), "reached": len([e for e in tragedy if e.reached])},
                "neutral": {"total": len(neutral), "reached": len([e for e in neutral if e.reached])},
                "hidden": {"total": len(hidden), "reached": len([e for e in hidden if e.reached])},
            },
            "final_ending": self._final_ending,
        }

    # ── 回调 ────────────────────────────────

    def on_trigger(self, callback: Callable[[Ending], None]) -> None:
        """注册结局触发回调"""
        self._on_trigger.append(callback)

    # ── 存档 ────────────────────────────────

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "endings": [
                {
                    "id": e.id,
                    "reached": e.reached,
                    "reached_at_turn": e.reached_at_turn,
                    "reached_in_scene": e.reached_in_scene,
                }
                for e in self._endings.values()
            ],
            "final_ending": self._final_ending,
        }

    def load_snapshot(self, snapshot: Dict[str, Any]) -> None:
        if not snapshot:
            return
        for e_data in snapshot.get("endings", []):
            e = self._endings.get(e_data.get("id"))
            if e:
                e.reached = e_data.get("reached", False)
                e.reached_at_turn = e_data.get("reached_at_turn", 0)
                e.reached_in_scene = e_data.get("reached_in_scene", "")
        self._final_ending = snapshot.get("final_ending")

    def bind_game_master(self, gm) -> None:
        """绑定 game_master，用于 get_available_endings 时求值"""
        self._gm = gm
