# core/game_master.py - 游戏主持人主逻辑
"""
GameMaster：整合 AgentScope Agent 作为 DM，驱动 RPG 叙事。
数值系统（systems/）独立于 LLM，结果可验证。
"""

import re
from typing import Dict, Optional, Tuple, List, Any
from agentscope import agent
from agentscope.model import AnthropicChatModel
from config.settings import DEFAULT_MODEL, BASE_URL, API_KEY
from .context_loader import ContextLoader, GameLoader, Scene
from .session import Session
from .prompt_builder import PromptBuilder


class GMCommandParser:
    """解析 GM_COMMAND 块，返回结构化指令"""

    @staticmethod
    def parse(text: str) -> Optional[Dict[str, Any]]:
        # 支持 \n 和真实换行的 GM_COMMAND
        pattern = r"\[GM_COMMAND\]\s*(.*?)\s*\[/GM_COMMAND\]"
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return None
        result = {}
        raw_block = match.group(1).replace("\\n", "\n")
        for line in raw_block.strip().split("\n"):
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()

        # action_tag 必填：如果 GM_COMMAND 中缺失，从全文已知 action_tag 列表匹配
        if "action_tag" not in result or not result.get("action_tag"):
            known_tags = ["huff_and_puff", "trick_pig", "threaten_pig", "give_up", "eat_pig", "run_away",
                          "huff_and_puff", "trick_pig", "threaten_pig", "give_up", "eat_pig", "run_away"]
            for tag in known_tags:
                if tag in text.lower():
                    result["action_tag"] = tag
                    break

        return result if result else None

    @staticmethod
    def extract_narrative(text: str) -> str:
        return re.sub(
            r"\[GM_COMMAND\].*?\[/GM_COMMAND\]",
            "",
            text,
            flags=re.DOTALL,
        ).strip()


