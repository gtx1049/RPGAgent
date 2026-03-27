# core/context_loader.py - 游戏上下文加载器
"""
从 games/ 目录加载剧本、人物、场景等结构化文件，
并转换为供 PromptBuilder 使用的 Python 对象。
"""

import json
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class Character:
    id: str
    name: str
    role: str  # protagonist / npc / enemy
    description: str
    stats: Dict[str, int] = field(default_factory=dict)
    inventory: List[str] = field(default_factory=list)  # item ids
    acquaintances: Dict[str, float] = field(default_factory=dict)  # npc_id -> weight (0~1)


@dataclass
class Scene:
    id: str
    title: str
    content: str  # Markdown 格式剧本内容
    available_actions: List[str] = field(default_factory=list)
    moral_debt_triggers: List[Dict] = field(default_factory=list)
    required_items: List[str] = field(default_factory=list)
    next_scenes: List[str] = field(default_factory=list)
    cg_config: Optional[Dict] = None  # CG 触发配置（从 .cg.yaml 加载）


@dataclass
class GameMeta:
    name: str
    version: str
    author: str
    summary: str
    tags: List[str]
    systems_enabled: Dict[str, bool] = field(default_factory=dict)
    hidden_values: List[Dict] = field(default_factory=dict)  # HiddenValueSystem 配置列表
    hidden_value_actions: Dict[str, Dict[str, int]] = field(default_factory=dict)  # action_map
    first_scene: Optional[str] = None  # 剧本入口场景 ID
    engine_version: Optional[str] = None  # 要求的最低引擎版本（如 "0.2"）
    cg_scenes: Dict[str, Dict] = field(default_factory=dict)  # CG 生成配置：{scene_id: {trigger, style}}


