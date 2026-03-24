# core/session.py - 会话/存档管理
"""
Session：单次游戏会话。
负责管理游戏状态快照，可序列化为 JSON 保存。
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any


@dataclass
class GameState:
    """可序列化的游戏状态快照"""
    game_id: str
    scene_id: str
    player_name: str
    stats: Dict[str, int]
    moral_debt: int
    inventory: List[Dict]
    relations: Dict[str, int]
    flags: Dict[str, Any]  # 自定义游戏事件标记
    turn_count: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


class SaveFile:
    """存档文件管理"""

    SAVE_DIR = Path.home() / ".openclaw" / "RPGAgent" / "saves"

    def __init__(self):
        self.SAVE_DIR.mkdir(parents=True, exist_ok=True)

    def save(self, state: GameState, name: Optional[str] = None) -> Path:
        """保存存档，返回文件路径"""
        if name is None:
            name = f"{state.game_id}_{state.scene_id}_{uuid.uuid4().hex[:6]}"
        filepath = self.SAVE_DIR / f"{name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        return filepath

    def load(self, name: str) -> Optional[GameState]:
        filepath = self.SAVE_DIR / f"{name}.json"
        if not filepath.exists():
            # 尝试模糊匹配
            for f in self.SAVE_DIR.glob(f"{name}*.json"):
                filepath = f
                break
            else:
                return None
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return GameState(**data)

    def list_saves(self) -> List[Dict]:
        saves = []
        for f in sorted(self.SAVE_DIR.glob("*.json")):
            try:
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                saves.append({
                    "name": f.stem,
                    "game_id": data.get("game_id", "?"),
                    "scene_id": data.get("scene_id", "?"),
                    "player_name": data.get("player_name", "?"),
                    "turn_count": data.get("turn_count", 0),
                    "moral_debt": data.get("moral_debt", 0),
                    "file": f.name,
                })
            except Exception:
                saves.append({"name": f.stem, "error": "加载失败"})
        return saves


class Session:
    """
    单次游戏会话。
    管理当前状态、历史记录，并提供存档/读档接口。
    """

    def __init__(
        self,
        game_id: str,
        player_name: str = "玩家",
        initial_scene_id: str = "start",
    ):
        self.id = uuid.uuid4().hex
        self.game_id = game_id
        self.player_name = player_name
        self.current_scene_id = initial_scene_id
        self.created_at = datetime.now()

        # 状态
        self.stats: Dict[str, int] = {}
        self.moral_debt: int = 0
        self.inventory: List[Dict] = []
        self.relations: Dict[str, int] = {}
        self.flags: Dict[str, Any] = {}  # 剧情标记
        self.turn_count: int = 0

        # 历史
        self.history: List[Dict] = []  # {"role": "player"/"gm", "content": str}

        # 存档
        self.savefile = SaveFile()

    def update_state(
        self,
        scene_id: Optional[str] = None,
        stats: Optional[Dict[str, int]] = None,
        moral_debt: Optional[int] = None,
        inventory: Optional[List[Dict]] = None,
        relations: Optional[Dict[str, int]] = None,
        flags: Optional[Dict[str, Any]] = None,
    ):
        """批量更新状态"""
        if scene_id is not None:
            self.current_scene_id = scene_id
        if stats is not None:
            self.stats = stats
        if moral_debt is not None:
            self.moral_debt = moral_debt
        if inventory is not None:
            self.inventory = inventory
        if relations is not None:
            self.relations = relations
        if flags is not None:
            self.flags.update(flags)

    def add_history(self, role: str, content: str):
        self.history.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})

    def increment_turn(self):
        self.turn_count += 1

    def get_snapshot(self) -> GameState:
        return GameState(
            game_id=self.game_id,
            scene_id=self.current_scene_id,
            player_name=self.player_name,
            stats=self.stats,
            moral_debt=self.moral_debt,
            inventory=self.inventory,
            relations=self.relations,
            flags=self.flags,
            turn_count=self.turn_count,
        )

    def save(self, name: Optional[str] = None) -> Path:
        return self.savefile.save(self.get_snapshot(), name or f"{self.id}")

    def load(self, name: str) -> bool:
        state = self.savefile.load(name)
        if state is None:
            return False
        self._apply_state(state)
        return True

    def _apply_state(self, state: GameState):
        self.game_id = state.game_id
        self.current_scene_id = state.scene_id
        self.player_name = state.player_name
        self.stats = state.stats
        self.moral_debt = state.moral_debt
        self.inventory = state.inventory
        self.relations = state.relations
        self.flags = state.flags
        self.turn_count = state.turn_count

    def get_history_summary(self, last_n: int = 5) -> str:
        recent = self.history[-last_n:]
        return "\n".join(
            f"[{h['role'].upper()}] {h['content'][:100]}"
            for h in recent
        )
