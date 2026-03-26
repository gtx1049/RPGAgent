"""
tests/unit/test_registry.py - RegistryClient 单元测试
"""

import pytest
from unittest.mock import patch, MagicMock
from rpgagent.systems.registry import (
    RegistryClient, GameListing, UpdateInfo,
    NetworkError, NotFoundError, RegistryError,
)


# ─── fixtures ──────────────────────────────────────────────


@pytest.fixture
def client():
    return RegistryClient(registry_url="https://test.market", timeout=5)


@pytest.fixture
def sample_games_response():
    return [
        {
            "id": "qinmo",
            "name": "秦末·大泽乡",
            "version": "1.2.0",
            "summary": "秦末农民起义第一章",
            "tags": ["历史", "战争", "剧情"],
            "author": "RPGAgent Team",
            "download_url": "https://test.market/qinmo-1.2.0.gamepkg",
            "checksum_sha256": "a" * 64,
            "engine_version": "0.2",
        },
        {
            "id": "three_pigs",
            "name": "三只小猪",
            "version": "1.0.0",
            "summary": "经典童话冒险",
            "tags": ["童话", "解谜"],
            "author": "RPGAgent Team",
            "download_url": "https://test.market/three_pigs-1.0.0.gamepkg",
            "checksum_sha256": "b" * 64,
            "engine_version": "0.2",
        },
    ]


# ─── GameListing ──────────────────────────────────────────────

class TestGameListing:
    def test_from_dict_basic(self):
        d = {
            "id": "test_game",
            "name": "测试游戏",
            "version": "1.0.0",
            "summary": "一个测试",
            "tags": ["tag1", "tag2"],
            "author": "Tester",
            "download_url": "https://example.com/game.gamepkg",
            "checksum_sha256": "abc123",
            "engine_version": "0.2",
        }
        g = GameListing.from_dict(d)
        assert g.id == "test_game"
        assert g.name == "测试游戏"
        assert g.version == "1.0.0"
        assert g.tags == ["tag1", "tag2"]
        assert g.checksum_sha256 == "abc123"

    def test_from_dict_missing_fields(self):
        g = GameListing.from_dict({})
        assert g.id == ""
        assert g.name == ""
        assert g.version == "1.0"
        assert g.tags == []
        assert g.checksum_sha256 is None


# ─── UpdateInfo ──────────────────────────────────────────────

class TestUpdateInfo:
    def test_has_update_true(self):
        u = UpdateInfo("game", "1.0.0", "1.1.0", "https://x.com", None)
        assert u.has_update is True

    def test_has_update_false(self):
        u = UpdateInfo("game", "1.0.0", "1.0.0", "https://x.com", None)
        assert u.has_update is False


# ─── RegistryClient.list_games ──────────────────────────────────

class TestListGames:
    def test_list_games_success(self, client, sample_games_response):
        with patch.object(client, "_get", return_value=sample_games_response):
            games = client.list_games()
        assert len(games) == 2
        assert games[0].id == "qinmo"
        assert games[0].name == "秦末·大泽乡"

    def test_list_games_network_error(self, client):
        with patch.object(client, "_get", side_effect=NetworkError("fail")):
            games = client.list_games()
        assert games == []  # 容错返回空列表

    def test_list_games_invalid_response(self, client):
        with patch.object(client, "_get", return_value={"not": "a list"}):
            games = client.list_games()
        assert games == []


# ─── RegistryClient.search ──────────────────────────────────

class TestSearch:
    def test_search_by_name(self, client, sample_games_response):
        with patch.object(client, "list_games", return_value=[
            GameListing.from_dict(g) for g in sample_games_response
        ]):
            results = client.search("秦末")
        assert len(results) == 1
        assert results[0].id == "qinmo"

    def test_search_by_tag(self, client, sample_games_response):
        with patch.object(client, "list_games", return_value=[
            GameListing.from_dict(g) for g in sample_games_response
        ]):
            results = client.search("战争")
        assert len(results) == 1
        assert results[0].id == "qinmo"

    def test_search_no_match(self, client, sample_games_response):
        with patch.object(client, "list_games", return_value=[
            GameListing.from_dict(g) for g in sample_games_response
        ]):
            results = client.search("不存在的游戏")
        # 返回全部（fallback）
        assert len(results) == 2


# ─── RegistryClient.check_update ──────────────────────────────

class TestCheckUpdate:
    def test_has_update(self, client, sample_games_response):
        with patch.object(client, "list_games", return_value=[
            GameListing.from_dict(g) for g in sample_games_response
        ]):
            installed = [{"id": "qinmo", "version": "1.0.0"}]
            updates = client.check_update(installed)
        assert len(updates) == 1
        assert updates[0].game_id == "qinmo"
        assert updates[0].current_version == "1.0.0"
        assert updates[0].latest_version == "1.2.0"
        assert updates[0].has_update is True

    def test_no_update(self, client, sample_games_response):
        with patch.object(client, "list_games", return_value=[
            GameListing.from_dict(g) for g in sample_games_response
        ]):
            installed = [{"id": "qinmo", "version": "1.2.0"}]
            updates = client.check_update(installed)
        assert len(updates) == 0

    def test_unknown_game_no_update(self, client, sample_games_response):
        with patch.object(client, "list_games", return_value=[
            GameListing.from_dict(g) for g in sample_games_response
        ]):
            installed = [{"id": "unknown_game", "version": "1.0.0"}]
            updates = client.check_update(installed)
        assert len(updates) == 0

    def test_network_error_returns_empty(self, client):
        with patch.object(client, "list_games", side_effect=NetworkError("fail")):
            updates = client.check_update([{"id": "qinmo", "version": "1.0.0"}])
        assert updates == []


# ─── RegistryClient.get_game ───────────────────────────────

class TestGetGame:
    def test_get_game_success(self, client, sample_games_response):
        with patch.object(client, "_get", return_value=sample_games_response[0]):
            game = client.get_game("qinmo")
        assert game.id == "qinmo"
        assert game.version == "1.2.0"

    def test_get_game_not_found(self, client):
        with patch.object(client, "_get", side_effect=NotFoundError("404")):
            with pytest.raises(NotFoundError):
                client.get_game("nonexistent")
