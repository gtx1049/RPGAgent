"""
rpgagent/systems/scenario_generator.py - AI 辅助剧本生成系统

用户输入世界观设定和大纲，LLM 自动生成完整剧本框架：
- meta.json（元信息）
- setting.md（世界观）
- characters/*.json（角色）
- scenes/*.md（场景）
- systems.yaml（数值配置）
- hidden_value_actions（隐藏数值行为映射）

生成完成后可立即加载游玩，或打包为 .gamepkg 分发。
"""

import json
import re
import yaml
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass

from ..config.settings import DEFAULT_MODEL, BASE_URL, API_KEY, ENGINE_VERSION


@dataclass
class GenerationOptions:
    """生成选项"""
    game_id: str                    # 剧本唯一 ID（英文/数字/-/_）
    game_name: str                  # 剧本中文名
    summary: str                    # 简介（1-2句）
    author: str = "AI Generated"    # 作者
    tags: list[str] = None          # 标签
    num_chapters: int = 3           # 章节数
    num_main_scenes: int = 8        # 主线场景总数
    num_npcs: int = 5               # NPC 数量
    genre: str = "fantasy"          # 类型：fantasy / sci_fi / historical / horror / romance

    def __post_init__(self):
        if self.tags is None:
            self.tags = [self.genre]


