# api/game_manager.py - 游戏会话管理器
"""
管理所有活跃游戏会话。
每个 session_id 对应一个独立的 GameMaster 实例。
支持客户端重连恢复：client_id -> session_id 映射，断连60秒后清理。
"""

import uuid
import asyncio
import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field
from collections import defaultdict
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

logger = logging.getLogger("rpgagent.manager")


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
    client_id: str = ""    # 关联的客户端 ID


class GameManager:
    """
    全局游戏会话管理器。
    负责：创建/查找/销毁游戏会话，支持自动存档。
    支持客户端重连恢复：client_id -> session_id 映射，断连60秒后清理。
    """

    AUTOSAVE_TURNS = 5  # 每 AUTOSAVE_TURNS 回合自动存档一次
    CLIENT_TIMEOUT_SECONDS = 60  # 客户端断连超过60秒后清理

    def __init__(self):
        self._sessions: Dict[str, GameSession] = {}
        self._lock = asyncio.Lock()
        self._auto_save_task: Optional[asyncio.Task] = None
        self._active_session_id: Optional[str] = None  # 最近一次活跃的会话 ID
        
        # 客户端 ID -> session_id 映射，用于重连恢复
        self._client_to_session: Dict[str, str] = {}
        # 客户端最后活跃时间 (client_id -> timestamp)
        self._client_last_active: Dict[str, float] = {}
        # 客户端 WebSocket 连接状态 (client_id -> 是否在线)
        self._client_online: Dict[str, bool] = {}
        # 客户端清理任务
        self._cleanup_task: Optional[asyncio.Task] = None

    def generate_client_id(self) -> str:
        """生成新的客户端 ID"""
        return uuid.uuid4().hex[:16]

    async def register_client(self, client_id: str, session_id: str) -> None:
        """注册客户端到会话的映射"""
        async with self._lock:
            self._client_to_session[client_id] = session_id
            self._client_last_active[client_id] = time.time()
            self._client_online[client_id] = True
            
            # 确保清理任务运行
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_inactive_clients())

    async def update_client_heartbeat(self, client_id: str) -> None:
        """更新客户端最后活跃时间"""
        async with self._lock:
            self._client_last_active[client_id] = time.time()
            self._client_online[client_id] = True

    async def set_client_offline(self, client_id: str) -> None:
        """标记客户端为离线"""
        async with self._lock:
            self._client_online[client_id] = False
            if client_id in self._client_last_active:
                self._client_last_active[client_id] = time.time()

    def get_session_by_client_id(self, client_id: str) -> Optional[GameSession]:
        """通过客户端 ID 获取会话"""
        session_id = self._client_to_session.get(client_id)
        if session_id:
            return self.get_session(session_id)
        return None

    async def _cleanup_inactive_clients(self) -> None:
        """定期清理断连超过60秒的客户端"""
        while True:
            await asyncio.sleep(30)  # 每30秒检查一次
            
            current_time = time.time()
            clients_to_remove = []
            
            async with self._lock:
                for client_id, last_active in list(self._client_last_active.items()):
                    is_online = self._client_online.get(client_id, False)
                    inactive_seconds = current_time - last_active
                    
                    # 离线且超过60秒，清理
                    if not is_online and inactive_seconds >= self.CLIENT_TIMEOUT_SECONDS:
                        clients_to_remove.append(client_id)
            
            for client_id in clients_to_remove:
                await self._remove_client(client_id)

    async def _remove_client(self, client_id: str) -> None:
        """移除客户端及其关联的会话"""
        session_id = self._client_to_session.pop(client_id, None)
        self._client_last_active.pop(client_id, None)
        self._client_online.pop(client_id, None)
        
        if session_id and session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"[Cleanup] Removed inactive client {client_id}, session {session_id}")

    async def start_game(
        self,
        game_id: str,
        player_name: str,
        game_loader: ContextLoader,
        db: Database,
        client_id: Optional[str] = None,
    ) -> tuple[GameSession, str]:
        """创建新游戏会话
        
        Args:
            game_id: 游戏 ID
            player_name: 玩家名称
            game_loader: 游戏加载器
            db: 数据库
            client_id: 客户端 ID（可选，用于重连恢复）
            
        Returns:
            (game_session, client_id)
            - game_session: 游戏会话
            - client_id: 客户端 ID（新建或传入的）
        """
        # 生成或使用传入的 client_id
        if not client_id:
            client_id = self.generate_client_id()
        
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
            client_id=client_id,
        )

        async with self._lock:
            self._sessions[session_id] = game_session
            self._active_session_id = session_id
            self._client_to_session[client_id] = session_id
            self._client_last_active[client_id] = time.time()
            self._client_online[client_id] = True

        # 生成 autosave ID 并触发首次存档
        game_session.autosave_id = f"autosave_{session_id}"
        self._do_autosave(game_session)

        # 启动后台自动存档任务（如果尚未启动）
        await self._start_auto_save_task()
        
        # 确保清理任务运行
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_inactive_clients())

        return game_session, client_id

    def get_session(self, session_id: str) -> Optional[GameSession]:
        session = self._sessions.get(session_id)
        if session:
            self._active_session_id = session_id
        return session

    def get_active_gm(self) -> Optional["GameMaster"]:
        """获取最近活跃游戏的 GameMaster 实例"""
        if not self._active_session_id:
            return None
        session = self._sessions.get(self._active_session_id)
        return session.gm if session else None

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
