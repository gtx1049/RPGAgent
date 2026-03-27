# config/settings.py - 全局配置
import os
import sys
from pathlib import Path

# 项目根目录（兼容开发模式和安装模式）
# 开发模式：rpgagent/config/settings.py → project_root/rpgagent/config/
# 安装模式：site-packages/rpgagent/config/ → 需要回退到 XDG_DATA_HOME
_package_root = Path(__file__).resolve().parent.parent

# 环境变量优先（Docker / 容器部署时直接指定）
if os.getenv("RPGAGENT_BASE"):
    BASE_DIR = Path(os.getenv("RPGAGENT_BASE"))
else:
    # 开发模式判断：在 rpgagent/ 上两层存在 games/ 目录
    _project_root_dev = _package_root.parent
    if (_project_root_dev / "games").exists():
        BASE_DIR = _project_root_dev       # 开发模式：games/ 在包旁边
    else:
        # 安装模式：从 site-packages 回退到项目根，或用 XDG_DATA_HOME
        _xdg = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        BASE_DIR = _xdg / "rpgagent"

# 游戏剧本目录（内置）
GAMES_DIR = BASE_DIR / "games"

# 用户安装剧本目录
USER_GAMES_DIR = BASE_DIR / "user_games"

# 默认模型（优先读取 OPENAI_MODEL，兼容旧 RPG_MODEL）
DEFAULT_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("RPG_MODEL") or "MiniMax-M2.7"

# LLM API 配置
# 环境变量（与 .env.example 保持一致）：
#   OPENAI_API_KEY  - API 密钥（必填）
#   OPENAI_BASE_URL - API 地址（默认 https://api.openai.com/v1）
#   RPG_MODEL       - 模型名称（默认 MiniMax-M2.7）
API_KEY = os.getenv("OPENAI_API_KEY", "")
if not API_KEY:
    # 尝试旧变量名（兼容已有配置）
    API_KEY = os.getenv("RPG_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
if not BASE_URL or BASE_URL == "https://api.openai.com/v1":
    # 尝试旧变量名（兼容已有配置）
    _legacy = os.getenv("RPG_BASE_URL", "")
    if _legacy:
        BASE_URL = _legacy

# 游戏设置
DEFAULT_PLAYER_NAME = "玩家"
MAX_CONTEXT_LENGTH = 128000  # 上下文上限（token）

# 行动力I 服务器
HOST = "0.0.0.0"
PORT = 7860

# 数值系统默认值
DEFAULT_STATS = {
    "hp": 100,
    "max_hp": 100,
    "stamina": 100,
    "max_stamina": 100,
    "action_power": 3,
    "max_action_power": 3,
    "level": 1,
    "exp": 0,
    "exp_to_level": 100,
    # D&D 六属性
    "strength": 10,      # 力量
    "dexterity": 10,    # 敏捷
    "constitution": 10,  # 体质
    "intelligence": 10,  # 智力
    "wisdom": 10,       # 感知
    "charisma": 10,     # 魅力
}

DEFAULT_MORAL_DEBT = 0  # 道德债务初始值

# 行动力系统
DEFAULT_ACTION_POWER = 3  # 每回合行动力

# 战斗系统
COMBAT_DICE = 20  # d20 系统
DIFFICULTY_EASY = 10
DIFFICULTY_MEDIUM = 15
DIFFICULTY_HARD = 20

# ─── 文生图 CG 系统 ─────────────────────────────────────────────────
# 环境变量：TONGYI_API_KEY

IMAGE_GENERATOR_CACHE_DIR = Path.home() / ".cache" / "rpgagent" / "cg"
IMAGE_GENERATOR_DEFAULT_PROVIDER = "tongyi"
IMAGE_GENERATOR_DEFAULT_STYLE = "fantasy illustration, dark atmosphere, high quality"
IMAGE_GENERATOR_ENABLED = os.getenv("TONGYI_API_KEY", "") != ""


# ─── 引擎版本兼容性 ───────────────────────────────────────────────

ENGINE_VERSION = __version__ = "0.2.0"


def check_engine_version(required: str | None) -> tuple[bool, str]:
    """
    检查引擎版本是否满足剧本要求的最低版本。

    Args:
        required: 剧本要求的最低引擎版本字符串（如 "0.2" 或 "0.2.0"）

    Returns:
        (is_compatible, message)
        - is_compatible=True  表示兼容
        - is_compatible=False 表示不兼容，message 说明原因
    """
    if not required:
        return True, ""

    req_parts = required.split(".")
    installed_parts = ENGINE_VERSION.split(".")

    # 补齐长度
    while len(req_parts) < len(installed_parts):
        req_parts.append("0")
    while len(installed_parts) < len(req_parts):
        installed_parts.append("0")

    for req_part, inst_part in zip(req_parts, installed_parts):
        try:
            req_num = int(req_part)
            inst_num = int(inst_part)
        except ValueError:
            # 非数字部分不比较（向后兼容 "0.2beta" 等）
            continue
        if inst_num < req_num:
            return False, (
                f"引擎版本不满足要求：当前 {ENGINE_VERSION}，剧本要求 >= {required}。"
                f"请更新 RPGAgent 至最新版本。"
            )
    return True, ""