class ScenarioGenerator:
    """
    AI 辅助剧本生成器。

    使用 LLM 从世界观设定和大纲生成完整剧本目录结构，
    输出可直接被 GameLoader 加载并游玩。
    """

    SYSTEM_PROMPT = """你是一个 RPG 游戏剧本生成专家。

你的任务：根据用户提供的世界观设定和大纲，生成一个完整的 RPGAgent 剧本框架。

## 输出格式要求

严格按以下格式输出 YAML，包含所有字段。不要输出任何额外解释。

```yaml
# === meta.json ===
meta:
  id: "游戏ID（小写英文/数字）"
  name: "游戏中文名"
  version: "1.0"
  author: "作者名"
  summary: "一句话简介"
  tags: ["tag1", "tag2"]
  first_scene: "start"
  engine_version: "0.2"
  systems_enabled:
    combat: true
    skill: true
    equipment: true
    moral_debt: true
    hidden_values: true
  hidden_values:
    - id: "moral_debt"
      name: "道德债务"
      initial: 0
      max: 100
      tick_decay: 0
      threshold_critical: 80
    - id: "courage"
      name: "勇气"
      initial: 50
      max: 100
      tick_decay: 2
      threshold_critical: 20
  hidden_value_actions:
    <action_tag>:
      moral_debt: <delta>
      courage: <delta>

# === setting.md ===
setting: |
  世界观描述（200-400字）
  第一段：时代背景
  第二段：核心冲突
  第三段：玩家角色背景

# === characters/{npc_id}.json ===
characters:
  <npc_id>:
    name: "NPC中文名"
    role: "npc"  # protagonist | npc | enemy
    description: "NPC人物描述（100字以内）"
    stats:
      strength: <1-18>
      dexterity: <1-18>
      constitution: <1-18>
      intelligence: <1-18>
      wisdom: <1-18>
      charisma: <1-18>
    acquaintances: {}

# === scenes/{scene_id}.md ===
scenes:
  <scene_id>:
    title: "场景标题"
    content: |
      场景叙事内容（200-500字）
      
      ## Available Actions
      - [action_tag_1] 行动1：描述
      - [action_tag_2] 行动2：描述

# === systems.yaml ===
systems:
  combat:
    enabled: true
  skill:
    enabled: true
    book:
      - id: "strength"
        name: "力量"
        max_rank: 5
        attribute: "strength"
        passive: true
      - id: "stealth"
        name: "潜行"
        max_rank: 3
        attribute: "dexterity"
        passive: false
      - id: "persuade"
        name: "说服"
        max_rank: 3
        attribute: "charisma"
        passive: false
  equipment:
    enabled: true
    rarity_weights:
      common: 60
      uncommon: 25
      rare: 12
      epic: 3
```

## 重要规则

1. action_tag 必须是英文小写+下划线格式，全局唯一
2. hidden_value_actions 中的 action_tag 必须与 scenes 中出现的 action_tag 一一对应
3. 每个场景的 Available Actions 要有明确的叙事后果描述
4. NPC 描述要与世界观自洽
5. 至少包含 1 个终局场景（内容中包含 [ENDING] id: ending_id [/END]）
6. 场景数量要 >= num_main_scenes（含章节过渡场景）
7. 不要在 content 中出现 [GM_COMMAND] 块（那是运行时生成的）
8. 所有 JSON/YAML 必须语法正确

现在，根据以下设定和大纲生成剧本："""

    USER_PROMPT_TEMPLATE = """## 世界观设定
{setting}

## 剧情大纲
{outline}

## 生成要求
- 游戏ID: {game_id}
- 游戏名: {game_name}
- 类型: {genre}
- 章节数: {num_chapters}
- 主线场景数: {num_main_scenes}
- NPC数量: {num_npcs}

请严格按上述格式输出完整剧本内容。"""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        api_key: str = API_KEY,
        base_url: str = BASE_URL,
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 生成内容"""
        try:
            from anthropic import Anthropic
        except ImportError:
            try:
                from openai import OpenAI
            except ImportError:
                raise RuntimeError("需要安装 anthropic 或 openai 库")

        if "openai" in self.base_url.lower() or not self.base_url.startswith("https://api.anthropic"):
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=16000,
                temperature=0.8,
            )
            return response.choices[0].message.content
        else:
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model_name,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=16000,
            )
            return response.content[0].text

    def _parse_yaml_content(self, raw: str) -> dict:
        """从 LLM 输出中提取并解析 YAML"""
        # 尝试提取 ```yaml ... ``` 块
        yaml_match = re.search(r"```(?:yaml)?\s*(.*?)```", raw, re.DOTALL)
        if yaml_match:
            yaml_str = yaml_match.group(1)
        else:
            # 尝试提取 --- ... --- 块
            dash_match = re.search(r"---(?:\s*\n)?(.*?)(?:---|\Z)", raw, re.DOTALL)
            if dash_match:
                yaml_str = dash_match.group(1)
            else:
                yaml_str = raw

        # 预处理：移除可能的引导性文字
        lines = yaml_str.split("\n")
        clean_lines = []
        in_content = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# ===") or stripped.startswith("```"):
                continue
            if stripped.startswith("meta:") or stripped.startswith("setting:") or \
               stripped.startswith("characters:") or stripped.startswith("scenes:") or \
               stripped.startswith("systems:"):
                in_content = True
            if in_content:
                clean_lines.append(line)

        yaml_str = "\n".join(clean_lines)
        return yaml.safe_load(yaml_str)

    def generate(self, setting: str, outline: str, options: GenerationOptions) -> dict:
        """
        根据设定和大纲生成剧本。

        Returns:
            dict: {
                "game_id": str,
                "files": {
                    "meta.json": {...},
                    "setting.md": "...",
                    "characters/{id}.json": {...},
                    "scenes/{id}.md": "...",
                    "systems.yaml": {...},
                },
                "summary": str,
            }
        """
        user_prompt = self.USER_PROMPT_TEMPLATE.format(
            setting=setting,
            outline=outline,
            game_id=options.game_id,
            game_name=options.game_name,
            genre=options.genre,
            num_chapters=options.num_chapters,
            num_main_scenes=options.num_main_scenes,
            num_npcs=options.num_npcs,
        )

        raw = self._call_llm(user_prompt)
        data = self._parse_yaml_content(raw)

        files = {}

        # meta.json
        meta = data.get("meta", {})
        meta["engine_version"] = meta.get("engine_version", ENGINE_VERSION)
        files["meta.json"] = meta

        # setting.md
        setting_text = data.get("setting", "")
        if isinstance(setting_text, dict):
            setting_text = setting_text.get("content", str(setting_text))
        files["setting.md"] = setting_text

        # characters/*.json
        characters_data = data.get("characters", {})
        for npc_id, char_data in characters_data.items():
            files[f"characters/{npc_id}.json"] = char_data

        # scenes/*.md
        scenes_data = data.get("scenes", {})
        for scene_id, scene_data in scenes_data.items():
            content = scene_data.get("content", "")
            if isinstance(content, dict):
                content = content.get("content", str(content))
            title = scene_data.get("title", scene_id)
            files[f"scenes/{scene_id}.md"] = f"# {title}\n\n{content}"

        # systems.yaml
        systems = data.get("systems", {})
        files["systems.yaml"] = systems

        # hidden_value_actions 额外输出（从 meta 或单独字段提取）
        hv_actions = data.get("hidden_value_actions", {})
        if not hv_actions and "meta" in data:
            hv_actions = data["meta"].get("hidden_value_actions", {})

        return {
            "game_id": options.game_id,
            "files": files,
            "hidden_value_actions": hv_actions,
            "summary": meta.get("summary", ""),
            "raw_yaml_snippet": raw[:500],
        }

    def save_to_directory(self, generated: dict, output_dir: Path) -> Path:
        """
        将生成的剧本保存到目录。

        Returns: 剧本根目录路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        files = generated["files"]

        # meta.json
        with open(output_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(files["meta.json"], f, ensure_ascii=False, indent=2)

        # setting.md
        with open(output_dir / "setting.md", "w", encoding="utf-8") as f:
            f.write(files["setting.md"])

        # characters/
        chars_dir = output_dir / "characters"
        chars_dir.mkdir(exist_ok=True)
        for path, content in files.items():
            if path.startswith("characters/") and path.endswith(".json"):
                filename = Path(path).name
                with open(chars_dir / filename, "w", encoding="utf-8") as f:
                    json.dump(content, f, ensure_ascii=False, indent=2)

        # scenes/
        scenes_dir = output_dir / "scenes"
        scenes_dir.mkdir(exist_ok=True)
        for path, content in files.items():
            if path.startswith("scenes/") and path.endswith(".md"):
                filename = Path(path).name
                with open(scenes_dir / filename, "w", encoding="utf-8") as f:
                    f.write(content)

        # systems.yaml
        if "systems.yaml" in files:
            with open(output_dir / "systems.yaml", "w", encoding="utf-8") as f:
                yaml.dump(
                    files["systems.yaml"],
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                )

        # 更新 meta.json 中的 hidden_value_actions（如果生成时包含）
        if generated.get("hidden_value_actions"):
            meta_path = output_dir / "meta.json"
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            meta["hidden_value_actions"] = generated["hidden_value_actions"]
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

        return output_dir

    def generate_and_save(
        self,
        setting: str,
        outline: str,
        options: GenerationOptions,
        output_dir: Path,
    ) -> dict:
        """
        一站式生成并保存剧本。
        """
        result = self.generate(setting, outline, options)
        saved_path = self.save_to_directory(result, output_dir)
        result["saved_path"] = str(saved_path)
        return result
