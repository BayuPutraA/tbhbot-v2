"""
vision.py - Backwards-compatibility bridge for Task Bar Hero.
Re-exports VisionEngine and TEMPLATE_MANIFEST from the modular vision package.
"""
from vision import VisionEngine, TEMPLATE_MANIFEST

__all__ = ["VisionEngine", "TEMPLATE_MANIFEST"]
