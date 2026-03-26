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


class GameManager:
    """
    全局游戏会话管理器。
    负责：创建/查找/销毁游戏会话。
    """

    def __init__(self):
        self._sessions: Dict[str, GameSession] = {}
        self._lock = asyncio.Lock()

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

        narrative, cmd = session.gm.process_input(player_input)
        session.turn += 1
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


# 全局单例
_manager: Optional[GameManager] = None


def get_manager() -> GameManager:
    global _manager
    if _manager is None:
        _manager = GameManager()
    return _manager
