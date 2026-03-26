"""
rpgagent/systems/gamepkg.py - 剧本包（gamepkg）管理

gamepkg 格式：本质是 .zip 文件，内含一个剧本目录（games/{id}/）
    秦末·大泽乡-1.0.gamepkg   # 单文件分发包
        └── games/
            └── qinmo/        # 剧本根目录（必须与 meta.json 同级的父目录名匹配）
                ├── meta.json
                ├── setting.md
                ├── characters/
                └── scenes/

设计原则：
- 安装后解压到 USER_GAMES_DIR（默认 ~/.local/share/rpgagent/games/）
- 元数据校验：必须包含 meta.json；id/version 必须合法
- 冲突处理：同名剧本覆盖安装（用户显式选择）
"""

import json
import zipfile
import shutil
from pathlib import Path
from typing import Optional
import hashlib


# ─── 异常 ──────────────────────────────────────────────


class GamePkgError(Exception):
    """gamepkg 相关错误"""
    pass


class PackageCorruptedError(GamePkgError):
    """包文件损坏或不完整"""
    pass


class MetaMissingError(GamePkgError):
    """缺少必要的 meta.json"""
    pass


class InvalidMetaError(GamePkgError):
    """meta.json 格式或内容非法"""
    pass


# ─── 核心校验 ──────────────────────────────────────────────


def validate_meta(meta: dict) -> list[str]:
    """
    校验 meta.json 内容，返回错误列表（空=合法）。
    必填字段：id, name
    """
    errors = []
    if not meta.get("id"):
        errors.append("meta.json 缺少必填字段：id")
    if not meta.get("name"):
        errors.append("meta.json 缺少必填字段：name")
    if meta.get("id"):
        # id 应只含字母、数字、连字符、下划线
        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", meta["id"]):
            errors.append(f"id '{meta['id']}' 包含非法字符，只允许字母/数字/-/_")
    return errors


def find_game_root_in_zip(zf: zipfile.ZipFile) -> tuple[Path, str]:
    """
    在 zip 中查找剧本根目录（即包含 meta.json 的那一层目录）。
    
    Returns:
        (game_root_path_in_zip, game_id)
        game_root_path_in_zip: zip 内的相对路径，如 "games/qinmo/"（末尾有/）
        game_id: 从 meta.json 读取的 id
    """
    # 策略：找所有 meta.json，验证其路径符合 games/{id}/meta.json
    meta_files = [n for n in zf.namelist() if n.endswith("meta.json") and "/meta.json" in n]
    if not meta_files:
        raise MetaMissingError("gamepkg 内未找到 meta.json 文件")

    candidates = []
    for mf in meta_files:
        parts = mf.split("/")
        if len(parts) >= 3 and parts[-1] == "meta.json":
            game_id = parts[-2]
            # game_root 是 meta.json 所在目录的父目录（即 games/{id}/）
            game_root = "/".join(parts[:-1]) + "/"
            try:
                raw = zf.read(mf).decode("utf-8")
                meta = json.loads(raw)
                errs = validate_meta(meta)
                if errs:
                    continue  # 跳过不合法的
                candidates.append((game_root, meta["id"], meta))
            except Exception:
                continue

    if not candidates:
        raise InvalidMetaError("未找到合法的 meta.json（缺少 id 或 name，或格式错误）")

    if len(candidates) > 1:
        # 多个合法剧本，取第一个（单剧本包不应有多个）
        pass

    return candidates[0][0], candidates[0][1]


# ─── PackageHandle：单个 gamepkg 文件的操作句柄 ────────────────────────────


