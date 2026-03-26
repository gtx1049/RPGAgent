# config/settings.py - 全局配置
import os
import sys
from pathlib import Path

# 项目根目录（兼容开发模式和安装模式）
# 开发模式：rpgagent/config/settings.py → project_root/rpgagent/config/
# 安装模式：site-packages/rpgagent/config/ → 需要回退到 XDG_DATA_HOME
_package_root = Path(__file__).resolve().parent.parent
if (_package_root / "games").exists():
    BASE_DIR = _package_root          # 开发模式：games/ 在包旁边
else:
    # 安装模式：从 site-packages 回溯到项目根，或用 XDG_DATA_HOME
    _xdg = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    BASE_DIR = _xdg / "rpgagent"

# 游戏剧本目录（内置）
GAMES_DIR = BASE_DIR / "games"

# 用户安装剧本目录
USER_GAMES_DIR = BASE_DIR / "user_games"

# 默认模型
DEFAULT_MODEL = os.getenv("RPG_MODEL", "MiniMax-M2.7")

# 行动力I 配置（默认使用 MiniMax，与 OpenClaw 保持一致）
API_KEY = os.getenv("RPG_API_KEY", "sk-cp-5OUTq07g5SrIULP1U36OvVM6eK5JDwf8m_gXPhxinNCG1MMukWMefIyk_nAC-DnTQzKCEKpEQA5pmOTawYgnN9u2MXPBsD22N_gHGkkSMqyLsVK11IML01o")
BASE_URL = os.getenv("RPG_BASE_URL", "https://api.minimaxi.com/anthropic")

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
