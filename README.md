# Task Bar Hero (TBH) — Chest & Hero-dric Cube Synthesizer

A Windows desktop automation application built with **Python**, **CustomTkinter**, and **OpenCV** designed to automate Chest Opening and Hero-dric Cube Gear Synthesis in *Task Bar Hero* on a scheduled 2-hour interval.

---

## Features

- **Automated Chest Opening:**
  - Multi-template matching against `chest_stack.png`, `chest_single.png`, and `chest.png` with configurable confidence threshold (default `0.72`).
  - **Double-Check Verification:** If no chest is detected on the initial frame, performs 2 extra clicks on the last known chest position, waits 500ms for animations/loot popups to clear, and re-captures the screen 2 more times (300ms apart) to guarantee single remaining chests are never missed.
- **Badge-Anchored Inventory Scanning (7-Column Support):**
  - Anchors detection on level text badges (`Lv.65`, `Lv.80`, `Lv.90`) via template matching with Non-Maximum Suppression (threshold `0.80`).
  - Automatically rejects partially clipped rows (must have at least 36px space above the badge inside the ROI).
  - Inspects the 44x44 item slot box above each badge along the inner border (avoiding center sprite and bottom-right indicators) to classify rarity into `Common`, `Uncommon`, `Rare`, and `Legendary`.
- **Two-Pass Scroll-and-Select Workflow:**
  - **Pass 1:** Resets scroll to top (15 scroll ticks UP), performs a full scroll-down pass, and computes deduplicated item counts using vertical template alignment (phase correlation) and scrollbar bottom detection.
  - **Pass 2:** For each eligible bucket with $\ge 9$ items, sets the Cube Tier Dropdown (`Lv.65~80` or `Lv.80~90`), scrolls from top, live-clicks the 9 matching item coordinates, and clicks the Synthesize button to the right of Auto Fill.
- **Safety & Control:**
  - **F8 Emergency Stop:** Global background hotkey immediately stops all automation.
  - **Physical Mouse Activity Monitor:** Pauses and waits 5 seconds if physical user mouse movement is detected before taking control.
  - **Always on Top:** Keeps the dashboard visible over the game.
- **Calibration Wizard & Dry-Run Testing (Tab 2):**
  - Live slider for Chest Match Confidence (`0.60` to `0.90`).
  - Snip buttons for Single / Stack Chests, Cube Level Dropdown, Synthesize Button, and Level Badges.
  - **"📜 Test Inventory Scroll Scan (Dry Run)"**: One-click test button to scroll and log all detected items without clicking or synthesizing.

---

## Quick Start

1. Double-click **`run_bot.bat`** to start the application.
2. The modern dark-mode GUI dashboard will launch.
3. Switch to the **"Screen Calibrator & Templates"** tab if you wish to calibrate ROIs or customize templates for your screen resolution:
   - Click **Snip Chest ROI** and drag a rectangle over the chest area.
   - Click **Snip Inventory Grid** and drag over your inventory grid.
   - Click **Sample Pixel** under Rarity Colors to sample your in-game borders.
4. On the **"Automation Dashboard"** tab:
   - Click **"▶ Start 2-Hour Auto Loop"** to run automatically every 2 hours, or
   - Click **"⚡ Run Cycle Now"** to test an immediate run.
   - Press **`F8`** at any time to abort immediately.

---

## File Structure

```
e:\TBH_bot\
├── main.py                     # CustomTkinter GUI dashboard & Calibrator tab
├── bot_engine.py               # 2-Hour scheduler, state machine, input automation & safety
├── vision.py                   # MSS capture, OpenCV matching, HSV rarity analyzer, lock check
├── calibrator.py               # Fullscreen crosshair snipping overlay & color picker
├── generate_default_assets.py  # Reference asset generator
├── config.json                 # Coordinates, HSV tolerances, timers & grid dimensions
├── run_bot.bat                 # Windows one-click launcher
├── requirements.txt            # Python dependencies
└── assets/                     # Cropped UI templates & level badges
```
