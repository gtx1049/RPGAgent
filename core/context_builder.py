# core/context_builder.py - Prompt 构造器（已重构为 DB query 模式）
"""
从 SQLite 数据库按需查询上下文，而非全量塞入。
确保 LLM context 大小可控、可验证。
"""

from typing import Dict, List, Optional, Any
from .context_loader import GameLoader, Scene


SYSTEM_PROMPT_TEMPLATE = """你是一名 RPG 游戏的主持人（Game Master）。

## 游戏名称
{name}

## 世界观设定
{setting}

## 当前场景
**{scene_title}**
{scene_content}

## 玩家状态
{player_status}

## 叙事风格（隐藏数值影响）
{narrative_styles}

## 可用叙事选项
{available_options}

## 被锁定的选项（隐藏数值限制）
{locked_options}

## 隐藏数值最近记录
{hidden_value_records}

## 当前场景活跃NPC状态
{npc_status}

## NPC对话历史（最近）
{dialogue_history}

## 世界事件回顾
{world_events}

## 你的职责
1. 根据玩家输入推进叙事
2. 遵守隐藏数值系统规则——某些选项在特定档位不可用
3. 叙事风格随隐藏数值档位变化（fragmented/dissociated 时改变语言风格）
4. 返回结构化指令（GM_COMMAND）
5. 不要泄露具体数值给玩家

## 返回格式
[GM_COMMAND]
action: narrative | choice | combat | transition
next_scene: <scene_id>
options: <选项列表>（choice时）
narrative_hint: <给玩家的叙事内容>
hidden_value_delta: <各隐藏值变化>（格式: id:delta;id:delta）
relation_delta: <NPC关系变化>（格式: npc_id:delta）
[/GM_COMMAND]
"""


PLAYER_STATUS_TEMPLATE = """
- 生命值: {hp}/{max_hp}
- 体力值: {stamina}/{max_stamina}
- 力量: {strength} | 敏捷: {agility} | 智力: {intelligence} | 魅力: {charisma}
"""


