# systems/exploration_system.py - 藏宝图/探索系统
"""
藏宝图与探索系统：玩家通过线索发现隐藏的宝藏。

核心流程：
  获得藏宝图/线索 → 探索行动 → 骰点判定成功 → 获得奖励
  探索成功可能获得下一张藏宝图 → 形成探索链

奖励类型：
  - equipment：装备
  - gold：金币
  - intel：情报（揭示其他宝藏位置）
  - skill_fragment：技能碎片（集齐兑换技能）

设计原则：
  - 宝藏线索可从 NPC、宝箱、战利品等多个渠道获得
  - 探索判定受属性/技能加成影响
  - 同一宝藏只能被挖掘一次
"""

import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ─── 宝藏类型 ────────────────────────────────────────


@dataclass
class TreasureReward:
    """单件宝藏奖励"""
    type: str           # equipment / gold / intel / skill_fragment / item
    id: str = ""        # equipment_id 或 item id
    name: str = ""
    quantity: int = 1
    description: str = ""


@dataclass
class TreasureSite:
    """
    一个宝藏地点。

    宝藏通过线索（clue）来描述，LLM 根据线索描述场景，玩家输入探索行动时触发判定。
    宝藏 ID 全局唯一，同一 ID 只能被发掘一次。
    """
    id: str
    name: str                           # 宝藏名称，如"陈胜的遗书"
    location_hint: str                   # 地点线索（给 LLM 看），如"大泽乡以北三里的枯井"
    clue_text: str                       # 藏宝图文本（给玩家看/念出来）
    rewards: List[TreasureReward] = field(default_factory=list)
    difficulty: int = 50                 # 探索难度 DC（1-100），骰点达到此值即成功
    attribute_key: str = "wisdom"       # 探索判定所使用的属性
    skill_bonus: str = ""               # 额外加成的技能ID（如"survival"）
    discovered: bool = False             # 是否已被发现/发掘
    excavated: bool = False              # 是否已被发掘（已领取奖励）
    discovered_at_turn: int = 0
    excavated_at_turn: int = 0
    parent_clue_id: str = ""            # 由哪个线索/藏宝图揭示（形成探索链）

    def get_difficulty_label(self) -> str:
        """返回直观难度档位"""
        if self.difficulty >= 80:
            return "极难"
        elif self.difficulty >= 60:
            return "困难"
        elif self.difficulty >= 40:
            return "中等"
        else:
            return "简单"

    def get_clue_for_narrative(self) -> str:
        """生成叙事用的线索描述"""
        return f"【藏宝图】{self.clue_text}"


# ─── 宝藏模板库 ───────────────────────────────────────


