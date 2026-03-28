# systems/context_compressor.py - 上下文压缩系统
"""
游戏幕间提示压缩机制。

防止长剧情游戏因上下文过大导致 LLM 无法继续运行。
在 token 估计超过阈值时，自动压缩对话历史，保留关键状态。
"""

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ────────────────────────────────────────────────
# Token 估算（简单字符级估计，中文≈2 token/字符，英文≈4 token/词）
# ────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """粗略估算一段文字的 token 数"""
    if not text:
        return 0
    # 中文字符
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    # 英文单词
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    # 标点和空白
    other = len(text) - chinese_chars - len(re.findall(r"[a-zA-Z]", text))
    return int(chinese_chars * 1.5 + english_words * 0.25 * 4 + other * 0.25)


@dataclass
class CompressionStats:
    """当前上下文压缩状态"""
    turn_count: int = 0
    history_length: int = 0
    token_estimate: int = 0
    compression_ratio: float = 0.0
    compression_triggered: bool = False
    last_compression_turn: int = 0
    can_continue: bool = True
    warning_level: str = "ok"  # ok | warning | critical

    def to_dict(self) -> Dict:
        return asdict(self)


class ContextCompressor:
    """
    上下文压缩器。

    支持三种压缩模式：
    - auto：自动检测阈值，触发轻度压缩
    - scene：幕间完整压缩，生成章节回顾
    - aggressive：激进压缩，最大化上下文精简

    保留信息（绝不压缩）：
    - 隐藏数值当前值
    - 未完成的支线任务
    - NPC 关系状态
    - 关键道具/装备
    - 剧情伏笔标记
    """

    # 各模块 token 预算占比
    TOKEN_BUDGET_SYSTEM = 0.15
    TOKEN_BUDGET_SCENE = 0.20
    TOKEN_BUDGET_HISTORY = 0.40
    TOKEN_BUDGET_OPTIONS = 0.10
    TOKEN_BUDGET_STATE = 0.15

    # 压缩触发阈值
    WARNING_THRESHOLD = 0.60  # token > 60% 上下文时警告
    CRITICAL_THRESHOLD = 0.75  # token > 75% 时强制压缩
    AUTO_COMPRESS_HISTORY_LENGTH = 50  # 历史轮数超过此值触发轻度压缩

    # 保留配置
    DEFAULT_KEEP_RECENT = 10  # 轻度压缩时保留最近 N 轮
    AGGRESSIVE_KEEP_RECENT = 5  # 激进压缩时保留最近 N 轮

    def __init__(
        self,
        max_context_tokens: int = 100000,
        # 外部依赖（由调用方注入，用于生成摘要）
        llm_client: Optional[Any] = None,
    ):
        self.max_context_tokens = max_context_tokens
        self.llm_client = llm_client  # 可选：用于 LLM 摘要生成

        # 运行时状态
        self._turn_count = 0
        self._history_length = 0
        self._last_compression_turn = 0
        self._compression_count = 0

        # 压缩摘要缓存（每次压缩后生成）
        self._summary_cache: Dict[str, Any] = {}

    def update(self, turn_count: int, history: List[Dict]) -> None:
        """更新压缩器状态（在每轮结束后调用）"""
        self._turn_count = turn_count
        self._history_length = len(history)

    def get_stats(
        self,
        history: List[Dict],
        system_prompt_tokens: int = 0,
        scene_tokens: int = 0,
        options_tokens: int = 0,
        state_tokens: int = 0,
    ) -> CompressionStats:
        """获取当前上下文统计"""
        history_tokens = sum(
            estimate_tokens(self._extract_text(h)) for h in history
        )
        total_tokens = (
            system_prompt_tokens
            + scene_tokens
            + history_tokens
            + options_tokens
            + state_tokens
        )

        usage_ratio = total_tokens / self.max_context_tokens if self.max_context_tokens > 0 else 0

        if usage_ratio >= self.CRITICAL_THRESHOLD:
            warning = "critical"
            can_continue = False
        elif usage_ratio >= self.WARNING_THRESHOLD:
            warning = "warning"
            can_continue = True
        else:
            warning = "ok"
            can_continue = True

        return CompressionStats(
            turn_count=self._turn_count,
            history_length=self._history_length,
            token_estimate=total_tokens,
            compression_ratio=round(usage_ratio, 2),
            compression_triggered=(self._compression_count > 0),
            last_compression_turn=self._last_compression_turn,
            can_continue=can_continue,
            warning_level=warning,
        )

    def _extract_text(self, entry: Dict) -> str:
        """从历史条目中提取可读文本"""
        # 支持多种历史格式
        if isinstance(entry, str):
            return entry
        if "narrative" in entry:
            return entry["narrative"]
        if "content" in entry:
            return entry["content"]
        if "player_input" in entry:
            return entry.get("player_input", "") + " " + entry.get("gm_response", "")
        if "gm_response" in entry:
            return entry.get("gm_response", "")
        return str(entry)

    def _summarize_entry(self, entry: Dict) -> str:
        """
        将一条历史条目压缩为一行摘要。
        不依赖 LLM，用规则提取关键信息。
        """
        text = self._extract_text(entry)
        turn = entry.get("turn", "?")
        scene = entry.get("scene_id", "")
        action_tag = entry.get("action_tag", "")

        # 提取关键叙事片段（取首尾各一段）
        sentences = re.split(r"[。！？\n]", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= 2:
            summary = " ".join(sentences)
        else:
            summary = f"{sentences[0]}…{sentences[-1]}"

        # 加上 action_tag 和场景
        tag_str = f" [标签:{action_tag}]" if action_tag else ""
        scene_str = f" @场景:{scene}" if scene else ""
        return f"[回合{turn}]{summary}{tag_str}{scene_str}"

    def compress_history(
        self,
        history: List[Dict],
        keep_recent: int = 10,
        mode: str = "auto",
    ) -> Dict[str, Any]:
        """
        压缩历史记录。

        参数：
            history: 对话历史列表
            keep_recent: 保留最近 N 轮完整对话
            mode: 压缩模式

        返回：
            {
                "summary": str,         # 早期对话摘要
                "recent": List[Dict],    # 保留的最近对话
                "key_states": Dict,     # 关键状态变化
                "compression_info": Dict # 压缩元信息
            }
        """
        if mode == "aggressive":
            keep_recent = self.AGGRESSIVE_KEEP_RECENT
        elif mode == "auto":
            keep_recent = max(self.DEFAULT_KEEP_RECENT, keep_recent)

        keep_recent = min(keep_recent, len(history))

        recent = history[-keep_recent:] if keep_recent > 0 else []
        early = history[:-keep_recent] if keep_recent < len(history) else []

        # 生成早期对话摘要
        if early:
            early_summaries = [self._summarize_entry(e) for e in early]
            summary = "｜".join(early_summaries[-20:])  # 最多20条摘要
        else:
            summary = "（无早期对话）"

        # 提取关键状态（从早期历史中提取数值变化）
        key_states = self._extract_key_states(early)

        self._last_compression_turn = self._turn_count
        self._compression_count += 1

        return {
            "summary": summary,
            "recent": recent,
            "key_states": key_states,
            "compression_info": {
                "mode": mode,
                "original_length": len(history),
                "kept_recent": keep_recent,
                "compressed_turns": len(early),
                "compression_turn": self._turn_count,
                "compression_id": self._compression_count,
                "timestamp": datetime.now().isoformat(),
            },
        }

    def _extract_key_states(self, entries: List[Dict]) -> Dict[str, Any]:
        """
        从历史条目中提取关键状态变化。
        保留：隐藏数值变化、装备获取、关系变化、NPC遭遇、重要决策。
        """
        states: Dict[str, Any] = {
            "hidden_value_changes": [],
            "equipment_gained": [],
            "relation_changes": [],
            "npc_encounters": [],
            "key_decisions": [],
            "quest_updates": [],
        }

        for entry in entries:
            # 隐藏数值变化
            if "hidden_value_delta" in entry:
                states["hidden_value_changes"].append(entry.get("hidden_value_delta"))
            # 装备
            if entry.get("action_tag") in ("get_equipment", "loot", "chest_open"):
                item = entry.get("item_gained", "")
                if item:
                    states["equipment_gained"].append(item)
            # 关系
            if "relation_delta" in entry:
                states["relation_changes"].append(entry.get("relation_delta"))
            # NPC 遭遇
            if "npc_id" in entry:
                npc_id = entry.get("npc_id")
                npc_name = entry.get("npc_name", npc_id)
                action = entry.get("player_action", "")
                states["npc_encounters"].append({
                    "npc_id": npc_id,
                    "npc_name": npc_name,
                    "action": action[:100],
                })
            # 关键决策
            if entry.get("action_tag") in ("important_choice", "key_decision"):
                decision = entry.get("player_input", "")[:100]
                states["key_decisions"].append(decision)

        return states

    def generate_act_review(
        self,
        act_history: List[Dict],
        act_number: int = 1,
        hidden_values: Dict[str, Any] | None = None,
        npc_relations: Dict[str, int] | None = None,
        pending_quests: List[str] | None = None,
    ) -> str:
        """
        生成幕间回顾（act transition compression）。
        用于幕结束时，总结当前幕的关键信息。
        """
        # 压缩历史获取关键状态
        compressed = self.compress_history(act_history, keep_recent=len(act_history), mode="scene")
        key_states = compressed["key_states"]

        # 汇总装备
        equip_list = ", ".join(key_states.get("equipment_gained", [])) or "无"

        # 汇总关系变化
        rel_changes = key_states.get("relation_changes", [])
        rel_summary = ", ".join(
            f"{k}{'+' if v >= 0 else ''}{v}" for d in rel_changes
            for k, v in (d.items() if isinstance(d, dict) else {})
        ) or "无明显变化"

        # 汇总 NPC 遭遇
        npc_list = key_states.get("npc_encounters", [])
        npc_names = list({n["npc_name"] for n in npc_list}) or []

        # 隐藏数值摘要
        hv_summary = ""
        if hidden_values:
            hv_lines = []
            for vid, state in hidden_values.items():
                if isinstance(state, dict):
                    level = state.get("level", 0)
                    name = state.get("name", vid)
                    hv_lines.append(f"{name}（等级{level}）")
                elif isinstance(state, (int, float)):
                    hv_lines.append(f"{vid}: {state}")
            hv_summary = "、".join(hv_lines) if hv_lines else "正常"

        # 关键决策
        decisions = key_states.get("key_decisions", [])
        decision_str = "、".join(decisions[:5]) if decisions else "无特别记录"

        # 悬疑/伏笔（pending quests）
        pending_str = "、".join(pending_quests[:5]) if pending_quests else "无"

        review = f"""## 第{act_number}幕回顾
**已达成**：{"、".join(npc_names) if npc_names else "无NPC遭遇"}
**关系变化**：{rel_summary}
**获得装备**：{equip_list}
**关键选择**：{decision_str}
**当前状态**：{hv_summary}
**未解悬念**：{pending_str}
"""
        return review

    def build_compressed_system_prompt(
        self,
        original_system_prompt: str,
        compressed_data: Dict[str, Any],
        hidden_values_snapshot: Dict[str, Any] | None = None,
        pending_quests: List[str] | None = None,
        npc_relations: Dict[str, Any] | None = None,
    ) -> str:
        """
        将压缩摘要注入新的 System Prompt。
        返回完整的压缩版 system prompt。
        """
        summary = compressed_data.get("summary", "")
        compression_info = compressed_data.get("compression_info", {})
        key_states = compressed_data.get("key_states", {})
        mode = compression_info.get("mode", "auto")
        compressed_turns = compression_info.get("compressed_turns", 0)

        # 构建压缩摘要头
        compression_header = f"""【上下文已压缩 · 模式:{mode} · 已压缩{compressed_turns}回合对话】
以下为早期对话摘要（请严格遵守其内容，不要与之矛盾）：

{summary}

"""

        # 注入隐藏数值快照（绝不压缩的关键状态）
        hv_section = ""
        if hidden_values_snapshot:
            hv_lines = []
            for vid, snap in hidden_values_snapshot.items():
                if isinstance(snap, dict):
                    hv_lines.append(
                        f"- {snap.get('name', vid)}: {snap.get('current_threshold', snap.get('level', '?'))}"
                    )
                else:
                    hv_lines.append(f"- {vid}: {snap}")
            if hv_lines:
                hv_section = "\n## 当前隐藏数值（此信息不可忽略）\n" + "\n".join(hv_lines)

        # 注入 NPC 关系
        npc_section = ""
        if npc_relations:
            rel_lines = [f"- {k}: {v}" for k, v in npc_relations.items()]
            npc_section = "\n## NPC关系状态\n" + "\n".join(rel_lines)

        # 注入未完成任务
        quest_section = ""
        if pending_quests:
            quest_section = "\n## 未完成的支线任务\n" + "\n".join(f"- {q}" for q in pending_quests)

        # 注入关键装备
        equip_section = ""
        equip_list = key_states.get("equipment_gained", [])
        if equip_list:
            equip_section = "\n## 已获得的关键装备\n" + "\n".join(f"- {e}" for e in equip_list)

        # 组装
        injection = (
            compression_header
            + hv_section
            + npc_section
            + quest_section
            + equip_section
            + "\n\n---\n"
        )

        return injection + original_system_prompt

    def should_auto_compress(
        self,
        history: List[Dict],
        token_ratio: float | None = None,
    ) -> Tuple[bool, str]:
        """
        判断是否应该触发自动压缩。

        返回 (是否压缩, 压缩模式)。
        """
        # 条件1：历史轮数超限
        if self._history_length > self.AUTO_COMPRESS_HISTORY_LENGTH:
            if token_ratio is not None and token_ratio >= self.CRITICAL_THRESHOLD:
                return True, "aggressive"
            return True, "auto"

        # 条件2：token 比例超限
        if token_ratio is not None and token_ratio >= self.CRITICAL_THRESHOLD:
            return True, "aggressive"
        if token_ratio is not None and token_ratio >= self.WARNING_THRESHOLD:
            return True, "auto"

        return False, "none"
