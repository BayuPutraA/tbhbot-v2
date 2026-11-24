"""
bot_engine.py - Backwards-compatibility bridge for Task Bar Hero.
Re-exports BotEngine from the modular core package.
"""
from core import BotEngine

__all__ = ["BotEngine"]
