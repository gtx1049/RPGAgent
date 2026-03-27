"""
rpgagent/systems/registry.py - 剧本市场注册表客户端

支持从远程 registry 查询剧本列表、搜索、按 ID 获取详情及检查更新。
Registry API（简化版）：

    GET {registry_url}/games.json
        返回: [{"id": "...", "name": "...", "version": "...",
                "summary": "...", "tags": [...], "author": "...",
                "download_url": "...", "checksum_sha256": "...",
                "engine_version": "..."}, ...]

    GET {registry_url}/games/{id}.json
        返回: 单个剧本详情（含完整描述、截图 URL 等）
"""

import hashlib
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


# ─── 数据模型 ──────────────────────────────────────────────


@dataclass
class GameListing:
    id: str
    name: str
    version: str
    summary: str
    tags: list[str]
    author: str
    download_url: str
    checksum_sha256: Optional[str]
    engine_version: Optional[str]

    @classmethod
    def from_dict(cls, d: dict) -> "GameListing":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", d.get("id", "")),
            version=d.get("version", "1.0"),
            summary=d.get("summary", ""),
            tags=d.get("tags", []),
            author=d.get("author", "unknown"),
            download_url=d.get("download_url", ""),
            checksum_sha256=d.get("checksum_sha256"),
            engine_version=d.get("engine_version"),
        )


@dataclass
class UpdateInfo:
    game_id: str
    current_version: str
    latest_version: str
    download_url: str
    checksum_sha256: Optional[str]

    @property
    def has_update(self) -> bool:
        return self.current_version != self.latest_version


# ─── 异常 ──────────────────────────────────────────────


class RegistryError(Exception):
    """注册表相关错误"""
    pass


class NetworkError(RegistryError):
    """网络连接失败"""
    pass


class NotFoundError(RegistryError):
    """剧本在 registry 中不存在"""
    pass


# ─── RegistryClient ──────────────────────────────────────────────


class RegistryClient:
    """
    剧本市场注册表客户端。
    支持搜索、查询详情、检查更新。
    """

    DEFAULT_REGISTRY = "https://rpgagent.market"

    def __init__(self, registry_url: Optional[str] = None, timeout: int = 10):
        self.registry_url = (registry_url or self.DEFAULT_REGISTRY).rstrip("/")
        self.timeout = timeout

    # ── 底层请求 ───────────────────────────────

    def _get(self, path: str) -> dict | list:
        url = f"{self.registry_url}{path}"
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "RPGAgent/0.2"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFoundError(f"资源不存在: {path}")
            raise NetworkError(f"HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise NetworkError(f"无法连接 registry ({self.registry_url}): {e.reason}")

    # ── API ───────────────────────────────

    def list_games(self) -> list[GameListing]:
        """
        获取 registry 上所有剧本列表。
        失败时返回空列表（容错）。
        """
        try:
            data = self._get("/games.json")
            if isinstance(data, list):
                return [GameListing.from_dict(d) for d in data]
            return []
        except (NetworkError, RegistryError):
            return []

    def search(self, query: str) -> list[GameListing]:
        """
        搜索剧本（按名称/TAG/作者模糊匹配）。
        registry 不可用时做本地 fallback 过滤。
        """
        q = query.lower()
        try:
            all_games = self.list_games()
        except (NetworkError, RegistryError):
            all_games = []

        # 先尝试 registry 搜索
        if all_games:
            remote_results = [g for g in all_games
                              if q in g.name.lower()
                              or q in g.summary.lower()
                              or any(q in tag.lower() for tag in g.tags)]
            if remote_results:
                return remote_results

        # fallback: 返回所有（让用户看到有东西）
        return all_games

    def get_game(self, game_id: str) -> GameListing:
        """获取指定剧本详情"""
        try:
            data = self._get(f"/games/{game_id}.json")
            return GameListing.from_dict(data)
        except NotFoundError:
            raise NotFoundError(f"剧本 '{game_id}' 不在市场中")

    def check_update(self, installed_games: list[dict]) -> list[UpdateInfo]:
        """
        检查已安装剧本的更新。

        Args:
            installed_games: [{"id": ..., "version": ...}, ...]
        Returns:
            [UpdateInfo, ...]（含 has_update=True 的条目）
        """
        try:
            all_remote = {g.id: g for g in self.list_games()}
        except (NetworkError, RegistryError):
            return []

        updates = []
        for local in installed_games:
            gid = local.get("id")
            if gid not in all_remote:
                continue
            remote = all_remote[gid]
            current_ver = local.get("version", "1.0")
            if current_ver != remote.version:
                updates.append(UpdateInfo(
                    game_id=gid,
                    current_version=current_ver,
                    latest_version=remote.version,
                    download_url=remote.download_url,
                    checksum_sha256=remote.checksum_sha256,
                ))
        return updates

    def download_and_install(
        self,
        game_id: str,
        dest_dir: Path,
        *,
        force: bool = False,
        progress_callback=None,
    ) -> dict:
        """
        下载并安装剧本（从 download_url）。

        Returns:
            {"ok": True, "version": ..., "path": ...}
        Raises:
            NetworkError / NotFoundError / RegistryError
        """
        import shutil, tempfile, zipfile

        info = self.get_game(game_id)
        if not info.download_url:
            raise RegistryError(f"剧本 '{game_id}' 无可用的下载链接")

        # 下载到临时文件
        tmp_path = Path(tempfile.mktemp(suffix=".gamepkg"))
        try:
            req = urllib.request.Request(
                info.download_url,
                headers={"User-Agent": "RPGAgent/0.2"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total:
                            progress_callback(downloaded, total)

            # SHA256 校验
            if info.checksum_sha256:
                h = hashlib.sha256()
                with open(tmp_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                actual = h.hexdigest()
                if actual.lower() != info.checksum_sha256.lower():
                    raise RegistryError(
                        f"SHA256 校验失败！文件可能已损坏。"
                        f"期望: {info.checksum_sha256[:16]}..., 实际: {actual[:16]}..."
                    )

            # 用 PackageManager 安装
            from rpgagent.systems.gamepkg import PackageManager, PackageCorruptedError
            mgr = PackageManager(dest_dir)
            result = mgr.install(tmp_path, force=force, skip_integrity=True)
            return {
                "ok": True,
                "version": info.version,
                "path": result["game"]["installed_path"],
                "overwritten": result["overwritten"],
            }
        finally:
            tmp_path.unlink(missing_ok=True)
