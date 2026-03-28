# systems/inventory.py - 背包/物品系统
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from .interface import IInventorySystem


@dataclass
class Item:
    id: str
    name: str
    description: str = ""
    quantity: int = 1
    usable: bool = False
    effect: Dict = field(default_factory=dict)
    tradable: bool = True


class InventorySystem(IInventorySystem):
    """物品管理系统（实现 IInventorySystem）"""

    def __init__(self, capacity: int = 20):
        self.capacity = capacity
        self.items: List[Item] = []
        self.equipped: Dict[str, str] = {}

    def add(self, item: Item) -> bool:
        if len(self.items) >= self.capacity:
            return False
        for existing in self.items:
            if existing.id == item.id:
                existing.quantity += item.quantity
                return True
        self.items.append(item)
        return True

    def remove(self, item_id: str, quantity: int = 1) -> bool:
        for item in self.items:
            if item.id == item_id:
                if item.quantity <= quantity:
                    self.items.remove(item)
                else:
                    item.quantity -= quantity
                return True
        return False

    def has(self, item_id: str) -> bool:
        return any(i.id == item_id for i in self.items)

    def get(self, item_id: str) -> Optional[Item]:
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def use_item(self, item_id: str, stats_sys) -> Dict:
        item = self.get(item_id)
        if not item or not item.usable:
            return {"success": False, "message": "无法使用该物品"}

        result = {"success": True, "effects": {}}
        for stat, delta in item.effect.items():
            old_val = stats_sys.get(stat)
            new_val = stats_sys.modify(stat, delta)
            result["effects"][stat] = {"from": old_val, "to": new_val, "delta": delta}

        result["message"] = f"使用了 {item.name}"
        return result

    def list_items(self) -> List[Dict]:
        return [
            {
                "id": i.id,
                "name": i.name,
                "description": i.description,
                "quantity": i.quantity,
                "usable": i.usable,
            }
            for i in self.items
        ]

    def add_item(self, name_or_id: str, item_data: Dict) -> bool:
        """
        便捷方法：从存档 dict 恢复物品。
        item_data 应包含 id/name/description/quantity/usable 等字段。
        """
        item = Item(
            id=item_data.get("id", name_or_id),
            name=item_data.get("name", name_or_id),
            description=item_data.get("description", ""),
            quantity=item_data.get("quantity", 1),
            usable=item_data.get("usable", False),
            effect=item_data.get("effect", {}),
            tradable=item_data.get("tradable", True),
        )
        return self.add(item)

    def get_snapshot(self) -> Dict:
        return {
            "capacity": self.capacity,
            "used": len(self.items),
            "items": self.list_items(),
            "equipped": self.equipped,
        }
