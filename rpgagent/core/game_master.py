# core/game_master.py - 游戏主持人主逻辑
"""
GameMaster：整合 AgentScope Agent 作为 DM，驱动 RPG 叙事。
数值系统（systems/）独立于 LLM，结果可验证。
"""

import re
from typing import Dict, Optional, Tuple, List, Any
from agentscope import agent
from agentscope.model import AnthropicChatModel
from ..config.settings import DEFAULT_MODEL, BASE_URL, API_KEY
from .context_loader import ContextLoader, GameLoader, Scene
from .session import Session
from .prompt_builder import PromptBuilder
from .scene_trigger import SceneTriggerEngine


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

    # ── 数值变化提取（从叙事文本中解析体力/HP/金币/经验变化）─────────
    # 支持格式：体力消耗：-10 / HP减少：10 / 金币 +50 / 经验 +20
    _VALUE_PATTERNS = [
        # 体力消耗/下降/减去（值>0表示消耗，取负）
        (re.compile(r"体力消耗[：:]\s*([+-]?\d+)"), "stamina", True),
        (re.compile(r"体力下降[：:]\s*([+-]?\d+)"), "stamina", True),
        (re.compile(r"体力-[：:]\s*(\d+)"), "stamina", True),
        # 体力恢复/增加（正值）
        (re.compile(r"体力恢复[：:]\s*([+-]?\d+)"), "stamina", False),
        (re.compile(r"体力\+\s*(\d+)"), "stamina", False),
        # HP减少/扣除/受到（值>0表示受伤，取负）
        (re.compile(r"HP减少[：:]\s*(\d+)"), "hp", True),
        (re.compile(r"HP扣除[：:]\s*(\d+)"), "hp", True),
        (re.compile(r"HP[：:]\s*-(?:\s*)(\d+)"), "hp", True),
        (re.compile(r"受到\s*\d+\s*点伤害"), "hp", True),
        # HP恢复/治疗（正值）
        (re.compile(r"HP恢复[：:]\s*([+-]?\d+)"), "hp", False),
        (re.compile(r"HP\+\s*(\d+)"), "hp", False),
        # 金币变化
        (re.compile(r"金币\s*([+-]?\d+)"), "gold", False),
        # 经验变化
        (re.compile(r"经验\s*([+-]?\d+)"), "exp", False),
        (re.compile(r"经验值\s*([+-]?\d+)"), "exp", False),
    ]

    @staticmethod
    def extract_value_deltas(narrative: str) -> Dict[str, int]:
        """从叙事文本中提取数值变化，返回 {field: delta} 字典"""
        deltas: Dict[str, int] = {}
        for pattern, field, is_cost in GMCommandParser._VALUE_PATTERNS:
            m = pattern.search(narrative)
            if m:
                raw = int(m.group(1))
                if is_cost:
                    delta = -abs(raw)
                else:
                    delta = raw if raw >= 0 else -abs(raw)
                deltas[field] = deltas.get(field, 0) + delta
        return deltas


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

        # 引擎版本兼容性检查
        from ..config.settings import check_engine_version
        meta = self.game_loader.meta
        required_engine = getattr(meta, "engine_version", None) if meta else None
        ok, msg = check_engine_version(required_engine)
        if not ok:
            raise ValueError(msg)

        # 初始化各系统（纯Python，无LLM依赖）
        from rpgagent.systems.stats import StatsSystem
        from rpgagent.systems.moral_debt import MoralDebtSystem
        from rpgagent.systems.inventory import InventorySystem
        from rpgagent.systems.dialogue import DialogueSystem
        from rpgagent.systems.hidden_value import HiddenValueSystem
        from rpgagent.systems.skill_system import SkillSystem
        from rpgagent.systems.equipment_system import EquipmentSystem

        self.stats_sys = StatsSystem()
        self.moral_sys = MoralDebtSystem()
        self.inv_sys = InventorySystem()
        self.dialogue_sys = DialogueSystem()
        self.skill_sys = SkillSystem()
        self.equipment_sys = EquipmentSystem()

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


        # NPC 长记忆与关系网络
        from rpgagent.systems.npc_memory import NpcMemorySystem
        self.npc_mem_sys = NpcMemorySystem()

        # 注册 NPC 社会关系网络
        self._register_npcs_from_loader()

        # 初始化 AgentScope 模型（使用 AnthropicChatModel，支持 /v1/messages 端点）
        # thinking={"type": "disabled"} 防止模型输出 thinking 块干扰 GM_COMMAND 解析

        # 骰点判定系统
        from rpgagent.systems.roll_system import RollSystem
        self.roll_sys = RollSystem(self.stats_sys, self.skill_sys, self.equipment_sys)

        # 装备获取系统（战利品/宝箱/NPC交易）
        from rpgagent.systems.acquisition import AcquisitionSystem
        self.acquisition_sys = AcquisitionSystem()

        # 队友系统（可招募NPC作为队友）
        from rpgagent.systems.teammate_system import TeammateSystem
        self.teammate_sys = TeammateSystem()
        self._register_teammates_from_loader()

        # 阵营声望系统
        from rpgagent.systems.faction_system import FactionSystem
        self.faction_sys = FactionSystem()
        self.faction_sys.load_from_meta(meta)

        # 多结局系统
        from rpgagent.systems.ending_system import EndingSystem
        self.ending_sys = EndingSystem()
        self.ending_sys.load_from_meta(meta, game_id=game_id)
        self.ending_sys.bind_game_master(self)

        # 昼夜循环系统
        from rpgagent.systems.day_night_cycle import DayNightCycle
        self.day_night_sys = DayNightCycle()
        # 恢复存档中的时间进度（如有）
        saved_day = getattr(session, "day", None)
        saved_period = getattr(session, "period", None)
        if saved_day and saved_period:
            self.day_night_sys.set_day(saved_day)
            from rpgagent.systems.day_night_cycle import TimePeriod
            try:
                self.day_night_sys.set_period(TimePeriod(saved_period))
            except ValueError:
                pass
        # 注册 NPC 作息（从角色 JSON 读取 schedule 字段）
        self._register_npc_schedules_from_loader()

        # 成就系统
        from rpgagent.systems.achievement_system import AchievementSystem
        ach_configs = getattr(meta, "achievements", []) or []
        self.achievement_sys = AchievementSystem(game_id=self.game_id, achievements=ach_configs)

        # 上下文压缩系统
        from rpgagent.systems.context_compressor import ContextCompressor
        self.compressor = ContextCompressor()
        # 从存档恢复成就进度（如有）
        saved_ach = session.achievements if hasattr(session, "achievements") else None
        if saved_ach:
            self.achievement_sys.load_snapshot(saved_ach)

        self.model = AnthropicChatModel(
            model_name=model_name,
            api_key=api_key,
            client_kwargs={"base_url": base_url.rstrip("/")},
            thinking={"type": "disabled"},
            stream=False,
        )

        # Prompt 构造器
        self.prompt_builder = PromptBuilder(
            self.game_loader,
            self.stats_sys,
            self.moral_sys,
            self.inv_sys,
            self.dialogue_sys,
            hidden_value_sys=self.hidden_value_sys,
            npc_mem_sys=self.npc_mem_sys,
            skill_sys=self.skill_sys,
            equipment_sys=self.equipment_sys,
            faction_sys=self.faction_sys,
            day_night_sys=self.day_night_sys,
            world_event_sys=None,  # 初始化后设置
        )

        # 动态世界事件系统
        from rpgagent.systems.world_event_system import WorldEventSystem
        self.world_event_sys = WorldEventSystem()
        self.world_event_sys.load_from_meta(meta)
        # 回填到 prompt_builder
        self.prompt_builder.world_event_sys = self.world_event_sys

        # 剧情回放系统
        from rpgagent.systems.replay_system import ReplaySystem
        self.replay_sys = ReplaySystem()

        # 藏宝图/探索系统
        from rpgagent.systems.exploration_system import ExplorationSystem
        self.explore_sys = ExplorationSystem()
        self.explore_sys._register_template_sites()
        self.explore_sys.load_from_meta(meta)

        # 场景触发引擎
        self.scene_trigger_engine = SceneTriggerEngine(self)

        # 获取初始场景
        self.current_scene = self.game_loader.get_first_scene()
        if self.current_scene:
            self.session.update_state(scene_id=self.current_scene.id)

        # AgentScope Agent（用于生成叙事）— 已废弃，改用 DirectLLMClient
        self._agent: Optional[agent.ReActAgent] = None

        # DirectLLMClient（自行管理 memory 和工具调用）
        self._llm_client: Optional[Any] = None

        # GMS 工具集（AgentScope Toolkit）
        self._toolkit: Optional[Any] = None

        # 文生图CG：每个场景/场景ID只自动生成一次
        self._auto_cg_generated_scenes: set = set()

    def _register_npcs_from_loader(self):
        """从 GameLoader 批量注册 NPC 社会关系网络"""
        if not self.game_loader:
            return
        npc_configs = []
        for npc_id, char in self.game_loader.characters.items():
            if char.role in ("npc", "enemy"):
                npc_configs.append({
                    "id": npc_id,
                    "name": char.name,
                    "acquaintances": char.acquaintances or {},
                })
        self.npc_mem_sys.register_npc_with_config(npc_configs)

    def _register_teammates_from_loader(self):
        """从 GameLoader 批量注册可招募队友"""
        if not self.game_loader:
            return
        for npc_id, char in self.game_loader.characters.items():
            # 构造 NPC 数据字典（GameLoader.character 是字符串字典）
            npc_data = {
                "id": npc_id,
                "name": char.name,
                "description": char.description or "",
                "role": char.role,
                "acquaintances": char.acquaintances or {},
            }
            # 如果角色 JSON 中包含队友配置，则注册
            raw_char = self.game_loader._characters_raw.get(npc_id, {})
            npc_data.update(raw_char)
            self.teammate_sys.load_from_npc(npc_id, npc_data)

    def _register_npc_schedules_from_loader(self):
        """从角色 JSON 的 schedule 字段注册 NPC 作息"""
        if not self.game_loader:
            return
        from rpgagent.systems.day_night_cycle import TimePeriod

        PERIOD_MAP = {
            "黎明": TimePeriod.DAWN,
            "上午": TimePeriod.MORNING,
            "正午": TimePeriod.NOON,
            "下午": TimePeriod.AFTERNOON,
            "傍晚": TimePeriod.EVENING,
            "夜晚": TimePeriod.NIGHT,
            "午夜": TimePeriod.MIDNIGHT,
        }

        for npc_id, char in self.game_loader.characters.items():
            raw_char = self.game_loader._characters_raw.get(npc_id, {})
            schedule_data = raw_char.get("schedule", [])
            if not schedule_data:
                continue
            periods = []
            for entry in schedule_data:
                if isinstance(entry, str) and entry in PERIOD_MAP:
                    periods.append(PERIOD_MAP[entry])
                elif isinstance(entry, dict):
                    for k in entry:
                        if k in PERIOD_MAP:
                            periods.append(PERIOD_MAP[k])
            if periods:
                self.day_night_sys.register_npc_schedule(npc_id, periods)

    @property
    def dm(self) -> agent.ReActAgent:
        """懒加载 DM Agent（带 GMS 工具集）- 已废弃，保留接口兼容"""
        if self._agent is None:
            scene = self.get_current_scene()
            sys_prompt = (
                self.prompt_builder.build_system_prompt(scene)
                if scene
                else "你是RPG游戏主持人。"
            )
            from agentscope.formatter._openai_formatter import OpenAIChatFormatter
            from rpgagent.core.gms_tools import create_gms_tools
            from agentscope.tool import Toolkit

            # 创建 Toolkit 并注册 GMS 工具
            self._toolkit = Toolkit()
            tool_funcs = create_gms_tools(self)
            for func in tool_funcs:
                self._toolkit.register_tool_function(func)

            self._agent = agent.ReActAgent(
                name="GameMaster",
                sys_prompt=sys_prompt,
                model=self.model,
                formatter=OpenAIChatFormatter(),
                toolkit=self._toolkit,
                max_iters=10,
                print_hint_msg=False,
            )
        return self._agent

    @property
    def llm_client(self) -> "DirectLLMClient":
        """懒加载 DirectLLMClient（自行管理 memory 和工具调用）"""
        if self._llm_client is None:
            from rpgagent.core.direct_llm_client import DirectLLMClient
            from rpgagent.core.gms_tools import create_gms_tools

            scene = self.get_current_scene()
            sys_prompt = (
                self.prompt_builder.build_system_prompt(scene)
                if scene
                else "你是RPG游戏主持人。"
            )

            # 获取工具定义（OpenAI function calling 格式）
            import inspect
            def get_tool_schema(func):
                """从方法签名提取参数 schema"""
                sig = inspect.signature(func)
                params = {}
                required = []
                for name, p in sig.parameters.items():
                    if name == 'self':
                        continue
                    param_type = 'string'
                    default = None
                    if p.default is not inspect.Parameter.empty:
                        default = p.default
                        if isinstance(default, int):
                            param_type = 'integer'
                        elif isinstance(default, bool):
                            param_type = 'boolean'
                        elif isinstance(default, float):
                            param_type = 'number'
                    else:
                        required.append(name)
                    param_info = {'type': param_type}
                    # 只添加可 JSON 序列化的默认值（排除哨兵对象如 _UNSET_STYLE）
                    if default is not None and isinstance(default, (str, int, float, bool)):
                        param_info['default'] = default
                    params[name] = param_info
                return {
                    'type': 'object',
                    'properties': params,
                    'required': required
                }

            tool_funcs = create_gms_tools(self)
            tool_schemas = []
            for func in tool_funcs:
                tool_schemas.append({
                    "type": "function",
                    "function": {
                        "name": func.__name__,
                        "description": (func.__doc__ or "").strip(),
                        "parameters": get_tool_schema(func),
                    },
                })

            self._llm_client = DirectLLMClient(
                model=self.model,
                system_prompt=sys_prompt,
                tools=tool_schemas,
                max_memory=10,  # 保留最近 10 条对话
                max_turns=10,
            )
        return self._llm_client

    def get_current_scene(self) -> Optional[Scene]:
        return self.current_scene

    def _cleanup_memory_after_reply(self) -> None:
        """
        清理 AgentScope memory 中的 tool 调用记录。

        MiniMax M2.7 在多轮对话后，对 tool_call ID 的解析会失败（2013错误）。
        解决方案：重建 memory，只保留纯文本消息（player/assistant narrative），
        删除所有 tool 消息和带 tool_use 的 assistant 消息。
        """
        import logging
        memory = self.dm.memory
        if not hasattr(memory, 'content'):
            logging.warning("[MEM] Memory has no content attribute, skip cleanup")
            return

        msg_count = len(memory.content)
        if msg_count == 0:
            return

        # 重建 memory：只保留需要保留的消息
        kept_msgs = []
        for msg_item, marks in memory.content:
            # 删除条件：role=tool 或 assistant 且包含 tool_use
            if msg_item.role == "tool":
                continue  # 删除 tool 消息
            if msg_item.role == "assistant":
                # 检查是否包含 tool_use content block
                if msg_item.has_content_blocks("tool_use"):
                    continue  # 删除带 tool_use 的 assistant
                # content 为 None/空 的 assistant 也删除
                if not msg_item.content:
                    continue
                # 如果 content 是空列表
                if isinstance(msg_item.content, list) and len(msg_item.content) == 0:
                    continue
            # 保留其他消息（player, system, 纯文本 assistant）
            kept_msgs.append((msg_item, marks))

        # 清空并重建
        memory.content.clear()
        for msg_item, marks in kept_msgs:
            memory.content.append((msg_item, marks))

        deleted = msg_count - len(memory.content)
        logging.info(f"[MEM] Cleanup: {msg_count} msgs → {len(memory.content)} msgs, deleted {deleted}")

        # 估算 token 数
        total_chars = sum(
            len(str(m.content)) if isinstance(m.content, str) else sum(len(str(b)) for b in m.content)
            for m, _ in memory.content
        )
        est_tokens = total_chars // 3
        logging.info(f"[MEM] Context size: ~{est_tokens} tokens (est ~{total_chars} chars)")

    async def process_input(self, player_input: str) -> Tuple[str, Optional[Dict]]:
        """
        处理玩家输入：
        1. 过滤注入攻击
        2. 检查行动力，耗尽则刷新
        3. 消耗 1 行动力
        4. 构造 user_prompt（附当前状态摘要）
        5. 调用 DirectLLMClient 生成叙事（自行管理 memory 和工具调用）
        6. 解析 GM_COMMAND，更新数值系统
        7. 返回叙事内容
        """
        import logging

        # ── 注入攻击过滤（保护 LLM 不得被 prompt injection 劫持） ──
        from rpgagent.utils.sanitize import sanitize_for_llm
        sanitized = sanitize_for_llm(player_input)
        if not sanitized:
            return "[系统] 检测到违规输入，内容已被拦截。请换一种表达。", None
        player_input = sanitized

        # 重置 CG 生成标记（新回合/新场景开始）
        self.session.scene_cg_generated = False

        scene = self.get_current_scene()
        if not scene:
            return "[系统错误] 当前场景未找到。", None

        # 构造用户输入
        history_summary = self.session.get_history_summary()
        user_prompt = self.prompt_builder.build_user_prompt(player_input, history_summary)

        # 更新 system prompt（DirectLLMClient 自行管理）
        current_sys_prompt = self.prompt_builder.build_system_prompt(scene)
        self.llm_client.update_system_prompt(current_sys_prompt)

        # ── 创建工具执行器 ──
        from rpgagent.core.gms_tools import GMSTools
        tools = GMSTools(self)

        def tool_executor(tool_name: str, args: dict) -> str:
            """执行工具调用"""
            if not hasattr(tools, tool_name):
                return f"[错误] 未知工具: {tool_name}"
            try:
                result = getattr(tools, tool_name)(**args)
                # 提取 ToolResponse 中的文本内容
                if hasattr(result, 'content'):
                    parts = []
                    for block in result.content:
                        if hasattr(block, 'text'):
                            parts.append(block.text)
                        elif isinstance(block, dict):
                            parts.append(str(block.get('text', '')))
                    return "".join(parts) if parts else str(result)
                return str(result)
            except Exception as e:
                return f"[工具执行错误] {str(e)}"

        # ── 调用 DirectLLMClient ──
        # DirectLLMClient 自己管理 memory、工具调用循环、滑动窗口
        # 不再依赖 AgentScope ReActAgent，完全可控
        logging.info(f"[DM] Calling llm_client.reply() for: '{player_input[:50]}'")

        narrative, cmd, all_msgs = await self.llm_client.reply(
            user_input=user_prompt,
            tool_executor=tool_executor,
        )

        ctx_info = self.llm_client.get_context_info()
        logging.info(f"[DM] reply OK: narrative_len={len(narrative)}, context={ctx_info}")

        if not narrative:
            return "[系统] AI暂时无法响应，请稍后重试。", None

        self.session.add_history("gm", narrative)

        # 记录升级前的等级（用于检测是否升级）
        level_before = self.stats_sys.stats.level

        # 解析 GM_COMMAND（DirectLLMClient 已自动提取纯文本 narrative）
        if cmd is None:
            cmd = GMCommandParser.parse(narrative)
        # 从叙事文本中提取数值变化（体力消耗/HP变化/金币/经验）
        narrative_deltas = GMCommandParser.extract_value_deltas(narrative)

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
            elif any(k in combined_text for k in ["交谈", "说话", "打招呼", "问", "答", "聊", "对话"]):
                cmd["action_tag"] = "talk_to_npc"

        # 执行指令
        if cmd:
            # ── 骰点判定 ──────────────────────────────────────────
            # GM 通过 roll 字段发起判定请求（格式：roll: <行动名> | attribute: <属性> | dc: <难度>）
            roll_result = None
            if "roll" in cmd and cmd["roll"].strip():
                try:
                    attr = cmd.get("attribute", "strength").strip()
                    dc_raw = cmd.get("dc", "50").strip()
                    # dc 在 roll_system 中是 1-100 难度阈值
                    dc = int(dc_raw) if dc_raw.isdigit() else 50
                    action_hint = cmd.get("roll", "").strip()
                    roll_result = self.roll_sys.check(
                        attribute_key=attr,
                        base_difficulty=dc,
                        narrative_hint=action_hint,
                    )
                    cmd["_roll_result"] = roll_result
                    # 根据判定结果选择对应叙事（成功/失败分支）
                    roll_block = f"\n🎲 **判定结果**\n{roll_result.description}\n"
                    if roll_result.success:
                        branch_narrative = cmd.get("narrative_success", "")
                    else:
                        branch_narrative = cmd.get("narrative_failure", "")
                    if branch_narrative:
                        narrative = branch_narrative + roll_block
                    else:
                        narrative = narrative + roll_block
                except (ValueError, KeyError) as e:
                    narrative = narrative + f"\n⚠️ 骰点解析失败：{e}\n"

            self._execute_command(cmd, player_input, narrative_deltas)

        # ── 昼夜循环推进 ───────────────────────────────────────
        # 每个行动后推进一档时间（午夜后跨天）
        self.day_night_sys.advance()

        # ── 动态世界事件评估 ───────────────────────────────────
        if self.world_event_sys and self.world_event_sys.is_loaded():
            fired = self.world_event_sys.evaluate(
                day=self.day_night_sys.get_day(),
                period=self.day_night_sys.get_current_period(),
                turn=self.session.turn_count,
                scene_id=self.session.current_scene_id,
                hidden_values=self.hidden_value_sys.get_snapshot() if self.hidden_value_sys else {},
                factions=self.faction_sys.get_all_reputations() if self.faction_sys else {},
                flags=self.session.flags,
            )
            for ev in fired:
                self.world_event_sys.fire_event(
                    event=ev,
                    turn=self.session.turn_count,
                    scene_id=self.session.current_scene_id,
                    day=self.day_night_sys.get_day(),
                    period=self.day_night_sys.get_current_period().value,
                )
                self.session.flags[f"_event_{ev.id}_fired"] = True
                self.session.flags["_pending_events"] = True
            # 清理过期事件
            self.world_event_sys.clean_expired_events(self.session.turn_count)

        self._sync_session()

        # ── 场景触发器检查 ──────────────────────────────────────
        # 在数值更新后检查触发器，满足条件则跳转场景
        triggered_scene = self.scene_trigger_engine.check_and_fire(self.session.current_scene_id)
        if triggered_scene:
            self.session.update_state(scene_id=triggered_scene)
            new_scene = self.game_loader.get_scene(triggered_scene)
            if new_scene:
                self.current_scene = new_scene
                # 将触发场景通知注入叙事上下文（供 DM 感知）
                self.session.flags[f"_triggered_scene"] = triggered_scene
                # 自动生成新场景 CG（线程执行，不阻塞 LLM 响应）
                self._spawn_cg_task(trigger_reason="scene_trigger")
            else:
                # 目标场景不存在，记录警告并保留当前场景
                import logging
                logging.warning(f"[场景切换] 触发器跳转失败：场景 '{triggered_scene}' 不存在，保留当前场景 '{self.current_scene.id if self.current_scene else '未知'}'")
                self.session.update_state(scene_id=self.current_scene.id if self.current_scene else triggered_scene)

        # 立即触发器检查（进入场景后立即执行）
        immediate_scenes = self.scene_trigger_engine.check_immediate(self.session.current_scene_id)
        for imm_scene in immediate_scenes:
            self.session.update_state(scene_id=imm_scene)
            new_scene = self.game_loader.get_scene(imm_scene)
            if new_scene:
                self.current_scene = new_scene
                self.session.flags[f"_triggered_scene"] = imm_scene
                # 自动生成新场景 CG（线程执行，不阻塞 LLM 响应）
                self._spawn_cg_task(trigger_reason="immediate_trigger")
            else:
                import logging
                logging.warning(f"[场景切换] 立即跳转失败：场景 '{imm_scene}' 不存在，保留当前场景 '{self.current_scene.id if self.current_scene else '未知'}'")
                self.session.update_state(scene_id=self.current_scene.id if self.current_scene else imm_scene)

        # ── 剧情回放：记录本回合 ─────────────────────────────────
        if self.replay_sys and self.replay_sys.is_recording():
            roll_result_dict = None
            if cmd and cmd.get("_roll_result"):
                rr = cmd["_roll_result"]
                roll_result_dict = {
                    "action": getattr(rr, "action", "?"),
                    "roll": getattr(rr, "roll", None),
                    "modifier": getattr(rr, "modifier", 0),
                    "total": getattr(rr, "total", None),
                    "dc": getattr(rr, "dc", None),
                    "success": getattr(rr, "success", "?"),
                }
            stats_snap = self.stats_sys.get_snapshot() if self.stats_sys else {}
            inv_snap = self.inv_sys.get_snapshot() if self.inv_sys else {}
            hv_snap = self.hidden_value_sys.get_snapshot() if self.hidden_value_sys else {}
            equipped = {}
            if self.equipment_sys:
                eq = self.equipment_sys.get_equipped()
                if eq:
                    equipped = {slot: (it.get("name") or it.get("id", "")) for slot, it in eq.items() if it}
            # 收集本回合触发的事件 ID
            fired_events = [
                k.replace("_event_", "").replace("_fired", "")
                for k in self.session.flags
                if k.startswith("_event_") and k.endswith("_fired")
            ]
            ending_reached = None
            if self.ending_sys.is_finished():
                final = self.ending_sys.get_final_ending()
                if final:
                    ending_reached = final.id
            self.replay_sys.record_turn(
                turn=self.session.turn_count + 1,  # 回放从 1 开始计数
                player_action=player_input,
                gm_narrative=narrative,
                action_points=stats_snap.get("action_power", 0),
                hp=stats_snap.get("hp", 0),
                hp_max=stats_snap.get("hp_max", 0),
                hidden_values=hv_snap,
                stats=stats_snap,
                inventory=inv_snap.get("items", []),
                equipped=equipped,
                roll_result=roll_result_dict,
                scene_id=self.session.current_scene_id or "",
                triggered_events=fired_events,
                ending_reached=ending_reached,
            )

        return narrative, cmd

    def _execute_command(self, cmd: Dict[str, Any], player_input: str = "", narrative_deltas: Optional[Dict[str, int]] = None) -> Dict[str, int]:
        """执行 GM_COMMAND 指令，返回隐藏数值变化量（vid → delta）"""
        action = cmd.get("action", "narrative")

        # ── 行动力消耗 ───────────────────────────
        # 消耗行动力的行为类型（非叙事行动本身也需要消耗）
        ap_cost_actions = {"narrative", "combat", "choice", "skill_use", "item_use", "explore"}
        if action in ap_cost_actions:
            # 预设快捷行动消耗1AP，自由行动消耗2AP
            preset_keywords = ["环顾四周", "与NPC交谈", "接近目标", "仔细调查", "观察周围", "检查"]
            is_preset = any(kw in player_input for kw in preset_keywords)
            ap_cost = 1 if is_preset else 2
            import logging
            logging.info(f"[AP] player_input='{player_input[:30]}', is_preset={is_preset}, ap_cost={ap_cost}")
            if not self.stats_sys.use_ap(ap_cost):
                # 行动力不足，尝试消耗较少AP
                if ap_cost > 1 and self.stats_sys.use_ap(1):
                    pass  # 允许用1AP执行
                else:
                    self.session.add_history("system", "【行动力耗尽】你感到力不从心，只能勉强观察周围环境。")
                    self.session.flags["_ap_exhausted"] = True
                    return

        # ── 叙事数值同步：将GM叙事中描述的体力/HP/金币/经验变化应用到游戏状态 ──
        # cmd 中的显式 delta 优先于叙事解析（cmd 来自 LLM 的结构化指令，更可靠）
        merged_deltas: Dict[str, int] = dict(narrative_deltas) if narrative_deltas else {}
        for field in ("stamina", "hp", "gold", "exp"):
            if field in cmd:
                try:
                    explicit = int(cmd[field])
                    merged_deltas[field] = explicit
                except ValueError:
                    pass
        # 应用合并后的数值变化
        for field, delta in merged_deltas.items():
            if delta == 0:
                continue
            if field == "stamina":
                self.stats_sys.modify("stamina", delta)
            elif field == "hp":
                self.stats_sys.modify("hp", delta)
            elif field == "gold":
                self.stats_sys.modify("gold", delta)
            elif field == "exp":
                self.stats_sys.modify("exp", delta)

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

            # ── NPC 长记忆：所有 NPC 记录玩家行为 ──
            npc_ids = [npc_id for npc_id, ch in self.game_loader.characters.items() if ch.role in ("npc", "enemy")]
            if npc_ids and player_input:
                for npc_id in npc_ids:
                    self.npc_mem_sys.record_player_action(
                        npc_id=npc_id,
                        action_description=player_input,
                        scene_id=self.session.current_scene_id,
                        turn=self.session.turn_count,
                        action_tag=action_tag,
                    )

        # 场景切换指令（next_scene 字段在任何 action 类型下均可触发）
        next_scene = cmd.get("next_scene")
        if next_scene:
            self.session.update_state(scene_id=next_scene)
            new_scene = self.game_loader.get_scene(next_scene)
            if new_scene:
                self.current_scene = new_scene
            else:
                # 目标场景不存在，记录警告并保留当前场景
                import logging
                logging.warning(f"[场景切换] GM指令跳转失败：场景 '{next_scene}' 不存在，保留当前场景 '{self.current_scene.id if self.current_scene else '未知'}'")
                self.session.update_state(scene_id=self.current_scene.id if self.current_scene else next_scene)

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

        # ── 技能学习指令 ───────────────────────────────────
        # skill_learn: 学习/升级技能（消耗技能点）
        if "skill_learn" in cmd:
            skill_id = cmd.get("skill_learn", "").strip()
            try:
                ranks = int(cmd.get("skill_ranks", "1"))
            except ValueError:
                ranks = 1
            if skill_id:
                success = self.skill_sys.learn_skill(skill_id, ranks)
                if not success:
                    skill = self.skill_sys.book.get(skill_id)
                    current = self.skill_sys.learned.get(skill_id, 0)
                    if skill and current >= skill.max_rank:
                        self.session.flags["_skill_msg"] = f"「{skill.name}」已达最高级"
                    elif self.skill_sys.skill_points < ranks:
                        self.session.flags["_skill_msg"] = f"技能点不足，当前剩余{self.skill_sys.skill_points}点"
                    else:
                        self.session.flags["_skill_msg"] = f"无法学习技能「{skill_id}」"
                else:
                    skill = self.skill_sys.book.get(skill_id)
                    new_rank = self.skill_sys.learned.get(skill_id, 0)
                    self.session.flags["_skill_msg"] = (
                        f"学会「{skill.name}」{new_rank}级（消耗{ranks}点技能点，剩余{self.skill_sys.skill_points}点）"
                        if skill else f"学会「{skill_id}」至{new_rank}级"
                    )

        # skill_points_grant: 奖励技能点（如升级奖励）
        if "skill_points_grant" in cmd:
            try:
                amount = int(cmd["skill_points_grant"])
                self.skill_sys.add_skill_points(amount)
                self.session.flags["_skill_msg"] = f"获得{amount}点技能点（现有{self.skill_sys.skill_points}点）"
            except ValueError:
                pass

        # skill_reset: 重置所有技能（退还技能点）
        if "skill_reset" in cmd and cmd.get("skill_reset", "").lower() in ("1", "true", "yes"):
            total_spent = sum(
                self.skill_sys.book.get(sid).max_rank
                for sid, rank in self.skill_sys.learned.items()
                if self.skill_sys.book.get(sid)
            )
            self.skill_sys.learned.clear()
            self.skill_sys.add_skill_points(total_spent)
            self.session.flags["_skill_msg"] = f"技能已重置，返还{total_spent}点技能点"

        # ── 装备获取指令 ─────────────────────────────────────
        # grant_equipment: 战利品/奖励直接发放装备
        if "grant_equipment" in cmd:
            equip_id = cmd.get("grant_equipment", "").strip()
            if equip_id:
                from rpgagent.systems.equipment_system import get_template_equipment
                equip = get_template_equipment(equip_id)
                if equip:
                    result = self.acquisition_sys.grant_equipment(equip)
                    self.session.flags["_loot_item"] = result
                    self.session.flags["_loot_message"] = (
                        f"【获得装备】{result['rarity_display']}「{equip.name}」"
                        f"（{equip.slot}槽）"
                        f"{' 技能：' + equip.stats.skill_id if equip.stats.skill_id else ''}"
                    )
                    # 自动装备（如果对应槽位为空）
                    current = self.equipment_sys.equipped.get(equip.slot)
                    if current is None:
                        eq_result = self.equipment_sys.equip(equip)
                        self.session.flags["_loot_message"] += f"\n已自动装备「{equip.name}」到「{equip.slot}」槽。"
                        # 更新 bonus 到 stats
                        self.stats_sys.recalculate_from_equipment(self.equipment_sys.total_bonus)
                    else:
                        self.session.flags["_loot_message"] += f"\n「{equip.slot}」槽已有「{current.name}」，可输入「换装 {equip.name}」替换。"

        # open_chest: 开启宝箱
        if "open_chest" in cmd:
            chest_id = cmd.get("open_chest", "").strip()
            if chest_id:
                result = self.acquisition_sys.open_chest(chest_id)
                self.session.flags["_chest_result"] = result
                if result["success"]:
                    detail = result["detail"]
                    msgs = []
                    for item in detail["items"]:
                        grant = self.acquisition_sys.grant_equipment(item)
                        self.session.flags["_loot_item"] = grant
                        msgs.append(f"{grant['rarity_display']}「{item.name}」")
                        # 自动装备
                        current = self.equipment_sys.equipped.get(item.slot)
                        if current is None:
                            self.equipment_sys.equip(item)
                    gold = detail.get("gold", 0)
                    item_str = "、".join(msgs) if msgs else "空空如也"
                    gold_str = f"，金币 +{gold}" if gold > 0 else ""
                    self.session.flags["_loot_message"] = (
                        f"【开启宝箱「{detail['chest_name']}」】\n"
                        f"获得了：{item_str}{gold_str}"
                    )
                    if gold > 0:
                        self.stats_sys.modify("gold", gold)
                else:
                    self.session.flags["_loot_message"] = f"【宝箱】{result['message']}"

        # npc_trade / buy_equipment: NPC 交易（展示商品）
        if "npc_trade" in cmd or "buy_equipment" in cmd:
            npc_id = cmd.get("npc_trade", "") or cmd.get("buy_equipment", "")
            npc_id = npc_id.strip() if npc_id else ""
            if npc_id:
                wares = self.acquisition_sys.get_merchant_wares(npc_id)
                self.session.flags["_merchant_wares"] = wares
                self.session.flags["_merchant_id"] = npc_id

        # ── 队友系统指令 ─────────────────────────────────────
        # teammate_recruit: 招募队友
        if "teammate_recruit" in cmd:
            teammate_id = cmd.get("teammate_recruit", "").strip()
            if teammate_id:
                result = self.teammate_sys.recruit(teammate_id)
                self.session.flags["_teammate_recruit"] = result

        # teammate_dismiss: 移除队友
        if "teammate_dismiss" in cmd:
            teammate_id = cmd.get("teammate_dismiss", "").strip()
            if teammate_id:
                dismissed = self.teammate_sys.dismiss(teammate_id)
                profile = self.teammate_sys.get_profile(teammate_id)
                name = profile.name if profile else teammate_id
                self.session.flags["_teammate_dismiss"] = {
                    "teammate_id": teammate_id,
                    "permanently_left": dismissed,
                    "message": f"「{name}」离队了。" if dismissed else f"「{name}」的忠诚度下降了。",
                }

        # teammate_loyalty_delta: 修改队友忠诚度
        if "teammate_loyalty_delta" in cmd:
            try:
                teammate_id = cmd.get("teammate_id", "").strip()
                delta = int(cmd.get("teammate_loyalty_delta", "0"))
                if teammate_id:
                    new_val = self.teammate_sys.modify_loyalty(teammate_id, delta)
                    self.session.flags["_teammate_loyalty_msg"] = f"队友忠诚度变为 {new_val}/100"
            except ValueError:
                pass

        # 主动作力消耗
        if "stat_delta" in cmd and "stat_name" in cmd:
            try:
                stat = cmd["stat_name"]
                delta = int(cmd["stat_delta"])
                # 如果是经验值变化，调用 gain_exp 处理升级逻辑
                if stat == "exp":
                    level_before = self.stats_sys.stats.level
                    result = self.stats_sys.gain_exp(delta)
                    for new_level in result.get("leveled_up", []):
                        self.skill_sys.add_skill_points(2)
                        self.session.flags["_skill_msg"] = (
                            f"🎉 升级至 Lv.{new_level}！获得2点技能点（现有{self.skill_sys.skill_points}点）"
                        )
                else:
                    self.stats_sys.modify(stat, delta)
            except ValueError:
                pass

        # ── 成就系统指令 ─────────────────────────────────────
        # achievement_unlock: 主动授予成就
        achievement_id = cmd.get("achievement_unlock", "").strip()
        if achievement_id:
            result = self.achievement_sys.unlock(
                achievement_id=achievement_id,
                turn=self.session.turn_count,
                scene_id=self.session.current_scene_id,
            )
            if result:
                self.session.flags["_achievement_unlocked"] = achievement_id

        # ── 多结局系统指令 ───────────────────────────────────
        # trigger_ending: 触发终局（指定结局ID）
        trigger_ending_id = cmd.get("trigger_ending", "").strip()
        if trigger_ending_id and not self.ending_sys.is_finished():
            ending = self.ending_sys.trigger_ending(
                ending_id=trigger_ending_id,
                turn=self.session.turn_count,
                scene_id=self.session.current_scene_id,
            )
            if ending:
                self.session.flags["_ending_triggered"] = {
                    "id": ending.id,
                    "name": ending.name,
                    "type": ending.ending_type,
                }
                # 游戏结束时结算成就
                self._evaluate_achievements()
            else:
                self.session.flags["_ending_triggered"] = None

        # trigger_final_ending: 触发终局（自动评估最高优先级结局）
        if cmd.get("trigger_final_ending", "").strip().lower() in ("1", "true", "yes"):
            if not self.ending_sys.is_finished():
                result = self.ending_sys.evaluate(game_master=self)
                if result:
                    self.ending_sys.trigger_ending(
                        ending_id=result.ending_id,
                        turn=self.session.turn_count,
                        scene_id=self.session.current_scene_id,
                    )
                    self.session.flags["_ending_triggered"] = {
                        "id": result.ending.id,
                        "name": result.ending.name,
                        "type": result.ending.ending_type,
                    }
                    # 游戏结束时结算成就
                    self._evaluate_achievements()
                else:
                    self.session.flags["_ending_triggered"] = None

        # ── 阵营声望系统指令 ───────────────────────────────────
        # faction_action: 执行阵营行动（根据 action_tag 映射到各阵营声望变化）
        faction_action_id = cmd.get("faction_action", "").strip()
        if faction_action_id:
            results = self.faction_sys.execute_faction_action(
                action_id=faction_action_id,
                scene_id=self.session.current_scene_id,
                turn=self.session.turn_count,
            )
            if results:
                parts = []
                for fid, new_val in results.items():
                    delta = new_val - (self.faction_sys.get_reputation(fid) - (results.get(fid, 0) - (next((d for d in self.faction_sys._history[-10:] if d["faction_id"] == fid), {}) or {}).get("delta", 0)))
                # 简化为直接展示变化
                for fid in results:
                    info = self.faction_sys.get_reputation_level_info(fid)
                    parts.append(f"「{info['faction_name']}」{info['value']}（{info['level']}）")
                if parts:
                    self.session.flags["_faction_changes"] = parts

        # faction_join: 玩家加入阵营
        join_faction_id = cmd.get("faction_join", "").strip()
        if join_faction_id:
            ok = self.faction_sys.join_faction(join_faction_id)
            if ok:
                faction = self.faction_sys._factions.get(join_faction_id)
                self.session.flags["_faction_join"] = f"你正式加入了「{faction.name if faction else join_faction_id}」"
            else:
                self.session.flags["_faction_join"] = f"无法加入「{join_faction_id}」（该阵营不可加入或不存在）"

        # faction_leave: 玩家离开/被驱逐阵营
        leave_faction_id = cmd.get("faction_leave", "").strip()
        if leave_faction_id:
            ok = self.faction_sys.leave_faction(leave_faction_id)
            if ok:
                faction = self.faction_sys._factions.get(leave_faction_id)
                self.session.flags["_faction_leave"] = f"你退出了「{faction.name if faction else leave_faction_id}」"
            else:
                self.session.flags["_faction_leave"] = f"你并不属于「{leave_faction_id}」"

        # faction_reputation_delta: 直接调整某阵营声望
        if "faction_reputation_delta" in cmd and "faction_id" in cmd:
            try:
                faction_id = cmd.get("faction_id", "").strip()
                delta = int(cmd.get("faction_reputation_delta", "0"))
                if faction_id and delta != 0:
                    new_val = self.faction_sys.modify_reputation(
                        faction_id=faction_id,
                        delta=delta,
                        source="gm_command",
                        scene_id=self.session.current_scene_id,
                        turn=self.session.turn_count,
                    )
                    info = self.faction_sys.get_reputation_level_info(faction_id)
                    self.session.flags["_faction_reputation_msg"] = (
                        f"「{info['faction_name']}」声望变为 {new_val}（{info['level']}）"
                    )
            except ValueError:
                pass

        # ── 昼夜循环系统指令 ───────────────────────────────────
        # advance_time: 前进一档时间（如等待、观察等不触发完整回合的动作）
        if cmd.get("advance_time", "").strip().lower() in ("1", "true", "yes"):
            self.day_night_sys.advance()
            self.session.add_history(
                "system",
                f"【时间流逝】{self.day_night_sys.get_time_string()}"
            )

        # rest / overnight: 休息/过夜，跳到次日黎明
        if cmd.get("rest", "").strip().lower() in ("1", "true", "yes", "overnight"):
            self.day_night_sys.rest()
            self.stats_sys.refresh_ap()
            if self.hidden_value_sys:
                decay_results = self.hidden_value_sys.tick_all(self.session.turn_count)
                if decay_results:
                    self.session.flags["_hv_decay"] = decay_results
            self.session.add_history(
                "system",
                f"【过夜休息】第{self.day_night_sys.get_day()}天开始了，行动力已恢复。"
            )

        # set_period: 手动设置当前时间档位（进入室内切场景等）
        set_period_val = cmd.get("set_period", "").strip()
        if set_period_val:
            from rpgagent.systems.day_night_cycle import TimePeriod
            try:
                self.day_night_sys.set_period(TimePeriod(set_period_val))
                self.session.add_history(
                    "system",
                    f"【时间变更】现在是{self.day_night_sys.get_time_string()}"
                )
            except ValueError:
                pass

        # ── 藏宝图/探索系统指令 ─────────────────────────────────
        # grant_clue: 给予玩家一条藏宝线索
        grant_clue_id = cmd.get("grant_clue", "").strip()
        if grant_clue_id:
            site = self.explore_sys.grant_clue(grant_clue_id)
            if site:
                self.session.flags["_clue_granted"] = {
                    "id": site.id,
                    "name": site.name,
                    "clue_text": site.clue_text,
                    "location_hint": site.location_hint,
                }
            else:
                self.session.flags["_clue_granted"] = None

        # explore: 玩家对指定宝藏进行探索
        explore_site_id = cmd.get("explore", "").strip()
        if explore_site_id:
            result = self.explore_sys.explore(
                site_id=explore_site_id,
                stats_sys=self.stats_sys,
                skill_sys=self.skill_sys,
                turn=self.session.turn_count,
            )
            # 发放奖励
            if result.success:
                for reward in result.rewards_given:
                    if reward.type == "gold":
                        self.stats_sys.modify("gold", reward.quantity)
                    elif reward.type == "equipment" and reward.id:
                        from rpgagent.systems.equipment_system import get_template_equipment
                        equip = get_template_equipment(reward.id)
                        if equip:
                            grant_result = self.acquisition_sys.grant_equipment(equip)
                            self.session.flags["_loot_item"] = grant_result
                            self.session.flags["_loot_message"] = (
                                f"【探索获得】{grant_result['rarity_display']}「{equip.name}」"
                            )
                            current_eq = self.equipment_sys.equipped.get(equip.slot)
                            if current_eq is None:
                                self.equipment_sys.equip(equip)
                                self.session.flags["_loot_message"] += f"\n已自动装备「{equip.name}」"
                    elif reward.type == "intel" and reward.id:
                        # intel 奖励自动注册为新线索
                        next_site = self.explore_sys.grant_clue(reward.id)
                        if next_site:
                            self.session.flags["_clue_granted"] = {
                                "id": next_site.id,
                                "name": next_site.name,
                                "clue_text": next_site.clue_text,
                                "location_hint": next_site.location_hint,
                                "from_intel": True,
                            }

            # 探索结果写入 flags
            self.session.flags["_explore_result"] = {
                "site_id": explore_site_id,
                "site_name": result.site.name if result.site else explore_site_id,
                "success": result.success,
                "roll": result.roll,
                "modifier": result.modifier,
                "total": result.total,
                "dc": result.dc,
                "rewards": [
                    {"type": r.type, "name": r.name, "quantity": r.quantity}
                    for r in result.rewards_given
                ],
                "has_new_clue": result.new_clue is not None,
            }

        # craft_skill_fragment: 消耗碎片兑换技能
        if cmd.get("craft_skill_fragment", "").strip().lower() in ("1", "true", "yes"):
            skill_id = self.explore_sys.consume_fragments_for_skill()
            if skill_id:
                self.session.flags["_skill_fragment_crafted"] = skill_id
            else:
                self.session.flags["_skill_fragment_crafted"] = None

        # 成就仅在游戏结束时结算（移除每回合自动评估）
        # _evaluate_achievements() 在结局触发时由 trigger_ending / trigger_final_ending 调用

    def _evaluate_achievements(self) -> None:
        """每回合自动评估成就，解锁后写入 session.flags 供叙事层感知"""
        visited = list(getattr(self.session, "visited_scenes", set()))
        visited.append(self.session.current_scene_id)

        combat_count = getattr(self.session, "combat_count", 0)
        skill_count = len(self.skill_sys.learned) if self.skill_sys else 0
        relations = {
            npc_id: info.get("value", 0)
            for npc_id, info in self.dialogue_sys.get_all_relations().items()
        }
        hv_snapshot = (
            self.hidden_value_sys.get_snapshot() if self.hidden_value_sys else {}
        )

        result = self.achievement_sys.evaluate(
            turn_count=self.session.turn_count,
            scene_id=self.session.current_scene_id,
            stats=self.stats_sys.get_snapshot() if self.stats_sys else {},
            hidden_values=hv_snapshot,
            skill_count=skill_count,
            combat_count=combat_count,
            visited_scenes=visited,
            relations=relations,
        )

        for ua in result.newly_unlocked:
            self.session.flags["_achievement_unlocked"] = ua.narrative

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
            flags={
                "_npc_memories": self.npc_mem_sys.get_snapshot(),
                "_teammates": self.teammate_sys.get_snapshot(),
                "_achievements": self.achievement_sys.get_snapshot(),
                "_factions": self.faction_sys.get_snapshot(),
                "_day_night": self.day_night_sys.get_snapshot(),
                "_endings": self.ending_sys.get_snapshot(),
                "_world_events": self.world_event_sys.get_snapshot() if self.world_event_sys else {},
                "_exploration": self.explore_sys.get_snapshot(),
            },
        )
        # 同步昼夜循环状态到 session
        self.session.day = self.day_night_sys.get_day()
        self.session.period = self.day_night_sys.get_current_period().value
        # 同步技能数据
        self.session.skill_points = self.skill_sys.skill_points
        self.session.learned_skills = self.skill_sys.learned.copy()
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

        # ── 战斗统计追踪 ───────────────────────────
        # 标记本回合为战斗回合（用于 stats API 聚合）
        self.session.flags["_combat_count"] = self.session.flags.get("_combat_count", 0) + 1
        # 追踪伤害数据
        dmg_dealt = getattr(result, "damage_dealt", 0)
        dmg_taken = getattr(result, "damage_taken", 0)
        self.session.flags["_total_damage_dealt"] = self.session.flags.get("_total_damage_dealt", 0) + dmg_dealt
        self.session.flags["_total_damage_taken"] = self.session.flags.get("_total_damage_taken", 0) + dmg_taken
        if killed:
            self.session.flags["_kills"] = self.session.flags.get("_kills", 0) + 1
        if result.damage_taken > 0 and self.stats_sys.stats.hp <= 0:
            self.session.flags["_deaths"] = self.session.flags.get("_deaths", 0) + 1
        # 胜负判断（击杀敌人 = 胜，受到致命伤害 = 负）
        if killed and result.damage_taken > 0:
            self.session.flags["_combat_losses"] = self.session.flags.get("_combat_losses", 0) + 1
        elif killed:
            self.session.flags["_combat_wins"] = self.session.flags.get("_combat_wins", 0) + 1
        elif result.damage_taken > 0 and self.stats_sys.stats.hp <= 0:
            self.session.flags["_combat_losses"] = self.session.flags.get("_combat_losses", 0) + 1

        # 战斗结束后自动生成场景 CG（线程执行，不阻塞 LLM 响应）
        if killed or result.damage_taken > 0:
            self._spawn_cg_task(trigger_reason="combat")

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
        learned = self.skill_sys.list_learned()
        ap = stats.get("action_power", 0)
        max_ap = stats.get("max_action_power", 3)
        ap_bar = "●" * ap + "○" * (max_ap - ap)
        skill_summary = (
            f"技能点 {self.skill_sys.skill_points}点 | "
            f"已学技能: {', '.join(s['name'] for s in learned) if learned else '无'}"
        )
        equipped = self.equipment_sys.get_equipped()
        equip_summary = ", ".join(
            f"{v['name']}" for v in equipped.values() if v
        ) or "无"
        teammate_summary = self.teammate_sys.get_status_summary()
        status_lines = [
            f"【状态】HP {stats['hp']}/{stats['max_hp']} | "
            f"体力 {stats['stamina']}/{stats['max_stamina']} | "
            f"行动力 {ap_bar}（{ap}/{max_ap}） | "
            f"道德债务 {moral['level']}（{moral['debt']}分） | "
            f"装备: {equip_summary} | "
            f"场景 {scene_title}",
            f"{skill_summary}",
            f"【队友】{teammate_summary}",
        ]
        return "\n".join(status_lines)

    def reset_dm(self) -> None:
        """重置 DM Agent（换场/重开时调用）"""
        self._agent = None
        self.scene_trigger_engine.reset()

    # ── 文生图 CG 自动生成（Phase 2）────────────────────────

    def _auto_generate_scene_cg(self, trigger_reason: str = "scene_change") -> None:
        """
        在关键叙事节点自动生成场景 CG。
        每个 scene_id 只自动生成一次（防止重复调用 API 浪费配额）。

        触发时机：
        - 场景切换后（进入新场景第一回合）
        - 战斗胜利/失败结算
        - 重要剧情节点（LLM 通过 gm_command 触发）
        - 每幕结尾（LLM 下发 next_scene 时）

        API 优先级：MINIMAX_API_KEY（主） > TONGYI_API_KEY（备）
        """
        import os

        scene = self.get_current_scene()
        if not scene:
            return

        scene_id = scene.id
        # 已生成过则跳过
        if scene_id in self._auto_cg_generated_scenes:
            return

        # 优先 MiniMax（与 openclaw 共用 key），备选通义万相
        api_key = os.getenv("MINIMAX_API_KEY", "") or os.getenv("TONGYI_API_KEY", "")
        if not api_key:
            return

        # 提取场景中出现的角色外观描述
        characters = []
        for npc_id, char in self.game_loader.characters.items():
            appearance = getattr(char, "appearance", "") or ""
            if appearance:
                characters.append({"name": char.name, "appearance": appearance})

        # 读取 CG 配置（优先级：scene.cg_config > meta.cg_scenes）
        # context_loader 已将 per-scene .cg.yaml 加载到 scene.cg_config
        scene_config: dict = {}
        if scene.cg_config:
            scene_config = scene.cg_config
        # 回退到 meta.cg_scenes（兼容旧格式）
        if not scene_config:
            cg_config = getattr(self.game_loader.meta, "cg_scenes", {}) or {}
            scene_config = cg_config.get(scene_id) or {}

        trigger_type = scene_config.get("trigger", "auto")
        if trigger_type == "manual":
            # 该场景配置为手动触发，不自动生成
            return

        style = scene_config.get("style", "fantasy illustration, dark atmosphere, high quality")
        # 战斗场景用不同风格
        if "combat" in trigger_reason or "battle" in trigger_reason:
            style = "epic battle scene, dramatic lighting, high quality"

        # 优先 MiniMax，备选 Tongyi
        provider = "minimax" if os.getenv("MINIMAX_API_KEY") else "tongyi"

        try:
            from rpgagent.systems.image_generator import make_generator
            import asyncio

            gen = make_generator(provider=provider, api_key=api_key)

            async def _gen():
                img_path = await gen.generate(
                    scene_id=scene_id,
                    scene_content=scene.content,
                    characters=characters,
                    style=style,
                )
                await gen.close()
                return img_path

            img_path = asyncio.run(_gen())

            self.session.scene_cg_path = img_path
            self.session.scene_cg_generated = True
            self._auto_cg_generated_scenes.add(scene_id)
            # 记录 CG 历史
            self.session.cg_history.append({
                "scene_id": scene_id,
                "scene_title": scene.title if scene else scene_id,
                "cg_path": img_path,
                "trigger": trigger_reason,
            })
        except Exception:
            # CG 生成失败不打断叙事，吞掉异常
            pass

    def _generate_scene_ending_cg(self) -> None:
        """
        在每幕结尾生成 CG。
        由 LLM 下发 next_scene 命令时触发。
        """
        self._spawn_cg_task(trigger_reason="scene_ending")

    def _spawn_cg_task(self, trigger_reason: str = "manual") -> None:
        """
        在独立线程中生成 CG，完全不阻塞调用方。
        MiniMax API 响应可能需要 10-60 秒，线程执行确保 WS 不超时。
        """
        import threading

        def _bg():
            try:
                self._auto_generate_scene_cg(trigger_reason=trigger_reason)
            except Exception:
                # CG 生成失败静默，不影响游戏流程
                pass

        t = threading.Thread(target=_bg, daemon=True)
        t.start()

    def new_game_plus(self, preserve: Optional[list[str]] = None) -> "Scene":
        """
        New Game+：以新游戏开局，可选择性保留进度。

        Args:
            preserve: 要保留的进度列表，可选值：
                - "skills"       保留已学会的技能和剩余技能点
                - "inventory"    保留背包物品
                - "relations"    保留 NPC 关系
                - "equipment"    保留已装备的物品
                - "hidden_values" 保留隐藏数值（如道德债务等级）

        Returns:
            新的初始场景对象
        """
        preserve = preserve or []
        p = set(preserve)

        # ── 1. 提取需要保留的状态 ─────────────────────────
        preserved_skills = {}
        preserved_skill_points = 0
        if "skills" in p:
            preserved_skills = dict(self.skill_sys.list_learned())
            preserved_skill_points = self.skill_sys.skill_points

        preserved_inventory = []
        if "inventory" in p:
            preserved_inventory = [item.copy() for item in self.inv_sys.get_snapshot().get("items", [])]

        preserved_relations = {}
        if "relations" in p:
            preserved_relations = dict(self.dialogue_sys.get_all_relations())

        preserved_equipment = {}
        if "equipment" in p:
            preserved_equipment = dict(self.equipment_sys.get_equipped())

        preserved_hidden = {}
        if "hidden_values" in p and self.hidden_value_sys:
            preserved_hidden = self.hidden_value_sys.get_snapshot()

        # ── 2. 创建新的 Session ────────────────────────────
        from .session import Session
        new_session = Session(
            game_id=self.game_id,
            player_name=self.session.player_name,
            initial_scene_id="start",
        )
        self.session = new_session

        # ── 3. 重新初始化所有系统（使用初始化参数）──────────
        self.stats_sys = StatsSystem()
        self.moral_sys = MoralDebtSystem()
        self.inv_sys = InventorySystem()
        self.dialogue_sys = DialogueSystem()
        self.skill_sys = SkillSystem()
        self.equipment_sys = EquipmentSystem()

        # 昼夜循环重置
        from rpgagent.systems.day_night_cycle import DayNightCycle
        self.day_night_sys = DayNightCycle()
        self._register_npc_schedules_from_loader()
        # 更新 PromptBuilder 中的引用
        self.prompt_builder.day_night_sys = self.day_night_sys

        # 多结局系统重置
        from rpgagent.systems.ending_system import EndingSystem
        self.ending_sys = EndingSystem()
        self.ending_sys.load_from_meta(self.game_loader.meta, game_id=self.game_id)
        self.ending_sys.bind_game_master(self)

        # 隐藏数值系统
        hv_configs = getattr(self.game_loader.meta, "hidden_values", []) or []
        hv_action_map = getattr(self.game_loader.meta, "hidden_value_actions", {}) or {}
        self.hidden_value_sys = None
        if hv_configs:
            self.hidden_value_sys = HiddenValueSystem(
                configs=hv_configs,
                action_map=hv_action_map,
            )

        # NPC 长记忆
        self.npc_mem_sys = NpcMemorySystem()
        self._register_npcs_from_loader()
        self._register_teammates_from_loader()

        # 骰点系统
        self.roll_sys = RollSystem(self.stats_sys, self.skill_sys, self.equipment_sys)

        # ── 4. 应用保留的进度 ─────────────────────────────
        if "skills" in p and preserved_skills:
            for skill_id, rank in preserved_skills.items():
                self.skill_sys.learn_skill(skill_id)
                for _ in range(rank - 1):
                    try:
                        self.skill_sys.upgrade_skill(skill_id)
                    except Exception:
                        pass
            self.skill_sys.skill_points = preserved_skill_points

        if "inventory" in p and preserved_inventory:
            for item in preserved_inventory:
                self.inv_sys.add_item(item.get("name", "unknown"), item)

        if "relations" in p and preserved_relations:
            for npc_id, rel_data in preserved_relations.items():
                self.dialogue_sys.set_relation(
                    npc_id,
                    rel_data.get("value", 0),
                    rel_data.get("level", "陌生"),
                )

        if "equipment" in p and preserved_equipment:
            for slot, item in preserved_equipment.items():
                if item:
                    self.equipment_sys.equip(item.get("item_id", ""), slot, item)

        if "hidden_values" in p and preserved_hidden:
            if self.hidden_value_sys:
                self.hidden_value_sys.load_snapshot(preserved_hidden)

        # ── 5. 重置 DM ────────────────────────────────────
        self.reset_dm()
        # 重置 CG 生成记录（新游戏不应复用旧 CG）
        self._auto_cg_generated_scenes.clear()

        # ── 6. 切换到初始场景 ─────────────────────────────
        self.current_scene = self.game_loader.get_first_scene()
        if self.current_scene:
            self.session.update_state(scene_id=self.current_scene.id)

        return self.current_scene
