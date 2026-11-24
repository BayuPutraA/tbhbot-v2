"""
UI Package for Task Bar Hero.
Exports the high-performance Qt 6 dashboard app, visual debugger, and UI constants.
"""
from .qt_app import TaskBarHeroQtApp, TaskBarHeroQtApp as TaskBarHeroApp, GEAR_NAMES, GEAR_ICONS, RARITIES_ORDER, LEVELS_ORDER
from .qt_visual_debugger import QtVisualDebugger, QtVisualDebugger as VisualDebuggerWindow

def __getattr__(name: str):
    if name == "TaskBarHeroTkApp":
        from .app import TaskBarHeroApp
        return TaskBarHeroApp
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "TaskBarHeroApp",
    "TaskBarHeroQtApp",
    "TaskBarHeroTkApp",
    "VisualDebuggerWindow",
    "QtVisualDebugger",
    "GEAR_NAMES",
    "GEAR_ICONS",
    "RARITIES_ORDER",
    "LEVELS_ORDER",
]