TREASURE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "chen_sheng_will",
        "name": "陈胜的遗书",
        "location_hint": "大泽乡以北，枯井旁的老槐树下",
        "clue_text": "吾战友吴广埋九徒于槐下，井中有铁匣，内藏帛书与剑。",
        "difficulty": 35,
        "attribute_key": "wisdom",
        "rewards": [
            {"type": "equipment", "id": "iron_sword", "name": "铁剑", "description": "虽有些锈迹，仍是一把好剑。"},
            {"type": "gold", "quantity": 30},
            {"type": "intel", "id": "wu_guang_cache", "name": "吴广的秘密藏匿点", "description": "你从帛书中得知吴广还有一笔积蓄，藏于营地东侧。"},
        ],
    },
    {
        "id": "wu_guang_cache",
        "name": "吴广的秘密藏匿点",
        "location_hint": "营地东侧粮仓废墟下",
        "clue_text": "帛书所言：'东廪之下，三尺有密。'",
        "difficulty": 45,
        "attribute_key": "perception",
        "rewards": [
            {"type": "gold", "quantity": 80},
            {"type": "equipment", "id": "leather", "name": "皮甲", "description": "民间匠人缝制，勉强能挡刀剑。"},
        ],
    },
    {
        "id": "abandoned_weapon_cache",
        "name": "秦军遗弃兵器窖",
        "location_hint": "村庄以东的山谷入口处",
        "clue_text": "老农说山谷里有个秦军废弃的兵器窖，入口被荆棘掩埋。",
        "difficulty": 55,
        "attribute_key": "strength",
        "rewards": [
            {"type": "equipment", "id": "bow", "name": "猎弓", "description": "民间仿制秦弩，威力一般但便于携带。"},
            {"type": "equipment", "id": "wooden_shield", "name": "木盾", "description": "陈旧的木盾，表面刻着秦篆。"},
        ],
    },
    {
        "id": "scholar_ruins",
        "name": "焚书儒生的密室",
        "location_hint": "县城废墟的书院遗址",
        "clue_text": "县城书院地下有密室，墙砖上刻有'知识不死'四字。",
        "difficulty": 65,
        "attribute_key": "intelligence",
        "rewards": [
            {"type": "skill_fragment", "id": "scholar_fragment", "name": "学者残卷", "description": "残破的竹简，记载着失传的学问。集齐3片可兑换技能。"},
            {"type": "gold", "quantity": 50},
            {"type": "intel", "id": "county_treasury", "name": "县府财库位置", "description": "你在竹简中发现了一张散落的地图，标注着县府财库的位置。"},
        ],
    },
    {
        "id": "county_treasury",
        "name": "县府秘密财库",
        "location_hint": "县府大堂地砖下",
        "clue_text": "地图所示：县府大堂正中有机关，踏第三块砖可开启。",
        "difficulty": 70,
        "attribute_key": "dexterity",
        "rewards": [
            {"type": "gold", "quantity": 200},
            {"type": "equipment", "id": "steel_sword", "name": "精钢剑", "description": "秦军制式武器，比普通刀剑锋利得多。"},
            {"type": "skill_fragment", "id": "tactics_fragment", "name": "兵法残篇", "description": "残缺的兵法竹简，记载着布阵要诀。"},
        ],
    },
    {
        "id": "hidden_shrine",
        "name": "山神隐藏祭坛",
        "location_hint": "山顶乱石阵中心",
        "clue_text": "猎人说山顶乱石下有古祭坛，祭拜可得好运。",
        "difficulty": 40,
        "attribute_key": "wisdom",
        "rewards": [
            {"type": "equipment", "id": "lucky_charm", "name": "护身符", "description": "古旧护身符，似乎带着某种神秘力量。"},
            {"type": "gold", "quantity": 15},
        ],
    },
]


# ─── 探索结果 ────────────────────────────────────────


@dataclass
class ExplorationResult:
    """一次探索的结果"""
    site: TreasureSite
    success: bool                          # 骰点是否成功
    roll: int                              # 原始骰点
    modifier: int                          # 属性/技能加成
    total: int                             # 最终值
    dc: int                               # 难度
    rewards_given: List[TreasureReward]   # 实际发放的奖励
    new_clue: Optional[TreasureSite]       # 是否获得新线索（intel 类奖励可能带出）
    narrative: str                          # 叙事描述


# ─── ExplorationSystem ───────────────────────────────────────


