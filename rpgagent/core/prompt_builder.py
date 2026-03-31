# core/prompt_builder.py - Prompt 构造器（统一版）
"""
负责组装完整的 system prompt，
将游戏设定 + 当前状态 + 数值系统快照注入 LLM。

支持两种数据来源模式：
- memory 模式（默认）：直接读取内存中的数值系统实例
- db 模式：使用 SQLite 数据库按需查询上下文

支持两套数值系统共存：
- HiddenValueSystem（通用框架）：道德债务、理智、成长等所有隐藏数值
- MoralDebtSystem（旧版）：保持向后兼容

Prompt 中的"道德债务"区块同时显示两组数据，
但以 HiddenValueSystem 为准。
"""

from typing import Dict, List, Optional, Any
import json

from ..systems.stats import StatsSystem
from ..systems.moral_debt import MoralDebtSystem
from ..systems.inventory import InventorySystem
from ..systems.dialogue import DialogueSystem
from ..systems.hidden_value import HiddenValueSystem
from ..systems.npc_memory import NpcMemorySystem
from .context_loader import GameLoader, Scene


# ────────────────────────────────────────────────
# Prompt 模板（memory / db 共用）
# ────────────────────────────────────────────────

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

## 隐藏数值（玩家不可见，影响叙事）
{hidden_values_section}

## 待插入触发场景
{pending_triggered_scenes_section}

## 可用叙事选项
{available_options}

## 被锁定的选项（隐藏数值限制）
{locked_options}

## 道德债务记录（最近3条）
{moral_debt_records}

## NPC 关系
{npc_relations}

## NPC 认知摘要（各 NPC 对玩家的记忆与印象）
{npc_memory_summaries}

## 阵营声望（各方势力对玩家的态度）
{faction_section}
{time_section}
{world_events_section}
{mode_extra}

## 你的职责
1. 根据主角的输入（自然语言），推进游戏叙事
2. 在适当场景注入决策点，让玩家选择
3. 遵守隐藏数值系统规则——数值达到特定档位时自动限制对应选项，并可触发特殊场景
4. 叙事结束后，返回结构化的游戏指令（见下）

## AI行为约束（硬约束）

以下规则**强制生效**，LLM 输出必须遵守，违者叙事将被后端拒绝或修正：

**1. 数值修改权限（最高优先级）**
- ✅ LLM可以说："你感到一阵剧痛。"
- ❌ LLM不得说："你的 HP 变成了 50/100。"（数值必须由 GM_COMMAND 中的 stat_delta 触发）
- ✅ LLM可以说："你获得了铁剑，属性优异。"
- ❌ LLM不得说："你的力量 +2。"（必须通过 GM_COMMAND 中的 equip 指令）

**2. 行动结果约束**
- ✅ 正确做法：在 GM_COMMAND 中写 roll: 推门 | attribute: strength | dc: 50，由系统执行判定后，LLM 收到结果再叙事
- ❌ 错误做法：在叙事中直接宣布"你成功推开了门"而不触发 Roll
- ❌ 错误做法：收到失败判定后仍然描写玩家成功

**3. 世界一致性约束**
- ❌ LLM不得引入剧本目录中不存在的 NPC、地点或事件
- ❌ LLM不得改变场景设定（如把森林变成沙漠）
- ❌ LLM不得创造新的魔法或超自然能力
- ✅ 例外：LLM可以在剧本允许范围内进行合理的推断和填充

**4. 对话真实性约束**
- ❌ NPC不得透露自己不知道的信息（如农民不该知道王国机密）
- ❌ NPC的性格不能前后矛盾
- ✅ LLM可以利用 NPC 记忆池中的历史来调整对话

**5. 行动点约束**
- LLM应在叙事中体现行动力消耗
- 当玩家行动力耗尽时，LLM应推进场景或描述时间流逝，而非继续让玩家行动

**6. 道德债务叙事约束**
- 债务「重债」以上：NPC 对玩家态度变差、世界对玩家的反馈变负面
- 债务「极债」：部分选项和 NPC 对话永久关闭，LLM不得绕过此限制
- LLM不得在叙事中主动清除或减少道德债务（除非通过特定赎罪行动触发）

