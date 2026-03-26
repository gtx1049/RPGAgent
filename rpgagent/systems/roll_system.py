# systems/roll_system.py - 简化为成功率的判定系统
"""
行动判定结果分 4 档，直接显示给玩家：
- 轻松（≥70% 成功率）：大多数普通人能完成的事
- 五五开（40-69%）：有风险，需要一定能力
- 难搞（20-39%）：困难任务，只有熟练者能完成
- 几无可能（<20%）：几乎不可能，需要特殊手段或运气

内部成功率计算：
  基础成功率 = (20 - DC + 10) / 20 × 100%
  最终成功率 = 基础成功率 + 属性修正（每点修正 ±5%）

属性修正 = (属性值 - 10) / 2
- 力量10 → 力量修正 0
- 力量12 → 力量修正 +1 → 成功率 +5%
- 力量8  → 力量修正 -1 → 成功率 -5%
"""

import random
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class DifficultyTier(Enum):
    """难度档位（显示给玩家）"""
    EASY = "轻松"           # ≥70%
    RISKY = "五五开"        # 40-69%
    HARD = "难搞"           # 20-39%
    NEAR_IMPOSSIBLE = "几无可能"  # <20%


@dataclass
class CheckResult:
    """判定结果"""
    tier: DifficultyTier       # 难度档位
    roll: int                 # 掷出的随机数 1-100
    threshold: int             # 成功阈值（1-100）
    modifier: int             # 属性修正
    success: bool            # 是否成功
    critical: bool            # 大成功（掷出96-100）
    fumble: bool             # 大失败（掷出1-5）
    description: str          # 叙事描述


# ─── 成功率阈值配置 ────────────────────────────────

TIER_THRESHOLDS = {
    DifficultyTier.NEAR_IMPOSSIBLE: 20,   # < 20
    DifficultyTier.HARD: 40,               # 20-39
    DifficultyTier.RISKY: 70,              # 40-69
    DifficultyTier.EASY: 100,              # ≥70
}

TIER_NAMES_CN = {
    DifficultyTier.EASY: "轻松",
    DifficultyTier.RISKY: "五五开",
    DifficultyTier.HARD: "难搞",
    DifficultyTier.NEAR_IMPOSSIBLE: "几无可能",
}

# 行动描述前缀（嵌入叙事用）
TIER_NARRATIVE = {
    DifficultyTier.EASY: "这件事对你来说轻而易举",
    DifficultyTier.RISKY: "这件事有一定风险，你没有十足把握",
    DifficultyTier.HARD: "这对你来说相当困难，需要拼尽全力",
    DifficultyTier.NEAR_IMPOSSIBLE: "这几乎是不可能完成的任务",
}


def tier_from_probability(probability: float) -> DifficultyTier:
    """根据成功率概率返回档位"""
    pct = probability * 100
    if pct >= 70:
        return DifficultyTier.EASY
    elif pct >= 40:
        return DifficultyTier.RISKY
    elif pct >= 20:
        return DifficultyTier.HARD
    else:
        return DifficultyTier.NEAR_IMPOSSIBLE


def tier_name(tier: DifficultyTier) -> str:
    return TIER_NAMES_CN[tier]


class RollSystem:
    """简化成功率判定系统"""

    def __init__(self, stats_sys, skill_sys=None, equipment_sys=None):
        self.stats_sys = stats_sys
        self.skill_sys = skill_sys
        self.equipment_sys = equipment_sys

    def _roll_d100(self) -> int:
        """掷百面骰（1-100）"""
        return random.randint(1, 100)

    @staticmethod
    def attribute_modifier(attribute_value: int) -> int:
        """属性修正：每 ±2 属性值 = ±5% 成功率"""
        return (attribute_value - 10) // 2

    def get_modifier(self, attribute_key: str) -> int:
        """获取玩家属性修正（含装备加成）"""
        base = self.stats_sys.get_modifier(attribute_key)
        # 装备属性加成
        if self.equipment_sys:
            bonus = self.equipment_sys.total_bonus
            equip_bonus = getattr(bonus, attribute_key, 0)
            return base + equip_bonus
        return base

    def get_success_probability(
        self,
        attribute_key: str,
        base_difficulty: int = 50,
    ) -> float:
        """
        计算给定属性下的成功概率。

        base_difficulty: 基础难度阈值（1-100）
        - 轻松行动：30-40（高成功率）
        - 五五开：50-60（中等成功率）
        - 难搞：65-80（低成功率）
        - 几无可能：80+（极低成功率）
        """
        modifier = self.get_modifier(attribute_key)
        # 阈值经过属性修正后，再换算成成功率
        adjusted = max(5, min(95, base_difficulty - modifier * 5))
        probability = (100 - adjusted) / 100.0
        return max(0.0, min(1.0, probability))

    def get_tier(
        self,
        attribute_key: str,
        base_difficulty: int = 50,
    ) -> tuple[DifficultyTier, float]:
        """
        获取难度档位和对应成功率。
        返回 (档位, 成功率百分比)
        """
        prob = self.get_success_probability(attribute_key, base_difficulty)
        return tier_from_probability(prob), prob

    def check(
        self,
        attribute_key: str,
        base_difficulty: int = 50,
        narrative_hint: str = "",
    ) -> CheckResult:
        """
        执行判定。

        参数：
        - attribute_key: 使用的属性（strength/dexterity 等）
        - base_difficulty: 基础难度（1-100），参考值：
          * 30 = 轻松（70%基础成功率）
          * 50 = 五五开
          * 65 = 难搞
          * 80 = 几无可能
        - narrative_hint: 行动名称（如"用力推开大石"）

        返回：CheckResult
        """
        modifier = self.get_modifier(attribute_key)

        # 计算成功阈值
        adjusted_threshold = max(5, min(95, base_difficulty - modifier * 5))
        success_threshold = 100 - adjusted_threshold  # 1-100 中需要掷出 >= 此值

        # 掷骰
        roll = self._roll_d100()

        # 判定
        success = roll >= success_threshold

        # 大成功 / 大失败
        critical = roll >= 96
        fumble = roll <= 5
        if fumble:
            success = False
        elif critical:
            success = True

        # 档位
        prob = self.get_success_probability(attribute_key, base_difficulty)
        tier = tier_from_probability(prob)

        # 描述
        if critical:
            tier_desc = "💥 大成功！远远超出预期"
        elif fumble:
            tier_desc = "💀 大失败！情况比你想象的更糟"
        elif success:
            tier_desc = f"✅ 成功（{roll} ≥ {success_threshold}）"
        else:
            tier_desc = f"❌ 失败（{roll} < {success_threshold}）"

        modifier_str = f"+{modifier}" if modifier >= 0 else str(modifier)
        tier_str = TIER_NAMES_CN[tier]
        hint = f"【{tier_str}】" if narrative_hint else ""

        description = (
            f"🎲 {hint}{narrative_hint}\n"
            f"   {tier_desc} | 属性修正 {modifier_str} | 阈值 {success_threshold}\n"
            f"   {TIER_NARRATIVE[tier]}"
        )

        return CheckResult(
            tier=tier,
            roll=roll,
            threshold=success_threshold,
            modifier=modifier,
            success=success,
            critical=critical,
            fumble=fumble,
            description=description,
        )

    def format_result(self, result: CheckResult, action: str = "") -> str:
        """格式化判定结果为叙事文本（嵌入 GM 叙事用）"""
        return result.description