class ExplorationSystem:
    """
    藏宝图与探索系统。

    使用方式：
        # 注册宝藏（从 meta.json 加载，或系统内置）
        sys.load_from_meta(meta)

        # 玩家尝试探索
        result = sys.explore(site_id, stats_sys, skill_sys)

        # 获得宝藏
        if result.success:
            for reward in result.rewards_given:
                gm.acquisition_sys.grant_equipment(...)
    """

    def __init__(self):
        # site_id -> TreasureSite
        self._sites: Dict[str, TreasureSite] = {}
        # 全局宝藏库（注册后永不消失，即使被发掘）
        self._global_library: Dict[str, TreasureSite] = {}
        # 玩家当前持有的线索列表（clue_id -> site_id）
        self._player_clues: Dict[str, str] = {}
        # 技能碎片收集（player_id -> fragment_id -> count）
        self._skill_fragments: Dict[str, Dict[str, int]] = {}
        # 探索历史（site_id -> ExplorationResult）
        self._history: List[Dict] = []
        # 宝藏是否从 meta.json 加载过
        self._loaded: bool = False

    # ── 加载配置 ────────────────────────────────

    def load_from_meta(self, meta: Any) -> None:
        """从 meta.json 的 treasures 配置加载宝藏"""
        self._loaded = True
        treasures_cfg = getattr(meta, "treasures", []) or []
        for tc in treasures_cfg:
            site = TreasureSite(
                id=tc["id"],
                name=tc.get("name", tc["id"]),
                location_hint=tc.get("location_hint", ""),
                clue_text=tc.get("clue", tc.get("clue_text", "")),
                difficulty=tc.get("difficulty", 50),
                attribute_key=tc.get("attribute", "wisdom"),
                skill_bonus=tc.get("skill", ""),
            )
            rewards_cfg = tc.get("rewards", [])
            for rc in rewards_cfg:
                site.rewards.append(TreasureReward(
                    type=rc["type"],
                    id=rc.get("id", ""),
                    name=rc.get("name", rc.get("id", "")),
                    quantity=rc.get("quantity", 1),
                    description=rc.get("description", ""),
                ))
            self.register_site(site)

    def register_site(self, site: TreasureSite, library: bool = True) -> None:
        """注册一个宝藏地点"""
        self._sites[site.id] = site
        if library:
            self._global_library[site.id] = site

    def is_loaded(self) -> bool:
        return self._loaded

    # ── 玩家线索管理 ────────────────────────────────

    def grant_clue(self, clue_id: str, player_id: str = "player") -> Optional[TreasureSite]:
        """
        给予玩家一条线索（藏宝图）。
        clue_id 可以是 site_id，也可以是 intel 类型奖励中的子线索 ID。
        返回对应的 TreasureSite（如果存在且未被发现）。
        """
        site = self._global_library.get(clue_id)
        if not site:
            # 尝试模糊匹配
            for sid, s in self._global_library.items():
                if clue_id.lower() in s.name.lower() or s.name.lower() in clue_id.lower():
                    site = s
                    break

        if not site:
            return None

        if site.discovered or site.excavated:
            # 宝藏已被发掘，线索变成废纸
            return None

        self._player_clues[clue_id] = site.id
        site.discovered = True
        return site

    def get_player_clues(self) -> List[TreasureSite]:
        """返回玩家当前持有的所有有效线索"""
        clue_sites = []
        for clue_id, site_id in self._player_clues.items():
            site = self._global_library.get(site_id)
            if site and not site.excavated:
                clue_sites.append(site)
        return clue_sites

    def has_clue(self, clue_id: str) -> bool:
        return clue_id in self._player_clues

    # ── 探索判定 ────────────────────────────────

    def explore(
        self,
        site_id: str,
        stats_sys: Any = None,
        skill_sys: Any = None,
        player_id: str = "player",
        turn: int = 0,
    ) -> ExplorationResult:
        """
        玩家对指定宝藏进行探索。
        返回 ExplorationResult，含骰点结果和奖励。
        """
        site = self._global_library.get(site_id)
        if not site:
            return ExplorationResult(
                site=site,
                success=False,
                roll=0,
                modifier=0,
                total=0,
                dc=0,
                rewards_given=[],
                new_clue=None,
                narrative=f"找不到名为「{site_id}」的宝藏。",
            )

        if site.excavated:
            return ExplorationResult(
                site=site,
                success=False,
                roll=0,
                modifier=0,
                total=0,
                dc=0,
                rewards_given=[],
                new_clue=None,
                narrative=f"「{site.name}」已经被发掘过了。",
            )

        # 骰点
        roll = random.randint(1, 100)
        modifier = 0

        # 属性加成
        if stats_sys and site.attribute_key:
            attr_val = stats_sys.get(site.attribute_key, 10)
            modifier += (attr_val - 10) // 2

        # 技能加成
        if skill_sys and site.skill_bonus:
            skill_rank = skill_sys.learned.get(site.skill_bonus, 0)
            modifier += skill_rank * 3  # 每级技能 +3

        total = roll + modifier
        success = total >= site.difficulty

        new_clue_site: Optional[TreasureSite] = None
        rewards_given: List[TreasureReward] = []

        if success:
            site.excavated = True
            site.excavated_at_turn = turn
            rewards_given = list(site.rewards)

            # 检查是否有 intel 类奖励（可能带出新线索）
            for reward in rewards_given:
                if reward.type == "intel" and reward.id:
                    next_site = self._global_library.get(reward.id)
                    if next_site and not next_site.discovered:
                        next_site.discovered = True
                        next_site.parent_clue_id = site.id
                        new_clue_site = next_site

            # 技能碎片收集
            for reward in rewards_given:
                if reward.type == "skill_fragment":
                    if player_id not in self._skill_fragments:
                        self._skill_fragments[player_id] = {}
                    fid = reward.id
                    self._skill_fragments[player_id][fid] = \
                        self._skill_fragments[player_id].get(fid, 0) + reward.quantity

        # 记录历史
        self._history.append({
            "site_id": site_id,
            "roll": roll,
            "modifier": modifier,
            "total": total,
            "dc": site.difficulty,
            "success": success,
            "turn": turn,
        })

        # 移除已发掘宝藏的线索引用
        for clue_id, sid in list(self._player_clues.items()):
            if sid == site_id:
                del self._player_clues[clue_id]

        difficulty_label = site.get_difficulty_label()
        roll_desc = f"🎲 探索判定：d100={roll} + 属性修正{modifier:+d} = **{total}** vs DC {site.difficulty}（{difficulty_label}）"

        if success:
            reward_lines = []
            for r in rewards_given:
                if r.type == "gold":
                    reward_lines.append(f"💰 金币 ×{r.quantity}")
                elif r.type == "equipment":
                    reward_lines.append(f"⚔️ {r.name}：{r.description}")
                elif r.type == "intel":
                    reward_lines.append(f"📜 情报「{r.name}」：{r.description}")
                    if new_clue_site:
                        reward_lines.append(f"   → 获得新线索：{new_clue_site.clue_text}")
                elif r.type == "skill_fragment":
                    reward_lines.append(f"📖 技能碎片「{r.name}」×{r.quantity}")
                elif r.type == "item":
                    reward_lines.append(f"🎁 {r.name}：{r.description}")

            rewards_text = "\n".join(reward_lines) if reward_lines else "（无）"
            narrative = (
                f"{roll_desc}\n\n"
                f"✨ 探索成功！你发掘了「{site.name}」。\n"
                f"{rewards_text}"
            )
        else:
            narrative = (
                f"{roll_desc}\n\n"
                f"❌ 探索失败。你未能找到「{site.name}」。"
                f"（提示：提升{site.attribute_key}属性或学习相关技能可增加判定加成）"
            )

        return ExplorationResult(
            site=site,
            success=success,
            roll=roll,
            modifier=modifier,
            total=total,
            dc=site.difficulty,
            rewards_given=rewards_given,
            new_clue=new_clue_site,
            narrative=narrative,
        )

    # ── 探索技能 ────────────────────────────────

    def get_skill_fragment_status(self, player_id: str = "player") -> Dict[str, int]:
        """获取玩家当前碎片收集状态"""
        return self._skill_fragments.get(player_id, {}).copy()

    def can_craft_skill(self, player_id: str = "player") -> List[str]:
        """
        检查玩家是否集齐了足够的碎片可兑换技能。
        当前设定：集齐任意3个碎片可兑换一个随机技能。
        """
        fragments = self._skill_fragments.get(player_id, {})
        total = sum(fragments.values())
        if total >= 3:
            return ["可兑换技能（3碎片 → 随机技能1个）"]
        return []

    def consume_fragments_for_skill(self, player_id: str = "player") -> Optional[str]:
        """
        消耗碎片兑换技能，返回技能ID。
        返回 None 如果碎片不足。
        """
        fragments = self._skill_fragments.get(player_id, {})
        total = sum(fragments.values())
        if total < 3:
            return None

        # 扣除3个碎片（优先扣除数量最多的类型）
        remaining = 3
        while remaining > 0 and fragments:
            max_fid = max(fragments, key=lambda k: fragments[k])
            if fragments[max_fid] <= remaining:
                remaining -= fragments[max_fid]
                del fragments[max_fid]
            else:
                fragments[max_fid] -= remaining
                remaining = 0

        # 返回可学习的技能（简化处理，返回技能ID列表中的随机一个）
        # 实际技能学习由 SkillSystem 处理
        craftable = ["scholar_fragment", "tactics_fragment"]
        return random.choice(craftable) if craftable else None

    # ── 查询 ────────────────────────────────

    def get_all_sites(self, include_excavated: bool = False) -> List[TreasureSite]:
        sites = list(self._global_library.values())
        if not include_excavated:
            sites = [s for s in sites if not s.excavated]
        return sites

    def get_site(self, site_id: str) -> Optional[TreasureSite]:
        return self._global_library.get(site_id)

    def get_exploration_summary(self) -> Dict[str, Any]:
        """获取探索系统状态摘要"""
        all_sites = list(self._global_library.values())
        excavated = [s for s in all_sites if s.excavated]
        discovered = [s for s in all_sites if s.discovered and not s.excavated]
        hidden = [s for s in all_sites if not s.discovered]
        return {
            "total_sites": len(all_sites),
            "excavated": len(excavated),
            "discovered_with_clues": len(discovered),
            "still_hidden": len(hidden),
            "player_clues_count": len(self._player_clues),
        }

    # ── 存档 ────────────────────────────────

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "sites_state": {
                sid: {
                    "discovered": site.discovered,
                    "excavated": site.excavated,
                    "discovered_at_turn": site.discovered_at_turn,
                    "excavated_at_turn": site.excavated_at_turn,
                }
                for sid, site in self._global_library.items()
            },
            "player_clues": self._player_clues.copy(),
            "skill_fragments": self._skill_fragments.copy(),
            "history": self._history[-50:],
        }

    def load_snapshot(self, snapshot: Dict[str, Any]) -> None:
        if not snapshot:
            return
        sites_state = snapshot.get("sites_state", {})
        for sid, state in sites_state.items():
            site = self._global_library.get(sid)
            if site:
                site.discovered = state.get("discovered", False)
                site.excavated = state.get("excavated", False)
                site.discovered_at_turn = state.get("discovered_at_turn", 0)
                site.excavated_at_turn = state.get("excavated_at_turn", 0)
        self._player_clues = snapshot.get("player_clues", {}).copy()
        self._skill_fragments = snapshot.get("skill_fragments", {})
        self._history = snapshot.get("history", [])

    # ── 初始化内置宝藏 ──────────────────────────────

    def _register_template_sites(self) -> None:
        """注册内置宝藏模板（在 load_from_meta 之前调用）"""
        if self._loaded:
            return
        for tmpl in TREASURE_TEMPLATES:
            site = TreasureSite(
                id=tmpl["id"],
                name=tmpl["name"],
                location_hint=tmpl["location_hint"],
                clue_text=tmpl["clue_text"],
                difficulty=tmpl.get("difficulty", 50),
                attribute_key=tmpl.get("attribute_key", "wisdom"),
                skill_bonus=tmpl.get("skill_bonus", ""),
            )
            for rc in tmpl.get("rewards", []):
                site.rewards.append(TreasureReward(
                    type=rc["type"],
                    id=rc.get("id", ""),
                    name=rc.get("name", rc.get("id", "")),
                    quantity=rc.get("quantity", 1),
                    description=rc.get("description", ""),
                ))
            self.register_site(site)
