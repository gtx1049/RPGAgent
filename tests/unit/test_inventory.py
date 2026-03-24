# tests/unit/test_inventory.py
import pytest
from systems.inventory import InventorySystem, Item


class TestInventorySystem:
    def test_add_item(self, inventory_system):
        item = Item(id="sword", name="铁剑")
        ok = inventory_system.add(item)
        assert ok is True
        assert inventory_system.has("sword")

    def test_add_stackable(self, inventory_system):
        item1 = Item(id="potion", name="血药", quantity=3)
        item2 = Item(id="potion", name="血药", quantity=2)
        inventory_system.add(item1)
        inventory_system.add(item2)
        assert inventory_system.get("potion").quantity == 5

    def test_add_capacity_limit(self, inventory_system):
        # 默认容量20，放21个
        for i in range(20):
            inventory_system.add(Item(id=f"item_{i}", name=f"物品{i}"))
        ok = inventory_system.add(Item(id="overflow", name="溢出"))
        assert ok is False

    def test_remove_item(self, inventory_system):
        inventory_system.add(Item(id="sword", name="铁剑", quantity=3))
        ok = inventory_system.remove("sword", 2)
        assert ok is True
        assert inventory_system.get("sword").quantity == 1

    def test_remove_last(self, inventory_system):
        inventory_system.add(Item(id="sword", name="铁剑"))
        inventory_system.remove("sword")
        assert inventory_system.has("sword") is False

    def test_remove_nonexistent(self, inventory_system):
        ok = inventory_system.remove("notexist")
        assert ok is False

    def test_get_item(self, inventory_system):
        inventory_system.add(Item(id="sword", name="铁剑"))
        item = inventory_system.get("sword")
        assert item.name == "铁剑"

    def test_get_nonexistent(self, inventory_system):
        item = inventory_system.get("notexist")
        assert item is None

    def test_list_items(self, inventory_system):
        inventory_system.add(Item(id="a", name="物品A"))
        inventory_system.add(Item(id="b", name="物品B"))
        items = inventory_system.list_items()
        assert len(items) == 2

    def test_snapshot(self, inventory_system):
        inventory_system.add(Item(id="sword", name="铁剑"))
        snap = inventory_system.get_snapshot()
        assert snap["capacity"] == 20
        assert snap["used"] == 1
        assert len(snap["items"]) == 1

    def test_use_item(self, inventory_system, stats_system):
        inventory_system.add(Item(
            id="potion", name="血药", usable=True,
            effect={"hp": 20}
        ))
        stats_system.take_damage(30)  # hp=70
        result = inventory_system.use_item("potion", stats_system)
        assert result["success"] is True
        assert stats_system.get("hp") == 90

    def test_use_item_not_usable(self, inventory_system):
        inventory_system.add(Item(id="sword", name="铁剑", usable=False))
        result = inventory_system.use_item("sword", None)
        assert result["success"] is False


class TestItem:
    def test_item_default(self):
        item = Item(id="test", name="测试")
        assert item.quantity == 1
        assert item.usable is False
        assert item.tradable is True
        assert item.effect == {}

    def test_item_with_effect(self):
        item = Item(id="potion", name="", effect={"hp": 10, "stamina": -5})
        assert item.effect["hp"] == 10