## 返回格式
每次回复后，**必须**附上结构化指令（供系统解析，不向玩家展示）：

[GM_COMMAND]
action: narrative | choice | combat | transition
next_scene: <scene_id>（如果是 transition）
options: <选项列表>（如果是 choice，格式：选项名|描述|触发条件）
combat_data: <战斗数据>（如果是 combat）
narrative_hint: <给玩家的叙事内容>
action_tag: <本次玩家行为触发的数值标签，如 huff_and_puff / trick_pig / threaten_pig / give_up / eat_pig / run_away，**必填**，对应 hidden_value_actions 中的键>
roll: <行动名称>（如果本次行动需要骰点判定，如"潜行"、"推门"等）
attribute: <使用的属性键>（可选，默认 strength，可选 dexterity/constitution/intelligence/wisdom/charisma）
dc: <难度阈值 1-100>（可选，默认 50；参考：30=轻松，50=五五开，65=难搞，80=几无可能）
narrative_success: <本次行动成功时的叙事内容>（roll 时必填，将替代 narrative_hint）
narrative_failure: <本次行动失败时的叙事内容>（roll 时必填，将替代 narrative_hint）
[/GM_COMMAND]
"""

# db 模式专属额外区块（拼接在 NPC 关系后）
DB_MODE_EXTRA_TEMPLATE = """
## 当前场景活跃NPC状态
{npc_status}

## NPC对话历史（最近）
{dialogue_history}

## 世界事件回顾
{world_events}
"""


PLAYER_STATUS_TEMPLATE = """
- 生命值: {hp}/{max_hp}
- 体力值: {stamina}/{max_stamina}
- 等级: {level}（经验 {exp}/{exp_to_level}）
- 行动力: {ap_bar}（{action_power}/{max_action_power}，●=可用 ○=已消耗）
- 力量: {strength} | 敏捷: {agility} | 智力: {intelligence} | 魅力: {charisma}
- 当前装备: {equipped_summary}
- 当前背包: {inventory}
- 技能点: {skill_points}点 | 已学技能: {learned_skills}
"""

# ────────────────────────────────────────────────
# Hidden Values 区块
# ────────────────────────────────────────────────

TIME_SECTION_TEMPLATE = """
## 游戏时间与氛围
{time_context}

【叙事提醒】请在叙事中自然体现当前时间段的环境、声音和光线特点。
例如：
- 黎明："天色微曦，营火将熄未熄"、"晨雾中传来…"
- 正午："烈日当空，暑气蒸腾"、"汗珠滴落在干燥的尘土上"
- 夜晚："篝火跳动，映照着每个人的脸"、"黑暗中有什么在移动"
- 午夜："万籁俱寂，只有自己的心跳声"

【NPC 可用性】以下 NPC 目前不在：
{unavailable_npcs}
"""


NARRATIVE_STYLE_GUIDANCE = """
### 叙事风格指导（请严格遵守）
- **normal**：标准叙事。用完整流畅的句子，客观第三人称叙述，情感克制。
- **fragmented**：碎片化叙事。短句为主，频繁切换视角/时间线，句子可残缺、不完整。玩家视角开始出现闪回、感知扭曲。
- **dissociated**：解离叙事。时态混乱（过去/现在/想象混用），人称飘移，描述自我疏离。玩家角色与身体/情感脱节。

### 叙事提示（narrative_hint）
narrative_hint 是针对当前档位更具体的 GM 文风指导。当一个隐藏数值的 narrative_hint 非空时，优先遵循其指示。"""

HIDDEN_VALUES_TEMPLATE = """
| 数值名称 | 当前档位 | 叙事语气 | 叙事风格 | 锁定选项 | 解锁选项 | 叙事提示 |
|----------|----------|----------|----------|----------|----------|----------|
{hv_rows}

### 行为标签（供 GM 在 action_tag 中使用）
action_tag 由 GM 在 [GM_COMMAND] 中返回，系统根据标签自动更新隐藏数值。
叙事风格（normal / fragmented / dissociated）用于指导你的叙事文风，请遵守。
{narrative_style_guidance}
以下是当前剧本定义的行为标签：

