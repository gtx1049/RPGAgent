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
        )

        # 场景触发引擎
        self.scene_trigger_engine = SceneTriggerEngine(self)

        # 获取初始场景
        self.current_scene = self.game_loader.get_first_scene()
        if self.current_scene:
            self.session.update_state(scene_id=self.current_scene.id)

        # AgentScope Agent（用于生成叙事）
        self._agent: Optional[agent.ReActAgent] = None

        # GMS 工具集（AgentScope Toolkit）
        self._toolkit: Optional[Any] = None

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

    @property
    def dm(self) -> agent.ReActAgent:
        """懒加载 DM Agent（带 GMS 工具集）"""
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

    def get_current_scene(self) -> Optional[Scene]:
        return self.game_loader.get_scene(self.session.current_scene_id)

    def process_input(self, player_input: str) -> Tuple[str, Optional[Dict]]:
        """
        处理玩家输入：
        1. 检查行动力，耗尽则刷新
        2. 消耗 1 行动力
        3. 构造 user_prompt（附当前状态摘要）
        4. 调用 AgentScope DM Agent 生成叙事
        5. 解析 GM_COMMAND，更新数值系统
        6. 返回叙事内容
        """
        # ── 行动力检查 ──────────────────────────────
        # 如果行动力为0，说明上一轮已耗尽，自动刷新
        if self.stats_sys.get("action_power") <= 0:
            self.stats_sys.refresh_ap()
            self.session.add_history("system", "【回合开始】行动力已刷新。")

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

        # 记录升级前的等级（用于检测是否升级）
        level_before = self.stats_sys.stats.level

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
                    # 将判定结果嵌入叙事
                    roll_block = f"\n🎲 **判定结果**\n{roll_result.description}\n"
                    narrative = narrative + roll_block
                except (ValueError, KeyError) as e:
                    narrative = narrative + f"\n⚠️ 骰点解析失败：{e}\n"

            self._execute_command(cmd, player_input)

        self._sync_session()

        # ── 场景触发器检查 ──────────────────────────────────────
        # 在数值更新后检查触发器，满足条件则跳转场景
        triggered_scene = self.scene_trigger_engine.check_and_fire(self.session.current_scene_id)
        if triggered_scene:
            self.session.update_state(scene_id=triggered_scene)
            self.current_scene = self.game_loader.get_scene(triggered_scene)
            # 将触发场景通知注入叙事上下文（供 DM 感知）
            self.session.flags[f"_triggered_scene"] = triggered_scene

        # 立即触发器检查（进入场景后立即执行）
        immediate_scenes = self.scene_trigger_engine.check_immediate(self.session.current_scene_id)
        for imm_scene in immediate_scenes:
            self.session.update_state(scene_id=imm_scene)
            self.current_scene = self.game_loader.get_scene(imm_scene)
            self.session.flags[f"_triggered_scene"] = imm_scene

        return narrative, cmd

    def _execute_command(self, cmd: Dict[str, Any], player_input: str = ""):
        """执行 GM_COMMAND 指令"""
        action = cmd.get("action", "narrative")

        # ── 行动力消耗 ───────────────────────────
        # 消耗行动力的行为类型（非叙事行动本身也需要消耗）
        ap_cost_actions = {"narrative", "combat", "choice", "skill_use", "item_use", "explore"}
        if action in ap_cost_actions:
            if not self.stats_sys.use_ap(1):
                # 行动力耗尽，仅允许观察（look/observe）
                if player_input and not any(k in player_input for k in ["看看", "观察", "look", "observe", "检查"]):
                    self.session.add_history("system", "【行动力耗尽】你感到力不从心，只能勉强观察周围环境。")
                    self.session.flags["_ap_exhausted"] = True
                    return

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
            },
        )
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
        return (
            f"【状态】HP {stats['hp']}/{stats['max_hp']} | "
            f"体力 {stats['stamina']}/{stats['max_stamina']} | "
            f"行动力 {ap_bar}（{ap}/{max_ap}） | "
            f"道德债务 {moral['level']}（{moral['debt']}分） | "
            f"装备: {equip_summary} | "
            f"场景 {scene_title} | "
            f"{skill_summary}"
        )

    def reset_dm(self) -> None:
        """重置 DM Agent（换场/重开时调用）"""
        self._agent = None
        self.scene_trigger_engine.reset()