class GameLoader:
    """剧本加载器"""

    def __init__(self, game_path: Path):
        self.game_path = Path(game_path)
        self.meta: Optional[GameMeta] = None
        self.setting: str = ""
        self.characters: Dict[str, Character] = {}
        self.scenes: Dict[str, Scene] = {}
        self.custom_systems: Dict[str, Any] = {}
        self._characters_raw: Dict[str, Dict] = {}  # 原始JSON数据（含teammate_config等扩展字段）

    def load(self) -> bool:
        """加载整个剧本，返回成功与否"""
        try:
            self._load_meta()
            self._load_setting()
            self._load_characters()
            self._load_scenes()
            self._load_systems()
            return True
        except Exception as e:
            print(f"[ContextLoader] 加载失败: {e}")
            return False

    def _load_meta(self):
        meta_path = self.game_path / "meta.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                data = json.load(f)
                self.meta = GameMeta(
                    name=data.get("name", self.game_path.name),
                    version=data.get("version", "1.0"),
                    author=data.get("author", "unknown"),
                    summary=data.get("summary", ""),
                    tags=data.get("tags", []),
                    systems_enabled=data.get("systems_enabled", {}),
                    hidden_values=data.get("hidden_values", []),
                    hidden_value_actions=data.get("hidden_value_actions", {}),
                    first_scene=data.get("first_scene"),
                    engine_version=data.get("engine_version"),
                    cg_scenes=data.get("cg_scenes", {}),
                )
        else:
            self.meta = GameMeta(
                name=self.game_path.name,
                version="1.0",
                author="unknown",
                summary="",
                tags=[],
            )

    def _load_setting(self):
        setting_path = self.game_path / "setting.md"
        if setting_path.exists():
            with open(setting_path, encoding="utf-8") as f:
                self.setting = f.read()

    def _load_characters(self):
        char_dir = self.game_path / "characters"
        if not char_dir.exists():
            return
        for file in char_dir.iterdir():
            if file.suffix not in (".json", ".yaml", ".yml"):
                continue
            with open(file, encoding="utf-8") as f:
                data = yaml.safe_load(f) if file.suffix in (".yaml", ".yml") else json.load(f)
                char = Character(
                    id=data.get("id", file.stem),
                    name=data.get("name", "未知"),
                    role=data.get("role", "npc"),
                    description=data.get("description", ""),
                    stats=data.get("stats", {}),
                    inventory=data.get("inventory", []),
                    acquaintances=data.get("acquaintances", {}),
                )
                self.characters[char.id] = char
                self._characters_raw[char.id] = data  # 保留原始数据（含teammate_config等扩展字段）

    def _load_scenes(self):
        scenes_dir = self.game_path / "scenes"
        if not scenes_dir.exists():
            return
        for file in scenes_dir.iterdir():
            if file.suffix != ".md":
                continue
            with open(file, encoding="utf-8") as f:
                content = f.read()
                # 简单解析：前100字符作为标题
                title = content.split("\n")[0].lstrip("# ").strip()

                # 解析 ## Available Actions 小节，提取结构化行动选项
                # 格式：- [action_tag] label: description
                available_actions: List[str] = []
                in_actions_section = False
                for line in content.split("\n"):
                    stripped = line.strip()
                    if stripped == "## Available Actions":
                        in_actions_section = True
                        continue
                    if in_actions_section:
                        # 遇到另一个 ## 标题，结束 Available Actions 小节
                        if stripped.startswith("## "):
                            in_actions_section = False
                            continue
                        # 解析 - [tag] label: description 格式
                        if stripped.startswith("- ["):
                            bracket_end = stripped.find("]")
                            if bracket_end != -1:
                                available_actions.append(stripped)
                        elif stripped.startswith("-"):
                            # 降级：没有 [tag] 的简单选项
                            available_actions.append(stripped)

                # 加载场景 CG 配置（可选）
                cg_config: Optional[Dict] = None
                cg_yaml_file = scenes_dir / f"{file.stem}.cg.yaml"
                if cg_yaml_file.exists():
                    try:
                        with open(cg_yaml_file, encoding="utf-8") as f:
                            cg_config = yaml.safe_load(f)
                    except Exception:
                        pass

                scene = Scene(
                    id=file.stem,
                    title=title or file.stem,
                    content=content,
                    available_actions=available_actions,
                    cg_config=cg_config,
                )
                self.scenes[scene.id] = scene

    def _load_systems(self):
        sys_path = self.game_path / "systems.yaml"
        if sys_path.exists():
            with open(sys_path, encoding="utf-8") as f:
                self.custom_systems = yaml.safe_load(f) or {}

    def get_scene(self, scene_id: str) -> Optional[Scene]:
        return self.scenes.get(scene_id)

    def get_first_scene(self) -> Optional[Scene]:
        """返回第一个场景（meta.json 中指定或字母序第一个）"""
        if self.meta:
            # 尝试从 meta 读取首场景
            first = getattr(self.meta, "first_scene", None)
            if first and first in self.scenes:
                return self.scenes[first]
        # fallback：第一个场景文件
        if self.scenes:
            return next(iter(self.scenes.values()))
        return None


class ContextLoader:
    """
    上下文加载管理。
    
    自动扫描多个剧本根目录（内置 + 用户安装），
    同 ID 剧本：用户安装版本优先覆盖内置版本。
    """

    def __init__(self, extra_dirs: list[Path] | None = None):
        """
        Args:
            extra_dirs: 额外剧本目录列表，会被并入扫描范围。
                       用于加入 USER_GAMES_DIR。
        """
        self.loaders: Dict[str, GameLoader] = {}
        self.available_games: List[str] = []
        self._extra_dirs = extra_dirs or []

    def register_game(self, game_id: str, game_path: Path):
        loader = GameLoader(game_path)
        if loader.load():
            self.loaders[game_id] = loader
            if game_id not in self.available_games:
                self.available_games.append(game_id)

    def register_dir(self, games_root: Path):
        """扫描剧本根目录，注册所有剧本（同 ID 覆盖式注册）"""
        if not games_root.exists():
            return
        for game_dir in games_root.iterdir():
            if not game_dir.is_dir():
                continue
            if game_dir.name.startswith("."):
                continue
            self.register_game(game_dir.name, game_dir)

    def get_loader(self, game_id: str) -> Optional[GameLoader]:
        return self.loaders.get(game_id)

    def list_games(self) -> List[Dict]:
        return [
            {
                "id": game_id,
                "name": loader.meta.name,
                "summary": loader.meta.summary,
                "tags": loader.meta.tags,
            }
            for game_id, loader in self.loaders.items()
        ]
