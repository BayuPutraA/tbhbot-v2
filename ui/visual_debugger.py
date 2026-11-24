"""
Visual Debugger Window for Task Bar Hero.
Displays real-time screen captures with live annotated bounding boxes,
rarity colors, item level badges, 3-corner detectors, and chest status.
Supports responsive 2-row tuning toolbar for 768p and 1080p+ screens.
"""
import json
import time
import threading
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
from typing import Dict, Any, Optional, List, Tuple
import cv2
import numpy as np

from vision import VisionEngine


class VisualDebuggerWindow(ctk.CTkToplevel):
    """
    Interactive live visual debugging tool for Task Bar Hero.
    Displays screen captures with live annotated bounding boxes,
    rarity colors, item level badges, and chest status.
    Supports 3 inspection modes:
    - Full Desktop: Full screen with ROI overlays and detected items.
    - Inventory Grid: Zoomed crop of Inventory Grid ROI with slot borders & badges.
    - Chest Region: Zoomed crop of Chest ROI with empty-floor / chest status.
    """
    def __init__(self, master, vision_engine: VisionEngine, config_data: Dict[str, Any]):
        super().__init__(master)

        self.title("🔍 Task Bar Hero — Visual Debugger & Live Inspection")
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        if screen_h <= 800:
            dbg_w = min(880, max(720, screen_w - 40))
            dbg_h = min(580, max(440, screen_h - 90))
            self.geometry(f"{dbg_w}x{dbg_h}")
            self.minsize(700, 420)
        else:
            self.geometry("920x660")
            self.minsize(760, 480)
        self.wm_attributes("-topmost", True)

        self.vision = vision_engine
        self.config_data = config_data
        self.auto_refresh_var = ctk.BooleanVar(value=False)
        self.current_mode = "full"
        self.after_id = None
        self.current_photo = None
        self.last_raw_bgr = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Initial capture after window renders
        self.after(150, self.refresh_view)

    def _build_ui(self):
        # 1. Top Controls Bar
        ctrl_bar = ctk.CTkFrame(self, fg_color="#181c2e", corner_radius=0, height=48)
        ctrl_bar.pack(fill="x", side="top")
        ctrl_bar.pack_propagate(False)

        ctk.CTkLabel(
            ctrl_bar,
            text="🔍 VISUAL DEBUGGER",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#00e5ff"
        ).pack(side="left", padx=12)

        # Mode selector
        self.mode_selector = ctk.CTkSegmentedButton(
            ctrl_bar,
            values=["Full Desktop", "Inventory Grid", "Chest Region"],
            command=self.on_mode_change,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.mode_selector.set("Full Desktop")
        self.mode_selector.pack(side="left", padx=12, pady=8)

        # Refresh button
        self.btn_refresh = ctk.CTkButton(
            ctrl_bar,
            text="📸 Capture & Refresh",
            command=self.refresh_view,
            fg_color="#1f538d",
            hover_color="#2b6cb0",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=140,
            height=28
        )
        self.btn_refresh.pack(side="right", padx=10, pady=8)

        # Auto-refresh checkbox
        self.cb_auto = ctk.CTkCheckBox(
            ctrl_bar,
            text="Auto (1s)",
            variable=self.auto_refresh_var,
            command=self.toggle_auto_refresh,
            font=ctk.CTkFont(size=11)
        )
        self.cb_auto.pack(side="right", padx=8)

        # 2. Stats / Diagnostic Bar
        stats_frame = ctk.CTkFrame(self, fg_color="#202538", corner_radius=0, height=36)
        stats_frame.pack(fill="x", side="top")
        stats_frame.pack_propagate(False)

        self.lbl_items_stat = ctk.CTkLabel(
            stats_frame,
            text="Visible Items: 0 (Lv.65: 0 | Lv.80-90: 0)",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38ef7d"
        )
        self.lbl_items_stat.pack(side="left", padx=12)

        self.lbl_rarity_stat = ctk.CTkLabel(
            stats_frame,
            text="Common: 0 | Uncommon: 0 | Rare: 0 | Legendary: 0",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#d0d5e2"
        )
        self.lbl_rarity_stat.pack(side="left", padx=8)

        self.lbl_chest_stat = ctk.CTkLabel(
            stats_frame,
            text="Chest: Checking...",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#ffd166"
        )
        self.lbl_chest_stat.pack(side="right", padx=12)

        # 3. Live Detection Tuning Bar (Bottom) - 2 Compact Rows for 768p+ responsiveness
        tune_bar = ctk.CTkFrame(self, fg_color="#181c2e", corner_radius=0, height=62)
        tune_bar.pack(fill="x", side="bottom")
        tune_bar.pack_propagate(False)

        tune_row1 = ctk.CTkFrame(tune_bar, fg_color="transparent")
        tune_row1.pack(fill="x", padx=6, pady=(3, 1))

        ctk.CTkLabel(
            tune_row1,
            text="⚙️ DETECTOR TUNING:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#ffd166"
        ).pack(side="left", padx=(4, 6))

        ctk.CTkLabel(tune_row1, text="Detect Conf (%):", font=ctk.CTkFont(size=10)).pack(side="left", padx=(2, 2))
        self.entry_t_conf = ctk.CTkEntry(tune_row1, width=44, height=22, font=ctk.CTkFont(size=10))
        curr_conf_pct = int(round(float(self.config_data.get("confidence_threshold", 0.75)) * 100))
        self.entry_t_conf.insert(0, str(curr_conf_pct))
        self.entry_t_conf.pack(side="left", padx=(2, 6))

        ctk.CTkLabel(tune_row1, text="Badge Match (%):", font=ctk.CTkFont(size=10)).pack(side="left", padx=(2, 2))
        self.entry_t_badge = ctk.CTkEntry(tune_row1, width=44, height=22, font=ctk.CTkFont(size=10))
        curr_badge_pct = int(round(float(self.config_data.get("badge_match_threshold", 0.75)) * 100))
        self.entry_t_badge.insert(0, str(curr_badge_pct))
        self.entry_t_badge.pack(side="left", padx=(2, 6))

        ctk.CTkLabel(tune_row1, text="Box W:", font=ctk.CTkFont(size=10)).pack(side="left", padx=(2, 2))
        self.entry_t_bw = ctk.CTkEntry(tune_row1, width=38, height=22, font=ctk.CTkFont(size=10))
        self.entry_t_bw.insert(0, str(self.config_data.get("badge_detector_width", 19)))
        self.entry_t_bw.pack(side="left", padx=(2, 6))

        ctk.CTkLabel(tune_row1, text="Box H:", font=ctk.CTkFont(size=10)).pack(side="left", padx=(2, 2))
        self.entry_t_bh = ctk.CTkEntry(tune_row1, width=36, height=22, font=ctk.CTkFont(size=10))
        self.entry_t_bh.insert(0, str(self.config_data.get("badge_detector_height", 15)))
        self.entry_t_bh.pack(side="left", padx=(2, 6))

        ctk.CTkLabel(tune_row1, text="Scroll Depth:", font=ctk.CTkFont(size=10)).pack(side="left", padx=(2, 2))
        self.entry_t_sdepth = ctk.CTkEntry(tune_row1, width=36, height=22, font=ctk.CTkFont(size=10))
        curr_sdepth = self.config_data.get("grid_settings", {}).get("scroll_depth_px", 40)
        self.entry_t_sdepth.insert(0, str(curr_sdepth))
        self.entry_t_sdepth.pack(side="left", padx=(2, 6))

        tune_row2 = ctk.CTkFrame(tune_bar, fg_color="transparent")
        tune_row2.pack(fill="x", padx=6, pady=(1, 3))

        self.var_3corner = ctk.BooleanVar(value=bool(self.config_data.get("multi_corner_rarity_enabled", False)))
        self.cb_3corner = ctk.CTkCheckBox(
            tune_row2,
            text="3-Corner Rarity",
            variable=self.var_3corner,
            command=self.toggle_3corner_rarity_action,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ff79c6",
            height=20
        )
        self.cb_3corner.pack(side="left", padx=(4, 8))

        self.btn_apply_tune = ctk.CTkButton(
            tune_row2,
            text="✔ Apply",
            command=self.apply_live_tuning,
            fg_color="#1f7a40",
            hover_color="#289650",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=75,
            height=24
        )
        self.btn_apply_tune.pack(side="left", padx=3)

        self.btn_test_scroll = ctk.CTkButton(
            tune_row2,
            text="📜 1-Step Scroll",
            command=self.test_1step_action,
            fg_color="#4f46e5",
            hover_color="#4338ca",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=95,
            height=24
        )
        self.btn_test_scroll.pack(side="left", padx=3)

        self.lbl_tune_feedback = ctk.CTkLabel(
            tune_row2,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#38ef7d"
        )
        self.lbl_tune_feedback.pack(side="left", padx=6)

        # 4. Canvas for rendering annotated image
        self.canvas = tk.Canvas(self, bg="#10121a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=(4, 6))
        self.canvas.bind("<Configure>", lambda e: self._render_canvas_image())

    def test_1step_action(self):
        """Runs 1-step scroll test and re-scans view."""
        if hasattr(self.master, "bot"):
            self.master.bot.reset_abort_state()
            def _worker():
                self.master.bot.test_single_step_scroll()
                time.sleep(0.4)
                if self.winfo_exists():
                    self.after(0, self.refresh_view)
            threading.Thread(target=_worker, daemon=True).start()

    def toggle_3corner_rarity_action(self):
        """Toggles 3-Corner Rarity detection feature on/off instantly and refreshes display."""
        try:
            val = self.var_3corner.get()
            self.config_data["multi_corner_rarity_enabled"] = val
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2)

            self.vision.update_config(self.config_data)
            if hasattr(self.master, "bot"):
                self.master.bot.reload_config()
                self.master.bot.vision.update_config(self.config_data)
            if hasattr(self.master, "sync_detector_settings_from_config"):
                self.master.sync_detector_settings_from_config()

            st_desc = "ON" if val else "OFF"
            self.lbl_tune_feedback.configure(text=f"✔ 3-Corner Rarity: {st_desc}")
            self.after(3000, lambda: self.lbl_tune_feedback.configure(text="") if self.winfo_exists() else None)
            self.refresh_view()
        except Exception as e:
            self.lbl_tune_feedback.configure(text=f"Error: {e}", text_color="#ff5555")

    def apply_live_tuning(self):
        """Applies detector and scroll parameters directly from tuning bar, updates config, and re-scans instantly."""
        try:
            conf_pct = float(self.entry_t_conf.get().strip())
            badge_pct = float(self.entry_t_badge.get().strip())
            bw_val = int(self.entry_t_bw.get().strip())
            bh_val = int(self.entry_t_bh.get().strip())
            sdepth_val = int(self.entry_t_sdepth.get().strip())

            conf_pct = max(40.0, min(100.0, conf_pct))
            badge_pct = max(30.0, min(100.0, badge_pct))
            bw_val = max(8, min(50, bw_val))
            bh_val = max(6, min(50, bh_val))
            sdepth_val = max(10, min(150, sdepth_val))

            self.config_data["confidence_threshold"] = round(conf_pct / 100.0, 2)
            self.config_data["badge_match_threshold"] = round(badge_pct / 100.0, 2)
            self.config_data["badge_detector_width"] = bw_val
            self.config_data["badge_detector_height"] = bh_val
            self.config_data["multi_corner_rarity_enabled"] = self.var_3corner.get()

            if "grid_settings" not in self.config_data:
                self.config_data["grid_settings"] = {}
            self.config_data["grid_settings"]["scroll_depth_px"] = sdepth_val
            if self.config_data["grid_settings"].get("scroll_amount", -120) < -240:
                self.config_data["grid_settings"]["scroll_amount"] = -120

            # Save to config.json
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2)

            self.vision.update_config(self.config_data)

            # Sync with master app if available
            if hasattr(self.master, "sync_detector_settings_from_config"):
                self.master.sync_detector_settings_from_config()

            c_st = "ON" if self.var_3corner.get() else "OFF"
            self.lbl_tune_feedback.configure(text=f"✔ Saved: {int(conf_pct)}%/{int(badge_pct)}% | {bw_val}x{bh_val}px | Depth {sdepth_val}px | 3-Corner {c_st}")
            self.after(3000, lambda: self.lbl_tune_feedback.configure(text="") if self.winfo_exists() else None)

            self.refresh_view()
        except Exception as e:
            self.lbl_tune_feedback.configure(text=f"Error: {e}", text_color="#ff5555")

    def on_mode_change(self, selected_label: str):
        mode_map = {
            "Full Desktop": "full",
            "Inventory Grid": "inventory",
            "Chest Region": "chest"
        }
        self.current_mode = mode_map.get(selected_label, "full")
        self.refresh_view()

    def toggle_auto_refresh(self):
        if self.auto_refresh_var.get():
            self._schedule_auto_refresh()
        else:
            if self.after_id:
                try:
                    self.after_cancel(self.after_id)
                except Exception:
                    pass
                self.after_id = None

    def _schedule_auto_refresh(self):
        if not self.winfo_exists():
            return
        if self.auto_refresh_var.get():
            self.refresh_view()
            self.after_id = self.after(1000, self._schedule_auto_refresh)

    def refresh_view(self):
        if not self.winfo_exists():
            return
        try:
            inv_roi = self.vision.get_inventory_roi()
            chest_roi = self.config_data.get("rois", {}).get("chest_region")

            annotated_bgr, stats = self.vision.render_debug_overlay(inv_roi, chest_roi, mode=self.current_mode)
            self.last_raw_bgr = annotated_bgr

            # Update stats banner
            total = stats.get("total_items", 0)
            t65 = stats.get("tier_65", 0)
            t80_90 = stats.get("tier_80_90", 0)
            ref_stats = stats.get("ref_stats", {})
            ref_tag = f" [SS: {ref_stats.get('total', 0)} active]" if ref_stats.get("loaded") else ""
            self.lbl_items_stat.configure(text=f"Matched Gear: {total} (Lv.65: {t65} | Lv.80-90: {t80_90}){ref_tag}")

            rc = stats.get("rarity_counts", {})
            self.lbl_rarity_stat.configure(
                text=f"Common: {rc.get('Common', 0)} | Uncommon: {rc.get('Uncommon', 0)} | Rare: {rc.get('Rare', 0)} | Legendary: {rc.get('Legendary', 0)}"
            )

            chest_status = stats.get("chest_status", "UNKNOWN")
            c_color = "#38ef7d" if "EMPTY" in chest_status else ("#ffd166" if "FOUND" in chest_status else "#ff5555")
            self.lbl_chest_stat.configure(text=f"Chest: {chest_status}", text_color=c_color)

            # Auto-confirm detected gear into master app checklist
            detected = stats.get("items", [])
            if detected and hasattr(self.master, "record_detected_items"):
                self.master.record_detected_items(detected)

            self._render_canvas_image()
        except Exception as e:
            print(f"Debugger refresh error: {e}")

    def _render_canvas_image(self):
        if self.last_raw_bgr is None:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 20 or ch < 20:
            return

        ih, iw = self.last_raw_bgr.shape[:2]
        scale = min(cw / iw, ch / ih)

        if self.current_mode in ["inventory", "chest"]:
            scale = min(scale, 2.5)

        nw = max(1, int(iw * scale))
        nh = max(1, int(ih * scale))

        resized = cv2.resize(self.last_raw_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        self.current_photo = ImageTk.PhotoImage(pil_img)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self.current_photo, anchor="center")

    def on_close(self):
        if self.after_id:
            try:
                self.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        self.destroy()
