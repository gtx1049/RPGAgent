# systems/moral_debt.py - 道德债务系统
from dataclasses import dataclass
from typing import List, Dict
from .interface import IMoralDebtSystem


DEBT_LEVELS = [
    (0, "洁净", []),
    (11, "微债", ["可进行普通叙事行动"]),
    (26, "轻债", ["部分积极选项受限"]),
    (51, "中债", ["关键选项被锁定"]),
    (76, "重债", ["只能选消极/破坏性选项"]),
    (100, "深债", ["极端结局触发"]),
]


@dataclass
class DebtRecord:
    source: str
    amount: int
    scene: str
    description: str


class MoralDebtSystem(IMoralDebtSystem):
    """道德债务管理系统（实现 IMoralDebtSystem）"""

    def __init__(self, initial: int = 0):
        self.debt = initial
        self.records: List[DebtRecord] = []

    def add(self, source: str, amount: int, scene: str, description: str = "") -> int:
        self.debt += amount
        self.records.append(DebtRecord(source, amount, scene, description))
        return self.debt

    def reduce(self, source: str, amount: int, scene: str, description: str = "") -> int:
        return self.add(source, -abs(amount), scene, description)

    def get_level(self) -> tuple:
        for threshold, name, effects in reversed(DEBT_LEVELS):
            if self.debt >= threshold:
                return threshold, name, effects
        return 0, "洁净", []

    def get_locked_options(self) -> List[str]:
        _, name, _ = self.get_level()
        locked = []
        if name in ("轻债", "中债", "重债", "深债"):
            locked.append("主动干预")
        if name in ("中债", "重债", "深债"):
            locked.append("积极行动")
        if name in ("重债", "深债"):
            locked.append("道德洁癖选项")
        return locked

    def can_take_option(self, option_type: str) -> bool:
        return option_type not in self.get_locked_options()

    def get_snapshot(self) -> Dict:
        threshold, name, effects = self.get_level()
        return {
            "debt": self.debt,
            "threshold": threshold,
            "level": name,
            "effects": effects,
            "locked_options": self.get_locked_options(),
            "record_count": len(self.records),
        }

    def get_recent_records(self, n: int = 5) -> List[Dict]:
        return [
            {"source": r.source, "amount": r.amount, "scene": r.scene, "desc": r.description}
            for r in self.records[-n:]
        ]