class PackageHandle:
    """
    代表一个 gamepkg 文件（本地 .gamepkg 路径）。
    提供只读操作：读取元数据、预览内容。
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._meta: Optional[dict] = None
        self._game_id: Optional[str] = None
        self._game_root: Optional[str] = None

    def open(self):
        try:
            with zipfile.ZipFile(self.path, "r") as zf:
                root, game_id = find_game_root_in_zip(zf)
                raw_meta = zf.read(f"{root}meta.json").decode("utf-8")
                self._meta = json.loads(raw_meta)
                self._game_id = game_id
                self._game_root = root
        except zipfile.BadZipFile:
            raise PackageCorruptedError(f"'{self.path.name}' 不是有效的 zip 文件")

    @property
    def meta(self) -> dict:
        if self._meta is None:
            self.open()
        return self._meta

    @property
    def game_id(self) -> str:
        if self._game_id is None:
            self.open()
        return self._game_id

    @property
    def version(self) -> str:
        return self.meta.get("version", "1.0")

    @property
    def name(self) -> str:
        return self.meta.get("name", self.game_id)

    @property
    def summary(self) -> str:
        return self.meta.get("summary", "")

    def preview_files(self) -> list[str]:
        """返回包内文件列表（不含 __MACOSX 等系统文件）"""
        with zipfile.ZipFile(self.path, "r") as zf:
            return [
                n for n in zf.namelist()
                if not n.startswith("__MACOSX/") and not n.endswith("/")
            ][:30]  # 限制预览数量

    def compute_sha256(self) -> str:
        """计算包文件 SHA256（用于缓存/校验）"""
        h = hashlib.sha256()
        with open(self.path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()


# ─── PackageManager：管理已安装的剧本包 ───────────────────────────────────


class PackageManager:
    """
    管理已安装剧本的生命周期：安装、卸载、列出、查询。
    剧本安装到 USER_GAMES_DIR，与内置 games/ 目录并列。
    """

    def __init__(self, games_dir: Path):
        self.games_dir = games_dir

    # ── 查询 ───────────────────────────────

    def list_installed(self) -> list[dict]:
        """返回所有已安装剧本的基本信息"""
        if not self.games_dir.exists():
            return []
        games = []
        for game_path in self.games_dir.iterdir():
            if not game_path.is_dir():
                continue
            meta_file = game_path / "meta.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    games.append({
                        "id": meta.get("id", game_path.name),
                        "name": meta.get("name", meta.get("id", game_path.name)),
                        "version": meta.get("version", "1.0"),
                        "author": meta.get("author", "unknown"),
                        "summary": meta.get("summary", ""),
                        "tags": meta.get("tags", []),
                        "installed_path": str(game_path),
                    })
                except Exception:
                    games.append({
                        "id": game_path.name,
                        "name": game_path.name,
                        "version": "unknown",
                        "author": "unknown",
                        "summary": "（元数据读取失败）",
                        "tags": [],
                        "installed_path": str(game_path),
                    })
        return games

    def get_installed(self, game_id: str) -> Optional[dict]:
        """查询指定剧本是否已安装"""
        games = self.list_installed()
        for g in games:
            if g["id"] == game_id:
                return g
        return None

    def is_installed(self, game_id: str) -> bool:
        return self.get_installed(game_id) is not None

    # ── 安装 ───────────────────────────────

    def install(self, pkg_path: Path, *, force: bool = False) -> dict:
        """
        将 .gamepkg 文件安装到 USER_GAMES_DIR。

        Args:
            pkg_path: .gamepkg 文件路径
            force:    若已安装同名剧本是否覆盖

        Returns:
            {"ok": True, "game": {...}, "overwritten": bool}
        Raises:
            PackageCorruptedError / InvalidMetaError
        """
        pkg = PackageHandle(pkg_path)
        pkg.open()
        game_id = pkg.game_id

        # 检查是否已安装
        existing = self.get_installed(game_id)
        if existing and not force:
            raise GamePkgError(
                f"剧本 '{pkg.name}'（{game_id}）已安装。"
                f" 使用 --force 强制覆盖。"
            )

        dest = self.games_dir / game_id

        # 清理旧版本（如果存在且 force）
        if dest.exists():
            shutil.rmtree(dest)

        # 解压
        self.games_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(pkg_path, "r") as zf:
            # 只提取 games/{game_id}/ 下的内容，跳过外层结构
            game_root_prefix = pkg._game_root  # 如 "games/qinmo/"
            extracted_count = 0
            for member in zf.namelist():
                if not member.startswith(game_root_prefix):
                    continue
                # 去掉前缀，重定向到目标目录
                target_rel = member[len(game_root_prefix):]
                if not target_rel:
                    continue
                target_path = dest / target_rel
                if member.endswith("/"):
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                extracted_count += 1

        if extracted_count == 0:
            raise PackageCorruptedError("解压后未找到任何文件，可能 gamepkg 结构异常")

        return {
            "ok": True,
            "game": self.get_installed(game_id),
            "overwritten": bool(existing),
            "extracted": extracted_count,
        }

    # ── 卸载 ───────────────────────────────

    def remove(self, game_id: str) -> bool:
        """
        卸载剧本（删除整个目录）。
        Returns: 是否成功删除
        """
        game_path = self.games_dir / game_id
        if not game_path.exists():
            return False
        shutil.rmtree(game_path)
        return True

    # ── 创建 gamepkg（打包）──────────────────────────────

    @staticmethod
    def pack(source_dir: Path, output_path: Path) -> Path:
        """
        将本地剧本目录打包为 .gamepkg 文件。

        Args:
            source_dir: 剧本根目录（含 meta.json）
            output_path: 输出 .gamepkg 路径（含 .gamepkg 后缀）

        Returns: 生成的 .gamepkg 路径
        """
        source_dir = Path(source_dir)
        meta_file = source_dir / "meta.json"
        if not meta_file.exists():
            raise MetaMissingError(f"剧本目录缺少 meta.json：{source_dir}")

        with open(meta_file, encoding="utf-8") as f:
            meta = json.load(f)
        errs = validate_meta(meta)
        if errs:
            raise InvalidMetaError(f"meta.json 不合法：{errs}")

        output_path = Path(output_path)
        if not output_path.name.endswith(".gamepkg"):
            output_path = output_path.with_name(output_path.name + ".gamepkg")

        game_id = meta["id"]
        # 包内结构：games/{game_id}/...
        prefix = f"games/{game_id}/"

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    arcname = prefix + str(file_path.relative_to(source_dir))
                    zf.write(file_path, arcname)

        return output_path