class GameMaster:
    """
    游戏主持人核心类。

    使用 AgentScope ReActAgent 作为 DM（叙事引擎），
    systems/ 模块负责所有数值逻辑，结果可验证。
    """

    def __init__(
        self,
        game_id: str,
        context_loader: ContextLoader,
        session: Session,
        model_name: str = DEFAULT_MODEL,
        api_key: str = API_KEY,
        base_url: str = BASE_URL,
    ):
        self.game_id = game_id
        self.context_loader = context_loader
        self.session = session

        # 获取游戏加载器
        self.game_loader = context_loader.get_loader(game_id)
        if not self.game_loader:
            raise ValueError(f"未找到游戏: {game_id}")

        # 初始化各系统（纯Python，无LLM依赖）
        from systems.stats import StatsSystem
        from systems.moral_debt import MoralDebtSystem
        from systems.inventory import InventorySystem
        from systems.dialogue import DialogueSystem
        from systems.hidden_value import HiddenValueSystem

        self.stats_sys = StatsSystem()
        self.moral_sys = MoralDebtSystem()
        self.inv_sys = InventorySystem()
        self.dialogue_sys = DialogueSystem()

        # 隐藏数值系统（从 meta.json 读取配置，支持道德债务/理智/成长等多种隐藏数值）
        meta = self.game_loader.meta
        hv_configs = getattr(meta, "hidden_values", []) or []
        hv_action_map = getattr(meta, "hidden_value_actions", {}) or {}
        self.hidden_value_sys: HiddenValueSystem | None = None
        if hv_configs:
            self.hidden_value_sys = HiddenValueSystem(
                configs=hv_configs,
                action_map=hv_action_map,
            )

        # Prompt 构造器
        self.prompt_builder = PromptBuilder(
            self.game_loader,
            self.stats_sys,
            self.moral_sys,
            self.inv_sys,
            self.dialogue_sys,
            hidden_value_sys=self.hidden_value_sys,
        )

        # 初始化 AgentScope 模型（使用 AnthropicChatModel，支持 /v1/messages 端点）
        # thinking={"type": "disabled"} 防止模型输出 thinking 块干扰 GM_COMMAND 解析
        self.model = AnthropicChatModel(
            model_name=model_name,
            api_key=api_key,
            client_kwargs={"base_url": base_url.rstrip("/")},
            thinking={"type": "disabled"},
            stream=False,
        )

        # 获取初始场景
        self.current_scene = self.game_loader.get_first_scene()
        if self.current_scene:
            self.session.update_state(scene_id=self.current_scene.id)

        # AgentScope Agent（用于生成叙事）
        self._agent: Optional[agent.ReActAgent] = None

    @property
    def dm(self) -> agent.ReActAgent:
        """懒加载 DM Agent"""
        if self._agent is None:
            scene = self.get_current_scene()
            sys_prompt = (
                self.prompt_builder.build_system_prompt(scene)
                if scene
                else "你是RPG游戏主持人。"
            )
            from agentscope.formatter._openai_formatter import OpenAIChatFormatter
            self._agent = agent.ReActAgent(
                name="GameMaster",
                sys_prompt=sys_prompt,
                model=self.model,
                formatter=OpenAIChatFormatter(),
                max_iters=10,
                print_hint_msg=False,
            )
        return self._agent

    def get_current_scene(self) -> Optional[Scene]:
        return self.game_loader.get_scene(self.session.current_scene_id)

    def process_input(self, player_input: str) -> Tuple[str, Optional[Dict]]:
        """
        处理玩家输入：
        1. 构造 user_prompt（附当前状态摘要）
        2. 调用 AgentScope DM Agent 生成叙事
        3. 解析 GM_COMMAND，更新数值系统
        4. 返回叙事内容
        """
        scene = self.get_current_scene()
        if not scene:
            return "[系统错误] 当前场景未找到。", None

        # 构造用户输入
        history_summary = self.session.get_history_summary()
        user_prompt = self.prompt_builder.build_user_prompt(player_input, history_summary)

        # 注入最新系统状态到 system prompt（每次动态更新）
        # 注意：ReActAgent.sys_prompt 是只读属性，需直接修改 _sys_prompt
        current_sys_prompt = self.prompt_builder.build_system_prompt(scene)
        self.dm._sys_prompt = current_sys_prompt

        # 调用 AgentScope Agent（reply 是 async 方法，需要传入 Msg 对象）
        from agentscope.message import Msg
        import asyncio
        msg = Msg(name="玩家", content=user_prompt, role="user")
        reply_result = self.dm.reply(msg)
        if asyncio.iscoroutine(reply_result):
            response = asyncio.run(reply_result)
        else:
            response = reply_result
        llm_output = response if isinstance(response, str) else str(response)

        self.session.add_history("gm", llm_output)

        # 解析 GM_COMMAND
        cmd = GMCommandParser.parse(llm_output)
        narrative = GMCommandParser.extract_narrative(llm_output)

        # 当 GM_COMMAND 中没有 action_tag 时，通过关键词推断（弥补 LLM 不遵循指令的问题）
        if cmd and "action_tag" not in cmd:
            combined_text = narrative.lower()
            if any(k in combined_text for k in ["吹", "huff", "吹倒", "吹气"]):
                cmd["action_tag"] = "huff_and_puff"
            elif any(k in combined_text for k in ["骗", "假装", "trick", "装", "哄"]):
                cmd["action_tag"] = "trick_pig"
            elif any(k in combined_text for k in ["威胁", "恐吓", "threaten"]):
                cmd["action_tag"] = "threaten_pig"
            elif any(k in combined_text for k in ["放弃", "give_up", "算了", "走"]):
                cmd["action_tag"] = "give_up"
            elif any(k in combined_text for k in ["吃", "吃掉", "eat", "吞"]):
                cmd["action_tag"] = "eat_pig"
            elif any(k in combined_text for k in ["逃跑", "run_away", "跑"]):
                cmd["action_tag"] = "run_away"

        # 执行指令
        if cmd:
            self._execute_command(cmd)

        self._sync_session()
        return narrative, cmd

    def _execute_command(self, cmd: Dict[str, Any]):
        """执行 GM_COMMAND 指令"""
        action = cmd.get("action", "narrative")

        # ── 隐藏数值系统：通过 action_tag 触发数值变化 ──
        if self.hidden_value_sys and "action_tag" in cmd:
            action_tag = cmd["action_tag"]
            player_input = cmd.get("player_input", "")
            deltas, triggered_scenes, relation_deltas, cross_trigger_results = self.hidden_value_sys.record_action(
                action_tag=action_tag,
                scene_id=self.session.current_scene_id,
                turn=self.session.turn_count,
                player_action=player_input,
            )
            # 如果触发了特殊场景，通知 GM（后续主循环处理跳转）
            for vid, scene_id in triggered_scenes.items():
                if scene_id:
                    self.session.flags[f"_hv_triggered_{vid}"] = scene_id
            # action_map 中的 relation_delta 直接应用到 DialogueSystem
            for npc_id, delta in relation_deltas.items():
                self.dialogue_sys.modify_relation(npc_id, delta)

        if action == "transition":
            next_scene = cmd.get("next_scene")
            if next_scene:
                self.session.update_state(scene_id=next_scene)
                self.current_scene = self.game_loader.get_scene(next_scene)

        # 道德债务指令
        if "moral_debt_delta" in cmd:
            try:
                delta = int(cmd["moral_debt_delta"])
                self.moral_sys.add(
                    source=cmd.get("moral_debt_source", "未标注"),
                    amount=delta,
                    scene=self.session.current_scene_id,
                    description=cmd.get("description", ""),
                )
            except ValueError:
                pass

        # ── 触发场景插入确认 ──
        # GM 在叙事中插入触发场景后，通过此指令确认，防止重复插入
        if "trigger_scene_ack" in cmd:
            hv_id = cmd["trigger_scene_ack"].strip()
            self.prompt_builder.acknowledge_triggered_scene(hv_id)

        # ── 旧版触发场景确认（兼容）──
        if "triggered_scene_ack" in cmd:
            hv_id = cmd["triggered_scene_ack"].strip()
            self.prompt_builder.acknowledge_triggered_scene(hv_id)

        # 关系修改指令
        if "relation_delta" in cmd and "npc_id" in cmd:
            try:
                delta = int(cmd["relation_delta"])
                self.dialogue_sys.modify_relation(cmd["npc_id"], delta)
            except ValueError:
                pass

        # 属性修改指令
        if "stat_delta" in cmd and "stat_name" in cmd:
            try:
                stat = cmd["stat_name"]
                delta = int(cmd["stat_delta"])
                self.stats_sys.modify(stat, delta)
            except ValueError:
                pass

    def _sync_session(self):
        """同步 session 状态"""
        # 收集隐藏数值快照（用于存档）
        hidden_value_snapshot = (
            self.hidden_value_sys.get_snapshot() if self.hidden_value_sys else {}
        )

        self.session.update_state(
            scene_id=self.current_scene.id if self.current_scene else None,
            stats=self.stats_sys.get_snapshot(),
            moral_debt=self.moral_sys.debt,
            inventory=self.inv_sys.get_snapshot()["items"],
            relations={
                npc_id: info["value"]
                for npc_id, info in self.dialogue_sys.get_all_relations().items()
            },
            hidden_values=hidden_value_snapshot,
        )
        self.session.increment_turn()

    def apply_combat_result(
        self,
        result,
        killed: bool = False,
        was_kind: bool = False,
        was_cruel: bool = False,
        avoided_harm: bool = False,
    ) -> dict:
        """
        战斗结算后更新数值。

        Args:
            result:        CombatResult 实例
            killed:        是否击杀了敌人
            was_kind:      是否在战斗中表现仁慈
            was_cruel:     是否以残忍手段结束战斗
            avoided_harm:  是否成功避免受到伤害

        Returns:
            combat_event() 的结果字典（含 deltas / relation_deltas 等）
        """
        if result.damage_taken > 0:
            self.stats_sys.take_damage(result.damage_taken)
        # 同步 stats 到 session
        self._sync_session()

        # 处理战斗事件对隐藏数值的影响
        combat_result = {}
        if self.hidden_value_sys:
            combat_result = self.hidden_value_sys.combat_event(
                killed=killed,
                was_kind=was_kind,
                was_cruel=was_cruel,
                was_injured=result.damage_taken > 0,
                avoided_harm=avoided_harm,
                scene_id=self.session.current_scene_id,
                turn=self.session.turn_count,
            )
            # 处理 relation_delta
            for npc_id, delta in combat_result.get("relation_deltas", {}).items():
                self.dialogue_sys.modify_relation(npc_id, delta)
            # 处理触发场景
            for vid, scene_id in combat_result.get("triggered_scenes", {}).items():
                if scene_id:
                    self.session.flags[f"_hv_triggered_{vid}"] = scene_id

        return combat_result

    def get_status(self) -> str:
        """获取当前状态摘要"""
        stats = self.stats_sys.get_snapshot()
        moral = self.moral_sys.get_snapshot()
        scene_title = self.current_scene.title if self.current_scene else "?"
        return (
            f"【状态】HP {stats['hp']}/{stats['max_hp']} | "
            f"体力 {stats['stamina']}/{stats['max_stamina']} | "
            f"道德债务 {moral['level']}（{moral['debt']}分） | "
            f"场景 {scene_title}"
        )

    def reset_dm(self) -> None:
        """重置 DM Agent（换场/重开时调用）"""
        self._agent = None
