"""
generate_default_assets.py - Creates reference placeholder templates in assets/
ensuring all required template files exist out-of-the-box.
"""

import os
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = "assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

def create_badge(filename, text, bg_color=(40, 40, 40), fg_color=(255, 255, 255), size=(48, 48)):
    img = Image.new("RGBA", size, bg_color)
    draw = ImageDraw.Draw(img)
    # Draw border
    draw.rectangle([0, 0, size[0]-1, size[1]-1], outline=(100, 100, 100), width=1)
    
    # Try default font
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size[0] - tw) // 2
    ty = (size[1] - th) // 2
    draw.text((tx, ty), text, fill=fg_color, font=font)
    
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        img.save(path)
        print(f"Created {path}")
    else:
        print(f"Preserved existing {path}")

# Core UI templates (Exact 15-asset manifest + optional lv90)
templates = [
    # Navigation & Chests
    ("chest_btn.png", "CHEST_BTN", (90, 50, 20), (255, 215, 0), (48, 48)),
    ("chest_pile.png", "CHEST_PILE", (139, 69, 19), (255, 215, 0), (52, 52)),
    ("empty_floor.png", "EMPTY_FLR", (30, 30, 30), (100, 100, 100), (48, 48)),
    ("inv_full.png", "INV_FULL", (180, 20, 20), (255, 255, 255), (64, 24)),
    ("inv_tab_btn.png", "INV_TAB", (200, 100, 20), (255, 255, 255), (64, 26)),

    # Cube Controls
    ("cube_btn.png", "CUBE_BTN", (70, 30, 90), (200, 180, 255), (48, 48)),
    ("tier_dropdown.png", "TIER_DROP", (50, 50, 70), (255, 255, 255), (80, 26)),
    ("tier_65_80.png", "Lv.65~80", (30, 70, 50), (100, 255, 180), (60, 28)),
    ("tier_80_90.png", "Lv.80~90", (30, 50, 90), (120, 200, 255), (60, 28)),
    ("synth_btn.png", "SYNTH_BTN", (20, 120, 40), (255, 255, 255), (76, 28)),

    # Item Detection (White & Red equip-restriction variants)
    ("lv65_white.png", "Lv.65", (20, 40, 60), (255, 255, 255), (28, 14)),
    ("lv65_red.png", "Lv.65", (80, 20, 20), (255, 255, 255), (28, 14)),
    ("lv80_white.png", "Lv.80", (25, 45, 65), (255, 255, 255), (28, 14)),
    ("lv80_red.png", "Lv.80", (85, 20, 20), (255, 255, 255), (28, 14)),
    ("lv90_white.png", "Lv.90", (25, 45, 65), (255, 255, 255), (28, 14)),
    ("lv90_red.png", "Lv.90", (85, 20, 20), (255, 255, 255), (28, 14)),
    ("lock_icon.png", "LOCK", (50, 50, 50), (255, 80, 80), (24, 24)),

    # Aliases/legacy support
    ("chest.png", "CHEST", (139, 69, 19), (255, 215, 0), (52, 52)),
    ("chest_stack.png", "STACK", (139, 69, 19), (255, 215, 0), (48, 48)),
    ("chest_single.png", "SINGLE", (120, 60, 20), (240, 200, 0), (44, 44)),
    ("chest_empty.png", "EMPTY", (30, 30, 30), (100, 100, 100), (48, 48)),
    ("inventory_full.png", "FULL", (180, 20, 20), (255, 255, 255), (64, 24)),
    ("cube_dropdown.png", "TIER v", (50, 50, 70), (255, 255, 255), (80, 26)),
    ("cube_synth_btn.png", "SYNTH", (20, 120, 40), (255, 255, 255), (76, 28)),
    ("synth_tab.png", "SYNTH", (40, 60, 80), (255, 255, 255), (64, 28)),
    ("synth_confirm.png", "PROCEED", (20, 100, 40), (255, 255, 255), (72, 32)),
    ("lv65.png", "Lv.65", (20, 40, 60), (255, 255, 255), (28, 14)),
    ("lv80.png", "Lv.80", (25, 45, 65), (255, 255, 255), (28, 14)),
    ("lv90.png", "Lv.90", (25, 45, 65), (255, 255, 255), (28, 14)),
]

for filename, text, bg, fg, sz in templates:
    create_badge(filename, text, bg, fg, sz)

print("Template manifest checked successfully!")
