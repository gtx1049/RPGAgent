# api/game_manager.py - 游戏会话管理器
"""
管理所有活跃游戏会话。
每个 session_id 对应一个独立的 GameMaster 实例。
"""

import uuid
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field
import sys
from pathlib import Path

# 确保项目路径在 sys.path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ..core.game_master import GameMaster
from ..core.session import Session
from ..core.context_loader import ContextLoader
from ..data.database import Database


@dataclass
class GameSession:
    """单次游戏会话"""
    session_id: str
    game_id: str
    player_name: str
    gm: GameMaster
    db: Database
    turn: int = 0
    autosave_id: str = ""  # 自动存档 ID


class GameManager:
    """
    全局游戏会话管理器。
    负责：创建/查找/销毁游戏会话，支持自动存档。
    """

    AUTOSAVE_TURNS = 5  # 每 AUTOSAVE_TURNS 回合自动存档一次

    def __init__(self):
        self._sessions: Dict[str, GameSession] = {}
        self._lock = asyncio.Lock()
        self._auto_save_task: Optional[asyncio.Task] = None

    async def start_game(
        self,
        game_id: str,
        player_name: str,
        game_loader: ContextLoader,
        db: Database,
    ) -> GameSession:
        """创建新游戏会话"""
        session_id = uuid.uuid4().hex[:12]
        session = Session(
            game_id=game_id,
            player_name=player_name,
            initial_scene_id="start",
        )

        try:
            gm = GameMaster(
                game_id=game_id,
                context_loader=game_loader,
                session=session,
            )
        except Exception as e:
            raise RuntimeError(f"启动游戏失败: {e}")

        game_session = GameSession(
            session_id=session_id,
            game_id=game_id,
            player_name=player_name,
            gm=gm,
            db=db,
        )

        async with self._lock:
            self._sessions[session_id] = game_session

        # 生成 autosave ID 并触发首次存档
        game_session.autosave_id = f"autosave_{session_id}"
        self._do_autosave(game_session)

        # 启动后台自动存档任务（如果尚未启动）
        await self._start_auto_save_task()

        return game_session

    def get_session(self, session_id: str) -> Optional[GameSession]:
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> bool:
        """关闭并清理会话"""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    async def restart_game(
        self,
        session_id: str,
        preserve: Optional[list[str]] = None,
    ) -> GameSession:
        """
        New Game+：重开游戏，可选择性保留进度。
        在原有会话上重置，保留 session_id。
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"会话不存在: {session_id}")

        scene = session.gm.new_game_plus(preserve=preserve)
        session.turn = 0

        # 新游戏写事件记录
        session.db.insert_event(
            turn=0,
            scene_id=scene.id if scene else "start",
            summary=f"New Game+（保留: {', '.join(preserve) if preserve else '无'}）",
            tags=["new_game_plus"],
        )

        return session

    async def process_action(
        self,
        session_id: str,
        player_input: str,
    ) -> tuple[str, Optional[dict]]:
        """
        处理玩家行动。
        返回: (narrative, command_data)
        """
        session = self.get_session(session_id)
        if not session:
            return "[错误] 会话不存在或已过期。", None

        narrative, cmd = await session.gm.process_input(player_input)
        session.turn += 1

        # 每 AUTOSAVE_TURNS 回合自动存档
        if session.turn % self.AUTOSAVE_TURNS == 0:
            self._do_autosave(session)

        return narrative, cmd

    def list_active_sessions(self) -> list[Dict]:
        return [
            {
                "session_id": s.session_id,
                "game_id": s.game_id,
                "player_name": s.player_name,
                "turn": s.turn,
            }
            for s in self._sessions.values()
        ]

    def _do_autosave(self, session: GameSession) -> None:
        """执行一次自动存档（同步，低频调用）"""
        try:
            snapshot = session.gm.session.get_snapshot()
            session.db.save_snapshot(session.autosave_id, snapshot.__dict__, slot=-1)
        except Exception as e:
            import sys
            print(f"[Autosave] 保存失败 session={session.session_id}: {e}", file=sys.stderr)

    async def _start_auto_save_task(self) -> None:
        """启动后台定时存档任务（每 AUTOSAVE_INTERVAL 秒对所有活跃会话存档）"""
        import asyncio
        AUTOSAVE_INTERVAL = 120  # 每120秒

        if self._auto_save_task is not None and not self._auto_save_task.done():
            return

        async def _loop():
            while True:
                await asyncio.sleep(AUTOSAVE_INTERVAL)
                async with self._lock:
                    for session in self._sessions.values():
                        self._do_autosave(session)

        self._auto_save_task = asyncio.create_task(_loop())


# 全局单例
_manager: Optional[GameManager] = None


def get_manager() -> GameManager:
    global _manager
    if _manager is None:
        _manager = GameManager()
    return _manager