{action_tags_section}
"""


class PromptBuilder:
    """
    Prompt 构造器（统一版）。

    持有所有数值系统实例，根据当前场景组装完整的 system prompt
    注入给 LLM（Game Master）。

    支持两种数据来源模式：
    - memory 模式（默认）：直接读取内存中的系统实例
    - db 模式：使用 SQLite 数据库查询上下文

    HiddenValueSystem 是新标准，支持任意多个隐藏数值（道德债务/理智/成长等）。
    MoralDebtSystem 保持向后兼容，Prompt 中同时显示两组数据，
    但以 HiddenValueSystem 为准。
    """

    def __init__(
        self,
        game_loader: GameLoader,
        stats_sys: Optional[StatsSystem] = None,
        moral_debt_sys: Optional[MoralDebtSystem] = None,
        inventory_sys: Optional[InventorySystem] = None,
        dialogue_sys: Optional[DialogueSystem] = None,
        hidden_value_sys: Optional[HiddenValueSystem] = None,
        npc_mem_sys: Optional[NpcMemorySystem] = None,
        skill_sys: Any = None,
        equipment_sys: Any = None,
        faction_sys: Any = None,
        day_night_sys: Any = None,
        world_event_sys: Any = None,
        # ── db 模式参数 ──
        db: Any = None,
        current_scene_id: str = "",
        turn: int = 0,
        # db 模式下需要此配置来查阈值→锁定选项映射
        hidden_values_cfg: Dict[str, Dict] | None = None,
    ):
        self.game_loader = game_loader
        self.stats_sys = stats_sys
        self.moral_debt_sys = moral_debt_sys
        self.inventory_sys = inventory_sys
        self.dialogue_sys = dialogue_sys
        self.hidden_value_sys = hidden_value_sys
        self.npc_mem_sys = npc_mem_sys
        self.skill_sys = skill_sys
        self.equipment_sys = equipment_sys
        self.faction_sys = faction_sys
        self.day_night_sys = day_night_sys
        self.world_event_sys = world_event_sys

        # ── db 模式 ──
        self.db = db
        self.current_scene_id = current_scene_id
        self.turn = turn
        # hidden_values_cfg：db 模式下用，格式同 meta.json 的 hidden_values
        self.hidden_values_cfg: Dict[str, Dict] = hidden_values_cfg or {}

    @property
    def mode(self) -> str:
        """当前数据来源模式"""
        return "db" if self.db else "memory"

    # ────────────────────────────────────────────────
    # 状态渲染（memory 模式）
    # ────────────────────────────────────────────────

    def _build_player_status(self) -> str:
        if self.mode == "db":
            # db 模式：玩家状态由 session 管理，此处简示
            return "（玩家状态由系统管理，可通过 status 命令查看）"
        stats = (self.stats_sys.get_snapshot() if self.stats_sys else {})
        ability = stats.get("ability", {})
        inv = (self.inventory_sys.list_items() if self.inventory_sys else [])
        inv_str = ", ".join([f"{i['name']}×{i['quantity']}" for i in inv]) or "（空）"
        skill_points = getattr(self.skill_sys, "skill_points", 0) if self.skill_sys else 0
        learned = []
        if self.skill_sys:
            learned = [s["name"] for s in self.skill_sys.list_learned()]
        learned_str = "、".join(learned) if learned else "无"

        # 装备摘要
        equip_summary = "无"
        if self.equipment_sys:
            equipped = self.equipment_sys.get_equipped()
            equip_items = [v["name"] for v in equipped.values() if v]
            equip_summary = "、".join(equip_items) if equip_items else "无"

        return PLAYER_STATUS_TEMPLATE.format(
            hp=stats.get("hp", "?"),
            max_hp=stats.get("max_hp", "?"),
            stamina=stats.get("stamina", "?"),
            max_stamina=stats.get("max_stamina", "?"),
            level=stats.get("level", "?"),
            exp=stats.get("exp", "?"),
            exp_to_level=stats.get("exp_to_level", "?"),
            ap_bar="●" * stats.get("action_power", 0) + "○" * (stats.get("max_action_power", 3) - stats.get("action_power", 0)),
            action_power=stats.get("action_power", 0),
            max_action_power=stats.get("max_action_power", "?"),
            strength=ability.get("strength", "?"),
            agility=ability.get("dexterity", "?"),
            intelligence=ability.get("intelligence", "?"),
            charisma=ability.get("charisma", "?"),
            equipped_summary=equip_summary,
            inventory=inv_str,
            skill_points=skill_points,
            learned_skills=learned_str,
        )

    def _build_hidden_values_section(self) -> str:
        """渲染隐藏数值总览区块（memory 模式）"""
        if self.mode == "db":
            # db 模式由 _build_narrative_styles 附带处理
            return ""

        if self.hidden_value_sys is None:
            return "（本剧本未启用隐藏数值框架，使用旧版道德债务系统）"

        snapshots = self.hidden_value_sys.get_snapshot()
        if not snapshots:
            return "（当前无激活的隐藏数值）"

        rows = []
        for vid, snap in snapshots.items():
            eff = snap["effect"]
            tone = eff.get("narrative_tone", "—")
            style = eff.get("narrative_style", "normal")
            locked_opts = eff.get("locked_options") or []
            locked_str = "、".join(locked_opts) if locked_opts else "（无）"
            unlock_opts = eff.get("unlock_options") or []
            unlock_str = "、".join(unlock_opts) if unlock_opts else "（无）"
            hint = eff.get("narrative_hint") or "—"
            rows.append(
                f"| {snap['name']} | {snap['current_threshold']} | "
                f"{tone} | {style} | 锁定：{locked_str} | 解锁：{unlock_str} | {hint} |"
            )

        default_row = "| — | — | — | — | — | — | — |"
        hv_section = HIDDEN_VALUES_TEMPLATE.format(
            hv_rows="\n".join(rows) if rows else default_row,
            narrative_style_guidance=NARRATIVE_STYLE_GUIDANCE,
            action_tags_section=self._build_action_tags_section(),
        )
        return hv_section.strip()

    def _build_action_tags_section(self) -> str:
        """渲染行为标签说明区块"""
        if self.hidden_value_sys is None or not self.hidden_value_sys.action_map:
            return "（剧本未定义行为标签表）"

        lines = []
        for tag, changes in self.hidden_value_sys.action_map.items():
            # relation_delta 是 dict（如 {"npc_id": -10}），不参与数值渲染
            change_desc = ", ".join(
                f"{vid}{'+' if d >= 0 else ''}{d}"
                for vid, d in changes.items()
                if vid != "relation_delta" and isinstance(d, int)
            )
            if change_desc:  # 跳过只有 relation_delta 的 action_tag
                lines.append(f"- **{tag}**：{change_desc}")
        return "\n".join(lines) if lines else "（无）"

    def _build_locked_options(self) -> str:
        """
        汇总所有来源的锁定选项。
        HiddenValueSystem 为准；MoralDebtSystem 作向后兼容补充。
        """
        locked: List[str] = []

        if self.mode == "db":
            # db 模式：从数据库 level 值 + hidden_values_cfg 映射
            hv_states = self.db.get_all_hidden_value_states()
            for hv in hv_states:
                vid = hv["hidden_value_id"]
                if vid not in self.hidden_values_cfg:
                    continue
                cfg = self.hidden_values_cfg[vid]
                effects_cfg = cfg.get("effects", {})
                level_idx = hv.get("level", 0)
                thresholds = cfg.get("thresholds", [0])
                if level_idx < len(thresholds):
                    threshold_key = str(thresholds[level_idx])
                    eff = effects_cfg.get(threshold_key, {})
                    locked.extend(eff.get("locked_options", []))
        else:
            # memory 模式
            if self.hidden_value_sys:
                locked.extend(self.hidden_value_sys.get_locked_options())
            # 旧版 MoralDebtSystem 兼容
            moral = (self.moral_debt_sys.get_snapshot() if self.moral_debt_sys else {})
            locked.extend(moral.get("locked_options", []))

        # 去重，保留顺序
        seen = set()
        unique = []
        for opt in locked:
            if opt not in seen:
                seen.add(opt)
                unique.append(opt)

        return "、".join(unique) if unique else "（无）"

    def _build_pending_triggered_scenes(self) -> str:
        """
        渲染待插入触发场景区块。

        get_pending_triggered_scenes() 返回已跨阈（trigger_fired=True）
        但尚未由 GM 插入（trigger_executed=False）的场景列表。
        GM 收到后将场景插入叙事流，然后调用 acknowledge_triggered_scene() 标记为已执行。
        """
        if self.hidden_value_sys is None:
            return "（本剧本未启用隐藏数值框架）"

        pending = self.hidden_value_sys.get_pending_triggered_scenes()
        if not pending:
            return "（当前无待插入的触发场景）"

        # 关联到场景名称（尝试从 game_loader 解析）
        lines = []
        for vid, scene_id in pending.items():
            hv = self.hidden_value_sys.values.get(vid)
            name = hv.name if hv else vid
            # 尝试获取场景标题
            scene = self.game_loader.get_scene(scene_id) if self.game_loader else None
            scene_title = scene.title if scene else scene_id
            lines.append(f"- **{name}** → 触发场景「{scene_title}」（{scene_id}）")
        return "\n".join(lines)

    # _build_moral_debt_records：_build_hidden_value_records 的别名，兼容旧调用方
    def _build_moral_debt_records(self) -> str:
        """渲染道德债务记录（别名，指向 _build_hidden_value_records）"""
        return self._build_hidden_value_records()

    def _build_hidden_value_records(self) -> str:
        """渲染隐藏数值变化记录（memory 模式：moral_debt 为主）"""
        if self.mode == "db":
            return self._build_hidden_value_records_from_db()

        # memory 模式
        if self.hidden_value_sys and "moral_debt" in self.hidden_value_sys.values:
            hv = self.hidden_value_sys.values["moral_debt"]
            records = hv.get_recent_records(3)
            if records:
                lines = []
                for r in records:
                    sign = "+" if r["delta"] > 0 else ""
                    lines.append(
                        f"- [{r['scene_id']}] {r['source']} {sign}{r['delta']}分"
                    )
                return "\n".join(lines)

        # Fallback：旧版 MoralDebtSystem
        records = (self.moral_debt_sys.get_recent_records(3) if self.moral_debt_sys else [])
        if not records:
            return "（暂无记录）"
        lines = []
        for r in records:
            sign = "+" if r.get("amount", 0) > 0 else ""
            lines.append(
                f"- [{r.get('scene', '?')}] {r.get('source', '')} "
                f"{sign}{r.get('amount', 0)}分"
            )
        return "\n".join(lines)

    def _build_npc_relations(self) -> str:
        if self.mode == "db":
            # db 模式走 _build_npc_status，那里已包含关系信息
            return self._build_npc_status()

        rels = (self.dialogue_sys.get_all_relations() if self.dialogue_sys else {})
        if not rels:
            return "（暂无建立关系）"
        lines = []
        for npc_id, info in rels.items():
            sign = "+" if info.get("value", 0) > 0 else ""
            lines.append(f"- {npc_id}: {info.get('level', '?')}（{sign}{info.get('value', 0)}）")
        return "\n".join(lines)

    def _build_npc_memory_summaries(self) -> str:
        """渲染各 NPC 对玩家的认知摘要（memory 模式）"""
        if not self.npc_mem_sys:
            return "（NPC 认知系统未启用）"
        summaries = self.npc_mem_sys.get_all_npc_summaries()
        if not summaries or all(not s for s in summaries.values()):
            return "（NPC 暂无对你的认知记录）"
        # 只显示有记忆的 NPC
        lines = []
        for npc_id, summary in summaries.items():
            if summary:
                lines.append(summary)
        return "\n".join(lines) if lines else "（NPC 暂无对你的认知记录）"

    def _build_faction_section(self) -> str:
        """渲染阵营声望区块（各方势力对玩家的态度）"""
        if not self.faction_sys:
            return "（阵营系统未启用）"
        context = self.faction_sys.get_narrative_context()
        return context if context else "（当前无阵营声望记录）"

    def _build_time_section(self) -> str:
        """渲染昼夜循环时间和 NPC 可用性区块"""
        if not self.day_night_sys:
            return ""
        time_context = self.day_night_sys.get_narrative_context()
        unavailable = self.day_night_sys.get_unavailable_npcs()
        unavailable_str = "（目前没有作息受限的 NPC）" if not unavailable else "、".join(unavailable)
        return TIME_SECTION_TEMPLATE.format(
            time_context=time_context,
            unavailable_npcs=unavailable_str,
        ).strip()

    def _build_world_events_section(self) -> str:
        """渲染当前激活的动态世界事件区块"""
        if not self.world_event_sys:
            return ""
        narrative = self.world_event_sys.get_active_event_narrative()
        return narrative if narrative else ""

    # ────────────────────────────────────────────────
    # 状态渲染（db 模式专属）
    # ────────────────────────────────────────────────

    def _build_narrative_styles(self) -> str:
        """各隐藏数值的当前叙事风格"""
        if self.mode == "db":
            hv_states = self.db.get_all_hidden_value_states()
            styles = []
            for hv in hv_states:
                records_json = hv.get("records_json", "{}")
                try:
                    records = json.loads(records_json)
                except Exception:
                    records = {}
                level = hv.get("level", 0)
                desc = hv.get("description", "")
                styles.append(f"- {hv['name']}: 等级{level}（{desc}）")
            return "\n".join(styles) if styles else "（各隐藏数值正常）"

        # memory 模式
        styles = {}
        if self.hidden_value_sys is not None:
            styles = self.hidden_value_sys.get_narrative_styles()
        return "\n".join([f"- {k}: {v}" for k, v in styles.items()]) or "（正常）"

    def _build_hidden_value_records_from_db(self) -> str:
        """db 模式：渲染隐藏数值最近记录（从 hidden_value_records 表读取）"""
        lines = []
        hv_states = self.db.get_all_hidden_value_states()
        for hv in hv_states:
            vid = hv["hidden_value_id"]
            name = hv.get("name", vid)
            # get_hidden_value_records() 返回最新在前的记录列表，取最后3条（时间顺序）
            raw_records = self.db.get_hidden_value_records(vid, limit=9999) or []
            # 最新在前 → 反转得到时间正序，再取最后3条
            recent = list(reversed(raw_records))[-3:]
            if not recent:
                continue
            for r in recent:
                delta = r.get("delta", 0)
                sign = "+" if delta >= 0 else ""
                lines.append(
                    f"- [{name}] {r.get('source', '')} "
                    f"{sign}{delta}（{r.get('scene_id', '')}）"
                )
        return "\n".join(lines) if lines else "（暂无记录）"

    def _build_npc_status(self) -> str:
        """db 模式：渲染当前场景活跃 NPC 状态"""
        if self.mode != "db":
            return ""

        npcs = self.db.query_npcs_in_scene(self.current_scene_id)
        if not npcs:
            npcs = self.db.get_all_npc_states()[:5]  # fallback：最近5个NPC
        if not npcs:
            return "（暂无NPC状态）"

        lines = []
        for npc in npcs:
            lines.append(
                f"- {npc['name']}（{npc['id']}）: "
                f"关系{npc.get('relation_value', 0)} | "
                f"位于{npc.get('current_location', '?')}"
            )
        return "\n".join(lines)

    def _build_dialogue_history(self) -> str:
        """db 模式：渲染最近对话历史"""
        if self.mode != "db":
            return ""

        dialogues = self.db.query_dialogue(limit=10)
        if not dialogues:
            return "（暂无对话历史）"

        lines = []
        for d in dialogues:
            prefix = "【玩家】" if d["speaker"] == "player" else f"【{d['npc_id']}】"
            content = d.get("summary") or d.get("content", "")[:50]
            lines.append(f"{prefix} {content}")
        return "\n".join(lines[:6])  # 最多6条

    def _build_world_events(self) -> str:
        """db 模式：渲染世界事件回顾"""
        if self.mode != "db":
            return ""

        if self.turn > 0:
            events = self.db.query_events(turn=self.turn, limit=5)
        else:
            events = self.db.query_events(limit=5)

        if not events:
            return "（暂无世界事件）"

        lines = []
        for e in events:
            tags = json.loads(e.get("tags", "[]"))
            tag_str = f"[{','.join(tags)}]" if tags else ""
            lines.append(f"- [{e['scene_id']}] {e['summary']} {tag_str}")
        return "\n".join(lines)

    # ────────────────────────────────────────────────
    # 主入口
    # ────────────────────────────────────────────────

    def build_system_prompt(self, scene: Scene) -> str:
        """
        构建完整的 system prompt。
        将所有数值系统状态渲染进 prompt，供 LLM 读取后驱动叙事。
        """
        locked_str = self._build_locked_options()

        if scene.available_actions:
            options_str = "\n".join(f"- {a}" for a in scene.available_actions)
        else:
            options_str = "（由你根据情境自由发挥）"

        # ── 模式专属额外区块 ──
        if self.mode == "db":
            mode_extra = DB_MODE_EXTRA_TEMPLATE.format(
                npc_status=self._build_npc_status(),
                dialogue_history=self._build_dialogue_history(),
                world_events=self._build_world_events(),
            ).strip()
            hidden_values_section = self._build_hidden_values_section_for_db()
        else:
            mode_extra = ""
            hidden_values_section = self._build_hidden_values_section()

        return SYSTEM_PROMPT_TEMPLATE.format(
            name=self.game_loader.meta.name,
            setting=self.game_loader.setting[:4000],
            scene_title=scene.title,
            scene_content=scene.content[:3000],
            player_status=self._build_player_status(),
            hidden_values_section=hidden_values_section,
            available_options=options_str,
            locked_options=locked_str,
            moral_debt_records=self._build_hidden_value_records(),
            npc_relations=self._build_npc_relations(),
            npc_memory_summaries=self._build_npc_memory_summaries(),
            pending_triggered_scenes_section=self._build_pending_triggered_scenes(),
            faction_section=self._build_faction_section(),
            world_events_section=self._build_world_events_section(),
            time_section=self._build_time_section(),
            mode_extra=f"\n\n{mode_extra}" if mode_extra else "",
        )

    def _build_hidden_values_section_for_db(self) -> str:
        """
        db 模式：渲染隐藏数值区块。

        从 hidden_value_state.effects_snapshot 列读取 effects 快照，
        用当前 level 对应的 threshold_key 索引得到该档位效果，
        从而渲染 narrative_tone 和 locked_options。
        """
        hv_states = self.db.get_all_hidden_value_states()
        if not hv_states:
            return "（暂无隐藏数值记录）"

        rows = []
        for hv in hv_states:
            level = hv.get("level", 0)

            # effects_snapshot：{ threshold_str: { locked_options, narrative_tone, ... }, ... }
            effects_snapshot_raw = hv.get("effects_snapshot", "{}")
            try:
                effects_snapshot: Dict = json.loads(effects_snapshot_raw) if effects_snapshot_raw else {}
            except Exception:
                effects_snapshot = {}

            # 用 level 找到当前 threshold 对应的 key
            vid = hv["hidden_value_id"]
            cfg = self.hidden_values_cfg.get(vid, {})
            thresholds = cfg.get("thresholds", [0])
            threshold_key = str(thresholds[level]) if level < len(thresholds) else str(thresholds[-1])

            # 优先从 effects_snapshot 读（数据库中已保存的运行时状态），
            # 降级到剧本原始配置
            snapshot_eff = effects_snapshot.get(threshold_key, {})
            effects_cfg = cfg.get("effects", {})
            cfg_eff = effects_cfg.get(threshold_key, {})
            tone = snapshot_eff.get("narrative_tone") or cfg_eff.get("narrative_tone", hv.get("description", "—"))
            style = snapshot_eff.get("narrative_style") or cfg_eff.get("narrative_style", "normal")
            locked = snapshot_eff.get("locked_options") or cfg_eff.get("locked_options", [])
            locked_str = "、".join(locked) if locked else "（无）"
            unlock = snapshot_eff.get("unlock_options") or cfg_eff.get("unlock_options", [])
            unlock_str = "、".join(unlock) if unlock else "（无）"
            hint = snapshot_eff.get("narrative_hint") or cfg_eff.get("narrative_hint", "—")

            rows.append(
                f"| {hv['name']} | 等级{level} | {tone} | {style} | 锁定：{locked_str} | 解锁：{unlock_str} | {hint} |"
            )

        default_row = "| — | — | — | — | — | — | — |"
        hv_section = HIDDEN_VALUES_TEMPLATE.format(
            hv_rows="\n".join(rows) if rows else default_row,
            narrative_style_guidance=NARRATIVE_STYLE_GUIDANCE,
            action_tags_section="（db 模式通过 hidden_value_delta 指令更新数值）",
        )
        return hv_section.strip()

    def build_user_prompt(self, player_input: str, history_summary: str = "") -> str:
        """构建用户输入的 prompt"""
        parts = []
        if history_summary:
            parts.append(f"[近期回顾]\n{history_summary}\n")
        parts.append(f"[你的行动]\n{player_input}")
        return "\n".join(parts)

    def build_choice_prompt(
        self,
        scene: Scene,
        options: List[Dict[str, str]],
        history_summary: str = "",
    ) -> str:
        """
        构建选项选择 prompt。
        用于 choice 模式下渲染预设选项列表。
        """
        options_lines = []
        for i, opt in enumerate(options, 1):
            desc = opt.get("description", "")
            tag = opt.get("action_tag", "")
            tag_hint = f" [action_tag: {tag}]" if tag else ""
            options_lines.append(f"{i}. {opt['name']}：{desc}{tag_hint}")

        options_section = "\n".join(options_lines)

        return f"""## 当前情境
{scene.content[:1500]}

