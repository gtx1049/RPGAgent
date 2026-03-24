# systems/combat.py - 战斗系统
import random
from dataclasses import dataclass
from typing import Tuple, Dict
from config.settings import COMBAT_DICE, DIFFICULTY_EASY, DIFFICULTY_MEDIUM, DIFFICULTY_HARD
from .interface import ICombatSystem


@dataclass
class CombatResult:
    success: bool
    roll: int
    modifier: int
    total: int
    difficulty: int
    damage_dealt: int = 0
    damage_taken: int = 0
    message: str = ""


class CombatSystem(ICombatSystem):
    """d20 战斗检定系统（实现 ICombatSystem）"""

    # 允许注入随机函数（方便测试）
    _randint = staticmethod(random.randint)
    _random = staticmethod(random.random)

    def roll_d20(self) -> int:
        return self._randint(1, COMBAT_DICE)

    @staticmethod
    def get_modifier(stat_value: int) -> int:
        return (stat_value - 10) // 2

    def attack_roll(
        self,
        attacker_strength: int,
        attacker_agility: int,
        difficulty: int = DIFFICULTY_MEDIUM,
        advantage: bool = False,
        disadvantage: bool = False,
    ) -> Tuple[int, int, int, bool]:
        roll = self.roll_d20()

        if advantage and not disadvantage:
            roll = max(roll, self.roll_d20())
        elif disadvantage and not advantage:
            roll = min(roll, self.roll_d20())

        modifier = self.get_modifier(attacker_strength)
        total = roll + modifier
        return roll, modifier, total, total >= difficulty

    def resolve_attack(
        self,
        attacker_strength: int,
        defender_armor: int,
        attack_roll: int,
        crit_range: int = 20,
    ) -> int:
        base_damage = self._randint(1, 6) + self.get_modifier(attacker_strength)
        base_damage = max(1, base_damage)

        if attack_roll >= crit_range:
            base_damage *= 2

        return max(1, base_damage - defender_armor // 4)

    def full_attack(
        self,
        attacker_stats: Dict,
        defender_stats: Dict,
        advantage: bool = False,
        difficulty: int = DIFFICULTY_MEDIUM,
    ) -> CombatResult:
        strength = attacker_stats.get("strength", 10)
        agility = attacker_stats.get("agility", 10)
        armor = attacker_stats.get("armor", 10)

        roll, mod, total, hit = self.attack_roll(
            strength, agility, difficulty, advantage
        )

        if hit:
            damage = self.resolve_attack(strength, armor, roll)
            taken = self._randint(0, 3) if self._random() > 0.5 else 0
            return CombatResult(
                success=True,
                roll=roll,
                modifier=mod,
                total=total,
                difficulty=difficulty,
                damage_dealt=damage,
                damage_taken=taken,
                message=f"攻击成功！造成 {damage} 点伤害，受到 {taken} 点反击伤害。",
            )
        else:
            return CombatResult(
                success=False,
                roll=roll,
                modifier=mod,
                total=total,
                difficulty=difficulty,
                message=f"攻击失败（{total} < {difficulty}）",
            )
