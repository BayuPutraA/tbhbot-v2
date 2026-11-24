"""
main.py - Main application entry point for Task Bar Hero.
Launches the high-performance Qt 6 Direct3D dashboard.
"""
import os
import sys

# Configure High-DPI scaling and suppress redundant QPA DPI warnings on Windows
if sys.platform == "win32":
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    rules = os.environ.get("QT_LOGGING_RULES", "")
    os.environ["QT_LOGGING_RULES"] = (rules + ";qt.qpa.window=false").strip(";")

from ui import TaskBarHeroApp, VisualDebuggerWindow, GEAR_NAMES, GEAR_ICONS, RARITIES_ORDER, LEVELS_ORDER

__all__ = [
    "TaskBarHeroApp",
    "VisualDebuggerWindow",
    "GEAR_NAMES",
    "GEAR_ICONS",
    "RARITIES_ORDER",
    "LEVELS_ORDER",
]

if __name__ == "__main__":
    app = TaskBarHeroApp()
    app.mainloop()
