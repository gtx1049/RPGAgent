# systems/__init__.py
from .interface import (
    IStatsSystem,
    IMoralDebtSystem,
    IInventorySystem,
    IDialogueSystem,
    ICombatSystem,
)
from .stats import StatsSystem, Stats
from .combat import CombatSystem, CombatResult
from .moral_debt import MoralDebtSystem
from .inventory import InventorySystem, Item
from .dialogue import DialogueSystem, DialogueLine
from .hidden_value import HiddenValue, HiddenValueSystem, LevelEffect, HiddenValueRecord
from .image_generator import (
    ImageGenerator,
    TongyiWanxiangGenerator,
    CGCache,
    CGTriggerConfig,
    make_generator,
    generate_scene_cg,
)

__all__ = [
    # Interfaces
    "IStatsSystem",
    "IMoralDebtSystem",
    "IInventorySystem",
    "IDialogueSystem",
    "ICombatSystem",
    # Implementations
    "StatsSystem",
    "Stats",
    "CombatSystem",
    "CombatResult",
    "MoralDebtSystem",
    "InventorySystem",
    "Item",
    "DialogueSystem",
    "DialogueLine",
    # New
    "HiddenValue",
    "HiddenValueSystem",
    "LevelEffect",
    "HiddenValueRecord",
    # Image Generator
    "ImageGenerator",
    "TongyiWanxiangGenerator",
    "CGCache",
    "CGTriggerConfig",
    "make_generator",
    "generate_scene_cg",
]
