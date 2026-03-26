# core/gms_tools.py - AgentScope 工具封装
"""
将 RPG 系统的核心功能封装为 AgentScope ToolCall 工具，
让 LLM 在叙事过程中主动调用，而不是依赖 GM_COMMAND 事后解析。

工具列表：
- check_hidden_value / get_all_hidden_values   # 查询隐藏数值状态
- record_player_action                         # 记录玩家行为
- get_locked_options / get_available_options   # 查询选项可用性
- check_threshold_trigger                      # 检查阈值触发
- generate_adventure_log                       # 生成冒险日志（已在 systems/adventure_log.py 实现）
"""

from typing import Any, Optional
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


# ─── 工具函数工厂 ────────────────────────────────────────

class GMSTools:
    """工具函数集合，所有方法返回 ToolResponse"""

    def __init__(self, game_master: Any):
        self.gm = game_master

    # ── 隐藏数值查询 ───────────────────────────────

    def check_hidden_value(self, hidden_value_id: str) -> ToolResponse:
        """查询指定隐藏数值的当前状态"""
        hv_sys = self.gm.hidden_value_sys
        if not hv_sys:
            return ToolResponse(content=[TextBlock(type="text", text="隐藏数值系统未初始化")])
        
        hv = hv_sys.get_hidden_value(hidden_value_id)
        if hv is None:
            return ToolResponse(content=[TextBlock(type="text", text=f"未找到隐藏数值: {hidden_value_id}")])
        
        level = hv.get_current_level_name()
        level_idx = hv.level_idx
        value = hv.get_value()
        
        effects = hv.get_effect_for_level(level_idx)
        locked = effects.locked_options if effects else []
        narrative_tone = effects.narrative_tone if effects else ""
        
        text = (
            f"【{hv.name}】\n"
            f"当前值: {value}\n"
            f"当前档位: {level}（{level_idx}级）\n"
            f"锁定选项: {locked if locked else '无'}\n"
            f"叙事语气: {narrative_tone or '正常'}"
        )
        return ToolResponse(content=[TextBlock(type="text", text=text)])

    def get_all_hidden_values(self) -> ToolResponse:
        """获取所有隐藏数值的快照"""
        hv_sys = self.gm.hidden_value_sys
        if not hv_sys:
            return ToolResponse(content=[TextBlock(type="text", text="隐藏数值系统未初始化")])
        
        all_values = hv_sys.get_all_levels()
        lines = []
        for vid, level_name in all_values.items():
            hv = hv_sys.get_hidden_value(vid)
            value = hv.get_value() if hv else "?"
            lines.append(f"- {vid}: {value}（{level_name}）")
        
        text = "【所有隐藏数值】\n" + ("\n".join(lines) if lines else "无")
        return ToolResponse(content=[TextBlock(type="text", text=text)])

    # ── 玩家行为记录 ───────────────────────────────

    def record_player_action(
        self,
        action_tag: str,
        player_action: str,
    ) -> ToolResponse:
        """记录玩家行为导致的隐藏数值变化"""
        hv_sys = self.gm.hidden_value_sys
        if not hv_sys:
            return ToolResponse(content=[TextBlock(type="text", text="隐藏数值系统未初始化")])
        
        deltas, triggered_scenes, relation_deltas, cross_results = hv_sys.record_action(
            action_tag=action_tag,
            scene_id=self.gm.session.current_scene_id,
            turn=self.gm.session.turn_count,
            player_action=player_action,
        )
        
        # 应用关系变化
        for npc_id, delta in relation_deltas.items():
            self.gm.dialogue_sys.modify_relation(npc_id, delta)
        
        # 通知触发场景
        for vid, scene_id in triggered_scenes.items():
            if scene_id:
                self.gm.session.flags[f"_hv_triggered_{vid}"] = scene_id
        
        # 汇总结果
        lines = [f"行为标签: {action_tag}", f"玩家动作: {player_action}"]
        if deltas:
            for vid, delta in deltas.items():
                hv = hv_sys.get_hidden_value(vid)
                name = hv.name if hv else vid
                lines.append(f"  {name}: {'+' if delta >= 0 else ''}{delta}")
        if triggered_scenes:
            for vid, scene_id in triggered_scenes.items():
                if scene_id:
                    lines.append(f"  触发场景: {scene_id}")
        
        # 同步 session
        self._sync_session()
        
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    # ── 选项可用性 ───────────────────────────────

    def get_locked_options(self, hidden_value_ids: Optional[list[str]] = None) -> ToolResponse:
        """查询当前被锁定的选项类型"""
        hv_sys = self.gm.hidden_value_sys
        if not hv_sys:
            return ToolResponse(content=[TextBlock(type="text", text="隐藏数值系统未初始化")])
        
        if hidden_value_ids:
            ids_to_check = hidden_value_ids
        else:
            ids_to_check = list(hv_sys.hidden_values.keys())
        
        locked_by_group = {}
        for vid in ids_to_check:
            hv = hv_sys.get_hidden_value(vid)
            if hv:
                level_idx = hv.level_idx
                effects = hv.get_effect_for_level(level_idx)
                if effects and effects.locked_options:
                    for opt in effects.locked_options:
                        locked_by_group[opt] = locked_by_group.get(opt, [])
                        locked_by_group[opt].append(hv.name)
        
        if not locked_by_group:
            return ToolResponse(content=[TextBlock(type="text", text="当前无锁定选项，所有选项可用")])
        
        lines = ["【当前锁定选项】"]
        for opt, sources in locked_by_group.items():
            lines.append(f"- {opt}（被以下数值锁定: {', '.join(sources)}）")
        
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    def get_available_options(self, option_types: list[str]) -> ToolResponse:
        """检查给定选项列表中哪些可用"""
        hv_sys = self.gm.hidden_value_sys
        if not hv_sys:
            return ToolResponse(content=[TextBlock(type="text", text="隐藏数值系统未初始化")])
        
        available = []
        locked = []
        for opt in option_types:
            is_locked = hv_sys.is_option_locked_by_any(opt)
            if is_locked:
                locked.append(opt)
            else:
                available.append(opt)
        
        lines = ["【选项可用性检查】"]
        if available:
            lines.append(f"可用: {', '.join(available)}")
        if locked:
            lines.append(f"锁定: {', '.join(locked)}")
        
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    # ── 阈值触发检查 ─────────────────────────────

    def check_threshold_trigger(self, hidden_value_id: str) -> ToolResponse:
        """检查是否跨过阈值，返回触发的场景ID或None"""
        hv_sys = self.gm.hidden_value_sys
        if not hv_sys:
            return ToolResponse(content=[TextBlock(type="text", text="隐藏数值系统未初始化")])
        
        scene_id = hv_sys.check_trigger(self.gm.session.current_scene_id, self.gm.session.turn_count)
        if scene_id:
            hv = hv_sys.get_hidden_value(hidden_value_id)
            name = hv.name if hv else hidden_value_id
            return ToolResponse(content=[TextBlock(type="text", text=f"触发场景: {scene_id}（{name}跨阈）")])
        else:
            return ToolResponse(content=[TextBlock(type="text", text="未触发任何场景")])

    # ── 冒险日志生成 ─────────────────────────────

    def generate_adventure_log(self, act_title: str) -> ToolResponse:
        """生成冒险日志（Markdown格式）"""
        from systems.adventure_log import generate_adventure_log
        
        session = self.gm.session
        hv_sys = self.gm.hidden_value_sys
        
        # 收集事件（从 history 提取关键事件）
        events = []
        for h in session.history:
            if h.get("role") in ("gm", "player") and h.get("content"):
                content = h["content"]
                if len(content) > 80:
                    content = content[:80] + "..."
                events.append({
                    "turn": events.__len__() + 1,
                    "icon": "🔸",
                    "description": content,
                })
        
        # 隐藏数值汇总
        hv_summary = {}
        if hv_sys:
            for vid, hv in hv_sys.hidden_values.items():
                hv_summary[vid] = {
                    "level": hv.get_current_level_name(),
                    "value": hv.get_value(),
                }
        
        # 最终状态
        final_stats = session.stats.copy() if session.stats else {}
        relations = {}
        if self.gm.dialogue_sys:
            for npc_id, info in self.gm.dialogue_sys.get_all_relations().items():
                relations[npc_id] = {
                    "relation": info.get("value", 0),
                }
        
        log = generate_adventure_log(
            act_id="current",
            act_title=act_title,
            turns=session.turn_count,
            events=events,
            hidden_value_summary={"moral_debt": hv_summary.get("moral_debt", {})},
            final_stats=final_stats,
            start_stats=None,
            relations=relations,
        )
        
        return ToolResponse(content=[TextBlock(type="text", text=log)])

    # ── 状态同步 ─────────────────────────────────

    def _sync_session(self):
        """同步 session 状态"""
        hidden_value_snapshot = (
            self.gm.hidden_value_sys.get_snapshot() if self.gm.hidden_value_sys else {}
        )
        self.gm.session.update_state(
            scene_id=self.gm.current_scene.id if self.gm.current_scene else None,
            stats=self.gm.stats_sys.get_snapshot(),
            moral_debt=self.gm.moral_sys.debt,
            inventory=self.gm.inv_sys.get_snapshot()["items"],
            relations={
                npc_id: info["value"]
                for npc_id, info in self.gm.dialogue_sys.get_all_relations().items()
            },
            hidden_values=hidden_value_snapshot,
        )


def create_gms_tools(game_master: Any) -> list:
    """
    创建所有 GMS 工具函数，返回列表。
    供 GameMaster 注册到 Toolkit。
    """
    tools = GMSTools(game_master)
    return [
        tools.check_hidden_value,
        tools.get_all_hidden_values,
        tools.record_player_action,
        tools.get_locked_options,
        tools.get_available_options,
        tools.check_threshold_trigger,
        tools.generate_adventure_log,
    ]
