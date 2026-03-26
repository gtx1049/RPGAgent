# core/scene_trigger.py - 场景触发引擎
"""
驱动 RPG 叙事中的条件分支：场景内的 [TRIGGER] 块定义条件，
满足时通知 GameMaster 执行场景跳转。

支持两种触发模式：
- 条件触发：隐藏数值、属性、持有物品、时间（回合数）等布尔条件
- 自动触发：进入场景后立即触发（immediate=True）

触发器嵌入场景 Markdown 中，格式：
```markdown
[TRIGGER]
condition: hunger >= 60
scene: rage_scene
immediate: false
priority: 1
[/TRIGGER]
```

条件表达式支持：
- 隐藏数值：hunger, reputation, moral_debt 等（来自 HiddenValueSystem）
- 属性：hp, stamina, strength 等（来自 StatsSystem）
- 关系：npc_{id}_relation（来自 DialogueSystem）
- 物品：has_{item_id}（来自 InventorySystem）
- 回合数：turn >= N
- 场景标记：flag_{name}（来自 session.flags）
- 组合条件：condition1 AND condition2 OR condition3
"""

import re
import operator
from typing import Optional
from dataclasses import dataclass


# ─── 触发器配置 ────────────────────────────────────────


@dataclass
class Trigger:
    id: str
    condition: str            # 原始条件表达式
    target_scene: str         # 满足条件时跳转的目标场景ID
    immediate: bool = False   # 是否进入场景后立即触发
    priority: int = 0         # 优先级，数值越大越优先
    once: bool = True         # 是否只触发一次
    description: str = ""     # 触发器描述，供叙事参考

    # 内部状态
    _triggered: bool = False  # 是否已触发过（用于 once=True）


# ─── 条件表达式求值器 ────────────────────────────────────────


class ConditionEvaluator:
    """
    求值布尔条件表达式。
    支持单条件、AND/OR 组合，运算符：>=, <=, ==, !=, >, <, in, has, flag
    """

    OPS = {
        ">=": operator.ge,
        "<=": operator.le,
        "==": operator.eq,
        "!=": operator.ne,
        ">": operator.gt,
        "<": operator.lt,
    }

    def __init__(self, game_master):
        self.gm = game_master

    def evaluate(self, condition: str) -> bool:
        """对完整表达式求值，支持 AND/OR"""
        condition = condition.strip()
        # 优先处理 OR（优先级低于 AND）
        if " OR " in condition:
            return any(self.evaluate(c.strip()) for c in condition.split(" OR "))
        if " AND " in condition:
            return all(self.evaluate(c.strip()) for c in condition.split(" AND "))
        # 单条件
        return self._eval_single(condition)

    def _eval_single(self, cond: str) -> bool:
        cond = cond.strip()
        # 括号
        if cond.startswith("(") and cond.endswith(")"):
            return self.evaluate(cond[1:-1])

        # flag 检查
        if cond.startswith("flag_"):
            # flag_true / flag_false
            parts = cond.split("_", 2)
            if len(parts) >= 3:
                flag_name = parts[1]
                suffix = parts[2] if len(parts) > 2 else "true"
                val = self.gm.session.flags.get(f"flag_{flag_name}", False)
                return val if suffix == "true" else not val
            return False

        # has_ 物品检查
        if cond.startswith("has_"):
            item_id = cond[4:].strip()
            inv = self.gm.inv_sys.get_snapshot()
            return item_id in inv.get("items", [])
        if cond.startswith("not_has_"):
            item_id = cond[8:].strip()
            inv = self.gm.inv_sys.get_snapshot()
            return item_id not in inv.get("items", [])

        # turn 比较
        turn_match = re.match(r"turn\s*(>=|<=|==|!=|>|<)\s*(\d+)", cond, re.IGNORECASE)
        if turn_match:
            op_sym = turn_match.group(1)
            threshold = int(turn_match.group(2))
            return self.OPS[op_sym](self.gm.session.turn_count, threshold)

        # 关系检查：npc_{id}_relation >= N
        rel_match = re.match(
            r"(npc_\w+_relation)\s*(>=|<=|==|!=|>|<)\s*(-?\d+)",
            cond,
            re.IGNORECASE,
        )
        if rel_match:
            rel_key = rel_match.group(1).lower()
            op_sym = rel_match.group(2)
            threshold = int(rel_match.group(3))
            rels = self.gm.dialogue_sys.get_all_relations()
            val = rels.get(rel_key, {}).get("value", 0)
            return self.OPS[op_sym](val, threshold)

        # 隐藏数值/属性比较
        for op_sym in [">=", "<=", "==", "!=", ">", "<"]:
            if op_sym in cond:
                parts = cond.split(op_sym)
                if len(parts) == 2:
                    key = parts[0].strip()
                    raw_val = parts[1].strip()
                    try:
                        threshold = float(raw_val) if "." in raw_val else int(raw_val)
                    except ValueError:
                        threshold = raw_val.strip('"').strip("'")

                    val = self._get_value(key)
                    if val is None:
                        return False
                    return self.OPS[op_sym](val, threshold)

        return False

    def _get_value(self, key: str) -> Optional[float]:
        """根据 key 解析当前游戏状态值"""
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
        # 道德债务（兼容旧 key）
        if key == "moral_debt":
            return float(self.gm.moral_sys.debt)
        return None