class PromptBuilder:
    """
    Prompt 构造器，支持两种模式：

    1. memory模式（默认）：使用传入的内存中数值系统
    2. db模式：使用 SQLite 数据库 query 构建上下文
    """

    def __init__(
        self,
        game_loader: GameLoader,
        # memory 模式参数
        stats_sys=None,
        moral_debt_sys=None,
        inventory_sys=None,
        dialogue_sys=None,
        # db 模式参数
        db=None,
        current_scene_id: str = "",
        turn: int = 0,
    ):
        self.game_loader = game_loader
        self.stats_sys = stats_sys
        self.moral_debt_sys = moral_debt_sys
        self.inventory_sys = inventory_sys
        self.dialogue_sys = dialogue_sys
        self.db = db
        self.current_scene_id = current_scene_id
        self.turn = turn

    @property
    def mode(self) -> str:
        return "db" if self.db else "memory"

    def _build_player_status(self) -> str:
        if self.mode == "db":
            # 从数据库查
            # 玩家状态目前还在 session 中，简化处理：留空让 LLM 从 hidden_value 推断
            return "(玩家状态由系统管理，可在需要时通过 status 命令查看)"
        else:
            stats = self.stats_sys.get_snapshot() if self.stats_sys else {}
            moral = self.moral_debt_sys.get_snapshot() if self.moral_debt_sys else {}
            inv = self.inventory_sys.list_items() if self.inventory_sys else []
            inv_str = ", ".join([f"{i['name']}×{i['quantity']}" for i in inv]) or "（空）"
            return PLAYER_STATUS_TEMPLATE.format(
                hp=stats.get("hp", "?"),
                max_hp=stats.get("max_hp", "?"),
                stamina=stats.get("stamina", "?"),
                max_stamina=stats.get("max_stamina", "?"),
                strength=stats.get("strength", "?"),
                agility=stats.get("agility", "?"),
                intelligence=stats.get("intelligence", "?"),
                charisma=stats.get("charisma", "?"),
            ) + f"\n- 道德债务等级: {moral.get('level', '?')}（{moral.get('debt', 0)}分）"

    def _build_narrative_styles(self) -> str:
        if self.mode == "db":
            hv_states = self.db.get_all_hidden_value_states()
            styles = []
            for hv in hv_states:
                records_json = hv.get("records_json", "[]")
                import json
                records = json.loads(records_json)
                # 取最新的 level
                level = hv.get("level", 0)
                styles.append(f"- {hv['name']}: 等级{level}（{hv.get('description','')}）")
            return "\n".join(styles) if styles else "（各隐藏数值正常）"
        else:
            # memory 模式
            styles = {}
            if hasattr(self.dialogue_sys, "get_narrative_styles"):
                styles = self.dialogue_sys.get_narrative_styles()
            return "\n".join([f"- {k}: {v}" for k, v in styles.items()]) or "（正常）"

    def _build_locked_options(self) -> str:
        if self.mode == "db":
            hv_states = self.db.get_all_hidden_value_states()
            import json
            all_locked = []
            for hv in hv_states:
                # 从 effects 字段提取（简化版，实际存储需对齐）
                all_locked.extend([])  # 留空，详细查 db 结构
            return "、".join(all_locked) if all_locked else "（无）"
        else:
            if hasattr(self.moral_debt_sys, "get_locked_options"):
                locked = self.moral_debt_sys.get_locked_options()
            else:
                locked = []
            return "、".join(locked) if locked else "（无）"

    def _build_hidden_value_records(self) -> str:
        if self.mode == "db":
            import json
            lines = []
            hv_states = self.db.get_all_hidden_value_states()
            for hv in hv_states:
                records = json.loads(hv.get("records_json", "[]"))
                if records:
                    recent = records[-3:]
                    for r in recent:
                        sign = "+" if r.get("delta", 0) > 0 else ""
                        lines.append(
                            f"- [{hv['name']}] {r.get('source','')} "
                            f"{sign}{r.get('delta',0)}（{r.get('scene_id','')}）"
                        )
            return "\n".join(lines) if lines else "（暂无记录）"
        else:
            if hasattr(self.moral_debt_sys, "get_recent_records"):
                records = self.moral_debt_sys.get_recent_records(3)
            else:
                records = []
            if not records:
                return "（暂无记录）"
            lines = []
            for r in records:
                sign = "+" if r.get("amount", 0) > 0 else ""
                lines.append(
                    f"- [{r.get('scene','')}] {r.get('source','')} "
                    f"{sign}{r.get('amount',0)}分"
                )
            return "\n".join(lines)

    def _build_npc_status(self) -> str:
        if self.mode == "db":
            npcs = self.db.get_npcs_in_scene(self.current_scene_id)
            if not npcs:
                npcs = self.db.get_all_npc_states()[:5]  # fallback：最近5个NPC
            if not npcs:
                return "（暂无NPC状态）"
            import json
            lines = []
            for npc in npcs:
                flags = json.loads(npc.get("flags", "{}"))
                lines.append(
                    f"- {npc['name']}（{npc['id']}）: "
                    f"关系{npc.get('relation_value', 0)} | "
                    f"位于{npc.get('current_location', '?')}"
                )
            return "\n".join(lines)
        else:
            if hasattr(self.dialogue_sys, "get_all_relations"):
                rels = self.dialogue_sys.get_all_relations()
            else:
                rels = {}
            if not rels:
                return "（暂无NPC关系）"
            lines = [
                f"- {npc_id}: {info['level']}（{info['value']}）"
                for npc_id, info in rels.items()
            ]
            return "\n".join(lines)

    def _build_dialogue_history(self) -> str:
        if self.mode == "db":
            dialogues = self.db.get_dialogue(limit=10)
            if not dialogues:
                return "（暂无对话历史）"
            lines = []
            for d in dialogues:
                prefix = "【玩家】" if d["speaker"] == "player" else f"【{d['npc_id']}】"
                lines.append(f"{prefix} {d.get('summary', d['content'][:50])}")
            return "\n".join(lines[:6])  # 最多6条
        else:
            return "（使用 memory 模式，对话历史在 session 中）"

    def _build_world_events(self) -> str:
        if self.mode == "db":
            events = self.db.query_events(turn=self.turn, limit=5) if self.turn else []
            if not events:
                events = self.db.query_events(limit=5)
            if not events:
                return "（暂无世界事件）"
            import json
            lines = []
            for e in events:
                tags = json.loads(e.get("tags", "[]"))
                tag_str = f"[{','.join(tags)}]" if tags else ""
                lines.append(f"- [{e['scene_id']}] {e['summary']} {tag_str}")
            return "\n".join(lines)
        else:
            return "（使用 memory 模式）"

    def build_system_prompt(self, scene: Scene) -> str:
        """构建完整的 system prompt"""
        hidden_val_records = self._build_hidden_value_records()
        locked = self._build_locked_options()
        options_str = "（由你根据情境自由发挥）"
        if scene.available_actions:
            options_str = "\n".join(f"- {a}" for a in scene.available_actions)

        return SYSTEM_PROMPT_TEMPLATE.format(
            name=self.game_loader.meta.name,
            setting=self.game_loader.setting[:4000],
            scene_title=scene.title,
            scene_content=scene.content[:3000],
            player_status=self._build_player_status(),
            narrative_styles=self._build_narrative_styles(),
            available_options=options_str,
            locked_options=locked,
            hidden_value_records=hidden_val_records,
            npc_status=self._build_npc_status(),
            dialogue_history=self._build_dialogue_history(),
            world_events=self._build_world_events(),
        )

    def build_user_prompt(self, player_input: str, history_summary: str = "") -> str:
        parts = []
        if history_summary:
            parts.append(f"[近期回顾]\n{history_summary}\n")
        parts.append(f"[你的行动]\n{player_input}")
        return "\n".join(parts)

    def update_turn(self, scene_id: str, turn: int):
        """更新当前场景和回合（切换场景时调用）"""
        self.current_scene_id = scene_id
        self.turn = turn
