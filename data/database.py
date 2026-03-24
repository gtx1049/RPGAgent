# data/database.py - SQLite 持久化层
"""
RPGAgent 数据持久化层。
使用 SQLite 按剧本分离存储，支持 query-based context 构建。
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator
from contextlib import contextmanager


SCHEMA = """
-- 世界事件时间线
CREATE TABLE IF NOT EXISTS world_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    turn         INTEGER NOT NULL,
    scene_id     TEXT,
    summary      TEXT NOT NULL,
    raw_content  TEXT,
    tags         TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- NPC 状态快照
CREATE TABLE IF NOT EXISTS npc_states (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    current_location TEXT,
    relation_value  INTEGER DEFAULT 0,
    flags           TEXT DEFAULT '{}',
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- NPC 对话历史
CREATE TABLE IF NOT EXISTS dialogue_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id      TEXT,
    turn        INTEGER,
    speaker     TEXT NOT NULL,
    content     TEXT NOT NULL,
    summary     TEXT DEFAULT '',
    turn_offset INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 隐藏数值记录
CREATE TABLE IF NOT EXISTS hidden_value_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    hidden_value_id  TEXT NOT NULL,
    delta            INTEGER NOT NULL,
    source           TEXT,
    scene_id         TEXT,
    player_action    TEXT,
    turn             INTEGER,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 隐藏数值当前状态
CREATE TABLE IF NOT EXISTS hidden_value_state (
    hidden_value_id TEXT PRIMARY KEY,
    name            TEXT,
    description     TEXT,
    level           INTEGER DEFAULT 0,
    records_json    TEXT DEFAULT '[]'
);

-- 场景标记（伏笔/开关/变量）
CREATE TABLE IF NOT EXISTS scene_flags (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 存档
CREATE TABLE IF NOT EXISTS saves (
    id          TEXT PRIMARY KEY,
    slot        INTEGER,
    snapshot    TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_events_scene ON world_events(scene_id);
CREATE INDEX IF NOT EXISTS idx_events_turn  ON world_events(turn);
CREATE INDEX IF NOT EXISTS idx_dialogue_npc ON dialogue_history(npc_id);
CREATE INDEX IF NOT EXISTS idx_dialogue_turn ON dialogue_history(turn);
CREATE INDEX IF NOT EXISTS idx_hv_records   ON hidden_value_records(hidden_value_id);
"""


class Database:
    """
    按剧本分离的 SQLite 数据库。

    每次游戏对应一个 .db 文件，路径：
      ~/.openclaw/RPGAgent/data/{game_id}.db
    """

    def __init__(self, game_id: str, db_dir: Optional[Path] = None):
        if db_dir is None:
            db_dir = Path.home() / ".openclaw" / "RPGAgent" / "data"
        db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_dir / f"{game_id}.db"
        self.game_id = game_id
        self._init_schema()

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ────────────────────────────────────────────────
    # 世界事件
    # ────────────────────────────────────────────────

    def insert_event(
        self,
        turn: int,
        scene_id: str,
        summary: str,
        raw_content: str = "",
        tags: List[str] | None = None,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO world_events
                      (turn, scene_id, summary, raw_content, tags)
                   VALUES (?, ?, ?, ?, ?)""",
                (turn, scene_id, summary, raw_content, json.dumps(tags or [])),
            )
            conn.commit()
            return cur.lastrowid

    def query_events(
        self,
        scene_id: str | None = None,
        turn: int | None = None,
        limit: int = 10,
    ) -> List[Dict]:
        sql = "SELECT * FROM world_events WHERE 1=1"
        params: List = []
        if scene_id:
            sql += " AND scene_id = ?"
            params.append(scene_id)
        if turn:
            sql += " AND turn = ?"
            params.append(turn)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ────────────────────────────────────────────────
    # NPC 状态
    # ────────────────────────────────────────────────

    def upsert_npc_state(
        self,
        npc_id: str,
        name: str = "",
        current_location: str = "",
        relation_value: int = 0,
        flags: Dict | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO npc_states (id, name, current_location, relation_value, flags)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       name            = excluded.name,
                       current_location= excluded.current_location,
                       relation_value = excluded.relation_value,
                       flags           = excluded.flags,
                       updated_at      = CURRENT_TIMESTAMP""",
                (npc_id, name, current_location, relation_value, json.dumps(flags or {})),
            )
            conn.commit()

    def get_npc_state(self, npc_id: str) -> Dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM npc_states WHERE id = ?", (npc_id,)
            ).fetchone()
        return dict(row) if row else None

    def query_npcs_in_scene(self, scene_id: str) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM npc_states WHERE current_location = ?",
                (scene_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_npc_states(self) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM npc_states").fetchall()
        return [dict(r) for r in rows]

    # ────────────────────────────────────────────────
    # 对话历史
    # ────────────────────────────────────────────────

    def insert_dialogue(
        self,
        npc_id: str,
        turn: int,
        speaker: str,
        content: str,
        summary: str = "",
        turn_offset: int = 0,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO dialogue_history
                      (npc_id, turn, speaker, content, summary, turn_offset)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (npc_id, turn, speaker, content, summary, turn_offset),
            )
            conn.commit()
            return cur.lastrowid

    def query_dialogue(
        self,
        npc_ids: List[str] | None = None,
        scene_id: str | None = None,
        limit: int = 20,
    ) -> List[Dict]:
        # scene_id 通过 world_events 关联，这里简化为按 npc_ids + turn 过滤
        sql = "SELECT * FROM dialogue_history WHERE 1=1"
        params: List = []
        if npc_ids:
            placeholders = ",".join("?" * len(npc_ids))
            sql += f" AND npc_id IN ({placeholders})"
            params.extend(npc_ids)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_npc_dialogue_summary(self, npc_id: str, limit: int = 10) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT npc_id, speaker, summary, turn
                   FROM dialogue_history
                   WHERE npc_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (npc_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ────────────────────────────────────────────────
    # 隐藏数值
    # ────────────────────────────────────────────────

    def insert_hidden_value_record(
        self,
        hidden_value_id: str,
        delta: int,
        source: str,
        scene_id: str = "",
        player_action: str = "",
        turn: int = 0,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO hidden_value_records
                      (hidden_value_id, delta, source, scene_id, player_action, turn)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (hidden_value_id, delta, source, scene_id, player_action, turn),
            )
            conn.commit()

    def get_hidden_value_records(
        self, hidden_value_id: str, limit: int = 20
    ) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM hidden_value_records
                   WHERE hidden_value_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (hidden_value_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_hidden_value_state(self, hidden_value_id: str) -> Dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM hidden_value_state WHERE hidden_value_id = ?",
                (hidden_value_id,),
            ).fetchone()
        return dict(row) if row else None

    def upsert_hidden_value_state(
        self,
        hidden_value_id: str,
        name: str = "",
        description: str = "",
        level: int = 0,
        records: List[Dict] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO hidden_value_state
                      (hidden_value_id, name, description, level, records_json)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(hidden_value_id) DO UPDATE SET
                       name         = excluded.name,
                       description  = excluded.description,
                       level        = excluded.level,
                       records_json = excluded.records_json""",
                (hidden_value_id, name, description, level, json.dumps(records or [])),
            )
            conn.commit()

    def get_all_hidden_value_states(self) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM hidden_value_state").fetchall()
        return [dict(r) for r in rows]

    # ────────────────────────────────────────────────
    # 场景标记
    # ────────────────────────────────────────────────

    def set_scene_flag(self, key: str, value: Any) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO scene_flags (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                       updated_at = CURRENT_TIMESTAMP""",
                (key, json.dumps(value)),
            )
            conn.commit()

    def get_scene_flag(self, key: str) -> Any:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM scene_flags WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row["value"]) if row else None

    def get_scene_flags(self) -> Dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM scene_flags").fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    # ────────────────────────────────────────────────
    # 存档
    # ────────────────────────────────────────────────

    def save_snapshot(self, save_id: str, snapshot: Dict, slot: int = 0) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO saves (id, slot, snapshot) VALUES (?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET snapshot = excluded.snapshot,
                       slot = excluded.slot, created_at = CURRENT_TIMESTAMP""",
                (save_id, slot, json.dumps(snapshot)),
            )
            conn.commit()

    def load_snapshot(self, save_id: str) -> Dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT snapshot FROM saves WHERE id = ?", (save_id,)
            ).fetchone()
        return json.loads(row["snapshot"]) if row else None

    def list_saves(self) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, slot, created_at FROM saves ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ────────────────────────────────────────────────
    # 统计 / 调试
    # ────────────────────────────────────────────────

    def stats(self) -> Dict:
        with self._conn() as conn:
            tables = [
                "world_events", "npc_states", "dialogue_history",
                "hidden_value_records", "scene_flags", "saves",
            ]
            return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in tables}