# ─── 场景触发引擎 ────────────────────────────────────────


class SceneTriggerEngine:
    """
    管理场景内所有触发器的解析、评估、和触发通知。
    """

    # 触发器块的正则
    TRIGGER_BLOCK_RE = re.compile(
        r"\[TRIGGER\]\s*(.*?)\s*\[/TRIGGER\]",
        re.DOTALL | re.IGNORECASE,
    )
    TRIGGER_FIELD_RE = re.compile(
        r"^\s*(\w+)\s*:\s*(.+?)\s*$",
        re.MULTILINE,
    )

    def __init__(self, game_master):
        self.gm = game_master
        self.evaluator = ConditionEvaluator(game_master)
        # 当前场景已解析的触发器（scene_id -> list[Trigger]）
        self._scene_triggers: dict[str, list[Trigger]] = {}
        # 已被"一次性"触发过的触发器 ID
        self._triggered_once: set[str] = set()

    # ── 解析 ────────────────────────────────

    def parse_scene_triggers(self, scene_content: str, scene_id: str) -> list[Trigger]:
        """
        从场景内容中提取所有 [TRIGGER] 块，返回 Trigger 对象列表。
        缓存结果避免重复解析。
        """
        if scene_id in self._scene_triggers:
            return self._scene_triggers[scene_id]

        triggers: list[Trigger] = []
        for block_idx, block_match in enumerate(
            self.TRIGGER_BLOCK_RE.finditer(scene_content)
        ):
            block = block_match.group(1)
            fields: dict[str, str] = {}
            for field_match in self.TRIGGER_FIELD_RE.finditer(block):
                fields[field_match.group(1)] = field_match.group(2)

            condition = fields.get("condition", fields.get("if", ""))
            target = fields.get("scene", fields.get("goto", ""))
            if not condition or not target:
                continue

            trigger_id = f"{scene_id}_t{block_idx}"
            trigger = Trigger(
                id=trigger_id,
                condition=condition,
                target_scene=target,
                immediate=fields.get("immediate", "false").lower() == "true",
                priority=int(fields.get("priority", 0)),
                once=fields.get("once", "true").lower() != "false",
                description=fields.get("description", ""),
            )
            triggers.append(trigger)

        triggers.sort(key=lambda t: t.priority, reverse=True)
        self._scene_triggers[scene_id] = triggers
        return triggers

    # ── 评估 ────────────────────────────────

    def evaluate_scene(self, scene_id: str) -> list[Trigger]:
        """
        评估当前场景所有触发器，返回所有满足条件的 Trigger 列表。
        不修改状态。
        """
        scene = self.gm.game_loader.get_scene(scene_id)
        if not scene:
            return []
        triggers = self.parse_scene_triggers(scene.content, scene_id)
        active: list[Trigger] = []
        for t in triggers:
            # once 过滤器
            if t.once and t.id in self._triggered_once:
                continue
            if self.evaluator.evaluate(t.condition):
                active.append(t)
        return active

    def check_and_fire(self, scene_id: str) -> Optional[str]:
        """
        评估场景触发器，如果有满足条件且非 immediate 的触发器，
        返回目标场景 ID（只返回第一个）。
        immediate 触发器调用 check_immediate() 处理。
        返回 None 表示无触发。
        """
        active = self.evaluate_scene(scene_id)
        for t in active:
            if not t.immediate:
                # 标记一次性触发器
                if t.once:
                    self._triggered_once.add(t.id)
                return t.target_scene
        return None

    def check_immediate(self, scene_id: str) -> list[str]:
        """
        返回场景中所有满足条件的 immediate 触发器的目标场景 ID 列表。
        由进入场景后立即调用。
        """
        active = self.evaluate_scene(scene_id)
        targets: list[str] = []
        for t in active:
            if t.immediate:
                if t.once:
                    self._triggered_once.add(t.id)
                targets.append(t.target_scene)
        return targets

    # ── 清除（换场时调用）───────────────────────────────

    def on_leave_scene(self, scene_id: str):
        """离开场景时清理该场景的缓存，下次进入重新解析"""
        self._scene_triggers.pop(scene_id, None)

    def reset(self):
        """重置所有触发状态（重新开始游戏时调用）"""
        self._scene_triggers.clear()
        self._triggered_once.clear()

    # ── 工具方法 ────────────────────────────────

    def get_trigger_summary(self, scene_id: str) -> str:
        """
        返回场景中所有触发器的可读摘要，供 DM 在叙事时参考。
        不评估条件，只展示已定义的触发规则。
        """
        scene = self.gm.game_loader.get_scene(scene_id)
        if not scene:
            return ""
        triggers = self.parse_scene_triggers(scene.content, scene_id)
        if not triggers:
            return ""
        lines = ["【场景触发规则】"]
        for t in triggers:
            once_tag = "（一次性）" if t.once else ""
            imm_tag = "【立即】" if t.immediate else ""
            lines.append(
                f"- 如果 {t.condition} → 跳转「{t.target_scene}」"
                f"{once_tag}{imm_tag}"
            )
        return "\n".join(lines)
