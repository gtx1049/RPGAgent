# api/routes/editor.py - 可视化剧本编辑器 API
"""
提供剧本内容的 CRUD 操作，供前端编辑器调用。

端点：
  GET    /editor/games                    列出可编辑的剧本
  GET    /editor/games/{game_id}          获取剧本完整结构
  GET    /editor/games/{game_id}/scenes   场景列表
  GET    /editor/games/{game_id}/scenes/{scene_id}  读取场景
  PUT    /editor/games/{game_id}/scenes/{scene_id}  保存场景
  POST   /editor/games/{game_id}/scenes   新建场景
  DELETE /editor/games/{game_id}/scenes/{scene_id}  删除场景
  GET    /editor/games/{game_id}/characters      角色列表
  GET    /editor/games/{game_id}/characters/{char_id}  读取角色
  PUT    /editor/games/{game_id}/characters/{char_id}  保存角色
  POST   /editor/games/{game_id}/characters      新建角色
  GET    /editor/games/{game_id}/meta            读取 meta.json
  PUT    /editor/games/{game_id}/meta            保存 meta.json
  GET    /editor/games/{game_id}/setting         读取 setting.md
  PUT    /editor/games/{game_id}/setting         保存 setting.md
  GET    /editor/games/{game_id}/npcs            NPC 记忆/关系数据
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import json

router = APIRouter(prefix="/editor", tags=["editor"])

# ─── 工具函数 ───────────────────────────────────────


def _game_path(game_id: str) -> Path:
    """获取剧本根目录"""
    # 优先查找 workspace/games/，其次查找系统剧本目录
    candidates = [
        Path(__file__).parent.parent.parent.parent / "games" / game_id,
        Path.home() / ".config" / "rpgagent" / "games" / game_id,
    ]
    for p in candidates:
        if p.exists():
            return p
    raise HTTPException(status_code=404, detail=f"剧本不存在：{game_id}")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ─── 请求/响应模型 ───────────────────────────────────


class SceneMeta(BaseModel):
    id: str
    title: str
    description: str = ""
    triggers: list[dict] = []


class CharacterData(BaseModel):
    id: str
    name: str
    role: str = "npc"  # npc | enemy | teammate
    description: str = ""
    personality: str = ""
    visible: bool = True
    # 扩展字段（供编辑器自由填充）
    extra: dict = {}


class MetaData(BaseModel):
    id: str
    name: str
    version: str = "1.0.0"
    author: str = ""
    summary: str = ""
    tags: list[str] = []
    engine_version: str = "0.2"
    first_scene: str = "act_01"


class GameStructure(BaseModel):
    game_id: str
    meta: dict
    setting: str
    scene_ids: list[str]
    character_ids: list[str]


# ─── 剧本列表 ───────────────────────────────────────


@router.get("/games")
async def list_games():
    """列出所有可编辑的剧本"""
    candidates = [
        Path(__file__).parent.parent.parent.parent / "games",
        Path.home() / ".config" / "rpgagent" / "games",
    ]
    games = []
    for base in candidates:
        if not base.exists():
            continue
        for gdir in base.iterdir():
            meta_file = gdir / "meta.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    games.append({
                        "id": gdir.name,
                        "name": meta.get("name", gdir.name),
                        "author": meta.get("author", ""),
                        "summary": meta.get("summary", ""),
                        "version": meta.get("version", "?"),
                        "path": str(gdir),
                    })
                except Exception:
                    games.append({
                        "id": gdir.name,
                        "name": gdir.name,
                        "author": "",
                        "summary": "",
                        "version": "?",
                        "path": str(gdir),
                    })
    return games


# ─── 剧本结构概览 ───────────────────────────────────


@router.get("/games/{game_id}")
async def get_game_structure(game_id: str):
    """获取剧本完整结构（不含内容）"""
    base = _game_path(game_id)

    meta = {}
    meta_file = base / "meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))

    setting = ""
    setting_file = base / "setting.md"
    if setting_file.exists():
        setting = setting_file.read_text(encoding="utf-8")

    scene_ids = []
    scenes_dir = base / "scenes"
    if scenes_dir.exists():
        scene_ids = sorted([p.stem for p in scenes_dir.glob("*.md")])

    character_ids = []
    chars_dir = base / "characters"
    if chars_dir.exists():
        character_ids = sorted([p.stem for p in chars_dir.glob("*.json")])

    return GameStructure(
        game_id=game_id,
        meta=meta,
        setting=setting,
        scene_ids=scene_ids,
        character_ids=character_ids,
    )


# ─── meta.json ───────────────────────────────────────


@router.get("/games/{game_id}/meta")
async def get_meta(game_id: str):
    base = _game_path(game_id)
    meta_file = base / "meta.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="meta.json 不存在")
    return json.loads(meta_file.read_text(encoding="utf-8"))


@router.put("/games/{game_id}/meta")
async def put_meta(game_id: str, data: dict):
    base = _game_path(game_id)
    meta_file = base / "meta.json"
    meta_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


# ─── setting.md ──────────────────────────────────────


@router.get("/games/{game_id}/setting")
async def get_setting(game_id: str):
    base = _game_path(game_id)
    setting_file = base / "setting.md"
    if not setting_file.exists():
        raise HTTPException(status_code=404, detail="setting.md 不存在")
    return {"content": setting_file.read_text(encoding="utf-8")}


@router.put("/games/{game_id}/setting")
async def put_setting(game_id: str, data: dict):
    base = _game_path(game_id)
    setting_file = base / "setting.md"
    content = data.get("content", "")
    setting_file.write_text(content, encoding="utf-8")
    return {"ok": True}


# ─── 场景 CRUD ───────────────────────────────────────


@router.get("/games/{game_id}/scenes")
async def list_scenes(game_id: str):
    """列出所有场景元信息"""
    base = _game_path(game_id)
    scenes_dir = base / "scenes"
    if not scenes_dir.exists():
        return []

    result = []
    for f in sorted(scenes_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        # 从 frontmatter 提取 title 和 triggers
        title = f.stem
        triggers = []
        description = ""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm = json.loads("{" + parts[1].strip().replace("\n", ",").replace(": ", '": "').replace(",\n}", '"}').replace('"\n}', '"}').replace(",\n", ",\n") + "}")
                    # 简单 frontmatter 解析
                    import re as _re
                    fm_text = parts[1]
                    title_m = _re.search(r'title:\s*["\']?(.+?)["\']?\s*$', fm_text, _re.MULTILINE)
                    if title_m:
                        title = title_m.group(1).strip('"\'')
                    triggers_m = _re.findall(r'-\s*["\']?(.+?)["\']?$', fm_text, _re.MULTILINE)
                    triggers = [{"raw": t} for t in triggers_m]
                except Exception:
                    pass
                # description 取第一段非 frontmatter 内容
                body_lines = [l for l in parts[2].strip().split("\n") if l.strip() and not l.startswith("#")]
                description = " ".join(body_lines[:2])[:100]
        result.append({
            "id": f.stem,
            "title": title,
            "description": description,
            "triggers": triggers,
            "word_count": len(content),
        })
    return result


@router.get("/games/{game_id}/scenes/{scene_id}")
async def get_scene(game_id: str, scene_id: str):
    """读取场景完整内容"""
    base = _game_path(game_id)
    scene_file = base / "scenes" / f"{scene_id}.md"
    if not scene_file.exists():
        raise HTTPException(status_code=404, detail=f"场景不存在：{scene_id}")
    return {
        "id": scene_id,
        "content": scene_file.read_text(encoding="utf-8"),
    }


@router.put("/games/{game_id}/scenes/{scene_id}")
async def put_scene(game_id: str, scene_id: str, data: dict):
    """保存场景内容"""
    base = _game_path(game_id)
    scenes_dir = base / "scenes"
    _ensure_dir(scenes_dir)
    scene_file = scenes_dir / f"{scene_id}.md"
    scene_file.write_text(data.get("content", ""), encoding="utf-8")
    return {"ok": True, "id": scene_id}


@router.post("/games/{game_id}/scenes")
async def create_scene(game_id: str, data: dict):
    """新建场景"""
    scene_id = data.get("id", "").strip()
    if not scene_id:
        raise HTTPException(status_code=400, detail="场景 ID 不能为空")
    if not scene_id.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="场景 ID 只能包含字母、数字、下划线和连字符")
    base = _game_path(game_id)
    scenes_dir = base / "scenes"
    _ensure_dir(scenes_dir)
    scene_file = scenes_dir / f"{scene_id}.md"
    if scene_file.exists():
        raise HTTPException(status_code=409, detail=f"场景已存在：{scene_id}")
    content = data.get("content", f"# {scene_id}\n\n新场景内容……\n")
    scene_file.write_text(content, encoding="utf-8")
    return {"ok": True, "id": scene_id}


@router.delete("/games/{game_id}/scenes/{scene_id}")
async def delete_scene(game_id: str, scene_id: str):
    """删除场景"""
    base = _game_path(game_id)
    scene_file = base / "scenes" / f"{scene_id}.md"
    if not scene_file.exists():
        raise HTTPException(status_code=404, detail=f"场景不存在：{scene_id}")
    scene_file.unlink()
    return {"ok": True}


# ─── 角色 CRUD ───────────────────────────────────────


@router.get("/games/{game_id}/characters")
async def list_characters(game_id: str):
    """列出所有角色"""
    base = _game_path(game_id)
    chars_dir = base / "characters"
    if not chars_dir.exists():
        return []
    result = []
    for f in sorted(chars_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "id": f.stem,
                "name": data.get("name", f.stem),
                "role": data.get("role", "npc"),
                "description": data.get("description", ""),
            })
        except Exception:
            result.append({"id": f.stem, "name": f.stem, "role": "npc", "description": ""})
    return result


@router.get("/games/{game_id}/characters/{char_id}")
async def get_character(game_id: str, char_id: str):
    """读取角色完整数据"""
    base = _game_path(game_id)
    char_file = base / "characters" / f"{char_id}.json"
    if not char_file.exists():
        raise HTTPException(status_code=404, detail=f"角色不存在：{char_id}")
    return json.loads(char_file.read_text(encoding="utf-8"))


@router.put("/games/{game_id}/characters/{char_id}")
async def put_character(game_id: str, char_id: str, data: dict):
    """保存角色数据"""
    base = _game_path(game_id)
    chars_dir = base / "characters"
    _ensure_dir(chars_dir)
    char_file = chars_dir / f"{char_id}.json"
    # 保留原有 id
    data["id"] = char_id
    char_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@router.post("/games/{game_id}/characters")
async def create_character(game_id: str, data: dict):
    """新建角色"""
    char_id = data.get("id", "").strip()
    if not char_id:
        raise HTTPException(status_code=400, detail="角色 ID 不能为空")
    base = _game_path(game_id)
    chars_dir = base / "characters"
    _ensure_dir(chars_dir)
    char_file = chars_dir / f"{char_id}.json"
    if char_file.exists():
        raise HTTPException(status_code=409, detail=f"角色已存在：{char_id}")
    char_data = {
        "id": char_id,
        "name": data.get("name", char_id),
        "role": data.get("role", "npc"),
        "description": data.get("description", ""),
        "personality": data.get("personality", ""),
        "visible": True,
        "extra": {},
    }
    char_file.write_text(json.dumps(char_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "id": char_id}


@router.delete("/games/{game_id}/characters/{char_id}")
async def delete_character(game_id: str, char_id: str):
    """删除角色"""
    base = _game_path(game_id)
    char_file = base / "characters" / f"{char_id}.json"
    if not char_file.exists():
        raise HTTPException(status_code=404, detail=f"角色不存在：{char_id}")
    char_file.unlink()
    return {"ok": True}


# ─── NPC 记忆数据（只读） ─────────────────────────────


@router.get("/games/{game_id}/npcs")
async def list_npc_data(game_id: str):
    """
    返回 NPC 关系/记忆的只读数据（从数据库读取当前进程的会话数据，
    编辑器中可预览，但 NPC 实际数据由游戏运行时管理）
    """
    # 编辑器模式下暂不提供运行时数据，只返回角色定义
    return await list_characters(game_id)


# ─── 剧本验证 ───────────────────────────────────────


@router.get("/games/{game_id}/validate")
async def validate_game(game_id: str):
    """
    对剧本进行全面校验，返回问题列表。
    校验项：meta.json 格式、场景/角色 ID 合法性、交叉引用完整性等。
    """
    from ...systems.scenario_validator import ScenarioValidator

    try:
        base = _game_path(game_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail=f"剧本不存在：{game_id}")

    validator = ScenarioValidator(base)
    report = validator.validate()

    return {
        "game_id": game_id,
        "is_valid": report.is_valid,
        "summary": report.summary(),
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "issues": [
            {
                "rule": i.rule,
                "severity": i.severity,
                "message": i.message,
                "file": i.file,
                "line": i.line,
            }
            for i in report.issues
        ],
    }
