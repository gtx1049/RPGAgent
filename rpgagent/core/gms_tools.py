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
        """生成冒险日志（Markdown格式）并自动保存到文件"""
        from rpgagent.systems.adventure_log import generate_adventure_log, save_adventure_log
        
        session = self.gm.session
        hv_sys = self.gm.hidden_value_sys
        
        # 收集事件（从 history 提取关键事件）
        events = []
        for i, h in enumerate(session.history):
            if h.get("role") in ("gm", "player") and h.get("content"):
                content = h["content"]
                if len(content) > 80:
                    content = content[:80] + "..."
                events.append({
                    "turn": i + 1,
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
        
        # 自动保存到文件
        try:
            filepath = save_adventure_log(
                game_id=self.gm.game_id,
                act_id="current",
                act_title=act_title,
                log_content=log,
            )
            saved_msg = f"\n\n📜 冒险日志已保存至: {filepath.name}"
        except Exception as e:
            saved_msg = ""
        
        return ToolResponse(content=[TextBlock(type="text", text=log + saved_msg)])

    # ── 技能系统 ──────────────────────────────────

    def get_skill_status(self) -> ToolResponse:
        """获取当前技能状态（技能点、已学技能列表）"""
        skill_sys = self.gm.skill_sys
        learned = skill_sys.list_learned()
        available = skill_sys.list_available()
        lines = [
            f"【技能系统】可用技能点: {skill_sys.skill_points} 点",
            "",
            "── 已学习技能 ──",
        ]
        if not learned:
            lines.append("  尚无已学技能")
        for s in learned:
            lines.append(
                f"  • {s['name']} Lv.{s['rank']}/{s['max_rank']} "
                f"[{s['type']}] {s['description']}"
            )
        lines.append("")
        lines.append("── 可学习技能（未学习，选取前8个） ──")
        if not available:
            lines.append("  已学习全部技能")
        for s in available[:8]:
            lines.append(
                f"  • {s['name']} [{s['type']}] 需{s['cost']}点 | {s['description']}"
            )
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    def learn_skill(self, skill_id: str, ranks: int = 1) -> ToolResponse:
        """学习或升级技能（消耗技能点）"""
        skill_sys = self.gm.skill_sys
        skill = skill_sys.book.get(skill_id)
        if not skill:
            return ToolResponse(content=[TextBlock(type="text", text=f"未找到技能ID: {skill_id}")])
        current = skill_sys.learned.get(skill_id, 0)
        if current >= skill.max_rank:
            return ToolResponse(content=[TextBlock(type="text", text=f"「{skill.name}」已达最高级（{skill.max_rank}级）")])
        if skill_sys.skill_points < ranks:
            return ToolResponse(content=[TextBlock(type="text", text=f"技能点不足：需要{ranks}点，当前{skill_sys.skill_points}点")])
        success = skill_sys.learn_skill(skill_id, ranks)
        if success:
            new_rank = skill_sys.learned.get(skill_id, 0)
            self._sync_session()
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 学会「{skill.name}」→ Lv.{new_rank}/{skill.max_rank}，剩余{skill_sys.skill_points}点")])
        return ToolResponse(content=[TextBlock(type="text", text="❌ 学习失败")])

    def grant_skill_points(self, amount: int, reason: str = "") -> ToolResponse:
        """奖励技能点（如完成任务、升级奖励等）"""
        skill_sys = self.gm.skill_sys
        skill_sys.add_skill_points(amount)
        self._sync_session()
        reason_str = f"（{reason}）" if reason else ""
        return ToolResponse(content=[TextBlock(type="text", text=f"🎁 获得 {amount} 点技能点 {reason_str}，现有 {skill_sys.skill_points} 点")])

    # ── 骰点判定 ───────────────────────────────────────

    def roll_check(
        self,
        attribute: str,
        dc: int = 50,
        action_hint: str = "",
    ) -> ToolResponse:
        """
        执行 d100 骰点判定。

        Args:
            attribute: 属性键名（strength/dexterity/constitution/intelligence/wisdom/charisma）
            dc: 难度阈值 1-100（参考：30=轻松，50=五五开，65=难搞，80=几无可能）
            action_hint: 行动描述（如"潜行绕过守卫"），会嵌入叙事
        """
        roll_sys = self.gm.roll_sys
        if not roll_sys:
            return ToolResponse(content=[TextBlock(type="text", text="骰点系统未初始化")])
        try:
            result = roll_sys.check(
                attribute_key=attribute,
                base_difficulty=dc,
                narrative_hint=action_hint,
            )
            return ToolResponse(content=[TextBlock(type="text", text=result.description)])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"判定失败：{e}")])

    # ── 场景 CG 生成 ─────────────────────────────────

    _UNSET_STYLE = object()

    def generate_scene_cg(
        self,
        style: Any = _UNSET_STYLE,
        characters: Optional[list[dict]] = None,
    ) -> ToolResponse:
        """
        为当前场景生成 CG 配图。

        Args:
            style: 美术风格描述，支持关键词如 "watercolor", "ink wash", "fantasy", "realistic" 等。
                   通义万相会将其融入画面。若不填，则使用 scene .cg.yaml / meta.cg_scenes 中的
                   配置风格。
            characters: 当前场景中出现的角色列表，格式：[{"name": "角色名", "appearance": "外貌描述"}]
        """
        scene = self.gm.get_current_scene()
        if not scene:
            return ToolResponse(content=[TextBlock(type="text", text="⚠️ 当前无场景，无法生成 CG")])

        # 检查 API key
        import os
        api_key = os.getenv("TONGYI_API_KEY", "")
        if not api_key:
            # CG 未启用，返回提示而非错误，不打断叙事
            return ToolResponse(content=[TextBlock(type="text", text="")])

        scene_id = self.gm.session.current_scene_id
        scene_content = scene.content if scene else ""

        # 读取场景 CG 配置（优先级：scene.cg_config > meta.cg_scenes）
        scene_config: dict = {}
        if scene.cg_config:
            scene_config = scene.cg_config
        else:
            cg_config = getattr(self.gm.game_loader.meta, "cg_scenes", {}) or {}
            scene_config = cg_config.get(scene_id) or {}

        # style 优先级：显式传入 > scene.cg_config > meta.cg_scenes > 内联默认值
        DEFAULT_STYLE = "fantasy illustration, dark atmosphere, high quality"
        if style is not self._UNSET_STYLE:
            resolved_style = style
        else:
            resolved_style = scene_config.get("style") or DEFAULT_STYLE

        try:
            from rpgagent.systems.image_generator import make_generator
            import asyncio

            gen = make_generator(provider="tongyi", api_key=api_key)
            img_path = asyncio.run(gen.generate(
                scene_id=scene_id,
                scene_content=scene_content,
                characters=characters or [],
                style=resolved_style,
            ))
            asyncio.run(gen.close())

            # 写入 session，供 API 层感知
            self.gm.session.scene_cg_path = img_path
            self.gm.session.scene_cg_generated = True
            # 标记该场景已生成，避免 auto 流程重复触发
            self.gm._auto_cg_generated_scenes.add(scene_id)
            # 记录 CG 历史
            scene_title = self.gm.current_scene.title if self.gm.current_scene else scene_id
            self.gm.session.cg_history.append({
                "scene_id": scene_id,
                "scene_title": scene_title,
                "cg_path": img_path,
                "trigger": "dm_request",
            })

            # 返回相对路径给 LLM（API 层会做 URL 转换）
            cg_filename = os.path.basename(img_path)
            return ToolResponse(content=[TextBlock(
                type="text",
                text=f"[CG_GENERATED:{cg_filename}]"
            )])
        except Exception as e:
            # 生成失败不影响叙事，吞掉异常
            return ToolResponse(content=[TextBlock(type="text", text="")])

    # ── 队友系统 ───────────────────────────────────────

    def list_recruitable_teammates(self) -> ToolResponse:
        """列出所有可招募的队友（尚未加入的NPC）"""
        tm = self.gm.teammate_sys
        profiles = tm.list_profiles()
        if not profiles:
            return ToolResponse(content=[TextBlock(type="text", text="目前没有可招募的队友。")])

        lines = ["【可招募队友】"]
        for p in profiles:
            is_active = tm.is_active(p["id"])
            status = "（已入队）" if is_active else "（可招募）"
            skills = ", ".join(p["available_skills"]) if p["available_skills"] else "无"
            lines.append(
                f"  · {p['name']} {status}\n"
                f"    性格: {p['personality']} | 初始HP: {p['hp']} | 技能: {skills}\n"
                f"    {p['description'][:50]}"
            )
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    def list_active_teammates(self) -> ToolResponse:
        """列出当前队伍中的队友状态"""
        tm = self.gm.teammate_sys
        active = tm.list_active()
        if not active:
            return ToolResponse(content=[TextBlock(type="text", text="队伍中暂无队友。")])

        lines = ["【当前队友】"]
        for s in active:
            profile = tm.get_profile(s["profile_id"])
            name = profile.name if profile else s["profile_id"]
            alive = "存活" if s["is_alive"] else "倒下"
            ap_bar = "●" * s["action_power"] + "○" * (s["max_action_power"] - s["action_power"])
            loyalty_bar = "❤" * (s["loyalty"] // 20) + "♡" * (5 - s["loyalty"] // 20)
            lines.append(
                f"  · {name} | HP {s['hp']}/{s['max_hp']} | "
                f"AP {ap_bar} | 忠诚 {loyalty_bar} | {alive}"
            )
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    def recruit_teammate(self, teammate_id: str) -> ToolResponse:
        """招募指定NPC为队友（通过 teammate_recruit GM_COMMAND）"""
        result = self.gm.teammate_sys.recruit(teammate_id)
        msg = result.get("message", str(result))
        return ToolResponse(content=[TextBlock(type="text", text=msg)])

    def get_teammate_status(self, teammate_id: str) -> ToolResponse:
        """查看指定队友的详细状态"""
        tm = self.gm.teammate_sys
        state = tm.get_active(teammate_id)
        profile = tm.get_profile(teammate_id)
        if not profile:
            return ToolResponse(content=[TextBlock(type="text", text=f"未找到队友：{teammate_id}")])
        if not state or not state.is_alive:
            return ToolResponse(content=[TextBlock(type="text", text=f"「{profile.name}」不在队伍中或已倒下。")])

        ap_bar = "●" * state.action_power + "○" * (state.max_action_power - state.action_power)
        loyalty_bar = "❤" * (state.loyalty // 20) + "♡" * (5 - state.loyalty // 20)
        cds = ", ".join(f"{k}({v}回合)" for k, v in state.cooldowns.items()) or "无"
        text = (
            f"【{profile.name}】\n"
            f"HP: {state.hp}/{state.max_hp} | "
            f"AP: {ap_bar} | "
            f"忠诚: {loyalty_bar}\n"
            f"性格: {profile.personality}\n"
            f"可用技能: {', '.join(profile.available_skills) or '无'}\n"
            f"技能冷却: {cds}\n"
            f"{profile.description}"
        )
        return ToolResponse(content=[TextBlock(type="text", text=text)])

    # ── 技能列表 ───────────────────────────────────────

    def list_all_skills(self) -> ToolResponse:
        """列出所有技能（显示已学/未学状态）"""
        skill_sys = self.gm.skill_sys
        lines = ["【全部技能列表】"]
        for skill in skill_sys.book.skills.values():
            rank = skill_sys.learned.get(skill.id, 0)
            status = f"Lv.{rank}/{skill.max_rank}" if rank > 0 else "未学习"
            lines.append(f"  • {skill.name} {status} [{skill.skill_type.value}] {skill.description}")
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    # ── 成就系统 ─────────────────────────────────────

    def list_achievements(self) -> ToolResponse:
        """列出所有成就（已解锁/未解锁）"""
        ach_list = self.gm.achievement_sys.list_achievements()
        if not ach_list:
            return ToolResponse(content=[TextBlock(type="text", text="目前没有可用成就。")])

        unlocked = [a for a in ach_list if a["unlocked"]]
        locked = [a for a in ach_list if not a["unlocked"]]
        lines = [f"【成就列表】（{len(unlocked)}/{len(ach_list)} 已解锁）"]
        if unlocked:
            lines.append("── 已解锁 ──")
            for a in unlocked:
                lines.append(f"  {a['icon']} 「{a['name']}」：{a['description']}")
        if locked:
            lines.append("── 未解锁 ──")
            for a in locked:
                lines.append(f"  🔒 「{a['name']}」：{a['description']}")
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    def check_achievements(self) -> ToolResponse:
        """触发成就评估，并返回本次新解锁的成就"""
        self.gm._evaluate_achievements()
        newly = [
            a for a in self.gm.achievement_sys.get_unlocked()
            if self.gm.session.flags.get("_achievement_unlocked")
            and a.narrative == self.gm.session.flags.get("_achievement_unlocked")
        ]
        if not newly:
            return ToolResponse(content=[TextBlock(type="text", text="本次无新成就解锁。")])
        lines = [a.narrative for a in newly]
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

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
            flags={
                "_npc_memories": self.gm.npc_mem_sys.get_snapshot(),
                "_teammates": self.gm.teammate_sys.get_snapshot(),
            },
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
        tools.get_skill_status,
        tools.learn_skill,
        tools.grant_skill_points,
        tools.list_all_skills,
        tools.roll_check,
        tools.list_recruitable_teammates,
        tools.list_active_teammates,
        tools.recruit_teammate,
        tools.get_teammate_status,
        tools.generate_scene_cg,
        tools.list_achievements,
        tools.check_achievements,
    ]
