# tests/unit/test_session.py
import pytest
import json
import tempfile
from pathlib import Path
from core.session import Session, GameState, SaveFile


class TestSession:
    def test_init(self):
        s = Session("game_01", "张三", "scene_start")
        assert s.game_id == "game_01"
        assert s.player_name == "张三"
        assert s.current_scene_id == "scene_start"
        assert s.turn_count == 0
        assert len(s.history) == 0

    def test_update_state(self):
        s = Session("game_01", "玩家", "start")
        s.update_state(
            scene_id="scene_02",
            stats={"hp": 80},
            moral_debt=15,
        )
        assert s.current_scene_id == "scene_02"
        assert s.stats["hp"] == 80
        assert s.moral_debt == 15

    def test_add_history(self):
        s = Session("game_01", "玩家", "start")
        s.add_history("player", "我想去看看")
        s.add_history("gm", "好的，你向东走。")
        assert len(s.history) == 2
        assert s.history[0]["role"] == "player"

    def test_increment_turn(self):
        s = Session("game_01", "玩家", "start")
        s.increment_turn()
        s.increment_turn()
        assert s.turn_count == 2

    def test_get_snapshot(self):
        s = Session("game_01", "玩家", "start")
        s.update_state(
            stats={"hp": 80, "stamina": 100},
            moral_debt=10,
            inventory=[{"id": "sword", "name": "铁剑"}],
            relations={"npc_01": 30},
        )
        snap = s.get_snapshot()
        assert snap.game_id == "game_01"
        assert snap.stats["hp"] == 80
        assert snap.moral_debt == 10
        assert len(snap.inventory) == 1

    def test_get_history_summary(self):
        s = Session("game_01", "玩家", "start")
        s.add_history("player", "我想去村里看看")
        s.add_history("gm", "你走进村子...")
        s.add_history("player", "我询问村民情况")
        summary = s.get_history_summary(last_n=2)
        assert "PLAYER" in summary
        assert "询问村民" in summary


class TestSaveFile:
    def test_save_and_load(self, tmp_path):
        # 临时化存档目录
        SaveFile.SAVE_DIR = tmp_path

        s = Session("game_01", "张三", "scene_a")
        s.update_state(
            stats={"hp": 75},
            moral_debt=12,
        )
        s.increment_turn()

        path = s.save("test_save")
        assert path.exists()

        # 新 session 读档
        s2 = Session("game_01", "玩家", "start")
        ok = s2.load("test_save")
        assert ok is True
        assert s2.stats["hp"] == 75
        assert s2.moral_debt == 12
        assert s2.current_scene_id == "scene_a"
        assert s2.turn_count == 1

    def test_load_nonexistent(self, tmp_path):
        SaveFile.SAVE_DIR = tmp_path
        s = Session("game_01", "玩家", "start")
        ok = s.load("not_exist")
        assert ok is False

    def test_list_saves(self, tmp_path):
        SaveFile.SAVE_DIR = tmp_path
        s1 = Session("game_01", "玩家A", "scene_x")
        s1.save("save_a")
        s2 = Session("game_02", "玩家B", "scene_y")
        s2.save("save_b")
        sf = SaveFile()
        saves = sf.list_saves()
        assert len(saves) == 2


class TestGameState:
    def test_to_dict(self):
        state = GameState(
            game_id="g1",
            scene_id="s1",
            player_name="张三",
            stats={"hp": 80},
            moral_debt=10,
            inventory=[],
            relations={},
            flags={"key_found": True},
            turn_count=5,
        )
        d = state.to_dict()
        assert d["game_id"] == "g1"
        assert d["flags"]["key_found"] is True

    def test_from_dict(self):
        d = {
            "game_id": "g1",
            "scene_id": "s1",
            "player_name": "张三",
            "stats": {"hp": 80},
            "moral_debt": 10,
            "inventory": [],
            "relations": {},
            "flags": {},
            "turn_count": 3,
        }
        state = GameState(**d)
        assert state.turn_count == 3
        assert state.stats["hp"] == 80
