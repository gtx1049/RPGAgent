# systems/interface.py - 数值系统抽象接口
"""
所有数值系统的抽象基类定义。
用于：1) 单元测试 mock 2) 未来替换实现
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class IStatsSystem(ABC):
    """属性系统接口"""

    @abstractmethod
    def get(self, key: str) -> int: ...

    @abstractmethod
    def modify(self, key: str, delta: int) -> int: ...

    @abstractmethod
    def take_damage(self, amount: int) -> int: ...

    @abstractmethod
    def heal(self, amount: int) -> int: ...

    @abstractmethod
    def use_stamina(self, amount: int) -> bool: ...

    @abstractmethod
    def restore_stamina(self, amount: int) -> int: ...

    @abstractmethod
    def get_snapshot(self) -> Dict[str, Any]: ...

    @abstractmethod
    def is_alive(self) -> bool: ...


class IMoralDebtSystem(ABC):
    """道德债务系统接口"""

    @abstractmethod
    def add(self, source: str, amount: int, scene: str, description: str = "") -> int: ...

    @abstractmethod
    def reduce(self, source: str, amount: int, scene: str, description: str = "") -> int: ...

    @abstractmethod
    def get_level(self) -> tuple: ...

    @abstractmethod
    def get_locked_options(self) -> list: ...

    @abstractmethod
    def can_take_option(self, option_type: str) -> bool: ...

    @abstractmethod
    def get_snapshot(self) -> Dict[str, Any]: ...


class IInventorySystem(ABC):
    """背包系统接口"""

    @abstractmethod
    def add(self, item) -> bool: ...

    @abstractmethod
    def remove(self, item_id: str, quantity: int = 1) -> bool: ...

    @abstractmethod
    def has(self, item_id: str) -> bool: ...

    @abstractmethod
    def get(self, item_id: str): ...

    @abstractmethod
    def list_items(self) -> list: ...

    @abstractmethod
    def get_snapshot(self) -> Dict[str, Any]: ...


class IDialogueSystem(ABC):
    """对话/关系系统接口"""

    @abstractmethod
    def set_relation(self, npc_id: str, value: int) -> int: ...

    @abstractmethod
    def modify_relation(self, npc_id: str, delta: int) -> int: ...

    @abstractmethod
    def get_relation(self, npc_id: str) -> int: ...

    @abstractmethod
    def get_relation_level(self, npc_id: str) -> str: ...

    @abstractmethod
    def get_all_relations(self) -> Dict[str, Dict]: ...

    @abstractmethod
    def get_snapshot(self) -> Dict[str, Any]: ...


class ICombatSystem(ABC):
    """战斗系统接口"""

    @abstractmethod
    def roll_d20(self) -> int: ...

    @abstractmethod
    def attack_roll(self, attacker_strength: int, attacker_agility: int,
                    difficulty: int = 15, advantage: bool = False,
                    disadvantage: bool = False): ...

    @abstractmethod
    def full_attack(self, attacker_stats: Dict, defender_stats: Dict,
                    advantage: bool = False, difficulty: int = 15): ...
