# systems/scenario_validator.py - 剧本验证器
"""
在打包或发布前，对剧本进行全面校验，提前发现结构性问题。

检查项：
1. meta.json 必填字段 + 格式校验
2. setting.md 存在性
3. 场景 ID 格式合法（字母/数字/-/_）
4. 场景 frontmatter title 非空
5. 角色 ID 格式合法
6. 角色 JSON 语法合法
7. first_scene 引用的场景是否存在
8. 场景内引用的角色 ID 是否在 characters/ 中定义
9. 场景内引用的跳转场景 ID 是否在 scenes/ 中存在
10. 重复 ID 检测（场景之间、角色之间）
11. 孤立场景检测（没有任何入口的场景）
12. 触发器格式校验（scene_trigger 引擎）

使用方式：
    from rpgagent.systems.scenario_validator import ScenarioValidator
    validator = ScenarioValidator(game_path)
    report = validator.validate()
    for issue in report.issues:
        print(f"[{issue.severity}] {issue.rule}: {issue.message}")
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ─── 异常级别 ─────────────────────────────────────────


class Severity:
    ERROR = "error"      # 阻止打包/发布
    WARNING = "warning"  # 警告但可放行
    INFO = "info"       # 建议


@dataclass
class Issue:
    rule: str
    severity: str
    message: str
    file: Optional[str] = None      # e.g. "scenes/act_01.md"
    line: Optional[int] = None


@dataclass
class ValidationReport:
    game_id: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """无 ERROR 级别 issue 即为有效"""
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    def summary(self) -> str:
        ok = "✅ 校验通过" if self.is_valid else "❌ 校验失败"
        return f"{ok}（{self.error_count} 错误，{self.warning_count} 警告）"


# ─── 场景 frontmatter 解析 ───────────────────────────


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(content: str) -> dict:
    """解析 YAML frontmatter，返回键值对字典"""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    raw = m.group(1)
    result = {}
    for line in raw.split("\n"):
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def _strip_frontmatter(content: str) -> str:
    """去掉 frontmatter，返回正文"""
    return _FRONTMATTER_RE.sub("", content).strip()


# ─── 场景内容引用提取 ─────────────────────────────────


_CHAR_REF_RE = re.compile(r"@char:([a-zA-Z0-9_-]+)", re.IGNORECASE)
_SCENE_REF_RE = re.compile(r"@scene:([a-zA-Z0-9_-]+)", re.IGNORECASE)


def _extract_refs(content: str) -> tuple[set[str], set[str]]:
    """从内容中提取引用的角色 ID 和场景 ID"""
    chars = set(_CHAR_REF_RE.findall(content))
    scenes = set(_SCENE_REF_RE.findall(content))
    return chars, scenes


# ─── 触发器解析 ──────────────────────────────────────


_TRIGGER_BLOCK_RE = re.compile(r"```ya?ml\s*\n?(triggers:.*?)```", re.IGNORECASE | re.DOTALL)


def _parse_triggers(content: str) -> list[dict]:
    """从内容中提取 triggers YAML 块"""
    blocks = _TRIGGER_BLOCK_RE.findall(content)
    triggers = []
    for block in blocks:
        try:
            import yaml
            data = yaml.safe_load(block)
            if isinstance(data, dict) and "triggers" in data:
                triggers.extend(data["triggers"])
            elif isinstance(data, dict):
                triggers.append(data)
        except Exception:
            pass
    return triggers


# ─── 主验证器 ─────────────────────────────────────────


class ScenarioValidator:
    """
    对剧本目录进行全面校验。
    """

    # 允许的角色文件扩展名
    VALID_CHAR_EXTS = {".json"}
    # 允许的场景文件扩展名
    VALID_SCENE_EXTS = {".md", ".txt"}

    def __init__(self, game_path: str | Path):
        self.game_path = Path(game_path)

    # ── 公共接口 ─────────────────────────────────────

    def validate(self) -> ValidationReport:
        """
        执行全量校验，返回报告。
        """
        issues: list[Issue] = []
        game_id = self.game_path.name

        # 1. meta.json
        issues.extend(self._validate_meta())

        # 2. setting.md
        issues.extend(self._validate_setting())

        # 3. scenes/ 结构
        scene_ids: set[str] = set()
        scene_refs_map: dict[str, tuple[set[str], set[str]]] = {}  # scene_id -> (char_refs, scene_refs)
        issues.extend(self._validate_scenes(scene_ids, scene_refs_map))

        # 4. characters/ 结构
        char_ids: set[str] = set()
        issues.extend(self._validate_characters(char_ids))

        # 5. first_scene 引用
        issues.extend(self._validate_first_scene(scene_ids))

        # 6. 跨场景引用校验（角色）
        issues.extend(self._validate_char_refs(char_ids, scene_refs_map))

        # 7. 跨场景引用校验（场景跳转）
        issues.extend(self._validate_scene_refs(scene_ids, scene_refs_map))

        # 8. 孤立场景检测
        issues.extend(self._detect_orphan_scenes(scene_ids, scene_refs_map))

        # 9. 重复 ID 检测
        issues.extend(self._detect_duplicate_ids())

        return ValidationReport(game_id=game_id, issues=issues)

    # ── 子校验步骤 ───────────────────────────────────

    def _validate_meta(self) -> list[Issue]:
        issues: list[Issue] = []
        meta_file = self.game_path / "meta.json"

        if not meta_file.exists():
            issues.append(Issue(
                rule="meta_missing",
                severity=Severity.ERROR,
                message="缺少 meta.json 文件",
                file="meta.json",
            ))
            return issues

        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            issues.append(Issue(
                rule="meta_json_invalid",
                severity=Severity.ERROR,
                message=f"meta.json JSON 格式错误：{e}",
                file="meta.json",
            ))
            return issues

        # 必填字段
        for field in ("id", "name"):
            if not meta.get(field):
                issues.append(Issue(
                    rule="meta_field_required",
                    severity=Severity.ERROR,
                    message=f"meta.json 缺少必填字段：{field}",
                    file="meta.json",
                ))

        # id 格式
        if meta.get("id") and not re.match(r"^[a-zA-Z0-9_-]+$", meta["id"]):
            issues.append(Issue(
                rule="meta_id_format",
                severity=Severity.ERROR,
                message=f"id '{meta['id']}' 包含非法字符，只允许字母/数字/-/_",
                file="meta.json",
            ))

        # version 格式（semver 简化）
        version = meta.get("version", "1.0")
        if not re.match(r"^\d+\.\d+(\.\d+)?$", str(version)):
            issues.append(Issue(
                rule="meta_version_format",
                severity=Severity.WARNING,
                message=f"version '{version}' 格式不规范，建议使用 semver 如 '1.0.0'",
                file="meta.json",
            ))

        # first_scene 存在性（如果指定了的话）
        first = meta.get("first_scene")
        if first:
            scenes_dir = self.game_path / "scenes"
            if scenes_dir.exists():
                scene_files = {p.stem for p in scenes_dir.glob("*.md")}
                if first not in scene_files:
                    issues.append(Issue(
                        rule="first_scene_missing",
                        severity=Severity.WARNING,
                        message=f"first_scene '{first}' 指向的场景不存在",
                        file="meta.json",
                    ))

        return issues

    def _validate_setting(self) -> list[Issue]:
        issues: list[Issue] = []
        setting_file = self.game_path / "setting.md"
        if not setting_file.exists():
            issues.append(Issue(
                rule="setting_missing",
                severity=Severity.WARNING,
                message="缺少 setting.md 文件（世界观设定）",
                file="setting.md",
            ))
        return issues

    def _validate_scenes(
        self,
        scene_ids: set[str],
        scene_refs_map: dict[str, tuple[set[str], set[str]]],
    ) -> list[Issue]:
        issues: list[Issue] = []
        scenes_dir = self.game_path / "scenes"

        if not scenes_dir.exists():
            issues.append(Issue(
                rule="scenes_dir_missing",
                severity=Severity.ERROR,
                message="缺少 scenes/ 目录",
                file="scenes/",
            ))
            return issues

        seen_ids: set[str] = set()
        for scene_file in sorted(scenes_dir.iterdir()):
            if scene_file.suffix not in self.VALID_SCENE_EXTS:
                issues.append(Issue(
                    rule="scene_ext_invalid",
                    severity=Severity.WARNING,
                    message=f"场景文件扩展名非标准：{scene_file.suffix}（建议 .md）",
                    file=f"scenes/{scene_file.name}",
                ))
                continue

            scene_id = scene_file.stem
            rel_path = f"scenes/{scene_file.name}"

            # ID 格式
            if not re.match(r"^[a-zA-Z0-9_-]+$", scene_id):
                issues.append(Issue(
                    rule="scene_id_format",
                    severity=Severity.ERROR,
                    message=f"场景 ID '{scene_id}' 包含非法字符，只允许字母/数字/-/_",
                    file=rel_path,
                ))

            # 重复 ID
            if scene_id in seen_ids:
                issues.append(Issue(
                    rule="scene_id_duplicate",
                    severity=Severity.ERROR,
                    message=f"场景 ID 重复：{scene_id}",
                    file=rel_path,
                ))
            seen_ids.add(scene_id)
            scene_ids.add(scene_id)

            # 内容检查
            try:
                content = scene_file.read_text(encoding="utf-8")
            except Exception as e:
                issues.append(Issue(
                    rule="scene_read_error",
                    severity=Severity.ERROR,
                    message=f"文件读取失败：{e}",
                    file=rel_path,
                ))
                continue

            if not content.strip():
                issues.append(Issue(
                    rule="scene_empty",
                    severity=Severity.WARNING,
                    message=f"场景文件为空",
                    file=rel_path,
                ))
                continue

            # frontmatter title
            fm = _parse_frontmatter(content)
            if not fm.get("title"):
                issues.append(Issue(
                    rule="scene_title_missing",
                    severity=Severity.WARNING,
                    message="frontmatter 缺少 title 字段",
                    file=rel_path,
                ))

            # 提取引用
            body = _strip_frontmatter(content)
            char_refs, scene_refs = _extract_refs(body)
            scene_refs_map[scene_id] = (char_refs, scene_refs)

            # 触发器格式
            triggers = _parse_triggers(content)
            for t in triggers:
                if not isinstance(t, dict):
                    issues.append(Issue(
                        rule="trigger_format",
                        severity=Severity.WARNING,
                        message=f"触发器格式异常（非 dict）：{t}",
                        file=rel_path,
                    ))

        return issues

    def _validate_characters(self, char_ids: set[str]) -> list[Issue]:
        issues: list[Issue] = []
        chars_dir = self.game_path / "characters"

        if not chars_dir.exists():
            # characters/ 是可选的
            return issues

        seen_ids: set[str] = set()
        for char_file in sorted(chars_dir.iterdir()):
            if char_file.suffix not in self.VALID_CHAR_EXTS:
                issues.append(Issue(
                    rule="char_ext_invalid",
                    severity=Severity.ERROR,
                    message=f"角色文件扩展名非法：{char_file.suffix}（只允许 .json）",
                    file=f"characters/{char_file.name}",
                ))
                continue

            char_id = char_file.stem
            rel_path = f"characters/{char_file.name}"

            # ID 格式
            if not re.match(r"^[a-zA-Z0-9_-]+$", char_id):
                issues.append(Issue(
                    rule="char_id_format",
                    severity=Severity.ERROR,
                    message=f"角色 ID '{char_id}' 包含非法字符，只允许字母/数字/-/_",
                    file=rel_path,
                ))

            # 重复 ID
            if char_id in seen_ids:
                issues.append(Issue(
                    rule="char_id_duplicate",
                    severity=Severity.ERROR,
                    message=f"角色 ID 重复：{char_id}",
                    file=rel_path,
                ))
            seen_ids.add(char_id)
            char_ids.add(char_id)

            # JSON 有效性
            try:
                data = json.loads(char_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                issues.append(Issue(
                    rule="char_json_invalid",
                    severity=Severity.ERROR,
                    message=f"JSON 格式错误：{e}",
                    file=rel_path,
                ))
                continue

            # name 字段
            if not data.get("name"):
                issues.append(Issue(
                    rule="char_name_missing",
                    severity=Severity.WARNING,
                    message="角色 JSON 缺少 'name' 字段",
                    file=rel_path,
                ))

            # role 字段合法性
            valid_roles = {"npc", "enemy", "teammate", "neutral"}
            role = data.get("role", "npc")
            if role not in valid_roles:
                issues.append(Issue(
                    rule="char_role_unknown",
                    severity=Severity.WARNING,
                    message=f"role '{role}' 不是预定义值（{valid_roles}）",
                    file=rel_path,
                ))

        return issues

    def _validate_first_scene(self, scene_ids: set[str]) -> list[Issue]:
        issues: list[Issue] = []
        meta_file = self.game_path / "meta.json"
        if not meta_file.exists():
            return issues

        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            return issues

        first = meta.get("first_scene")
        if first and scene_ids and first not in scene_ids:
            issues.append(Issue(
                rule="first_scene_missing",
                severity=Severity.ERROR,
                message=f"first_scene '{first}' 不存在于 scenes/ 目录",
                file="meta.json",
            ))
        return issues

    def _validate_char_refs(
        self,
        char_ids: set[str],
        scene_refs_map: dict[str, tuple[set[str], set[str]]],
    ) -> list[Issue]:
        issues: list[Issue] = []
        if not char_ids:
            return issues

        for scene_id, (char_refs, _) in scene_refs_map.items():
            for ref in char_refs:
                if ref not in char_ids:
                    issues.append(Issue(
                        rule="char_ref_missing",
                        severity=Severity.ERROR,
                        message=f"场景引用了角色 '{ref}'，但该角色在 characters/ 中不存在",
                        file=f"scenes/{scene_id}.md",
                    ))
        return issues

    def _validate_scene_refs(
        self,
        scene_ids: set[str],
        scene_refs_map: dict[str, tuple[set[str], set[str]]],
    ) -> list[Issue]:
        issues: list[Issue] = []
        if not scene_ids:
            return issues

        for scene_id, (_, scene_refs) in scene_refs_map.items():
            for ref in scene_refs:
                if ref not in scene_ids:
                    issues.append(Issue(
                        rule="scene_ref_missing",
                        severity=Severity.WARNING,
                        message=f"场景引用了跳转目标 '{ref}'，但该场景不存在",
                        file=f"scenes/{scene_id}.md",
                    ))
        return issues

    def _detect_orphan_scenes(
        self,
        scene_ids: set[str],
        scene_refs_map: dict[str, tuple[set[str], set[str]]],
    ) -> list[Issue]:
        """
        孤立场景：没有任何入口（未被任何场景引用，且不是 first_scene）的场景。
        """
        issues: list[Issue] = []
        if not scene_ids:
            return issues

        # 收集所有被引用的场景
        referenced = set()
        for _, (_, scene_refs) in scene_refs_map.items():
            referenced.update(scene_refs)

        # 检查 first_scene
        meta_file = self.game_path / "meta.json"
        first_scene = None
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                first_scene = meta.get("first_scene")
            except Exception:
                pass

        orphans = scene_ids - referenced
        if first_scene and first_scene in orphans:
            orphans.discard(first_scene)

        for orphan in sorted(orphans):
            issues.append(Issue(
                rule="scene_orphan",
                severity=Severity.INFO,
                message=f"场景 '{orphan}' 无入口（无场景跳转到它，也非 first_scene），可能是孤立场景",
                file=f"scenes/{orphan}.md",
            ))

        return issues

    def _detect_duplicate_ids(self) -> list[Issue]:
        """检测场景 ID 与角色 ID 之间的冲突（不允许重名）"""
        issues: list[Issue] = []
        scene_ids = set()
        char_ids = set()

        scenes_dir = self.game_path / "scenes"
        if scenes_dir.exists():
            scene_ids = {p.stem for p in scenes_dir.glob("*.md")}

        chars_dir = self.game_path / "characters"
        if chars_dir.exists():
            char_ids = {p.stem for p in chars_dir.glob("*.json")}

        overlap = scene_ids & char_ids
        for dup in sorted(overlap):
            issues.append(Issue(
                rule="id_conflict",
                severity=Severity.ERROR,
                message=f"场景 ID 与角色 ID 冲突：'{dup}' 同时存在于 scenes/ 和 characters/",
            ))

        return issues
