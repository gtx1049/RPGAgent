# core/game_master.py - 游戏主持人主逻辑
"""
GameMaster：整合 AgentScope Agent 作为 DM，驱动 RPG 叙事。
数值系统（systems/）独立于 LLM，结果可验证。
"""

import re
from typing import Dict, Optional, Tuple, List, Any
from agentscope import agent
from agentscope.model import OpenAIChatModel
from config.settings import DEFAULT_MODEL, BASE_URL, API_KEY
from .context_loader import ContextLoader, GameLoader, Scene
from .session import Session
from .prompt_builder import PromptBuilder


class GMCommandParser:
    """解析 GM_COMMAND 块，返回结构化指令"""

    @staticmethod
    def parse(text: str) -> Optional[Dict[str, Any]]:
        pattern = r"\[GM_COMMAND\]\s*(.*?)\s*\[/GM_COMMAND\]"
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return None
        result = {}
        for line in match.group(1).strip().split("\n"):
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
        return result

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

        # 初始化 AgentScope 模型
        self.model = OpenAIChatModel(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url.rstrip("/") + "/v1",
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
            self._agent = agent.ReActAgent(
                name="GameMaster",
                sys_prompt=sys_prompt,
                model=self.model,
                formatter=None,  # 使用默认 formatter
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
        current_sys_prompt = self.prompt_builder.build_system_prompt(scene)
        self.dm.sys_prompt = current_sys_prompt

        # 调用 AgentScope Agent
        response = self.dm.reply(user_prompt)
        llm_output = response if isinstance(response, str) else str(response)

        self.session.add_history("gm", llm_output)

        # 解析 GM_COMMAND
        cmd = GMCommandParser.parse(llm_output)
        narrative = GMCommandParser.extract_narrative(llm_output)

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
            deltas, triggered_scenes, relation_deltas = self.hidden_value_sys.record_action(
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

    def apply_combat_result(self, result) -> None:
        """战斗结算后更新数值"""
        if result.damage_taken > 0:
            self.stats_sys.take_damage(result.damage_taken)
        self._sync_session()

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
