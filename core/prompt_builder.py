# core/prompt_builder.py - Prompt 构造器
"""
负责组装完整的 system prompt，
将游戏设定 + 当前状态 + 数值系统快照注入 LLM。
"""

from typing import Dict, List, Optional
from systems.stats import StatsSystem
from systems.moral_debt import MoralDebtSystem
from systems.inventory import InventorySystem
from systems.dialogue import DialogueSystem
from .context_loader import GameLoader, Scene


SYSTEM_PROMPT_TEMPLATE = """你是一名 RPG 游戏的主持人（Game Master）。

## 游戏名称
{name}

## 世界观设定
{setting}

## 当前场景
**{scene_title}**
{scene_content}

## 主角状态
{player_status}

## 可用叙事选项
{available_options}

## 被锁定的选项（道德债务限制）
{locked_options}

## 道德债务记录（最近3条）
{moral_debt_records}

## NPC 关系
{npc_relations}

## 你的职责
1. 根据主角的输入（自然语言），推进游戏叙事
2. 在适当场景注入决策点，让玩家选择
3. 遵守道德债务系统规则——债务高的玩家无法选择某些"积极"选项
4. 叙事结束后，返回结构化的游戏指令（见下）

## 返回格式
每次回复后，附上结构化指令（供系统解析，不向玩家展示）：

[GM_COMMAND]
action: narrative | choice | combat | transition
next_scene: <scene_id>（如果是 transition）
options: <选项列表>（如果是 choice，格式：选项名|描述|触发条件）
combat_data: <战斗数据>（如果是 combat）
narrative_hint: <给玩家的叙事内容>
[/GM_COMMAND]
"""


PLAYER_STATUS_TEMPLATE = """
- 生命值: {hp}/{max_hp}
- 体力值: {stamina}/{max_stamina}
- 力量: {strength} | 敏捷: {agility} | 智力: {intelligence} | 魅力: {charisma}
- 道德债务: {debt_level}（{debt_value}分）
- 当前背包: {inventory}
"""


class PromptBuilder:
    """Prompt 构造器"""

    def __init__(
        self,
        game_loader: GameLoader,
        stats_sys: StatsSystem,
        moral_debt_sys: MoralDebtSystem,
        inventory_sys: InventorySystem,
        dialogue_sys: DialogueSystem,
    ):
        self.game_loader = game_loader
        self.stats_sys = stats_sys
        self.moral_debt_sys = moral_debt_sys
        self.inventory_sys = inventory_sys
        self.dialogue_sys = dialogue_sys

    def _build_player_status(self) -> str:
        stats = self.stats_sys.get_snapshot()
        moral = self.moral_debt_sys.get_snapshot()
        inv = self.inventory_sys.list_items()
        inv_str = ", ".join([f"{i['name']}×{i['quantity']}" for i in inv]) or "（空）"

        return PLAYER_STATUS_TEMPLATE.format(
            hp=stats["hp"],
            max_hp=stats["max_hp"],
            stamina=stats["stamina"],
            max_stamina=stats["max_stamina"],
            strength=stats["strength"],
            agility=stats["agility"],
            intelligence=stats["intelligence"],
            charisma=stats["charisma"],
            debt_level=moral["level"],
            debt_value=moral["debt"],
            inventory=inv_str,
        )

    def _build_moral_debt_records(self) -> str:
        records = self.moral_debt_sys.get_recent_records(3)
        if not records:
            return "（暂无记录）"
        lines = []
        for r in records:
            sign = "+" if r["amount"] > 0 else ""
            lines.append(f"- [{r['scene']}] {r['source']} {sign}{r['amount']}分")
        return "\n".join(lines)

    def _build_npc_relations(self) -> str:
        rels = self.dialogue_sys.get_all_relations()
        if not rels:
            return "（暂无建立关系）"
        lines = []
        for npc_id, info in rels.items():
            sign = "+" if info["value"] > 0 else ""
            lines.append(f"- {npc_id}: {info['level']}（{sign}{info['value']}）")
        return "\n".join(lines)

    def build_system_prompt(self, scene: Scene) -> str:
        """构建完整的 system prompt"""
        moral = self.moral_debt_sys.get_snapshot()
        locked = moral["locked_options"]
        locked_str = "、".join(locked) if locked else "（无）"

        # 获取场景中的可用选项（如果有预设）
        options_str = ""
        if scene.available_actions:
            options_str = "\n".join(f"- {a}" for a in scene.available_actions)
        else:
            options_str = "（由你根据情境自由发挥）"

        return SYSTEM_PROMPT_TEMPLATE.format(
            name=self.game_loader.meta.name,
            setting=self.game_loader.setting[:4000],  # 截断防止超长
            scene_title=scene.title,
            scene_content=scene.content[:3000],
            player_status=self._build_player_status(),
            available_options=options_str,
            locked_options=locked_str,
            moral_debt_records=self._build_moral_debt_records(),
            npc_relations=self._build_npc_relations(),
        )

    def build_user_prompt(self, player_input: str, history_summary: str = "") -> str:
        """构建用户输入的 prompt"""
        parts = []
        if history_summary:
            parts.append(f"[近期回顾]\n{history_summary}\n")
        parts.append(f"[你的行动]\n{player_input}")
        return "\n".join(parts)
