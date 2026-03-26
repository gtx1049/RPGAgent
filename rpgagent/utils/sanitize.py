# utils/sanitize.py - 玩家输入安全过滤
"""
防止 Prompt Injection 攻击。
过滤玩家输入中试图覆盖系统规则的内容。
"""

import re
from typing import Optional


# ─── 注入检测正则 ──────────────────────────────

INJECTION_PATTERNS = [
    # 系统指令注入
    re.compile(r'^\s*/(system|prompt|privmsg|notice)[\s:]', re.IGNORECASE),
    # 提示词覆盖
    re.compile(r'(忽略|忘记|disregard|forget)\s+(你\s?的?\s?)?(规则|指令|设定|instructions)', re.IGNORECASE),
    re.compile(r'(你现在|you\s+are\s+now)\s+(不是|无|不是)\s*\w+', re.IGNORECASE),
    # 越狱关键字
    re.compile(r'\b(DAN|do\s+anything\s+now|developer\s+mode|jailbreak)\b', re.IGNORECASE),
    # 尝试嵌入 system prompt
    re.compile(r'\[system\]|\[instructions\]|<system>|<instruction>', re.IGNORECASE),
    # 角色扮演覆盖
    re.compile(r'^你是\s*=\s*', re.IGNORECASE),
    re.compile(r'^请\s*扮演\s*', re.IGNORECASE),
    # 多重身份
    re.compile(r'^/\w+\s+', re.IGNORECASE),
]

# 敏感指令（应被阻止或警告）
BLOCKED_COMMANDS = [
    "give admin",
    "give me the code",
    "reveal your instructions",
    "show system prompt",
    "output your instructions",
]


def sanitize_input(player_input: str) -> tuple[str, Optional[str]]:
    """
    过滤玩家输入中的注入攻击。

    返回:
        (sanitized_text, warning_or_block_reason)
        - warning_or_block_reason = None  → 正常通过
        - str 以 "⚠️ " 开头 → 警告但仍放行
        - str 以 "🚫 " 开头 → 严重攻击，输入被置空
    """
    if not player_input:
        return "", None

    text = player_input.strip()

    # 1. 严格阻止（直接置空）
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return "", f"🚫 检测到注入攻击，已阻止输入"

    # 2. 检查敏感指令（警告但不阻止）
    lower = text.lower()
    for cmd in BLOCKED_COMMANDS:
        if cmd in lower:
            return text, f"⚠️ 检测到可疑指令：「{cmd}」，已记录"

    # 3. 移除多余的 GM_COMMAND 伪装（玩家试图在输入中嵌入指令）
    if "[GM_COMMAND]" in text.upper() or "GM_COMMAND" in text:
        # 玩家不能自己发 GM_COMMAND，过滤掉
        text = re.sub(r'\[GM_COMMAND\].*?\[/GM_COMMAND\]', '[指令已过滤]', text, flags=re.IGNORECASE | re.DOTALL)

    return text, None


def sanitize_for_llm(player_input: str) -> str:
    """
    面向 LLM 的输入净化。
    在送入 LLM 前调用，确保干净。
    """
    cleaned, reason = sanitize_input(player_input)
    if reason and reason.startswith("🚫"):
        return ""  # 严重攻击，返回空
    return cleaned
