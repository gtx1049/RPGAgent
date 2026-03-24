# core/context_builder.py - Prompt 构造器（db 模式兼容层）
"""
向后兼容模块。

core/prompt_builder.py 已重构为统一版（memory + db 双模式）。
本文件保留以确保现有导入链不断裂。

新代码请直接使用 core.prompt_builder.PromptBuilder。
"""

from core.prompt_builder import PromptBuilder

__all__ = ["PromptBuilder"]
