# config/settings.py - 全局配置
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 游戏剧本目录
GAMES_DIR = BASE_DIR / "games"

# 默认模型
DEFAULT_MODEL = os.getenv("RPG_MODEL", "MiniMax-M2.7")

# API 配置（默认使用 MiniMax，与 OpenClaw 保持一致）
API_KEY = os.getenv("RPG_API_KEY", "sk-cp-5OUTq07g5SrIULP1U36OvVM6eK5JDwf8m_gXPhxinNCG1MMukWMefIyk_nAC-DnTQzKCEKpEQA5pmOTawYgnN9u2MXPBsD22N_gHGkkSMqyLsVK11IML01o")
BASE_URL = os.getenv("RPG_BASE_URL", "https://api.minimaxi.com/anthropic")

# 游戏设置
DEFAULT_PLAYER_NAME = "玩家"
MAX_CONTEXT_LENGTH = 128000  # 上下文上限（token）

# API 服务器
HOST = "0.0.0.0"
PORT = 7860

# 数值系统默认值
DEFAULT_STATS = {
    "hp": 100,
    "max_hp": 100,
    "stamina": 100,
    "max_stamina": 100,
    "strength": 10,
    "agility": 10,
    "intelligence": 10,
    "charisma": 10,
}

DEFAULT_MORAL_DEBT = 0  # 道德债务初始值

# 战斗系统
COMBAT_DICE = 20  # d20 系统
DIFFICULTY_EASY = 10
DIFFICULTY_MEDIUM = 15
DIFFICULTY_HARD = 20
