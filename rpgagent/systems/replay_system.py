# systems/replay_system.py - 剧情回放/录像系统
"""
记录完整游戏过程，支持回放和分享。

每个玩家的游戏会话会被记录为一系列「回合快照」，
回放时按顺序重放每个回合的完整状态。

核心数据结构：
- ReplayRecord：单个回合的快照
- ReplaySession：整个游戏的记录

API 用途：
- GET  /replay              - 获取当前游戏回放概览
- GET  /replay/turns        - 获取所有回合快照列表
- GET  /replay/turn/{n}     - 获取第 N 回合的完整快照
- GET  /replay/export       - 导出为 Markdown 可分享格式
- POST /replay/start        - 开始一段新录制
- POST /replay/stop         - 结束录制
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any


@dataclass
class TurnRecord:
    """单个回合的完整快照"""
    turn: int                          # 回合数（从 1 开始）
    timestamp: str                     # ISO 时间戳

    # 叙事内容
    player_action: str                 # 玩家输入
    gm_narrative: str                  # DM 叙事原文

    # 数值状态快照
    action_points: int                  # 行动点
    hp: int; hp_max: int              # 生命值
    hidden_values: Dict[str, Any]      # 隐藏数值快照
    stats: Dict[str, Any]              # 六属性快照
    inventory: List[Dict]              # 背包快照
    equipped: Dict[str, str]           # 当前装备

    # 战斗/检定结果
    roll_result: Optional[Dict] = None  # 骰点结果

    # 特殊事件
    scene_id: str = ""                  # 场景 ID
    triggered_events: List[str] = field(default_factory=list)  # 触发的事件 ID
    ending_reached: Optional[str] = None  # 触发的结局 ID

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplaySession:
    """一段完整游戏的回放记录"""
    session_id: str
    game_id: str
    act_title: str
    started_at: str                     # ISO 时间戳
    ended_at: Optional[str] = None
    final_ending: Optional[str] = None
    turns: List[TurnRecord] = field(default_factory=list)

    @property
    def total_turns(self) -> int:
        return len(self.turns)

    def add_turn(self, record: TurnRecord):
        self.turns.append(record)

    def is_active(self) -> bool:
        return self.ended_at is None

    def get_turn(self, n: int) -> Optional[TurnRecord]:
        """获取第 n 回合（1-indexed）"""
        idx = n - 1
        if 0 <= idx < len(self.turns):
            return self.turns[idx]
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "game_id": self.game_id,
            "act_title": self.act_title,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "final_ending": self.final_ending,
            "total_turns": self.total_turns,
            "turns": [t.to_dict() for t in self.turns],
        }


class ReplaySystem:
    """
    剧情回放录制与管理器。

    用法（GameMaster 内部）：
        # 开始游戏时
        self.replay_sys.start_recording(session_id, game_id, act_title)

        # 每次行动后
        self.replay_sys.record_turn(self._build_turn_record(turn, ...))

        # 游戏结束时
        self.replay_sys.stop_recording(final_ending_id)

        # 查询
        self.replay_sys.get_replay_summary()
        self.replay_sys.export_markdown()
    """

    def __init__(self):
        # session_id -> ReplaySession
        self._sessions: Dict[str, ReplaySession] = {}
        # 当前活跃录制
        self._active: Optional[ReplaySession] = None

    # ── 录制控制 ─────────────────────────────────────

    def start_recording(self, session_id: str, game_id: str, act_title: str = "") -> ReplaySession:
        """开始一段新录制"""
        session = ReplaySession(
            session_id=session_id,
            game_id=game_id,
            act_title=act_title or f"冒险记录_{datetime.now().strftime('%m%d_%H%M')}",
            started_at=datetime.now().isoformat(),
        )
        self._sessions[session_id] = session
        self._active = session
        return session

    def stop_recording(self, final_ending: Optional[str] = None) -> Optional[ReplaySession]:
        """结束当前录制"""
        if not self._active:
            return None
        self._active.ended_at = datetime.now().isoformat()
        self._active.final_ending = final_ending
        session = self._active
        self._active = None
        return session

    def is_recording(self) -> bool:
        return self._active is not None

    # ── 记录回合 ─────────────────────────────────────

    def record_turn(
        self,
        turn: int,
        player_action: str,
        gm_narrative: str,
        action_points: int,
        hp: int,
        hp_max: int,
        hidden_values: Dict[str, Any],
        stats: Dict[str, Any],
        inventory: List[Dict],
        equipped: Dict[str, str],
        roll_result: Optional[Dict] = None,
        scene_id: str = "",
        triggered_events: Optional[List[str]] = None,
        ending_reached: Optional[str] = None,
    ) -> TurnRecord:
        """
        记录一个回合。GameMaster 在每个回合结束时调用。
        """
        record = TurnRecord(
            turn=turn,
            timestamp=datetime.now().isoformat(),
            player_action=player_action,
            gm_narrative=gm_narrative,
            action_points=action_points,
            hp=hp,
            hp_max=hp_max,
            hidden_values=hidden_values,
            stats=stats,
            inventory=inventory,
            equipped=equipped,
            roll_result=roll_result,
            scene_id=scene_id,
            triggered_events=triggered_events or [],
            ending_reached=ending_reached,
        )
        if self._active:
            self._active.add_turn(record)
        return record

    # ── 查询 ────────────────────────────────────────

    def get_replay(self, session_id: str) -> Optional[ReplaySession]:
        return self._sessions.get(session_id)

    def get_active_session(self) -> Optional[ReplaySession]:
        return self._active

    def get_all_sessions(self) -> List[ReplaySession]:
        return list(self._sessions.values())

    def get_replay_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取回放概览（不含完整叙事）"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        return {
            "session_id": session.session_id,
            "game_id": session.game_id,
            "act_title": session.act_title,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "final_ending": session.final_ending,
            "total_turns": session.total_turns,
            "is_active": session.is_active(),
            "turns_summary": [
                {
                    "turn": t.turn,
                    "timestamp": t.timestamp,
                    "scene_id": t.scene_id,
                    "action_preview": t.player_action[:50] + "..." if len(t.player_action) > 50 else t.player_action,
                    "has_roll": t.roll_result is not None,
                    "ending_reached": t.ending_reached,
                }
                for t in session.turns
            ],
        }

    # ── 导出 ────────────────────────────────────────

    def export_markdown(self, session_id: str) -> Optional[str]:
        """
        导出为可分享的 Markdown 格式。
        包含完整叙事流，适合直接分享或归档。
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        lines = [
            f"# {session.act_title}",
            "",
            f"**游戏**：{session.game_id}",
            f"**开始时间**：{session.started_at}",
            f"**结束时间**：{session.ended_at or '（进行中）'}",
            f"**总回合数**：{session.total_turns}",
        ]

        if session.final_ending:
            lines.append(f"**结局**：{session.final_ending}")

        lines.append("")
        lines.append("---")
        lines.append("")

        for t in session.turns:
            lines.append(f"## 第 {t.turn} 回合")
            lines.append("")
            lines.append(f"**场景**：{t.scene_id or '（未知）'}")
            lines.append(f"**时间**：{t.timestamp}")
            lines.append("")
            lines.append(f"**→ 玩家**：{t.player_action}")
            lines.append("")
            lines.append(t.gm_narrative)
            lines.append("")

            if t.roll_result:
                rr = t.roll_result
                lines.append(
                    f"🎲 **判定**：{rr.get('action', '?')} | "
                    f"掷出 {rr.get('roll', '?')} + {rr.get('modifier', 0)} "
                    f"= {rr.get('total', '?')} | DC {rr.get('dc', '?')} | "
                    f"{rr.get('success', '?')}"
                )
                lines.append("")

            if t.triggered_events:
                lines.append(f"⚡ **触发事件**：{', '.join(t.triggered_events)}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    # ── 存档/恢复 ───────────────────────────────────

    def get_snapshot(self) -> Dict[str, Any]:
        """获取所有录制会话的快照（用于存档）"""
        return {
            "sessions": {sid: s.to_dict() for sid, s in self._sessions.items()},
            "active_session_id": self._active.session_id if self._active else None,
        }

    def load_snapshot(self, data: Dict[str, Any]) -> None:
        """从快照恢复"""
        self._sessions.clear()
        for sid, sdata in data.get("sessions", {}).items():
            session = ReplaySession(
                session_id=sdata["session_id"],
                game_id=sdata["game_id"],
                act_title=sdata["act_title"],
                started_at=sdata["started_at"],
                ended_at=sdata.get("ended_at"),
                final_ending=sdata.get("final_ending"),
            )
            for tdata in sdata.get("turns", []):
                turn = TurnRecord(**tdata)
                session.add_turn(turn)
            self._sessions[sid] = session

        active_id = data.get("active_session_id")
        self._active = self._sessions.get(active_id)
