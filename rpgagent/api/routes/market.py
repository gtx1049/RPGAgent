# api/routes/market.py - 剧本市场 API
"""
GET /api/market/games
    返回所有已安装剧本的完整信息（含 meta.json + manifest.yaml）
    ?tag=历史  → 仅返回含有该标签的剧本

GET /api/market/tags
    返回所有已安装剧本的标签汇总（去重）
"""
from fastapi import APIRouter
from ...config.settings import GAMES_DIR, USER_GAMES_DIR
from ...systems.gamepkg import PackageManager

router = APIRouter(prefix="/market", tags=["market"])


def _collect_games() -> list[dict]:
    """从 GAMES_DIR 和 USER_GAMES_DIR 收集所有剧本"""
    games = []
    for base_dir in (GAMES_DIR, USER_GAMES_DIR):
        if not base_dir.exists():
            continue
        for game_path in base_dir.iterdir():
            if not game_path.is_dir():
                continue
            meta_file = game_path / "meta.json"
            if not meta_file.exists():
                continue
            import json
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            manifest_file = game_path / "manifest.yaml"
            manifest = None
            if manifest_file.exists():
                try:
                    import yaml
                    manifest = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            import hashlib, zipfile
            checksum = None
            gamepkg_candidates = list(game_path.parent.glob(f"{game_path.name}*.gamepkg"))
            if gamepkg_candidates:
                pkg_path = gamepkg_candidates[0]
                h = hashlib.sha256()
                with open(pkg_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                checksum = h.hexdigest()

            from ...config.settings import ENGINE_VERSION, check_engine_version
            engine_ok, engine_msg = True, ""
            ev = manifest.get("engine_version") if manifest else None
            if ev:
                engine_ok, engine_msg = check_engine_version(ev)

            games.append({
                "id": meta.get("id", game_path.name),
                "name": meta.get("name", meta.get("id", game_path.name)),
                "version": meta.get("version", "1.0"),
                "author": meta.get("author", "未知"),
                "summary": meta.get("summary", ""),
                "tags": meta.get("tags", []),
                "first_scene": meta.get("first_scene", ""),
                "engine_version_required": ev,
                "engine_compatible": engine_ok,
                "engine_msg": engine_msg,
                "installed_path": str(game_path),
                "source": "builtin" if game_path.parent == GAMES_DIR else "user",
                "pkg_checksum": checksum,
                "scene_count": len(list(game_path.glob("scenes/*.md"))) if (game_path / "scenes").exists() else 0,
                "character_count": len(list(game_path.glob("characters/*.json"))) if (game_path / "characters").exists() else 0,
            })
    return games


@router.get("/games")
async def list_market_games(tag: str | None = None):
    """
    返回剧本列表，可按标签过滤。
    每个剧本返回完整 meta 信息。
    """
    all_games = _collect_games()
    if tag:
        tag = tag.strip()
        all_games = [g for g in all_games if tag in g.get("tags", [])]
    return all_games


@router.get("/tags")
async def list_all_tags():
    """返回所有剧本标签的去重列表"""
    all_games = _collect_games()
    tags = set()
    for g in all_games:
        for t in g.get("tags", []):
            tags.add(t)
    return sorted(tags)
