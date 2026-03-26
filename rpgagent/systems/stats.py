# systems/stats.py - 角色属性系统
from dataclasses import dataclass
from typing import Dict
from ..config.settings import DEFAULT_STATS
from .interface import IStatsSystem


@dataclass
class Stats:
    hp: int = 100
    max_hp: int = 100
    stamina: int = 100
    max_stamina: int = 100
    strength: int = 10
    agility: int = 10
    intelligence: int = 10
    charisma: int = 10

    def to_dict(self) -> Dict:
        return {
            "hp": self.hp,
            "max_hp": self.max_hp,
            "stamina": self.stamina,
            "max_stamina": self.max_stamina,
            "strength": self.strength,
            "agility": self.agility,
            "intelligence": self.intelligence,
            "charisma": self.charisma,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Stats":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in valid})


class StatsSystem(IStatsSystem):
    """角色属性管理系统（实现 IStatsSystem）"""

    def __init__(self, initial: Dict = None):
        defaults = DEFAULT_STATS.copy()
        if initial:
            defaults.update(initial)
        self.stats = Stats(**defaults)

    def get(self, key: str) -> int:
        return getattr(self.stats, key, 0)

    def modify(self, key: str, delta: int) -> int:
        current = self.get(key)
        new_val = current + delta

        if key in ("hp", "max_hp"):
            self.stats.hp = max(0, min(new_val, self.stats.max_hp))
        elif key in ("stamina", "max_stamina"):
            self.stats.stamina = max(0, min(new_val, self.stats.max_stamina))
        else:
            setattr(self.stats, key, new_val)

        return getattr(self.stats, key)

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

    def get_snapshot(self) -> Dict:
        return self.stats.to_dict()

    def is_alive(self) -> bool:
        return self.stats.hp > 0
