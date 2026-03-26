# systems/acquisition.py - 装备获取系统
"""
处理装备的获取途径：
1. 战利品掉落（loot）— 敌人死亡/战斗结算时触发
2. 宝箱开启（chest）— 场景探索时触发
3. NPC 交易（trade）— 与商人 NPC 对话时触发

获取流程：
  骰点判定 → 成功则按稀有度权重随机抽取 → 发放到背包或直接穿戴提示
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .equipment_system import (
    Equipment, Rarity,
    ARMOR_TEMPLATES,
    OFFHAND_TEMPLATES, ACCESSORY_TEMPLATES,
    get_template_equipment,
)


# ─── 战利品配置 ────────────────────────────────────────

@dataclass
class LootEntry:
    """单条战利品配置"""
    equipment_id: str          # 模板 ID
    weight: int = 1            # 权重（权重越高越容易掉落）
    min_rarity: Rarity = Rarity.COMMON   # 最低稀有度
    max_rarity: Rarity = Rarity.LEGENDARY  # 最高稀有度


@dataclass
class LootTable:
    """一个敌人的战利品表"""
    enemy_id: str
    entries: List[LootEntry] = field(default_factory=list)
    base_drop_chance: float = 0.5   # 基础掉落概率（0.0-1.0）

    def roll_drop(self) -> Optional[Equipment]:
        """骰点判定是否掉落，返回装备或None"""
        if random.random() > self.base_drop_chance:
            return None

        total_weight = sum(e.weight for e in self.entries)
        if total_weight == 0:
            return None

        r = random.randint(1, total_weight)
        cumulative = 0
        chosen: Optional[LootEntry] = None
        for entry in self.entries:
            cumulative += entry.weight
            if r <= cumulative:
                chosen = entry
                break

        if chosen is None:
            return None

        equip = get_template_equipment(chosen.equipment_id)
        if equip is None:
            return None

        # 根据稀有度筛选：如果当前装备稀有度超出范围，向上/下兼容
        return equip


# ─── 宝箱配置 ────────────────────────────────────────

@dataclass
class ChestContent:
    """单个宝箱的内容配置"""
    id: str
    name: str           # 展示名称（如"破旧的木箱"）
    guaranteed: List[str] = field(default_factory=list)  # 必掉物品ID列表
    optional: List[LootEntry] = field(default_factory=list)  # 可选物品（按权重抽取）
    optional_count: int = 1   # 可选抽取数量
    gold_range: tuple[int, int] = (0, 0)   # 金币范围
    opened_desc: str = ""   # 开启后的描述

    def open(self) -> Dict:
        """开启宝箱，返回结果"""
        items: List[Equipment] = []
        gold = random.randint(*self.gold_range) if self.gold_range != (0, 0) else 0

        # 必掉
        for eid in self.guaranteed:
            e = get_template_equipment(eid)
            if e:
                items.append(e)

        # 可选抽取
        if self.optional and self.optional_count > 0:
            total_weight = sum(o.weight for o in self.optional)
            drawn: List[LootEntry] = []
            for _ in range(min(self.optional_count, len(self.optional))):
                if total_weight == 0:
                    break
                r = random.randint(1, total_weight)
                cumulative = 0
                for entry in self.optional:
                    cumulative += entry.weight
                    if r <= cumulative:
                        drawn.append(entry)
                        total_weight -= entry.weight
                        break
            for entry in drawn:
                e = get_template_equipment(entry.equipment_id)
                if e:
                    items.append(e)

        return {
            "chest_id": self.id,
            "chest_name": self.name,
            "items": items,
            "gold": gold,
            "opened_desc": self.opened_desc,
        }


# ─── NPC 商人配置 ─────────────────────────────────────

@dataclass
class MerchantEntry:
    """NPC 商人的商品列表"""
    npc_id: str
    wares: List[str] = field(default_factory=list)  # 装备模板ID列表
    restock_each_turn: bool = False  # 是否每回合刷新库存
    _inventory: List[str] = field(default_factory=list, init=False, repr=False)

    def get_inventory(self) -> List[Equipment]:
        items = []
        for wid in self._inventory:
            e = get_template_equipment(wid)
            if e:
                items.append(e)
        return items

    def restock(self):
        """刷新库存"""
        self._inventory = list(self.wares)


# ─── 全局获取配置 ──────────────────────────────────────

# 默认战利品表（按敌人ID映射）
DEFAULT_LOOT_TABLES: Dict[str, LootTable] = {
    "soldier_1": LootTable(
        enemy_id="soldier_1",
        base_drop_chance=0.4,
        entries=[
            LootEntry("wooden_sword", weight=3, min_rarity=Rarity.COMMON, max_rarity=Rarity.UNCOMMON),
            LootEntry("bow", weight=2, min_rarity=Rarity.COMMON, max_rarity=Rarity.RARE),
            LootEntry("leather", weight=2, min_rarity=Rarity.UNCOMMON, max_rarity=Rarity.RARE),
            LootEntry("wooden_shield", weight=3, min_rarity=Rarity.COMMON, max_rarity=Rarity.UNCOMMON),
            LootEntry("lucky_charm", weight=1, min_rarity=Rarity.RARE, max_rarity=Rarity.EPIC),
        ],
    ),
}

# 默认宝箱配置（按 chest_xxx ID 映射）
DEFAULT_CHESTS: Dict[str, ChestContent] = {
    "wooden_chest": ChestContent(
        id="wooden_chest",
        name="破旧的木箱",
        guaranteed=[],
        optional=[
            LootEntry("wooden_sword", weight=3),
            LootEntry("cloth", weight=3),
            LootEntry("leather", weight=2),
            LootEntry("lucky_charm", weight=1),
        ],
        optional_count=1,
        gold_range=(5, 20),
        opened_desc="木箱已经腐朽，你撬开锈蚀的锁扣，里头的东西露了出来。",
    ),
    "iron_chest": ChestContent(
        id="iron_chest",
        name="铁皮宝箱",
        guaranteed=[],
        optional=[
            LootEntry("iron_sword", weight=3),
            LootEntry("leather", weight=2),
            LootEntry("chainmail", weight=2),
            LootEntry("iron_shield", weight=2),
            LootEntry("wisdom_tome", weight=1),
        ],
        optional_count=2,
        gold_range=(20, 60),
        opened_desc="铁箱沉重，你用力掀开箱盖，一阵金属气息扑面而来。",
    ),
    "captain_chest": ChestContent(
        id="captain_chest",
        name="军官的镶钉箱",
        guaranteed=["steel_sword"],
        optional=[
            LootEntry("strength_belt", weight=2),
            LootEntry("iron_shield", weight=2),
        ],
        optional_count=1,
        gold_range=(50, 100),
        opened_desc="这是一只镶钉木箱，箱面刷着褪色的秦篆。你推开锁扣，金石之声清脆作响。",
    ),
}

# 默认 NPC 商人
DEFAULT_MERCHANTS: Dict[str, MerchantEntry] = {
    "village_merchant": MerchantEntry(
        npc_id="village_merchant",
        wares=["wooden_sword", "bow", "leather", "wooden_shield", "cloth"],
        restock_each_turn=False,
    ),
}


# ─── AcquisitionSystem ─────────────────────────────────────

class AcquisitionSystem:
    """
    统一管理装备获取入口：
    - 战利品掉落（loot）
    - 宝箱开启（chest）
    - NPC 交易（trade）
    """

    def __init__(
        self,
        loot_tables: Optional[Dict[str, LootTable]] = None,
        chests: Optional[Dict[str, ChestContent]] = None,
        merchants: Optional[Dict[str, MerchantEntry]] = None,
    ):
        self.loot_tables = loot_tables if loot_tables else dict(DEFAULT_LOOT_TABLES)
        self.chests = chests if chests else dict(DEFAULT_CHESTS)
        self.merchants = merchants if merchants else dict(DEFAULT_MERCHANTS)
        self.chest_states: Dict[str, bool] = {}

        # 初始化商人库存
        for m in self.merchants.values():
            m.restock()

    # ── 战利品掉落 ────────────────────────────────────

    def roll_loot(self, enemy_id: str) -> Optional[Equipment]:
        """为指定敌人骰点战利品，返回装备或None"""
        table = self.loot_tables.get(enemy_id)
        if not table:
            return None
        return table.roll_drop()

    def register_loot_table(self, table: LootTable):
        self.loot_tables[table.enemy_id] = table

    # ── 宝箱开启 ───────────────────────────────────────

    def get_chest(self, chest_id: str) -> Optional[ChestContent]:
        return self.chests.get(chest_id)

    def register_chest(self, chest: ChestContent):
        self.chests[chest.id] = chest

    def is_chest_opened(self, chest_id: str) -> bool:
        return self.chest_states.get(chest_id, False)

    def open_chest(self, chest_id: str) -> Dict:
        """
        开启宝箱（附骰点叙事）。
        chest_id 可以是 chest_xxx，也可以是内联名称如 "iron_chest"。
        如果找不到精确匹配，尝试模糊匹配（名称关键词）。
        """
        # 已开启检查
        if self.is_chest_opened(chest_id):
            return {
                "success": False,
                "message": "这个宝箱已经被打开过了。",
                "chest_id": chest_id,
            }

        chest = self.chests.get(chest_id)
        if chest is None:
            # 模糊匹配：用 chest_id 作为关键词在名称中搜索
            for cid, c in self.chests.items():
                if chest_id.lower() in c.name.lower() or c.name.lower() in chest_id.lower():
                    chest = c
                    chest_id = cid
                    break

        if chest is None:
            return {
                "success": False,
                "message": f"找不到名为「{chest_id}」的宝箱。",
                "chest_id": chest_id,
            }

        result = chest.open()
        self.chest_states[chest.id] = True

        items_summary = [e.name for e in result["items"]]
        gold_summary = result["gold"]

        summary_parts = []
        if items_summary:
            summary_parts.append("获得了：" + "、".join(items_summary))
        if gold_summary > 0:
            summary_parts.append(f"金币 +{gold_summary}")
        summary = "，".join(summary_parts) if summary_parts else "里面空空如也。"

        return {
            "success": True,
            "message": summary,
            "detail": result,
        }

    # ── NPC 交易 ───────────────────────────────────────

    def get_merchant(self, npc_id: str) -> Optional[MerchantEntry]:
        return self.merchants.get(npc_id)

    def register_merchant(self, merchant: MerchantEntry):
        self.merchants[merchant.npc_id] = merchant
        merchant.restock()

    def get_merchant_wares(self, npc_id: str) -> List[Dict]:
        """返回商人的商品列表（供 GM 在叙事中展示）"""
        merchant = self.merchants.get(npc_id)
        if not merchant:
            return []
        items = merchant.get_inventory()
        return [
            {
                "id": e.id,
                "name": e.name,
                "slot": e.slot,
                "rarity": e.rarity.value,
                "description": e.description,
                "stats": e.stats.to_dict(),
            }
            for e in items
        ]

    def buy_equipment(self, npc_id: str, equipment_id: str) -> Dict:
        """
        玩家从 NPC 购买装备。
        实际金币扣除和背包操作由调用方（GameMaster）执行。
        这里只返回装备对象。
        """
        merchant = self.merchants.get(npc_id)
        if not merchant:
            return {"success": False, "message": f"找不到 NPC「{npc_id}」。"}

        if equipment_id not in merchant._inventory:
            return {"success": False, "message": f"该NPC没有「{equipment_id}」出售。"}

        equip = get_template_equipment(equipment_id)
        if not equip:
            return {"success": False, "message": "装备模板不存在。"}

        return {
            "success": True,
            "equipment": equip,
            "message": f"购入了「{equip.name}」。",
        }

    def restock_merchant(self, npc_id: str):
        """刷新商人库存"""
        merchant = self.merchants.get(npc_id)
        if merchant:
            merchant.restock()

    # ── 统一发放装备 ────────────────────────────────────

    def grant_equipment(self, equipment: Equipment) -> Dict:
        """
        将装备发放给玩家（附加系统通知）。
        实际决定是直接装备还是放入背包，由 GameMaster 判断。
        """
        rarity_colors = {
            Rarity.COMMON: "白色",
            Rarity.UNCOMMON: "绿色",
            Rarity.RARE: "蓝色",
            Rarity.EPIC: "紫色",
            Rarity.LEGENDARY: "橙色",
        }
        rarity_str = rarity_colors.get(equipment.rarity, "白色")
        return {
            "equipment": equipment,
            "slot": equipment.slot,
            "name": equipment.name,
            "rarity": equipment.rarity.value,
            "rarity_display": rarity_str,
            "description": equipment.description,
            "stats": equipment.stats.to_dict(),
        }