## 可选行动
{options_section}

{self.build_user_prompt("", history_summary)}
"""

    def update_turn(self, scene_id: str, turn: int) -> None:
        """更新当前场景和回合（切换场景时调用）"""
        self.current_scene_id = scene_id
        self.turn = turn

    def get_hidden_value_snapshot(self) -> Dict[str, Dict]:
        """暴露隐藏数值快照，供调用方（如 game_master.py）查询"""
        if self.hidden_value_sys is None:
            return {}
        return self.hidden_value_sys.get_snapshot()

    # get_snapshot：get_hidden_value_snapshot 的别名，兼容 context_builder 测试
    def get_snapshot(self) -> Dict[str, Dict]:
        """get_hidden_value_snapshot 的别名"""
        return self.get_hidden_value_snapshot()

    def get_narrative_styles(self) -> Dict[str, str]:
        """暴露各隐藏数值的当前叙事风格，供 GM 层使用"""
        if self.hidden_value_sys is None:
            return {}
        return self.hidden_value_sys.get_narrative_styles()

    def get_pending_triggered_scenes(self) -> Dict[str, str]:
        """
        暴露待插入触发场景，供 GameMaster 查询。
        返回 {hidden_value_id: scene_id}。
        """
        if self.hidden_value_sys is None:
            return {}
        return self.hidden_value_sys.get_pending_triggered_scenes()

    def acknowledge_triggered_scene(self, hidden_value_id: str) -> None:
        """
        标记指定隐藏数值的触发场景已被 GM 插入。
        调用此方法后，get_pending_triggered_scenes() 不再返回该场景。
        """
        if self.hidden_value_sys is None:
            return
        self.hidden_value_sys.acknowledge_triggered_scene(hidden_value_id)

    def record_action(
        self,
        action_tag: str,
        scene_id: str,
        turn: int,
        player_action: str,
    ) -> tuple[Dict[str, int], Dict[str, Optional[str]], Dict[str, int], Dict[str, List[Dict]]]:
        """
        通过 action_tag 触发隐藏数值变化。
        返回 (各值变化量, 各值触发场景, 关系变化量, 跨值联动结果).

        调用方应在 GM 返回 action_tag 后调用此方法。
        relation_delta 由调用方自行处理（如应用到 DialogueSystem）。

        注意：仅 memory 模式可用。db 模式下请直接操作数据库。
        """
        if self.hidden_value_sys is None:
            return {}, {}, {}, {}
        return self.hidden_value_sys.record_action(
            action_tag=action_tag,
            scene_id=scene_id,
            turn=turn,
            player_action=player_action,
        )
