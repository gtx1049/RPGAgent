# systems/stats.py - 角色属性系统（D&D 风格扩展）
"""
D&D 风格六属性 + RPG 数值 + 行动力系统

属性修正 = (属性值 - 10) / 2（向下取整）

行动力（行动力）：
- 每回合开始时恢复至最大
- 普通行动消耗1行动力，特殊行动消耗更多
- 行动力耗尽时只能执行免费动作（说话、观察）
"""

from dataclasses import dataclass, field
from typing import Dict
from ..config.settings import DEFAULT_STATS, DEFAULT_ACTION_POWER
from .interface import IStatsSystem


@dataclass
class AbilityScores:
    """D&D 风格六属性"""
    strength: int = 10       # 力量
    dexterity: int = 10      # 敏捷
    constitution: int = 10   # 体质
    intelligence: int = 10  # 智力
    wisdom: int = 10        # 感知
    charisma: int = 10       # 魅力

    def modifier(self, attr: str) -> int:
        val = getattr(self, attr, 10)
        return (val - 10) // 2

    def to_dict(self) -> Dict:
        return {
            "strength": self.strength,
            "dexterity": self.dexterity,
            "constitution": self.constitution,
            "intelligence": self.intelligence,
            "wisdom": self.wisdom,
            "charisma": self.charisma,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "AbilityScores":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class Stats:
    """RPG 角色战斗/状态数值"""
    hp: int = 100
    max_hp: int = 100
    stamina: int = 100
    max_stamina: int = 100
    action_power: int = 3   # 行动力（每回合消耗）
    max_action_power: int = 3
    level: int = 1           # 等级
    exp: int = 0             # 经验值
    exp_to_level: int = 100  # 升级所需经验

    def to_dict(self) -> Dict:
        return {
            "hp": self.hp,
            "max_hp": self.max_hp,
            "stamina": self.stamina,
            "max_stamina": self.max_stamina,
            "action_power": self.action_power,
            "max_action_power": self.max_action_power,
            "level": self.level,
            "exp": self.exp,
            "exp_to_level": self.exp_to_level,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Stats":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in valid})


class StatsSystem(IStatsSystem):
    """角色属性管理系统"""

    def __init__(self, initial: Dict = None):
        defaults = DEFAULT_STATS.copy()
        defaults["action_power"] = DEFAULT_ACTION_POWER
        defaults["max_action_power"] = DEFAULT_ACTION_POWER
        if initial:
            defaults.update(initial)
        self.stats = Stats(**{k: defaults[k] for k in [
            "hp", "max_hp", "stamina", "max_stamina",
            "action_power", "max_action_power", "level", "exp", "exp_to_level"
        ] if k in defaults})
        self.ability = AbilityScores(**{k: defaults[k] for k in [
            "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"
        ] if k in defaults})
        self.gold = 0  # 金币（独立属性，不在 Stats dataclass 中）
        # 装备加成追踪（用于增量更新，避免重复叠加）
        self._prev_equip_bonus: Dict = {
            "strength": 0, "dexterity": 0, "constitution": 0,
            "intelligence": 0, "wisdom": 0, "charisma": 0,
            "max_hp": 0,
        }

    def get(self, key: str) -> int:
        return getattr(self.stats, key, 0)

    def modify(self, key: str, delta: int) -> int:
        current = self.get(key)
        new_val = current + delta

        if key in ("hp", "max_hp"):
            self.stats.hp = max(0, min(new_val, self.stats.max_hp))
        elif key in ("stamina", "max_stamina"):
            self.stats.stamina = max(0, min(new_val, self.stats.max_stamina))
        elif key in ("action_power",):
            self.stats.action_power = max(0, min(new_val, self.stats.max_action_power))
        elif key == "gold":
            self.gold = max(0, new_val)
            return self.gold
        else:
            setattr(self.stats, key, new_val)

        return getattr(self.stats, key)

    def recalculate_from_equipment(self, bonus_dict: Dict) -> None:
        """
        根据装备加成字典增量更新属性。
        
        仅施加「新增/减少」的差值，避免重复叠加。
        调用时机：装备变更后（自动装备 / 换装 / 卸装）。
        
        Args:
            bonus_dict: EquipmentSystem.get_total_bonus() 返回的字典，
                        包含 strength/dexterity/constitution/intelligence/
                        wisdom/charisma/max_hp 等属性加成。
        """
        if not bonus_dict:
            return

        attrs = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
        for attr in attrs:
            prev = self._prev_equip_bonus.get(attr, 0)
            curr = bonus_dict.get(attr, 0)
            delta = curr - prev
            if delta != 0:
                old_val = getattr(self.ability, attr)
                new_val = old_val + delta
                setattr(self.ability, attr, new_val)
                self._prev_equip_bonus[attr] = curr

        # max_hp：EquipmentStats 的 max_hp 是装备提供的加值
        prev_hp = self._prev_equip_bonus.get("max_hp", 0)
        curr_hp = bonus_dict.get("max_hp", 0)
        hp_delta = curr_hp - prev_hp
        if hp_delta != 0:
            # 同时更新 max_hp 和当前 hp（保持当前 hp 比例）
            old_max = self.stats.max_hp
            new_max = old_max + hp_delta
            # HP 比例不变地上调
            if old_max > 0:
                hp_ratio = self.stats.hp / old_max
                self.stats.hp = int(new_max * hp_ratio)
            self.stats.max_hp = new_max
            self._prev_equip_bonus["max_hp"] = curr_hp

    def take_damage(self, amount: int) -> int:
        return self.modify("hp", -abs(amount))

    def heal(self, amount: int) -> int:
        return self.modify("hp", abs(amount))

    def use_stamina(self, amount: int) -> bool:
        if self.stats.stamina >= amount:
            self.modify("stamina", -abs(amount))
            return True
        return False

    def restore_stamina(self, amount: int) -> int:
        return self.modify("stamina", abs(amount))

    def use_ap(self, amount: int = 1) -> bool:
        """消耗行动力，返回是否成功（行动力不足时返回False）"""
        if self.stats.action_power >= amount:
            self.modify("action_power", -amount)
            return True
        return False

    def refresh_ap(self):
        """新回合开始，重置行动力"""
        self.stats.action_power = self.stats.max_action_power

    def gain_exp(self, amount: int) -> Dict:
        """获得经验值，检查是否升级"""
        self.stats.exp += amount
        leveled_up = []
        while self.stats.exp >= self.stats.exp_to_level:
            self.stats.exp -= self.stats.exp_to_level
            self.stats.level += 1
            self.stats.exp_to_level = int(self.stats.exp_to_level * 1.5)
            # 升级奖励
            self.stats.max_hp += 10
            self.stats.hp = self.stats.max_hp
            self.stats.max_action_power = min(self.stats.max_action_power + 1, 6)
            self.stats.action_power = self.stats.max_action_power
            leveled_up.append(self.stats.level)
        return {"leveled_up": leveled_up, "level": self.stats.level, "exp": self.stats.exp}

    def get_modifier(self, attribute_key: str) -> int:
        """获取属性修正值"""
        return self.ability.modifier(attribute_key)

    def get_snapshot(self) -> Dict:
        return {
            **self.stats.to_dict(),
            "gold": self.gold,
            "ability": self.ability.to_dict(),
            "ability_modifiers": {
                "strength": self.ability.modifier("strength"),
                "dexterity": self.ability.modifier("dexterity"),
                "constitution": self.ability.modifier("constitution"),
                "intelligence": self.ability.modifier("intelligence"),
                "wisdom": self.ability.modifier("wisdom"),
                "charisma": self.ability.modifier("charisma"),
            },
        }

    def is_alive(self) -> bool:
        return self.stats.hp > 0
