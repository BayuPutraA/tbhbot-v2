"""
Core automation package for Task Bar Hero.
"""
from .engine import BotEngine
from .actions import InputActions
from .scheduler import CycleScheduler
from .synthesis import SynthesisManager
from .telegram_watchdog import TelegramWatchdog, TelegramClient

__all__ = [
    "BotEngine",
    "InputActions",
    "CycleScheduler",
    "SynthesisManager",
    "TelegramWatchdog",
    "TelegramClient",
]
