"""
calibrator.py - Interactive Screen-Snipping & Calibration Overlay for Task Bar Hero
Allows user to visually calibrate Regions of Interest (ROIs), crop template images,
and sample rarity border colors with a live fullscreen crosshair overlay.
"""

import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import numpy as np
import mss
from PIL import Image, ImageTk
from typing import Optional, Callable, Dict, Any, Tuple


class ScreenSnipperOverlay:
    """
    High-precision fullscreen snipping overlay.
    Freezes the screen with a slight tint, displays crosshairs,
    and supports rectangle cropping or single-pixel color picking.
    """
    def __init__(
        self,
        mode: str = "roi",  # 'roi', 'template', or 'color_picker'
        title: str = "Select Region",
        template_filename: Optional[str] = None,
        rarity_target: Optional[str] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        config_path: str = "config.json",
        assets_dir: str = "assets"
    ):
        self.mode = mode
        self.title_text = title
        self.template_filename = template_filename
        self.rarity_target = rarity_target
        self.on_complete = on_complete
        self.config_path = config_path
        self.assets_dir = assets_dir

        os.makedirs(self.assets_dir, exist_ok=True)

        # 1. Capture pristine screenshot before launching overlay
        self.mon_left = 0
        self.mon_top = 0
        self.mon_width = 1920
        self.mon_height = 1080
        screenshot_captured = False

        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                self.mon_left = mon["left"]
                self.mon_top = mon["top"]
                self.mon_width = mon["width"]
                self.mon_height = mon["height"]
                raw_shot = sct.grab(mon)
                self.clean_bgr = cv2.cvtColor(np.array(raw_shot), cv2.COLOR_BGRA2BGR)
                screenshot_captured = True
        except Exception:
            pass

        if not screenshot_captured:
            try:
                from PIL import ImageGrab
                pil_shot = ImageGrab.grab()
                self.mon_width, self.mon_height = pil_shot.size
                self.clean_bgr = cv2.cvtColor(np.array(pil_shot), cv2.COLOR_RGB2BGR)
                screenshot_captured = True
            except Exception:
                # Fallback to dark canvas if desktop is locked
                self.clean_bgr = np.zeros((self.mon_height, self.mon_width, 3), dtype=np.uint8)
                self.clean_bgr[:] = (30, 30, 40)

        self.clean_rgb = cv2.cvtColor(self.clean_bgr, cv2.COLOR_BGR2RGB)

        # Create dimmed version for display
        dimmed_rgb = cv2.addWeighted(self.clean_rgb, 0.75, np.zeros_like(self.clean_rgb), 0.25, 0)
        self.display_pil = Image.fromarray(dimmed_rgb)

        # 2. Build Fullscreen Borderless Window
        self.root = tk.Toplevel()
        self.root.title("Screen Calibration Overlay")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.mon_width}x{self.mon_height}+{self.mon_left}+{self.mon_top}")
        self.root.config(cursor="cross")

        self.canvas = tk.Canvas(
            self.root,
            width=self.mon_width,
            height=self.mon_height,
            cursor="cross",
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.tk_img = ImageTk.PhotoImage(self.display_pil)
        self.canvas.create_image(0, 0, image=self.tk_img, anchor=tk.NW)

        # Instruction HUD header
        hud_bg = self.canvas.create_rectangle(
            self.mon_width // 2 - 250, 10,
            self.mon_width // 2 + 250, 50,
            fill="#1e1e1e", outline="#3b8ed0", width=2
        )
        if self.mode == "color_picker":
            mode_hint = "Click on the exact pixel to sample color"
        elif self.mode == "point_or_area":
            mode_hint = "Click for Point (X,Y) OR Drag to select Area"
        else:
            mode_hint = "Click & Drag to select area"
        self.hud_text = self.canvas.create_text(
            self.mon_width // 2, 30,
            text=f"{self.title_text} — {mode_hint} | Press ESC to cancel",
            fill="#00ffcc", font=("Segoe UI", 11, "bold")
        )

        # Tracking variables
        self.start_x = 0
        self.start_y = 0
        self.current_rect = None
        self.dim_text = None

        # Bind events
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.root.bind("<Escape>", lambda e: self.close())

    def on_mouse_move(self, event):
        """Update cursor coordinate indicator."""
        x, y = event.x, event.y
        if self.mode == "color_picker":
            if 0 <= y < self.clean_rgb.shape[0] and 0 <= x < self.clean_rgb.shape[1]:
                r, g, b = self.clean_rgb[y, x]
                hex_col = f"#{r:02X}{g:02X}{b:02X}"
                self.canvas.itemconfigure(
                    self.hud_text,
                    text=f"Hover: X:{x} Y:{y} | RGB:({r}, {g}, {b}) {hex_col} | Click to select for {self.rarity_target}"
                )
        elif self.mode == "point_or_area":
            self.canvas.itemconfigure(
                self.hud_text,
                text=f"{self.title_text} — Hover: ({x}, {y}) | Click for Point OR Drag for Area | ESC to cancel"
            )

    def on_mouse_down(self, event):
        self.start_x = event.x
        self.start_y = event.y

        if self.mode == "color_picker":
            self.finish_color_pick(event.x, event.y)
            return

        if self.current_rect:
            self.canvas.delete(self.current_rect)
        if self.dim_text:
            self.canvas.delete(self.dim_text)

        self.current_rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#00ffcc", width=2, dash=(4, 4)
        )
        self.dim_text = self.canvas.create_text(
            self.start_x + 10, self.start_y - 12,
            text="0 x 0", fill="#ffffff", font=("Segoe UI", 9, "bold")
        )

    def on_mouse_drag(self, event):
        if self.mode == "color_picker":
            return

        cur_x, cur_y = event.x, event.y
        self.canvas.coords(self.current_rect, self.start_x, self.start_y, cur_x, cur_y)
        w = abs(cur_x - self.start_x)
        h = abs(cur_y - self.start_y)
        text_x = max(self.start_x, cur_x) + 5
        text_y = min(self.start_y, cur_y) - 10
        self.canvas.coords(self.dim_text, text_x, text_y)
        self.canvas.itemconfigure(self.dim_text, text=f"{w} x {h} px")

    def on_mouse_up(self, event):
        if self.mode == "color_picker":
            return

        end_x = event.x
        end_y = event.y

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        w = x2 - x1
        h = y2 - y1

        if self.mode == "point_or_area" and (w < 6 and h < 6):
            # Single click without dragging -> Exact POINT selection!
            global_x = self.mon_left + self.start_x
            global_y = self.mon_top + self.start_y
            result_data = {
                "type": "point",
                "x": int(global_x),
                "y": int(global_y),
                "width": 0,
                "height": 0
            }
            self.close()
            if self.on_complete:
                self.on_complete(result_data)
            return

        if w < 5 or h < 5:
            # Clicked without dragging in roi/template mode, ignore
            self.canvas.delete(self.current_rect)
            self.canvas.delete(self.dim_text)
            return

        # Dragged rectangle -> AREA selection!
        global_x = self.mon_left + x1
        global_y = self.mon_top + y1
        center_x = int(global_x + w // 2)
        center_y = int(global_y + h // 2)

        result_data = {
            "type": "area",
            "x": center_x,
            "y": center_y,
            "box_x": int(global_x),
            "box_y": int(global_y),
            "width": int(w),
            "height": int(h)
        }

        if (self.mode == "template" or self.mode == "point_or_area") and self.template_filename:
            # Crop from clean pristine screenshot
            cropped_bgr = self.clean_bgr[y1:y2, x1:x2]
            save_path = os.path.join(self.assets_dir, self.template_filename)
            if not save_path.endswith(".png"):
                save_path += ".png"
            cv2.imwrite(save_path, cropped_bgr)
            result_data["template_path"] = save_path
            result_data["template_saved"] = True

        self.close()

        if self.on_complete:
            self.on_complete(result_data)

    def finish_color_pick(self, x: int, y: int):
        """Processes clicked pixel for rarity color calibration."""
        if 0 <= y < self.clean_bgr.shape[0] and 0 <= x < self.clean_bgr.shape[1]:
            # Sample BGR
            b, g, r = self.clean_bgr[y, x]
            # Convert to HSV via 1x1 image
            pixel_bgr = np.uint8([[[b, g, r]]])
            pixel_hsv = cv2.cvtColor(pixel_bgr, cv2.COLOR_BGR2HSV)[0][0]
            h, s, v = int(pixel_hsv[0]), int(pixel_hsv[1]), int(pixel_hsv[2])

            # Compute balanced tolerance
            h_tol = 15
            s_tol = 60
            v_tol = 60

            h_lower = max(0, h - h_tol)
            h_upper = min(180, h + h_tol)
            s_lower = max(30, s - s_tol)
            s_upper = min(255, s + s_tol)
            v_lower = max(40, v - v_tol)
            v_upper = min(255, v + v_tol)

            hex_color = f"#{int(r):02X}{int(g):02X}{int(b):02X}"

            result = {
                "rarity": self.rarity_target,
                "rgb_sample": [int(r), int(g), int(b)],
                "hex": hex_color,
                "hsv": [h, s, v],
                "hsv_lower": [h_lower, s_lower, v_lower],
                "hsv_upper": [h_upper, s_upper, v_upper]
            }

            self.close()

            if self.on_complete:
                self.on_complete(result)

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


class CalibratorManager:
    """
    Coordinates ROI snipping, template cropping, and config updates.
    """
    def __init__(self, config_path: str = "config.json", assets_dir: str = "assets"):
        self.config_path = config_path
        self.assets_dir = assets_dir

    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self, cfg: Dict[str, Any]):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    def snip_roi(self, roi_key: str, title: str, callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Launch snipping overlay to capture an ROI and save into config.json."""
        def on_done(result):
            cfg = self.load_config()
            if "rois" not in cfg:
                cfg["rois"] = {}
            cfg["rois"][roi_key] = {
                "x": result["x"],
                "y": result["y"],
                "width": result["width"],
                "height": result["height"]
            }
            self.save_config(cfg)
            if callback:
                callback(result)

        ScreenSnipperOverlay(
            mode="roi",
            title=f"Calibrate ROI: {title}",
            on_complete=on_done,
            config_path=self.config_path,
            assets_dir=self.assets_dir
        )

    def snip_template(self, template_filename: str, title: str, callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Launch snipping overlay to crop a template PNG and save into assets/."""
        def on_done(result):
            if callback:
                callback(result)

        ScreenSnipperOverlay(
            mode="template",
            title=f"Snip Template: {title}",
            template_filename=template_filename,
            on_complete=on_done,
            config_path=self.config_path,
            assets_dir=self.assets_dir
        )

    def snip_gear_to_ss(self, filename: str, title: str, ss_dir: str = "SS", callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Launch snipping overlay to crop a gear reference template and save directly into SS/ folder."""
        def on_done(result):
            if callback:
                callback(result)

        ScreenSnipperOverlay(
            mode="template",
            title=f"Snip Gear Reference: {title}",
            template_filename=filename,
            on_complete=on_done,
            config_path=self.config_path,
            assets_dir=ss_dir
        )

    def snip_material_to_ss(self, filename: str, title: str, materials_dir: str = "SS_materials", callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Launch snipping overlay to crop a material reference template and save directly into SS_materials/ folder."""
        def on_done(result):
            if callback:
                callback(result)

        ScreenSnipperOverlay(
            mode="template",
            title=f"Snip Material: {title}",
            template_filename=filename,
            on_complete=on_done,
            config_path=self.config_path,
            assets_dir=materials_dir
        )

    def pick_rarity_color(self, rarity_name: str, callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Launch color picker overlay to sample exact border color."""
        def on_done(result):
            cfg = self.load_config()
            if "rarity_colors" not in cfg:
                cfg["rarity_colors"] = {}
            cfg["rarity_colors"][rarity_name] = {
                "name": rarity_name,
                "hsv_lower": result["hsv_lower"],
                "hsv_upper": result["hsv_upper"],
                "rgb_sample": result["rgb_sample"],
                "hex": result["hex"]
            }
            self.save_config(cfg)
            if callback:
                callback(result)

        ScreenSnipperOverlay(
            mode="color_picker",
            title=f"Pick Pixel Color for {rarity_name}",
            rarity_target=rarity_name,
            on_complete=on_done,
            config_path=self.config_path,
            assets_dir=self.assets_dir
        )

    def snip_button_coord(self, btn_key: str, title: str, template_filename: Optional[str] = None, callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Launch snipping overlay to capture a button coordinate (and optional template) and save to config.json."""
        def on_done(result):
            cfg = self.load_config()
            if "button_coords" not in cfg:
                cfg["button_coords"] = {}
            cx = result["x"] + result["width"] // 2
            cy = result["y"] + result["height"] // 2
            cfg["button_coords"][btn_key] = {"x": cx, "y": cy}
            self.save_config(cfg)
            if callback:
                callback(result)

        ScreenSnipperOverlay(
            mode="template" if template_filename else "roi",
            title=f"Calibrate Button: {title}",
            template_filename=template_filename,
            on_complete=on_done,
            config_path=self.config_path,
            assets_dir=self.assets_dir
        )

    def calibrate_point_or_area(
        self,
        btn_key: str,
        title: str,
        template_filename: Optional[str] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Launches overlay allowing user to either single-click to select a Point (X, Y)
        or drag to select an Area (X, Y, W, H).
        Saves button_coords[btn_key] and rois[btn_key] into config.json.
        """
        def on_done(result):
            cfg = self.load_config()
            if "button_coords" not in cfg:
                cfg["button_coords"] = {}
            if "rois" not in cfg:
                cfg["rois"] = {}

            target_x = result["x"]
            target_y = result["y"]

            cfg["button_coords"][btn_key] = {
                "x": target_x,
                "y": target_y
            }

            if result.get("type") == "area":
                cfg["rois"][btn_key] = {
                    "x": result["box_x"],
                    "y": result["box_y"],
                    "width": result["width"],
                    "height": result["height"]
                }
                cfg["button_coords"][btn_key]["width"] = result["width"]
                cfg["button_coords"][btn_key]["height"] = result["height"]
            else:
                cfg["rois"].pop(btn_key, None)

            # Sync aliases for synthesis button
            if btn_key in ("cube_synth_btn", "synth_btn"):
                cfg["button_coords"]["cube_synth_btn"] = {"x": target_x, "y": target_y}
                cfg["button_coords"]["synth_btn"] = {"x": target_x, "y": target_y}
                if result.get("type") == "area":
                    cfg["rois"]["synth_btn"] = {
                        "x": result["box_x"],
                        "y": result["box_y"],
                        "width": result["width"],
                        "height": result["height"]
                    }
                    cfg["button_coords"]["cube_synth_btn"]["width"] = result["width"]
                    cfg["button_coords"]["cube_synth_btn"]["height"] = result["height"]
                else:
                    cfg["rois"].pop("synth_btn", None)

            self.save_config(cfg)
            if callback:
                callback(result)

        ScreenSnipperOverlay(
            mode="point_or_area",
            title=title,
            template_filename=template_filename,
            on_complete=on_done,
            config_path=self.config_path,
            assets_dir=self.assets_dir
        )


