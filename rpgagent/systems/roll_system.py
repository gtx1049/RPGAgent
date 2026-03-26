# systems/roll_system.py - D20 骰点判定系统
"""
玩家行动需要通过 d20 判定。
公式：d20 + 属性修正 vs 难度等级（DC）

属性修正 = (属性值 - 10) / 2（向下取整）

难度等级：
- 简单 DC 10：普通社交、采集
- 中等 DC 15：战斗、潜行、欺骗
- 困难 DC 20：高风险行动
- 极难 DC 25：传奇级行动

判定结果：
- 1 = 大失败（自动失败）
- 20 = 大成功（自动成功 + 额外效果）
- d20 + mod >= DC = 成功
- d20 + mod < DC = 失败
"""

import random
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class DifficultyLevel(Enum):
    TRIVIAL = 5      # 容易
    EASY = 10        # 简单
    MEDIUM = 15      # 中等
    HARD = 20       # 困难
    VERY_HARD = 25   # 极难
    NEARLY_IMPOSSIBLE = 30  # 几乎不可能


@dataclass
class RollResult:
    """单次 d20 判定结果"""
    roll: int          # 掷出的 d20 点数
    modifier: int      # 属性/技能修正
    total: int         # 最终值（roll + modifier）
    difficulty: int    # 难度等级 DC
    success: bool      # 是否成功
    critical: bool     # 是否大成功（20）
    fumble: bool       # 是否大失败（1）
    description: str   # 结果描述


class RollSystem:
    """d20 骰点判定系统"""

    D20_SIDES = 20

    def __init__(self, stats_sys, skill_sys=None):
        self.stats_sys = stats_sys
        self.skill_sys = skill_sys
        self._seed = None  # 可设置随机种子用于测试

    def _roll_d20(self) -> int:
        """掷 d20，返回 1-20"""
        if self._seed is not None:
            # 测试用确定性随机
            random.seed(self._seed)
        return random.randint(1, self.D20_SIDES)

    @staticmethod
    def attribute_modifier(attribute_value: int) -> int:
        """属性值 → 修正值（d20 规则：(属性-10)/2，向下取整）"""
        return (attribute_value - 10) // 2

    def get_modifier(self, attribute_key: str, skill_key: Optional[str] = None) -> int:
        """
        获取完整修正值 = 属性修正 + 技能修正（如果有）
        """
        attr_val = self.stats_sys.get(attribute_key)
        mod = self.attribute_modifier(attr_val)

        if skill_key and self.skill_sys:
            skill_bonus = self.skill_sys.get_skill_bonus(skill_key)
            mod += skill_bonus

        return mod

    def roll(
        self,
        attribute_key: str,
        skill_key: Optional[str] = None,
        difficulty: int = 15,
        advantage: bool = False,
        disadvantage: bool = False,
    ) -> RollResult:
        """
        执行 d20 判定。

        参数：
        - attribute_key: 属性键（strength, agility, intelligence 等）
        - skill_key: 技能键（可选）
        - difficulty: 难度等级 DC
        - advantage: 优势（掷2个d20，取较高）
        - disadvantage: 劣势（掷2个d20，取较低）

        返回：RollResult
        """
        modifier = self.get_modifier(attribute_key, skill_key)

        # 优势/劣势
        if advantage and not disadvantage:
            roll1 = self._roll_d20()
            roll2 = self._roll_d20()
            roll = max(roll1, roll2)
            roll_type = f"2d20H({roll1},{roll2})"
        elif disadvantage and not advantage:
            roll1 = self._roll_d20()
            roll2 = self._roll_d20()
            roll = min(roll1, roll2)
            roll_type = f"2d20L({roll1},{roll2})"
        else:
            roll = self._roll_d20()
            roll_type = f"d20({roll})"

        total = roll + modifier
        success = total >= difficulty

        # 大成功/大失败
        critical = (roll == 20)
        fumble = (roll == 1)

        # 自动成功/失败（1和大成功20仍然要计算）
        if fumble:
            success = False
        if critical:
            success = True

        # 描述
        if critical:
            desc = "💥 大成功！"
        elif fumble:
            desc = "💀 大失败！"
        elif success:
            margin = total - difficulty
            if margin >= 10:
                desc = f"✅ 大成功（超过DC {margin}点）"
            else:
                desc = f"✅ 成功（超过DC {margin}点）"
        else:
            margin = difficulty - total
            desc = f"❌ 失败（差 {margin}点）"

        desc += f" [{roll_type} + {modifier} = {total} vs DC {difficulty}]"

        return RollResult(
            roll=roll,
            modifier=modifier,
            total=total,
            difficulty=difficulty,
            success=success,
            critical=critical,
            fumble=fumble,
            description=desc,
        )

    def roll_for_opponent(
        self,
        attacker_roll: RollResult,
        defense_attribute: str = "agility",
        base_defense: int = 10,
    ) -> RollResult:
        """
        防御方判定（用于对抗性检定，如敏捷回避）
        返回防御方结果，对比攻击方是否穿透
        """
        defense_result = self.roll(defense_attribute, difficulty=base_defense)
        return defense_result

    def format_roll_check(self, result: RollResult, action_name: str) -> str:
        """格式化为叙事文本"""
        return (
            f"🎲 {action_name}判定\n"
            f"   {result.description}\n"
        )
