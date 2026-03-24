# config/settings.py - 全局配置
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 游戏剧本目录
GAMES_DIR = BASE_DIR / "games"

# 默认模型
DEFAULT_MODEL = os.getenv("RPG_MODEL", "gpt-4-turbo")

# API 配置
API_KEY = os.getenv("OPENAI_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

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

# Prompt 模板路径
PROMPT_TEMPLATES_DIR = BASE_DIR / "core" / "prompts"
