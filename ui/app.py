"""
Modern Dark-Mode GUI Dashboard & Calibrator for Task Bar Hero.
Built with CustomTkinter for high responsiveness and sleek aesthetics.
Provides real-time asset checklist table for the 15 PNG templates in assets/,
fail-safe Hybrid scroll selector, instant test buttons, and live Visual Debugger.
"""
import os
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk
from typing import Dict, Any, Optional, List, Tuple
import cv2
import numpy as np

from core import BotEngine
from calibrator import CalibratorManager
from vision import VisionEngine, TEMPLATE_MANIFEST
from .visual_debugger import VisualDebuggerWindow

# Reference gear matrix configuration (12 items x 4 rarities x 3 levels = 144 total combinations)
GEAR_NAMES = [
    "armor", "arrow", "boots", "bow", "gloves", "helmet",
    "orb", "scepter", "shield", "staff", "sword", "tome"
]

GEAR_ICONS = {
    "armor": "👕",
    "arrow": "🏹",
    "boots": "👢",
    "bow": "🏹",
    "gloves": "🧤",
    "helmet": "🪖",
    "orb": "🔮",
    "scepter": "🪄",
    "shield": "🛡️",
    "staff": "🦯",
    "sword": "🗡️",
    "tome": "📖"
}

RARITIES_ORDER = [
    ("c", "Common", "#AAAAAA"),
    ("u", "Uncommon", "#32CD32"),
    ("r", "Rare", "#1E90FF"),
    ("l", "Legendary", "#FFA500")
]

LEVELS_ORDER = ["50", "65", "80", "90"]

# Appearance configuration
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class NativeLabel(tk.Label):
    """Ultra-lightweight native Win32 Label that avoids CTkCanvas allocation and supports text_color."""
    def __init__(self, master=None, cnf={}, **kwargs):
        if "text_color" in kwargs:
            kwargs["fg"] = kwargs.pop("text_color")
        super().__init__(master, cnf, **kwargs)

    def configure(self, cnf=None, **kwargs):
        if "text_color" in kwargs:
            kwargs["fg"] = kwargs.pop("text_color")
        return super().configure(cnf, **kwargs)


class NativeEntry(tk.Entry):
    """Ultra-lightweight native Win32 Entry with dark theme styling matching CustomTkinter."""
    def __init__(self, master=None, cnf={}, **kwargs):
        kwargs.setdefault("bg", "#1a1d2e")
        kwargs.setdefault("fg", "#ffffff")
        kwargs.setdefault("insertbackground", "#00e5ff")
        kwargs.setdefault("relief", "flat")
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", "#303548")
        kwargs.setdefault("highlightcolor", "#00e5ff")
        kwargs.setdefault("font", ("Segoe UI", 9))
        super().__init__(master, cnf, **kwargs)


class LightweightScrollableFrame(tk.Frame):
    """Zero-overhead native scrollable container using 1 tk.Canvas and 1 ttk.Scrollbar."""
    def __init__(self, master, bg="#10121c", **kwargs):
        super().__init__(master, bg=bg, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable = tk.Frame(self.canvas, bg=bg)

        self._window_id = self.canvas.create_window((0, 0), window=self.scrollable, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.scrollable.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._window_id, width=e.width)
        )

        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))


class TaskBarHeroApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window settings with screen resolution responsiveness (allows compact companion mode down to 560x390)
        self.title("Task Bar Hero — Auto Chest & Cube Synthesizer")
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        if screen_h <= 800:
            app_w = min(840, max(640, screen_w - 40))
            app_h = min(580, max(420, screen_h - 80))
            self.geometry(f"{app_w}x{app_h}")
        else:
            self.geometry("860x650")
        self.minsize(560, 390)

        # File paths
        self.config_path = "config.json"
        self.assets_dir = "assets"
        self.ss_dir = "SS"
        self.materials_dir = "SS_materials"
        self.confirmed_gears_path = "confirmed_gear.json"
        self.materials_manifest_path = "materials_manifest.json"

        # Load configuration, confirmed gear records & materials manifest
        self.config_data = self.load_config()
        self.confirmed_gears: Dict[str, Dict[str, Any]] = self.load_confirmed_gears()
        self.materials_manifest: Dict[str, List[Dict[str, Any]]] = self.load_materials_manifest()
        self.material_status_labels: Dict[str, ctk.CTkLabel] = {}
        self.material_name_entries: Dict[str, ctk.CTkEntry] = {}
        self.ss_file_cache: Dict[str, Tuple[int, int]] = {}
        self.all_gear_items: List[Dict[str, Any]] = []

        # Window Topmost state
        self.always_on_top_var = ctk.BooleanVar(value=self.config_data.get("always_on_top", True))
        self.wm_attributes("-topmost", self.always_on_top_var.get())

        # Initialize Calibrator Manager
        self.calibrator = CalibratorManager(self.config_path, self.assets_dir)

        # Initialize Bot Engine
        self.bot = BotEngine(
            config_path=self.config_path,
            assets_dir=self.assets_dir,
            on_status=self.update_status_banner,
            on_log=self.append_log,
            on_countdown=self.update_countdown_display,
            on_buckets_update=self.update_live_buckets,
            on_items_detected=self.record_detected_items
        )

        # Visual debugger window reference
        self.debugger_window = None

        # Template status labels cache: {filename: label_widget}
        self.template_status_labels: Dict[str, ctk.CTkLabel] = {}

        # Build UI layout
        self._build_header()
        self._build_tabs()

        # GUI readiness flag & delayed scheduler startup
        self._gui_ready = False
        self.after(250, self._on_gui_ready)

        # Initial UI sync
        self.append_log("Task Bar Hero Automation Initialized.", "info")
        self.append_log("Using 15-asset manifest & native Hardware Wheel Scroll.", "info")
        self.append_log("Press F8 at any time for Emergency Stop.", "warning")

    def _on_gui_ready(self):
        """Called once the Tkinter mainloop is fully running."""
        self._gui_ready = True
        self.bot.start_scheduler()
        self.update_live_buckets(self.bot.live_buckets)
        self._update_auto_loop_button_text()

    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, indent=2)
        self.bot.reload_config()
        self.append_log("Configuration saved and reloaded.", "info")

    def load_confirmed_gears(self) -> Dict[str, Dict[str, Any]]:
        """Loads persistent confirmed gear checklist from confirmed_gear.json."""
        if os.path.exists(self.confirmed_gears_path):
            try:
                with open(self.confirmed_gears_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_confirmed_gears(self):
        """Saves persistent confirmed gear records to confirmed_gear.json."""
        try:
            with open(self.confirmed_gears_path, "w", encoding="utf-8") as f:
                json.dump(self.confirmed_gears, f, indent=2)
        except Exception as e:
            print(f"Error saving confirmed gears: {e}")

    def load_materials_manifest(self) -> Dict[str, List[Dict[str, Any]]]:
        """Loads persistent material checklist from materials_manifest.json."""
        if os.path.exists(self.materials_manifest_path):
            try:
                with open(self.materials_manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "uncommon": [{"id": f"u-mat_{i}", "name": f"Uncommon Mat {i}", "filename": f"u-mat_{i}.png"} for i in range(1, 12)],
            "rare": [{"id": f"r-mat_{i}", "name": f"Rare Mat {i}", "filename": f"r-mat_{i}.png"} for i in range(1, 12)],
            "legendary": [{"id": f"l-mat_{i}", "name": f"Legendary Mat {i}", "filename": f"l-mat_{i}.png"} for i in range(1, 11)],
            "immortal": [{"id": f"i-mat_{i}", "name": f"Immortal Mat {i}", "filename": f"i-mat_{i}.png"} for i in range(1, 11)],
        }

    def save_materials_manifest(self):
        """Saves persistent material checklist to materials_manifest.json."""
        try:
            with open(self.materials_manifest_path, "w", encoding="utf-8") as f:
                json.dump(self.materials_manifest, f, indent=2)
        except Exception as e:
            print(f"Error saving materials manifest: {e}")

    def record_detected_items(self, items: List[Dict[str, Any]]):
        """
        Auto-confirmation hook: called automatically whenever the bot scans visible inventory,
        runs test scans, or the Visual Debugger captures visible inventory.
        """
        if not getattr(self, "_gui_ready", False) or not self.winfo_exists():
            return

        new_confirms = 0
        for itm in items:
            ref_file = itm.get("ref_file")
            if not ref_file:
                continue

            was_confirmed = self.confirmed_gears.get(ref_file, {}).get("confirmed", False)
            self.confirmed_gears[ref_file] = {
                "confirmed": True,
                "score": round(float(itm.get("score", 1.0)), 2),
                "level": str(itm.get("level", "")),
                "gear_name": str(itm.get("gear_name", "")),
                "rarity": str(itm.get("rarity", "")),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            if not was_confirmed:
                new_confirms += 1

        if new_confirms > 0:
            self.save_confirmed_gears()
            if hasattr(self, "gear_tree") and self.gear_tree.winfo_exists():
                self.after(0, self.refresh_gear_checklist_data)

    # ---------------------------------------------------------
    # Header Section
    # ---------------------------------------------------------
    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#181824", height=42)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)

        title_label = ctk.CTkLabel(
            header_frame,
            text="⚡ TASK BAR HERO",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#00e5ff"
        )
        title_label.pack(side="left", padx=(10, 6))

        hotkey_badge = ctk.CTkLabel(
            header_frame,
            text="[ Stop: F8 ]",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#ff5555"
        )
        hotkey_badge.pack(side="left", padx=4)

        # Always on Top checkbox
        topmost_cb = ctk.CTkCheckBox(
            header_frame,
            text="Always on Top",
            variable=self.always_on_top_var,
            command=self.toggle_topmost,
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        topmost_cb.pack(side="right", padx=10)

    def toggle_topmost(self):
        is_top = self.always_on_top_var.get()
        self.wm_attributes("-topmost", is_top)
        self.config_data["always_on_top"] = is_top
        self.save_config()

    # ---------------------------------------------------------
    # Tabview Builder (with High-Performance Lazy Tab Loading)
    # ---------------------------------------------------------
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self, corner_radius=8, command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True, padx=6, pady=(3, 6))

        self.tab_dashboard = self.tabview.add("Dashboard")
        self.tab_calibrator = self.tabview.add("Calibrator & Assets")
        self.tab_gear_checklist = self.tabview.add("🛡 Gears")
        self.tab_materials = self.tabview.add("📦 Materials")

        self._built_tabs = set()
        # Build Dashboard tab upfront; remaining tabs lazy-load on first user click
        self._build_dashboard_tab()
        self._built_tabs.add("Dashboard")

    def _on_tab_changed(self):
        """Lazy load tab contents on first selection to keep base app lightweight, fast, and responsive."""
        selected_tab = self.tabview.get()
        if selected_tab not in self._built_tabs:
            if selected_tab == "Calibrator & Assets":
                self._build_calibrator_tab()
                self._built_tabs.add("Calibrator & Assets")
            elif selected_tab == "🛡 Gears":
                self._build_gear_checklist_tab()
                self._built_tabs.add("🛡 Gears")
                if hasattr(self, "refresh_gear_checklist_data"):
                    self.refresh_gear_checklist_data()
            elif selected_tab == "📦 Materials":
                self._build_materials_tab()
                self._built_tabs.add("📦 Materials")

        # Instantly ungrid/hide inactive tab frames instead of waiting for CTkTabview's 100ms lag delay
        try:
            self.tabview._grid_forget_all_tabs(exclude_name=selected_tab)
        except Exception:
            pass

    # ---------------------------------------------------------
    # Tab 1: Automation Dashboard
    # ---------------------------------------------------------
    def _build_dashboard_tab(self):
        # 1. Status Banner (compact height=30)
        self.status_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="#202538", corner_radius=6, height=30)
        self.status_frame.pack(fill="x", padx=6, pady=(2, 4))
        self.status_frame.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="STATUS: Idle - Waiting for Timer",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38ef7d"
        )
        self.status_label.pack(side="left", padx=8)

        # 2. Timer & Controls Row
        ctrl_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=6, pady=2)

        # Timer Card (compact width=175)
        timer_card = ctk.CTkFrame(ctrl_frame, fg_color="#181c2e", corner_radius=6, width=175)
        timer_card.pack(side="left", fill="y", padx=(0, 6), pady=2)
        timer_card.pack_propagate(False)

        timer_title = tk.Label(timer_card, text="CYCLE COUNTDOWN", font=("Segoe UI", 9, "bold"), bg="#181c2e", fg="#8892b0")
        timer_title.pack(anchor="w", padx=8, pady=(4, 0))

        self.timer_readout = ctk.CTkLabel(
            timer_card,
            text="02:00:00",
            font=ctk.CTkFont(family="Consolas", size=22, weight="bold"),
            text_color="#00e5ff"
        )
        self.timer_readout.pack(padx=8, pady=(0, 2))

        # Manual Interval Setting Row
        t_set_row = tk.Frame(timer_card, bg="#181c2e")
        t_set_row.pack(fill="x", padx=4, pady=(0, 2))

        tk.Label(t_set_row, text="Interval:", font=("Segoe UI", 9), bg="#181c2e", fg="#8892b0").pack(side="left", padx=(1, 1))
        self.entry_timer_min = ctk.CTkEntry(t_set_row, width=38, height=20, font=ctk.CTkFont(size=9))
        cur_min_val = int(self.config_data.get("timer_interval_minutes", 120))
        self.entry_timer_min.insert(0, str(cur_min_val))
        self.entry_timer_min.pack(side="left", padx=(1, 1))
        tk.Label(t_set_row, text="m", font=("Segoe UI", 9), bg="#181c2e", fg="#8892b0").pack(side="left", padx=(0, 2))

        self.btn_set_timer = ctk.CTkButton(
            t_set_row,
            text="✔",
            command=self.apply_manual_timer_interval,
            width=28,
            height=20,
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#1f7a40",
            hover_color="#289650"
        )
        self.btn_set_timer.pack(side="left", padx=1)

        # Quick Interval Presets Row (1h, 1.5h, 2h)
        t_preset_row = tk.Frame(timer_card, bg="#181c2e")
        t_preset_row.pack(fill="x", padx=4, pady=(0, 4))

        for p_lbl, p_m in [("1h", 60), ("1.5h", 90), ("2h", 120)]:
            ctk.CTkButton(
                t_preset_row,
                text=p_lbl,
                command=lambda m=p_m: self.set_timer_preset(m),
                width=36,
                height=18,
                font=ctk.CTkFont(size=8, weight="bold"),
                fg_color="#272c42",
                hover_color="#3d4463"
            ).pack(side="left", padx=1)

        # Control Buttons (2x2 grid)
        btn_box = tk.Frame(ctrl_frame, bg="#121625")
        btn_box.pack(side="left", fill="both", expand=True)

        self.btn_auto_loop = ctk.CTkButton(
            btn_box,
            text="▶ Start Auto Loop",
            command=self.toggle_auto_loop_action,
            fg_color="#1f7a40",
            hover_color="#289650",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=30
        )
        self.btn_auto_loop.grid(row=0, column=0, padx=3, pady=2, sticky="ew")

        self.btn_run_now = ctk.CTkButton(
            btn_box,
            text="⚡ Run Cycle Now",
            command=self.run_cycle_now_action,
            fg_color="#1f538d",
            hover_color="#2b6cb0",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=30
        )
        self.btn_run_now.grid(row=0, column=1, padx=3, pady=2, sticky="ew")

        self.btn_emergency_stop = ctk.CTkButton(
            btn_box,
            text="🛑 Stop (F8)",
            command=self.bot.trigger_emergency_stop,
            fg_color="#a82323",
            hover_color="#c92a2a",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=30
        )
        self.btn_emergency_stop.grid(row=1, column=0, padx=3, pady=2, sticky="ew")

        self.btn_visual_debugger = ctk.CTkButton(
            btn_box,
            text="🔍 Debugger",
            command=self.open_visual_debugger,
            fg_color="#0d9488",
            hover_color="#0f766e",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=30
        )
        self.btn_visual_debugger.grid(row=1, column=1, padx=3, pady=2, sticky="ew")

        btn_box.columnconfigure(0, weight=1)
        btn_box.columnconfigure(1, weight=1)

        # 3. Diagnostic Test Tools & Feature Toggles Card (Responsive 3-Column Layout)
        test_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="#181c2e", corner_radius=6)
        test_frame.pack(fill="x", padx=6, pady=(3, 4))

        # Top row inside test_frame: Scroll Mode + Toggles
        options_bar = tk.Frame(test_frame, bg="#181c2e")
        options_bar.pack(fill="x", padx=6, pady=(3, 2))

        tk.Label(options_bar, text="Scroll:", font=("Segoe UI", 10, "bold"), bg="#181c2e", fg="#8892b0").pack(side="left", padx=(2, 2))
        saved_scroll_mode = self.config_data.get("scroll_mode", "Hardware Wheel (SendInput)")
        self.opt_scroll_mode = ctk.CTkOptionMenu(
            options_bar,
            values=["Hardware Wheel (SendInput)", "Mouse Drag Scroll"],
            command=self.on_scroll_mode_selected,
            font=ctk.CTkFont(size=10),
            width=140,
            height=22
        )
        self.opt_scroll_mode.set(saved_scroll_mode)
        self.opt_scroll_mode.pack(side="left", padx=(0, 6))
        self.bot.scroll_mode = saved_scroll_mode

        self.var_full_inv_anticipation = ctk.BooleanVar(value=bool(self.config_data.get("full_inventory_anticipation", False)))
        chk_full_inv = ctk.CTkCheckBox(
            options_bar,
            text="Full Inv Stash",
            font=ctk.CTkFont(size=10, weight="bold"),
            variable=self.var_full_inv_anticipation,
            command=self.toggle_full_inv_anticipation
        )
        chk_full_inv.pack(side="right", padx=(4, 2))

        self.var_auto_stash_mat = ctk.BooleanVar(value=bool(self.config_data.get("auto_stash_materials", True)))
        chk_auto_mat = ctk.CTkCheckBox(
            options_bar,
            text="Auto-Stash Mat",
            font=ctk.CTkFont(size=10, weight="bold"),
            variable=self.var_auto_stash_mat,
            command=self.toggle_auto_stash_materials
        )
        chk_auto_mat.pack(side="right", padx=(4, 6))

        # Action Buttons Grid (3 columns x 2 rows, equal weight)
        tools_grid = tk.Frame(test_frame, bg="#181c2e")
        tools_grid.pack(fill="x", padx=4, pady=(1, 4))

        test_buttons = [
            ("🖼 Visual Scan", self.run_test_visual_scan_action, "#4338ca", "#5548db"),
            ("📜 1-Step Scroll", self.run_test_single_step_scroll_action, "#4f46e5", "#4338ca"),
            ("📜 Full Scroll", self.run_test_scroll_action, "#6366f1", "#4f46e5"),
            ("📦 Test Chests", self.run_test_chest_action, "#059669", "#047857"),
            ("🧪 Test Synthesis", self.run_test_synthesis_action, "#8b5cf6", "#7c3aed"),
            ("📦 Test Materials", self.run_test_material_stash_action, "#0284c7", "#0369a1"),
        ]

        for idx, (btn_text, btn_cmd, fg_c, hov_c) in enumerate(test_buttons):
            r = idx // 3
            c = idx % 3
            btn = ctk.CTkButton(
                tools_grid,
                text=btn_text,
                command=btn_cmd,
                fg_color=fg_c,
                hover_color=hov_c,
                font=ctk.CTkFont(size=10, weight="bold"),
                height=24
            )
            btn.grid(row=r, column=c, padx=2, pady=2, sticky="ew")

        for c in range(3):
            tools_grid.columnconfigure(c, weight=1)

        # 4. Live Inventory Bucket Counters Card
        bucket_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="#181c2e", corner_radius=6)
        bucket_frame.pack(fill="x", padx=6, pady=(0, 4))

        bucket_header = tk.Label(
            bucket_frame,
            text="LIVE GEAR BUCKETS (Need 9 of same tier & rarity to Synthesize)",
            font=("Segoe UI", 10, "bold"),
            bg="#181c2e",
            fg="#8892b0"
        )
        bucket_header.pack(anchor="w", padx=8, pady=(3, 1))

        self.bucket_labels: Dict[str, Dict[str, tk.Label]] = {
            "tier_65_80": {},
            "tier_80_90": {}
        }

        counts_grid = tk.Frame(bucket_frame, bg="#181c2e")
        counts_grid.pack(fill="x", padx=8, pady=(0, 4))

        tiers_info = [
            ("tier_65_80", "Lv.65~80:"),
            ("tier_80_90", "Lv.80~90:")
        ]
        rarities = [("Common", "#AAAAAA"), ("Uncommon", "#32CD32"), ("Rare", "#1E90FF"), ("Legendary", "#FFA500")]

        for row_idx, (tier_key, tier_name) in enumerate(tiers_info):
            lbl_tier = tk.Label(counts_grid, text=tier_name, font=("Segoe UI", 10, "bold"), bg="#181c2e", fg="#ffffff", anchor="w")
            lbl_tier.grid(row=row_idx, column=0, padx=2, pady=1, sticky="w")

            for col_idx, (rarity, color) in enumerate(rarities):
                lbl = tk.Label(
                    counts_grid,
                    text=f"{rarity}: 0/9",
                    font=("Segoe UI", 10, "bold"),
                    bg="#181c2e",
                    fg=color,
                    anchor="center"
                )
                lbl.grid(row=row_idx, column=col_idx + 1, padx=2, pady=1, sticky="ew")
                self.bucket_labels[tier_key][rarity] = lbl

        for c in range(5):
            counts_grid.columnconfigure(c, weight=1)

        # 5. Activity Log Box
        log_header_frame = tk.Frame(self.tab_dashboard, bg="#121625")
        log_header_frame.pack(fill="x", padx=6, pady=(1, 0))

        log_title = tk.Label(log_header_frame, text="ACTIVITY LOG", font=("Segoe UI", 10, "bold"), bg="#121625", fg="#8892b0")
        log_title.pack(side="left")

        clear_btn = ctk.CTkButton(
            log_header_frame,
            text="Clear Log",
            width=65,
            height=18,
            font=ctk.CTkFont(size=9),
            fg_color="#303548",
            hover_color="#404660",
            command=self.clear_log
        )
        clear_btn.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            self.tab_dashboard,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color="#12141f",
            text_color="#d0d5e2",
            wrap="word"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=6, pady=(2, 4))

    def on_scroll_mode_selected(self, chosen_mode: str):
        self.config_data["scroll_mode"] = chosen_mode
        self.save_config()
        self.bot.scroll_mode = chosen_mode
        self.append_log(f"Scroll mode set to: {chosen_mode}", "info")

    def update_status_banner(self, text: str):
        if not getattr(self, "_gui_ready", False) or not self.winfo_exists():
            return
        color = "#38ef7d"
        if "Opening" in text:
            color = "#ffd166"
        elif "Scanning" in text:
            color = "#00e5ff"
        elif "Synthesizing" in text:
            color = "#bb86fc"
        elif "Waiting" in text or "Paused" in text:
            color = "#ffa500"
        elif "Stopped" in text or "Error" in text or "Full" in text:
            color = "#ff5555"

        self.after(0, lambda: self.status_label.configure(text=f"STATUS: {text}", text_color=color))

    def update_countdown_display(self, time_str: str, seconds_left: int):
        if not getattr(self, "_gui_ready", False) or not self.winfo_exists():
            return
        self.after(0, lambda: self.timer_readout.configure(text=time_str))

    def update_live_buckets(self, buckets_data: Dict[str, Dict[str, int]]):
        if not getattr(self, "_gui_ready", False) or not self.winfo_exists():
            return
        def _update():
            for tier_key in ["tier_65_80", "tier_80_90"]:
                for rarity, count in buckets_data.get(tier_key, {}).items():
                    lbl = self.bucket_labels[tier_key].get(rarity)
                    if lbl:
                        ready_tag = " [READY]" if count >= 9 else ""
                        lbl.configure(text=f"{rarity}: {count}/9{ready_tag}")
        self.after(0, _update)

    def append_log(self, message: str, level: str = "info"):
        if not getattr(self, "_gui_ready", False) or not self.winfo_exists():
            return
        def _append():
            self.log_textbox.insert("end", message + "\n")
            try:
                line_count = int(self.log_textbox.index("end-1c").split(".")[0])
                if line_count > 400:
                    self.log_textbox.delete("1.0", "100.0")
            except Exception:
                pass
            self.log_textbox.see("end")
        self.after(0, _append)

    def clear_log(self):
        self.log_textbox.delete("1.0", "end")

    def apply_manual_timer_interval(self):
        try:
            val = int(self.entry_timer_min.get().strip())
            val = max(1, min(1440, val))
            self.bot.set_timer_interval(val)
            self.config_data["timer_interval_minutes"] = val
            self._update_auto_loop_button_text()
            self.append_log(f"Cycle timer interval updated to {val} minutes ({val / 60:.1f}h).", "info")
        except Exception as e:
            self.append_log(f"Invalid timer interval: {e}", "warning")

    def set_timer_preset(self, minutes: int):
        self.entry_timer_min.delete(0, "end")
        self.entry_timer_min.insert(0, str(minutes))
        self.apply_manual_timer_interval()

    def _update_auto_loop_button_text(self):
        cur_min = int(self.config_data.get("timer_interval_minutes", 120))
        time_desc = f"{cur_min / 60:.1f}h" if cur_min % 60 != 0 else f"{cur_min // 60}h"
        if getattr(self.bot, "auto_loop_enabled", False):
            self.btn_auto_loop.configure(text=f"⏸ Pause Loop ({time_desc})", fg_color="#b8621b", hover_color="#d47322")
        else:
            self.btn_auto_loop.configure(text=f"▶ Start Loop ({time_desc})", fg_color="#1f7a40", hover_color="#289650")

    def toggle_auto_loop_action(self):
        self.bot.toggle_auto_loop()
        self._update_auto_loop_button_text()

    def run_cycle_now_action(self):
        self.bot.reset_abort_state()
        self.append_log("User requested immediate cycle trigger...", "info")
        self.bot.start_cycle_async()

    def run_test_visual_scan_action(self):
        self.bot.reset_abort_state()
        self.append_log("Running Test Visual Scan on current visible inventory...", "info")
        self.bot.test_visual_scan()
        self.open_visual_debugger(default_mode="inventory")

    def run_test_single_step_scroll_action(self):
        self.bot.reset_abort_state()
        def _worker():
            self.append_log(f"Testing 1-Step Scroll ({self.bot.scroll_mode})...", "info")
            moved, at_bottom, diff = self.bot.test_single_step_scroll()
            if moved:
                self.append_log(f"Test 1-Step Scroll: MOVED successfully (pixel diff: {diff:.2f})", "info")
            else:
                self.append_log(f"Test 1-Step Scroll: No movement detected (pixel diff: {diff:.2f})", "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def run_test_scroll_action(self):
        self.bot.reset_abort_state()
        self.append_log(f"Running Full Scroll Test ({self.bot.scroll_mode})...", "info")
        self.bot.test_scroll_top_to_bottom()

    def run_test_chest_action(self):
        self.bot.reset_abort_state()
        self.append_log("Running Test Chest Detection (chest_pile vs empty_floor)...", "info")
        self.bot.test_chest_detection()
        self.open_visual_debugger(default_mode="chest")

    def run_test_synthesis_action(self):
        self.bot.reset_abort_state()
        def _worker():
            self.append_log("Starting Synthesis Test: Loading 9 gears into Cube via RIGHT-CLICK and proceeding with synthesis...", "info")
            loaded, bracket, rarity = self.bot.test_synthesis_loading()
            t_label = "Lv.80~90" if bracket == "80_90" else "Lv.65~80"
            auto_press = self.bot.config.get("auto_press_synth_btn", True)
            if loaded >= 9:
                if auto_press:
                    self.append_log(f"Test Synthesis Complete: Loaded {loaded}/9 gears ({t_label} {rarity}), clicked Synthesize, and clicked Return button above Auto Input!", "info")
                    messagebox.showinfo(
                        "Synthesis Test Complete",
                        f"Successfully loaded {loaded}/9 gears ({t_label} {rarity}) into the Cube, clicked Synthesize, and clicked the Return button above Auto Input!\n\n"
                        "Synthesis & retrieve sequence completed successfully."
                    )
                else:
                    self.append_log(f"Test Synthesis Finished: Successfully loaded {loaded}/9 gears ({t_label} {rarity}) into Cube! Stopped before pressing Synthesize button.", "info")
                    messagebox.showinfo(
                        "Synthesis Test Complete",
                        f"Successfully loaded {loaded}/9 gears ({t_label} {rarity}) into the Cube via RIGHT-CLICK!\n\n"
                        "Stopped before clicking Synthesize button (auto_press_synth_btn=False)."
                    )
            else:
                self.append_log(f"Test Synthesis Incomplete: Loaded {loaded}/9 gears ({t_label} {rarity}).", "warning")
                messagebox.showinfo(
                    "Synthesis Test Incomplete",
                    f"Loaded {loaded}/9 gears ({t_label} {rarity}) into the Cube."
                )
        threading.Thread(target=_worker, daemon=True).start()

    # ---------------------------------------------------------
    # Tab 2: Asset Checklist & Calibrator
    # ---------------------------------------------------------
    def _build_calibrator_tab(self):
        scroll_container = LightweightScrollableFrame(self.tab_calibrator, bg="#10121c")
        scroll_container.pack(fill="both", expand=True, padx=4, pady=4)
        scrollable = scroll_container.scrollable

        # Header Info Card
        info_card = ctk.CTkFrame(scrollable, fg_color="#181c2e", corner_radius=6)
        info_card.pack(fill="x", padx=6, pady=4)

        ctk.CTkLabel(
            info_card,
            text="📁 ASSET CHECKLIST (15 USER-CAPTURED TEMPLATES IN assets/)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00e5ff"
        ).pack(anchor="w", padx=10, pady=(8, 2))

        NativeLabel(
            info_card,
            text="Every template can be snipped directly from screen and auto-saves to assets/ with the exact required name.\n"
                 "Green ✅ Loaded indicates ready. Click 'Snip Now' on any template to capture or replace it instantly.",
            font=("Segoe UI", 9),
            bg="#181c2e",
            fg="#8892b0",
            justify="left"
        ).pack(anchor="w", padx=10, pady=(0, 6))

        btn_refresh_all = ctk.CTkButton(
            info_card,
            text="🔄 Refresh All Asset Statuses",
            command=self.refresh_all_asset_statuses,
            fg_color="#303548",
            hover_color="#404660",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=26
        )
        btn_refresh_all.pack(anchor="e", padx=10, pady=(0, 8))

        # SS Reference Gear Library Card
        ss_card = ctk.CTkFrame(scrollable, fg_color="#181c2e", corner_radius=6)
        ss_card.pack(fill="x", padx=6, pady=4)

        ss_header_row = tk.Frame(ss_card, bg="#181c2e")
        ss_header_row.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(
            ss_header_row,
            text="🛡 SS REFERENCE GEAR LIBRARY (SS/ FOLDER)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00e5ff"
        ).pack(side="left")

        btn_reload_ss = ctk.CTkButton(
            ss_header_row,
            text="🔄 Reload SS Library",
            command=self.reload_ss_library_action,
            fg_color="#303548",
            hover_color="#404660",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=140,
            height=24
        )
        btn_reload_ss.pack(side="right")

        ss_stats = self.bot.vision.get_reference_library_stats()
        self.lbl_ss_status = NativeLabel(
            ss_card,
            text=ss_stats["status_text"],
            font=("Segoe UI", 10, "bold"),
            bg="#181c2e",
            fg="#38ef7d" if ss_stats["loaded"] else "#ff5555"
        )
        self.lbl_ss_status.pack(anchor="w", padx=10, pady=(2, 2))

        rc = ss_stats["rarity_counts"]
        lc = ss_stats["level_counts"]
        self.lbl_ss_breakdown = NativeLabel(
            ss_card,
            text=f"Rarities: Common: {rc['Common']} | Uncommon: {rc['Uncommon']} | Rare: {rc['Rare']} | Legendary: {rc['Legendary']}\n"
                 f"Levels: Lv.65: {lc['65']} | Lv.80: {lc['80']} | Lv.90: {lc['90']}\n"
                 "Strict Filter: Only gear matching images in SS/ is counted or synthesized. Unmatched items are skipped.",
            font=("Segoe UI", 9),
            bg="#181c2e",
            fg="#d0d5e2",
            justify="left"
        )
        self.lbl_ss_breakdown.pack(anchor="w", padx=10, pady=(0, 8))

        # System Templates Checklist Card (Lightweight Native Treeview)
        tmpl_card = ctk.CTkFrame(scrollable, fg_color="#181c2e", corner_radius=6)
        tmpl_card.pack(fill="x", padx=6, pady=4)

        tmpl_head = tk.Frame(tmpl_card, bg="#181c2e")
        tmpl_head.pack(fill="x", padx=10, pady=(6, 4))

        ctk.CTkLabel(
            tmpl_head,
            text="📁 SYSTEM TEMPLATES CHECKLIST (assets/)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#00e5ff"
        ).pack(side="left")

        btn_snip_tmpl = ctk.CTkButton(
            tmpl_head,
            text="✂ Snip Selected",
            command=self.snip_selected_template_action,
            fg_color="#0d9488",
            hover_color="#0f766e",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=110,
            height=24
        )
        btn_snip_tmpl.pack(side="right", padx=2)

        tree_frame = tk.Frame(tmpl_card, bg="#10121c")
        tree_frame.pack(fill="x", padx=10, pady=(0, 8))

        columns = ("cat", "status", "desc")
        self.template_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            style="Mat.Treeview",
            selectmode="browse",
            show="tree headings",
            height=8
        )
        t_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.template_tree.yview)
        self.template_tree.configure(yscrollcommand=t_scroll.set)
        t_scroll.pack(side="right", fill="y")
        self.template_tree.pack(side="left", fill="both", expand=True)

        self.template_tree.heading("#0", text="FILENAME", anchor="w")
        self.template_tree.column("#0", width=140, minwidth=110, anchor="w")

        self.template_tree.heading("cat", text="CATEGORY", anchor="w")
        self.template_tree.column("cat", width=130, minwidth=90, anchor="w")

        self.template_tree.heading("status", text="STATUS", anchor="center")
        self.template_tree.column("status", width=110, minwidth=85, anchor="center")

        self.template_tree.heading("desc", text="DESCRIPTION", anchor="w")
        self.template_tree.column("desc", width=240, minwidth=160, anchor="w")

        self.template_tree.tag_configure("loaded", foreground="#38ef7d")
        self.template_tree.tag_configure("missing", foreground="#ff5555")
        self.template_tree.tag_configure("optional", foreground="#ffa500")

        self.template_tree.bind("<Double-1>", lambda e: self.snip_selected_template_action())

        self.refresh_all_asset_statuses()

        # Region of Interest (ROI) Calibration Card
        roi_card = ctk.CTkFrame(scrollable, fg_color="#181c2e", corner_radius=6)
        roi_card.pack(fill="x", padx=6, pady=6)

        ctk.CTkLabel(
            roi_card,
            text="🎯 REGION OF INTEREST (ROI) CALIBRATION",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00e5ff"
        ).pack(anchor="w", padx=10, pady=(8, 2))

        NativeLabel(
            roi_card,
            text="Tip: If Inventory Grid ROI is not manually set, the bot automatically anchors it directly above inv_tab_btn.png.",
            font=("Segoe UI", 9),
            bg="#181c2e",
            fg="#8892b0"
        ).pack(anchor="w", padx=10, pady=(0, 6))

        roi_grid = tk.Frame(roi_card, bg="#181c2e")
        roi_grid.pack(fill="x", padx=10, pady=(0, 8))

        # Chest ROI
        self.lbl_chest_roi = NativeLabel(roi_grid, text=self._format_roi_text("chest_region"), font=("Segoe UI", 9), bg="#181c2e", fg="#d0d5e2", width=25, anchor="w")
        self.lbl_chest_roi.grid(row=0, column=0, padx=3, pady=3, sticky="w")
        ctk.CTkButton(
            roi_grid, text="Snip Chest ROI", width=125, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.snip_roi_action("chest_region", "Chest Pile Area", self.lbl_chest_roi)
        ).grid(row=0, column=1, padx=3, pady=3)

        # Inventory Grid ROI
        self.lbl_inv_roi = NativeLabel(roi_grid, text=self._format_roi_text("inventory_grid"), font=("Segoe UI", 9), bg="#181c2e", fg="#d0d5e2", width=25, anchor="w")
        self.lbl_inv_roi.grid(row=1, column=0, padx=3, pady=3, sticky="w")
        ctk.CTkButton(
            roi_grid, text="Snip Inv Grid ROI", width=125, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.snip_roi_action("inventory_grid", "7-Column Inventory Grid", self.lbl_inv_roi)
        ).grid(row=1, column=1, padx=3, pady=3)

        # Synthesis Button Calibration (Point or Area)
        self.lbl_synth_btn = NativeLabel(roi_grid, text=self._format_synth_btn_text(), font=("Segoe UI", 9), bg="#181c2e", fg="#d0d5e2", width=25, anchor="w")
        self.lbl_synth_btn.grid(row=2, column=0, padx=3, pady=3, sticky="w")
        ctk.CTkButton(
            roi_grid, text="🎯 Select Target", width=125, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            command=self.calibrate_synth_btn_action
        ).grid(row=2, column=1, padx=3, pady=3)
        ctk.CTkButton(
            roi_grid, text="▶ Test Click", width=80, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#6366f1", hover_color="#4f46e5",
            command=self.test_click_synth_btn_action
        ).grid(row=2, column=2, padx=3, pady=3)

        # Stash Slot Calibration (Point or Area for full-inventory bypass)
        self.lbl_stash_slot = NativeLabel(roi_grid, text=self._format_stash_slot_text(), font=("Segoe UI", 9), bg="#181c2e", fg="#d0d5e2", width=25, anchor="w")
        self.lbl_stash_slot.grid(row=3, column=0, padx=3, pady=3, sticky="w")
        ctk.CTkButton(
            roi_grid, text="🎯 Select Target", width=125, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            command=self.calibrate_stash_slot_action
        ).grid(row=3, column=1, padx=3, pady=3)
        ctk.CTkButton(
            roi_grid, text="🔄 Test Drag", width=80, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#059669", hover_color="#047857",
            command=self.test_stash_drag_action
        ).grid(row=3, column=2, padx=3, pady=3)

        # Cube Dropdown Calibration
        self.lbl_cube_dropdown = NativeLabel(roi_grid, text=self._format_cube_dropdown_text(), font=("Segoe UI", 9), bg="#181c2e", fg="#d0d5e2", width=25, anchor="w")
        self.lbl_cube_dropdown.grid(row=4, column=0, padx=3, pady=3, sticky="w")
        ctk.CTkButton(
            roi_grid, text="🎯 Select Dropdown", width=125, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            command=self.calibrate_cube_dropdown_action
        ).grid(row=4, column=1, padx=3, pady=3)
        ctk.CTkButton(
            roi_grid, text="▶ Test Dropdown", width=80, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#d97706", hover_color="#b45309",
            command=self.test_cube_dropdown_action
        ).grid(row=4, column=2, padx=3, pady=3)

        # Tier Lv.80~90 Option Calibration
        self.lbl_tier_80_90 = NativeLabel(roi_grid, text=self._format_tier_80_90_text(), font=("Segoe UI", 9), bg="#181c2e", fg="#d0d5e2", width=25, anchor="w")
        self.lbl_tier_80_90.grid(row=5, column=0, padx=3, pady=3, sticky="w")
        ctk.CTkButton(
            roi_grid, text="🎯 Select Lv.80~90", width=125, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            command=self.calibrate_tier_80_90_action
        ).grid(row=5, column=1, padx=3, pady=3)

        # Tier Lv.65~80 Option Calibration
        self.lbl_tier_65_80 = NativeLabel(roi_grid, text=self._format_tier_65_80_text(), font=("Segoe UI", 9), bg="#181c2e", fg="#d0d5e2", width=25, anchor="w")
        self.lbl_tier_65_80.grid(row=6, column=0, padx=3, pady=3, sticky="w")
        ctk.CTkButton(
            roi_grid, text="🎯 Select Lv.65~80", width=125, height=24, font=ctk.CTkFont(size=10, weight="bold"),
            command=self.calibrate_tier_65_80_action
        ).grid(row=6, column=1, padx=3, pady=3)

        # Auto-Select Cube Tier Dropdown Checkbox
        self.var_auto_tier = ctk.BooleanVar(value=bool(self.config_data.get("auto_select_cube_tier", False)))
        chk_auto_tier = ctk.CTkCheckBox(
            roi_grid,
            text="Auto-Select Cube Tier (uncheck to bypass dropdown)",
            font=ctk.CTkFont(size=10),
            variable=self.var_auto_tier,
            command=self.toggle_auto_tier_action
        )
        chk_auto_tier.grid(row=7, column=0, columnspan=3, padx=3, pady=(4, 2), sticky="w")

        # Full Inventory Anticipation Checkbox (Stash Slot Bypass)
        chk_calib_full_inv = ctk.CTkCheckBox(
            roi_grid,
            text="Full Inventory Anticipation (stash 1 slot if full)",
            font=ctk.CTkFont(size=10),
            variable=self.var_full_inv_anticipation,
            command=self.toggle_full_inv_anticipation
        )
        chk_calib_full_inv.grid(row=8, column=0, columnspan=3, padx=3, pady=(2, 4), sticky="w")

        # Manual Adjustment Controls for Inventory Width, Scroll Tracking & Detector
        dim_card = tk.Frame(roi_card, bg="#131625")
        dim_card.pack(fill="x", padx=10, pady=(4, 10))

        tk.Label(
            dim_card,
            text="📏 MANUAL DETECTOR & DIMENSION SETTINGS:",
            font=("Segoe UI", 10, "bold"),
            bg="#131625",
            fg="#ffd166"
        ).grid(row=0, column=0, columnspan=4, padx=8, pady=(6, 4), sticky="w")

        curr_inv = self.config_data.get("rois", {}).get("inventory_grid", {})
        curr_strip_w = self.config_data.get("grid_settings", {}).get("scroll_strip_width", 270)
        curr_conf_pct = int(round(float(self.config_data.get("confidence_threshold", 0.75)) * 100))
        curr_badge_pct = int(round(float(self.config_data.get("badge_match_threshold", 0.75)) * 100))
        curr_bw = int(self.config_data.get("badge_detector_width", 19))
        curr_bh = int(self.config_data.get("badge_detector_height", 15))

        # Row 1: Dimensions
        tk.Label(dim_card, text="Inv Width:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=1, column=0, padx=(8, 2), pady=2, sticky="e")
        self.entry_inv_w = NativeEntry(dim_card, width=7, justify="center")
        self.entry_inv_w.insert(0, str(curr_inv.get("width", 289)))
        self.entry_inv_w.grid(row=1, column=1, padx=(2, 6), pady=2, sticky="w")

        tk.Label(dim_card, text="Inv Height:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=1, column=2, padx=(6, 2), pady=2, sticky="e")
        self.entry_inv_h = NativeEntry(dim_card, width=7, justify="center")
        self.entry_inv_h.insert(0, str(curr_inv.get("height", 122)))
        self.entry_inv_h.grid(row=1, column=3, padx=(2, 6), pady=2, sticky="w")

        # Row 2: Scroll
        tk.Label(dim_card, text="Scroll Width:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=2, column=0, padx=(8, 2), pady=2, sticky="e")
        self.entry_scroll_w = NativeEntry(dim_card, width=7, justify="center")
        self.entry_scroll_w.insert(0, str(curr_strip_w))
        self.entry_scroll_w.grid(row=2, column=1, padx=(2, 6), pady=2, sticky="w")

        tk.Label(dim_card, text="Scroll Depth:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=2, column=2, padx=(6, 2), pady=2, sticky="e")
        self.entry_scroll_depth = NativeEntry(dim_card, width=7, justify="center")
        curr_sdepth = self.config_data.get("grid_settings", {}).get("scroll_depth_px", 40)
        self.entry_scroll_depth.insert(0, str(curr_sdepth))
        self.entry_scroll_depth.grid(row=2, column=3, padx=(2, 6), pady=2, sticky="w")

        # Row 3: Detection Percentages
        tk.Label(dim_card, text="Detect Conf (%):", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=3, column=0, padx=(8, 2), pady=2, sticky="e")
        self.entry_conf_thresh = NativeEntry(dim_card, width=7, justify="center")
        self.entry_conf_thresh.insert(0, str(curr_conf_pct))
        self.entry_conf_thresh.grid(row=3, column=1, padx=(2, 6), pady=2, sticky="w")

        tk.Label(dim_card, text="Badge Match (%):", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=3, column=2, padx=(6, 2), pady=2, sticky="e")
        self.entry_badge_thresh = NativeEntry(dim_card, width=7, justify="center")
        self.entry_badge_thresh.insert(0, str(curr_badge_pct))
        self.entry_badge_thresh.grid(row=3, column=3, padx=(2, 6), pady=2, sticky="w")

        # Row 4: Box Dimensions
        tk.Label(dim_card, text="Box Width:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=4, column=0, padx=(8, 2), pady=2, sticky="e")
        self.entry_badge_w = NativeEntry(dim_card, width=7, justify="center")
        self.entry_badge_w.insert(0, str(curr_bw))
        self.entry_badge_w.grid(row=4, column=1, padx=(2, 6), pady=2, sticky="w")

        tk.Label(dim_card, text="Box Height:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=4, column=2, padx=(6, 2), pady=2, sticky="e")
        self.entry_badge_h = NativeEntry(dim_card, width=7, justify="center")
        self.entry_badge_h.insert(0, str(curr_bh))
        self.entry_badge_h.grid(row=4, column=3, padx=(2, 6), pady=2, sticky="w")

        # Row 5: Coordinates
        curr_synth = self.config_data.get("button_coords", {}).get("cube_synth_btn") or self.config_data.get("button_coords", {}).get("synth_btn", {})
        curr_stash = self.config_data.get("button_coords", {}).get("stash_slot", {})

        tk.Label(dim_card, text="Synth X:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=5, column=0, padx=(8, 2), pady=2, sticky="e")
        self.entry_synth_x = NativeEntry(dim_card, width=7, justify="center")
        self.entry_synth_x.insert(0, str(curr_synth.get("x", 520)))
        self.entry_synth_x.grid(row=5, column=1, padx=(2, 6), pady=2, sticky="w")

        tk.Label(dim_card, text="Synth Y:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=5, column=2, padx=(6, 2), pady=2, sticky="e")
        self.entry_synth_y = NativeEntry(dim_card, width=7, justify="center")
        self.entry_synth_y.insert(0, str(curr_synth.get("y", 510)))
        self.entry_synth_y.grid(row=5, column=3, padx=(2, 6), pady=2, sticky="w")

        # Row 6: Stash Coordinates
        tk.Label(dim_card, text="Stash X:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=6, column=0, padx=(8, 2), pady=2, sticky="e")
        self.entry_stash_x = NativeEntry(dim_card, width=7, justify="center")
        if "x" in curr_stash:
            self.entry_stash_x.insert(0, str(curr_stash["x"]))
        self.entry_stash_x.grid(row=6, column=1, padx=(2, 6), pady=2, sticky="w")

        tk.Label(dim_card, text="Stash Y:", font=("Segoe UI", 9), bg="#131625", fg="#a0aec0").grid(row=6, column=2, padx=(6, 2), pady=2, sticky="e")
        self.entry_stash_y = NativeEntry(dim_card, width=7, justify="center")
        if "y" in curr_stash:
            self.entry_stash_y.insert(0, str(curr_stash["y"]))
        self.entry_stash_y.grid(row=6, column=3, padx=(2, 6), pady=2, sticky="w")

        # Row 7: Action Controls
        btn_box = tk.Frame(dim_card, bg="#131625")
        btn_box.grid(row=7, column=0, columnspan=4, padx=8, pady=(4, 6), sticky="w")

        ctk.CTkButton(
            btn_box,
            text="✔ Apply Settings",
            width=130,
            height=24,
            fg_color="#1f7a40",
            hover_color="#289650",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self.apply_manual_dimensions_action
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_box,
            text="📜 Step Scroll",
            width=95,
            height=24,
            fg_color="#4f46e5",
            hover_color="#4338ca",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self.run_test_single_step_scroll_action
        ).pack(side="left", padx=(0, 6))

        self.var_calib_3corner = ctk.BooleanVar(value=bool(self.config_data.get("multi_corner_rarity_enabled", False)))
        self.cb_calib_3corner = ctk.CTkCheckBox(
            btn_box,
            text="Multi-Corner Rarity",
            variable=self.var_calib_3corner,
            command=self.toggle_calib_3corner_rarity,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ff79c6"
        )
        self.cb_calib_3corner.pack(side="left", padx=2)

        # Diagnostics & Save row
        diag_frame = tk.Frame(scrollable, bg="#10121c")
        diag_frame.pack(fill="x", padx=6, pady=(4, 10))

        diag_grid = tk.Frame(diag_frame, bg="#10121c")
        diag_grid.pack(fill="x", pady=2)

        test_btns = [
            ("🖼 Visual Scan", self.run_test_visual_scan_action, "#4338ca", "#5548db"),
            ("📜 Test Scroll", self.run_test_scroll_action, "#6366f1", "#4f46e5"),
            ("📦 Test Chests", self.run_test_chest_action, "#059669", "#047857"),
            ("🧪 Test Synthesis", self.run_test_synthesis_action, "#8b5cf6", "#7c3aed"),
        ]

        for i, (b_txt, b_cmd, b_fg, b_hov) in enumerate(test_btns):
            b = ctk.CTkButton(
                diag_grid,
                text=b_txt,
                command=b_cmd,
                fg_color=b_fg,
                hover_color=b_hov,
                font=ctk.CTkFont(size=10, weight="bold"),
                height=26
            )
            b.grid(row=0, column=i, padx=2, pady=2, sticky="ew")
            diag_grid.columnconfigure(i, weight=1)

        ctk.CTkButton(
            diag_frame,
            text="💾 Save Configuration",
            command=self.save_config,
            fg_color="#1f7a40",
            hover_color="#289650",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28
        ).pack(fill="x", pady=(4, 2))

    def _format_roi_text(self, roi_key: str) -> str:
        roi = self.config_data.get("rois", {}).get(roi_key, {})
        tag = "Chest" if "chest" in roi_key else "Inv Grid"
        return f"{tag}: {roi.get('width', 0)}x{roi.get('height', 0)} ({roi.get('x', 0)}, {roi.get('y', 0)})"

    def _format_synth_btn_text(self) -> str:
        roi = self.config_data.get("rois", {}).get("synth_btn") or self.config_data.get("rois", {}).get("cube_synth_btn")
        pt = self.config_data.get("button_coords", {}).get("cube_synth_btn") or self.config_data.get("button_coords", {}).get("synth_btn")
        if roi and roi.get("width", 0) > 10 and roi.get("height", 0) > 10:
            return f"Synth Btn: Area ({roi.get('x')}, {roi.get('y')})"
        elif pt and "x" in pt and "y" in pt:
            return f"Synth Btn: Point ({pt.get('x')}, {pt.get('y')})"
        return "Synth Btn: Not set"

    def _format_stash_slot_text(self) -> str:
        roi = self.config_data.get("rois", {}).get("stash_slot")
        pt = self.config_data.get("button_coords", {}).get("stash_slot")
        if roi and roi.get("width", 0) > 10 and roi.get("height", 0) > 10:
            return f"Stash: Area ({roi.get('x')}, {roi.get('y')})"
        elif pt and "x" in pt and "y" in pt and int(pt.get("x", 0)) > 0:
            return f"Stash: Point ({pt.get('x')}, {pt.get('y')})"
        return "Stash Slot: Not set"

    def _format_cube_dropdown_text(self) -> str:
        pt = self.config_data.get("button_coords", {}).get("cube_dropdown")
        if pt and "x" in pt and "y" in pt and int(pt.get("x", 0)) > 0:
            return f"Dropdown: ({pt.get('x')}, {pt.get('y')})"
        return "Dropdown: Not set"

    def _format_tier_80_90_text(self) -> str:
        pt = self.config_data.get("button_coords", {}).get("tier_80_90")
        if pt and "x" in pt and "y" in pt and int(pt.get("x", 0)) > 0:
            return f"Tier 80~90: ({pt.get('x')}, {pt.get('y')})"
        return "Tier 80~90: Auto Offset"

    def _format_tier_65_80_text(self) -> str:
        pt = self.config_data.get("button_coords", {}).get("tier_65_80")
        if pt and "x" in pt and "y" in pt and int(pt.get("x", 0)) > 0:
            return f"Tier 65~80: ({pt.get('x')}, {pt.get('y')})"
        return "Tier 65~80: Auto Offset"

    def snip_selected_template_action(self):
        """Snips the template currently selected in the system templates Treeview."""
        if not hasattr(self, "template_tree") or not self.template_tree.winfo_exists():
            return
        selected = self.template_tree.selection()
        if not selected:
            messagebox.showinfo("Select Template", "Please click a template in the list first, then click 'Snip Selected'.")
            return
        fn = selected[0]
        item = self.template_tree.item(fn)
        desc = item["values"][2] if len(item["values"]) > 2 else fn
        self.snip_template_action(fn, desc)

    def refresh_all_asset_statuses(self):
        """Updates the status in the template treeview and labels dict."""
        if hasattr(self, "template_tree") and self.template_tree.winfo_exists():
            self.template_tree.delete(*self.template_tree.get_children())
            for item in TEMPLATE_MANIFEST:
                fn = item["filename"]
                is_loaded, status_str, dims = self.bot.vision.get_template_status(fn)
                tag = "loaded" if is_loaded else ("optional" if item.get("optional") else "missing")
                self.template_tree.insert(
                    "", "end",
                    iid=fn,
                    text=fn,
                    values=(item["category"], status_str, item["desc"]),
                    tags=(tag,)
                )
        for fn, lbl in self.template_status_labels.items():
            try:
                is_loaded, status_str, dims = self.bot.vision.get_template_status(fn)
                st_color = "#38ef7d" if is_loaded else "#ff5555"
                lbl.configure(text=status_str, text_color=st_color)
            except Exception:
                pass
        self.append_log("All template asset statuses refreshed.", "info")

    def reload_ss_library_action(self):
        """Forces full reload of SS/ reference gear library and updates UI card."""
        stats = self.bot.vision.reload_reference_gear_library()
        if hasattr(self, "lbl_ss_status") and self.lbl_ss_status.winfo_exists():
            self.lbl_ss_status.configure(
                text=stats["status_text"],
                text_color="#38ef7d" if stats["loaded"] else "#ff5555"
            )
        if hasattr(self, "lbl_ss_breakdown") and self.lbl_ss_breakdown.winfo_exists():
            rc = stats["rarity_counts"]
            lc = stats["level_counts"]
            self.lbl_ss_breakdown.configure(
                text=f"Rarities: Common: {rc['Common']} | Uncommon: {rc['Uncommon']} | Rare: {rc['Rare']} | Legendary: {rc['Legendary']}\n"
                     f"Levels: Lv.65: {lc['65']} | Lv.80: {lc['80']} | Lv.90: {lc['90']}\n"
                     "Strict Filter: Only gear matching images in SS/ is counted or synthesized. Unmatched items are skipped."
            )
        self.append_log(f"Reloaded SS/ gear library: {stats['total']} templates active.", "info")

    def apply_manual_dimensions_action(self):
        """Applies user-entered Inventory Grid dimensions, Scroll Strip Width, and Detector parameters, persisting to config.json."""
        try:
            w_val = int(self.entry_inv_w.get().strip())
            h_val = int(self.entry_inv_h.get().strip())
            scroll_w = int(self.entry_scroll_w.get().strip())

            conf_pct = float(self.entry_conf_thresh.get().strip())
            badge_pct = float(self.entry_badge_thresh.get().strip())
            bw_val = int(self.entry_badge_w.get().strip())
            bh_val = int(self.entry_badge_h.get().strip())
            sdepth_val = int(self.entry_scroll_depth.get().strip())

            conf_pct = max(40.0, min(100.0, conf_pct))
            badge_pct = max(30.0, min(100.0, badge_pct))
            bw_val = max(8, min(50, bw_val))
            bh_val = max(6, min(50, bh_val))
            sdepth_val = max(10, min(150, sdepth_val))

            if "rois" not in self.config_data:
                self.config_data["rois"] = {}
            if "inventory_grid" not in self.config_data["rois"]:
                self.config_data["rois"]["inventory_grid"] = {"x": 1243, "y": 639, "width": 289, "height": 122}

            self.config_data["rois"]["inventory_grid"]["width"] = w_val
            self.config_data["rois"]["inventory_grid"]["height"] = h_val

            if "grid_settings" not in self.config_data:
                self.config_data["grid_settings"] = {}
            self.config_data["grid_settings"]["scroll_strip_width"] = scroll_w
            self.config_data["grid_settings"]["scroll_depth_px"] = sdepth_val
            if self.config_data["grid_settings"].get("scroll_amount", -120) < -240:
                self.config_data["grid_settings"]["scroll_amount"] = -120

            self.config_data["confidence_threshold"] = round(conf_pct / 100.0, 2)
            self.config_data["badge_match_threshold"] = round(badge_pct / 100.0, 2)
            self.config_data["badge_detector_width"] = bw_val
            self.config_data["badge_detector_height"] = bh_val
            if hasattr(self, "var_calib_3corner"):
                self.config_data["multi_corner_rarity_enabled"] = self.var_calib_3corner.get()

            # Manual Synth Button Coordinates
            if hasattr(self, "entry_synth_x") and hasattr(self, "entry_synth_y"):
                sx_str = self.entry_synth_x.get().strip()
                sy_str = self.entry_synth_y.get().strip()
                if sx_str and sy_str:
                    try:
                        sx_val = int(sx_str)
                        sy_val = int(sy_str)
                        if "button_coords" not in self.config_data:
                            self.config_data["button_coords"] = {}
                        self.config_data["button_coords"]["cube_synth_btn"] = {"x": sx_val, "y": sy_val}
                        self.config_data["button_coords"]["synth_btn"] = {"x": sx_val, "y": sy_val}
                    except ValueError:
                        pass

            # Manual Stash Slot Coordinates
            if hasattr(self, "entry_stash_x") and hasattr(self, "entry_stash_y"):
                stx_str = self.entry_stash_x.get().strip()
                sty_str = self.entry_stash_y.get().strip()
                if stx_str and sty_str:
                    try:
                        stx_val = int(stx_str)
                        sty_val = int(sty_str)
                        if "button_coords" not in self.config_data:
                            self.config_data["button_coords"] = {}
                        self.config_data["button_coords"]["stash_slot"] = {"x": stx_val, "y": sty_val}
                    except ValueError:
                        pass

            # Save to config.json
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2)

            self.bot.reload_config()
            self.bot.vision.update_config(self.config_data)

            # Sync with debugger window if open
            if self.debugger_window and self.debugger_window.winfo_exists():
                try:
                    self.debugger_window.entry_t_conf.delete(0, "end")
                    self.debugger_window.entry_t_conf.insert(0, str(int(conf_pct)))
                    self.debugger_window.entry_t_badge.delete(0, "end")
                    self.debugger_window.entry_t_badge.insert(0, str(int(badge_pct)))
                    self.debugger_window.entry_t_bw.delete(0, "end")
                    self.debugger_window.entry_t_bw.insert(0, str(bw_val))
                    self.debugger_window.entry_t_bh.delete(0, "end")
                    self.debugger_window.entry_t_bh.insert(0, str(bh_val))
                    if hasattr(self.debugger_window, "entry_t_sdepth"):
                        self.debugger_window.entry_t_sdepth.delete(0, "end")
                        self.debugger_window.entry_t_sdepth.insert(0, str(sdepth_val))
                    if hasattr(self.debugger_window, "var_3corner") and hasattr(self, "var_calib_3corner"):
                        self.debugger_window.var_3corner.set(self.var_calib_3corner.get())
                    self.debugger_window.refresh_view()
                except Exception:
                    pass

            self.lbl_inv_roi.configure(text=self._format_roi_text("inventory_grid"))
            if hasattr(self, "lbl_synth_btn") and self.lbl_synth_btn.winfo_exists():
                self.lbl_synth_btn.configure(text=self._format_synth_btn_text())
            if hasattr(self, "lbl_stash_slot") and self.lbl_stash_slot.winfo_exists():
                self.lbl_stash_slot.configure(text=self._format_stash_slot_text())
            if hasattr(self, "lbl_cube_dropdown") and self.lbl_cube_dropdown.winfo_exists():
                self.lbl_cube_dropdown.configure(text=self._format_cube_dropdown_text())
            if hasattr(self, "lbl_tier_80_90") and self.lbl_tier_80_90.winfo_exists():
                self.lbl_tier_80_90.configure(text=self._format_tier_80_90_text())
            if hasattr(self, "lbl_tier_65_80") and self.lbl_tier_65_80.winfo_exists():
                self.lbl_tier_65_80.configure(text=self._format_tier_65_80_text())
            c_st = "ON" if self.config_data.get("multi_corner_rarity_enabled", False) else "OFF"
            self.append_log(
                f"Saved settings: Conf={int(conf_pct)}% | Badge Match={int(badge_pct)}% | "
                f"Box={bw_val}x{bh_val}px | Inv={w_val}x{h_val}px | Scroll Shift={scroll_w}px | Scroll Depth={sdepth_val}px | 3-Corner Rarity={c_st}",
                "info"
            )
        except Exception as e:
            self.append_log(f"Error applying settings: {e}", "warning")

    def toggle_calib_3corner_rarity(self):
        """Toggles 3-Corner Rarity feature from Calibrator tab and syncs across views."""
        val = self.var_calib_3corner.get()
        self.config_data["multi_corner_rarity_enabled"] = val
        self.save_config()
        self.bot.reload_config()
        self.bot.vision.update_config(self.config_data)
        if self.debugger_window and self.debugger_window.winfo_exists():
            if hasattr(self.debugger_window, "var_3corner"):
                self.debugger_window.var_3corner.set(val)
            self.debugger_window.refresh_view()
        self.append_log(f"3-Corner Rarity Identification feature set to: {'ENABLED' if val else 'DISABLED'}", "info")

    def sync_detector_settings_from_config(self):
        """Syncs entry fields in Calibrator tab when updated from Visual Debugger."""
        try:
            curr_conf_pct = int(round(float(self.config_data.get("confidence_threshold", 0.75)) * 100))
            curr_badge_pct = int(round(float(self.config_data.get("badge_match_threshold", 0.75)) * 100))
            curr_bw = int(self.config_data.get("badge_detector_width", 19))
            curr_bh = int(self.config_data.get("badge_detector_height", 15))
            curr_sdepth = self.config_data.get("grid_settings", {}).get("scroll_depth_px", 40)

            if hasattr(self, "entry_conf_thresh") and self.entry_conf_thresh.winfo_exists():
                self.entry_conf_thresh.delete(0, "end")
                self.entry_conf_thresh.insert(0, str(curr_conf_pct))
            if hasattr(self, "entry_badge_thresh") and self.entry_badge_thresh.winfo_exists():
                self.entry_badge_thresh.delete(0, "end")
                self.entry_badge_thresh.insert(0, str(curr_badge_pct))
            if hasattr(self, "entry_badge_w") and self.entry_badge_w.winfo_exists():
                self.entry_badge_w.delete(0, "end")
                self.entry_badge_w.insert(0, str(curr_bw))
            if hasattr(self, "entry_badge_h") and self.entry_badge_h.winfo_exists():
                self.entry_badge_h.delete(0, "end")
                self.entry_badge_h.insert(0, str(curr_bh))
            if hasattr(self, "entry_scroll_depth") and self.entry_scroll_depth.winfo_exists():
                self.entry_scroll_depth.delete(0, "end")
                self.entry_scroll_depth.insert(0, str(curr_sdepth))
            if hasattr(self, "var_calib_3corner"):
                self.var_calib_3corner.set(bool(self.config_data.get("multi_corner_rarity_enabled", False)))
            self.bot.reload_config()
        except Exception:
            pass

    def snip_roi_action(self, roi_key: str, title: str, label_widget: ctk.CTkLabel):
        def on_done(res):
            self.config_data = self.calibrator.load_config()
            label_widget.configure(text=f"{roi_key}: {res['width']}x{res['height']} at ({res['x']}, {res['y']})")
            if roi_key == "inventory_grid":
                if hasattr(self, "entry_inv_w"):
                    self.entry_inv_w.delete(0, "end")
                    self.entry_inv_w.insert(0, str(res['width']))
                if hasattr(self, "entry_inv_h"):
                    self.entry_inv_h.delete(0, "end")
                    self.entry_inv_h.insert(0, str(res['height']))
            self.append_log(f"Calibrated ROI for {roi_key}: {res['width']}x{res['height']} at ({res['x']}, {res['y']})", "info")

        self.calibrator.snip_roi(roi_key, title, callback=on_done)

    def snip_template_action(self, filename: str, title: str, status_widget: Optional[ctk.CTkLabel] = None):
        if filename in ("synth_btn.png", "cube_synth_btn.png"):
            self.calibrate_synth_btn_action(status_widget=status_widget)
            return
        if filename in ("tier_dropdown.png", "cube_dropdown.png"):
            self.calibrate_cube_dropdown_action(status_widget=status_widget)
            return
        if filename in ("tier_80_90.png",):
            self.calibrate_tier_80_90_action(status_widget=status_widget)
            return
        if filename in ("tier_65_80.png",):
            self.calibrate_tier_65_80_action(status_widget=status_widget)
            return

        def on_done(res):
            if status_widget:
                w, h = res.get("width", 0), res.get("height", 0)
                status_widget.configure(text=f"✅ Loaded ({w}x{h})", text_color="#38ef7d")
            self.bot.vision.clear_cache()
            self.append_log(f"Snipped & saved template '{filename}' ({res['width']}x{res['height']}).", "info")

        self.calibrator.snip_template(filename, title, callback=on_done)

    def calibrate_synth_btn_action(self, status_widget: Optional[ctk.CTkLabel] = None):
        def on_done(res):
            self.config_data = self.calibrator.load_config()
            if hasattr(self, "lbl_synth_btn") and self.lbl_synth_btn.winfo_exists():
                self.lbl_synth_btn.configure(text=self._format_synth_btn_text())
            if hasattr(self, "entry_synth_x") and hasattr(self, "entry_synth_y"):
                pt = self.config_data.get("button_coords", {}).get("cube_synth_btn", {})
                if "x" in pt and "y" in pt:
                    self.entry_synth_x.delete(0, "end")
                    self.entry_synth_x.insert(0, str(pt["x"]))
                    self.entry_synth_y.delete(0, "end")
                    self.entry_synth_y.insert(0, str(pt["y"]))
            if status_widget and status_widget.winfo_exists():
                if res.get("type") == "area":
                    status_widget.configure(text=f"✅ Area ({res['width']}x{res['height']})", text_color="#38ef7d")
                else:
                    status_widget.configure(text=f"✅ Point ({res['x']},{res['y']})", text_color="#38ef7d")
            elif hasattr(self, "template_status_labels") and "synth_btn.png" in self.template_status_labels:
                lbl = self.template_status_labels["synth_btn.png"]
                if lbl.winfo_exists():
                    if res.get("type") == "area":
                        lbl.configure(text=f"✅ Area ({res['width']}x{res['height']})", text_color="#38ef7d")
                    else:
                        lbl.configure(text=f"✅ Point ({res['x']},{res['y']})", text_color="#38ef7d")
            self.bot.reload_config()
            self.bot.vision.clear_cache()
            sel_type = "Area" if res.get("type") == "area" else "Point"
            self.append_log(f"Calibrated Synthesis Button ({sel_type}): target=({res['x']}, {res['y']})", "info")

        self.calibrator.calibrate_point_or_area(
            btn_key="synth_btn",
            title="Synthesize Button — Click for POINT or Drag for AREA",
            template_filename="synth_btn.png",
            callback=on_done
        )

    def test_click_synth_btn_action(self):
        def _worker():
            self.append_log("Testing Synthesis Button click...", "info")
            self.bot.synthesis.click_synth_button()
            self.append_log("Synthesis Button test click completed.", "info")
        threading.Thread(target=_worker, daemon=True).start()

    def calibrate_stash_slot_action(self):
        def on_done(res):
            self.config_data = self.calibrator.load_config()
            if hasattr(self, "lbl_stash_slot") and self.lbl_stash_slot.winfo_exists():
                self.lbl_stash_slot.configure(text=self._format_stash_slot_text())
            if hasattr(self, "lbl_cube_dropdown") and self.lbl_cube_dropdown.winfo_exists():
                self.lbl_cube_dropdown.configure(text=self._format_cube_dropdown_text())
            if hasattr(self, "lbl_tier_80_90") and self.lbl_tier_80_90.winfo_exists():
                self.lbl_tier_80_90.configure(text=self._format_tier_80_90_text())
            if hasattr(self, "lbl_tier_65_80") and self.lbl_tier_65_80.winfo_exists():
                self.lbl_tier_65_80.configure(text=self._format_tier_65_80_text())
            if hasattr(self, "entry_stash_x") and hasattr(self, "entry_stash_y"):
                pt = self.config_data.get("button_coords", {}).get("stash_slot", {})
                if "x" in pt and "y" in pt:
                    self.entry_stash_x.delete(0, "end")
                    self.entry_stash_x.insert(0, str(pt["x"]))
                    self.entry_stash_y.delete(0, "end")
                    self.entry_stash_y.insert(0, str(pt["y"]))
            self.bot.reload_config()
            self.bot.vision.clear_cache()
            sel_type = "Area" if res.get("type") == "area" else "Point"
            self.append_log(f"Calibrated Stash Slot ({sel_type}): target=({res['x']}, {res['y']})", "info")

        self.calibrator.calibrate_point_or_area(
            btn_key="stash_slot",
            title="Stash Slot — Click for POINT or Drag for AREA",
            callback=on_done
        )

    def test_stash_drag_action(self):
        def _worker():
            self.append_log("Testing Stash Transfer (slot 0,0 -> Stash -> slot 0,0)...", "info")
            ok = self.bot.test_stash_transfer()
            if ok:
                self.append_log("Stash transfer test finished successfully!", "info")
            else:
                self.append_log("Stash transfer test failed or aborted.", "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def toggle_auto_tier_action(self):
        val = self.var_auto_tier.get()
        self.config_data["auto_select_cube_tier"] = val
        self.save_config()
        self.bot.reload_config()
        st = "ENABLED (bot will select tier)" if val else "DISABLED (bot skips dropdown & assumes Cube is already set)"
        self.append_log(f"Auto-Select Cube Tier set to: {st}", "info")

    def calibrate_cube_dropdown_action(self, status_widget: Optional[ctk.CTkLabel] = None):
        def on_done(res):
            self.config_data = self.calibrator.load_config()
            if hasattr(self, "lbl_cube_dropdown") and self.lbl_cube_dropdown.winfo_exists():
                self.lbl_cube_dropdown.configure(text=self._format_cube_dropdown_text())
            if status_widget and status_widget.winfo_exists():
                status_widget.configure(text=f"✅ Point ({res['x']},{res['y']})", text_color="#38ef7d")
            elif hasattr(self, "template_status_labels") and "tier_dropdown.png" in self.template_status_labels:
                lbl = self.template_status_labels["tier_dropdown.png"]
                if lbl.winfo_exists():
                    lbl.configure(text=f"✅ Point ({res['x']},{res['y']})", text_color="#38ef7d")
            self.bot.reload_config()
            self.bot.vision.clear_cache()
            self.append_log(f"Calibrated Cube Dropdown: target=({res['x']}, {res['y']})", "info")

        self.calibrator.calibrate_point_or_area(
            btn_key="cube_dropdown",
            title="Cube Tier Dropdown — Click dropdown button on Cube",
            template_filename="tier_dropdown.png",
            callback=on_done
        )

    def calibrate_tier_80_90_action(self, status_widget: Optional[ctk.CTkLabel] = None):
        def on_done(res):
            self.config_data = self.calibrator.load_config()
            if hasattr(self, "lbl_tier_80_90") and self.lbl_tier_80_90.winfo_exists():
                self.lbl_tier_80_90.configure(text=self._format_tier_80_90_text())
            if status_widget and status_widget.winfo_exists():
                status_widget.configure(text=f"✅ Point ({res['x']},{res['y']})", text_color="#38ef7d")
            elif hasattr(self, "template_status_labels") and "tier_80_90.png" in self.template_status_labels:
                lbl = self.template_status_labels["tier_80_90.png"]
                if lbl.winfo_exists():
                    lbl.configure(text=f"✅ Point ({res['x']},{res['y']})", text_color="#38ef7d")
            self.bot.reload_config()
            self.bot.vision.clear_cache()
            self.append_log(f"Calibrated Lv.80~90 Option: target=({res['x']}, {res['y']})", "info")

        self.calibrator.calibrate_point_or_area(
            btn_key="tier_80_90",
            title="Lv.80~90 Option — Open dropdown and click the Lv.80~90 row",
            template_filename="tier_80_90.png",
            callback=on_done
        )

    def calibrate_tier_65_80_action(self, status_widget: Optional[ctk.CTkLabel] = None):
        def on_done(res):
            self.config_data = self.calibrator.load_config()
            if hasattr(self, "lbl_tier_65_80") and self.lbl_tier_65_80.winfo_exists():
                self.lbl_tier_65_80.configure(text=self._format_tier_65_80_text())
            if status_widget and status_widget.winfo_exists():
                status_widget.configure(text=f"✅ Point ({res['x']},{res['y']})", text_color="#38ef7d")
            elif hasattr(self, "template_status_labels") and "tier_65_80.png" in self.template_status_labels:
                lbl = self.template_status_labels["tier_65_80.png"]
                if lbl.winfo_exists():
                    lbl.configure(text=f"✅ Point ({res['x']},{res['y']})", text_color="#38ef7d")
            self.bot.reload_config()
            self.bot.vision.clear_cache()
            self.append_log(f"Calibrated Lv.65~80 Option: target=({res['x']}, {res['y']})", "info")

        self.calibrator.calibrate_point_or_area(
            btn_key="tier_65_80",
            title="Lv.65~80 Option — Open dropdown and click the Lv.65~80 row",
            template_filename="tier_65_80.png",
            callback=on_done
        )

    def test_cube_dropdown_action(self):
        def _worker():
            self.append_log("Testing Cube Dropdown & Lv.80~90 selection...", "info")
            ok = self.bot.test_cube_tier_selection("80_90")
            if ok:
                self.append_log("Cube Dropdown test completed successfully!", "info")
            else:
                self.append_log("Cube Dropdown test could not complete.", "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def open_visual_debugger(self, default_mode: str = "full"):
        """Launches or brings to front the interactive Visual Debugger window."""
        mode_label_map = {"full": "Full Desktop", "inventory": "Inventory Grid", "chest": "Chest Region"}
        if self.debugger_window is not None and self.debugger_window.winfo_exists():
            self.debugger_window.lift()
            self.debugger_window.focus()
            if default_mode != "full":
                self.debugger_window.current_mode = default_mode
                self.debugger_window.mode_selector.set(mode_label_map.get(default_mode, "Full Desktop"))
            self.debugger_window.refresh_view()
        else:
            self.debugger_window = VisualDebuggerWindow(self, self.bot.vision, self.config_data)
            if default_mode != "full":
                self.debugger_window.current_mode = default_mode
                self.debugger_window.mode_selector.set(mode_label_map.get(default_mode, "Full Desktop"))
                self.debugger_window.refresh_view()
        self.append_log(f"Visual Debugger window opened ({mode_label_map.get(default_mode, 'Full Desktop')}).", "info")

    # ---------------------------------------------------------
    # Tab 3: Reference Gear Checklist & Library Verification
    # ---------------------------------------------------------
    def _build_gear_checklist_tab(self):
        # 1. Header & Counter Card
        top_card = ctk.CTkFrame(self.tab_gear_checklist, fg_color="#181c2e", corner_radius=6)
        top_card.pack(fill="x", padx=6, pady=(4, 6))

        title_row = tk.Frame(top_card, bg="#181c2e")
        title_row.pack(fill="x", padx=10, pady=(6, 2))

        ctk.CTkLabel(
            title_row,
            text="🛡 REFERENCE GEAR CHECKLIST (12 GEAR TYPES × 4 RARITIES × 4 LEVELS = 192 MATRIX ITEMS)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00e5ff"
        ).pack(side="left")

        self.lbl_gear_showing_count = NativeLabel(
            title_row,
            text="Showing: 192 / 192 gears",
            font=("Segoe UI", 10, "bold"),
            bg="#181c2e",
            fg="#8892b0"
        )
        self.lbl_gear_showing_count.pack(side="right")

        # Stats Badges Row
        stats_row = tk.Frame(top_card, bg="#181c2e")
        stats_row.pack(fill="x", padx=10, pady=(0, 6))

        self.lbl_badge_total = NativeLabel(
            stats_row, text="Total: 192",
            font=("Segoe UI", 10, "bold"), bg="#181c2e", fg="#d0d5e2"
        )
        self.lbl_badge_total.pack(side="left", padx=(0, 10))

        self.lbl_badge_in_ss = NativeLabel(
            stats_row, text="📁 In SS: 0 / 192",
            font=("Segoe UI", 10, "bold"), bg="#181c2e", fg="#38ef7d"
        )
        self.lbl_badge_in_ss.pack(side="left", padx=10)

        self.lbl_badge_confirmed = NativeLabel(
            stats_row, text="🟢 Confirmed Detected: 0 / 192",
            font=("Segoe UI", 10, "bold"), bg="#181c2e", fg="#00e5ff"
        )
        self.lbl_badge_confirmed.pack(side="left", padx=10)

        self.lbl_badge_missing = NativeLabel(
            stats_row, text="❌ Missing from SS: 0",
            font=("Segoe UI", 10, "bold"), bg="#181c2e", fg="#ff5555"
        )
        self.lbl_badge_missing.pack(side="left", padx=10)

        self.lbl_badge_outliers = NativeLabel(
            stats_row, text="⚠️ Size Outliers (<45px): 0",
            font=("Segoe UI", 10, "bold"), bg="#181c2e", fg="#ffa500"
        )
        self.lbl_badge_outliers.pack(side="left", padx=10)

        # 2. Filter & Actions Toolbar (2-Row Responsive Layout)
        filter_bar = ctk.CTkFrame(self.tab_gear_checklist, fg_color="#181c2e", corner_radius=6)
        filter_bar.pack(fill="x", padx=6, pady=(0, 6))

        filter_row1 = tk.Frame(filter_bar, bg="#181c2e")
        filter_row1.pack(fill="x", padx=4, pady=(4, 2))

        # Filter: Rarity
        tk.Label(filter_row1, text="Rarity:", font=("Segoe UI", 9, "bold"), bg="#181c2e", fg="#8892b0").pack(side="left", padx=(6, 4), pady=2)
        self.gear_rarity_filter_var = ctk.StringVar(value="All Rarities")
        opt_rarity = ctk.CTkOptionMenu(
            filter_row1,
            values=["All Rarities", "Common", "Uncommon", "Rare", "Legendary"],
            variable=self.gear_rarity_filter_var,
            command=lambda _: self.apply_gear_filter(),
            width=115, height=24, font=ctk.CTkFont(size=11)
        )
        opt_rarity.pack(side="left", padx=4, pady=2)

        # Filter: Level
        tk.Label(filter_row1, text="Level:", font=("Segoe UI", 9, "bold"), bg="#181c2e", fg="#8892b0").pack(side="left", padx=(8, 4), pady=2)
        self.gear_level_filter_var = ctk.StringVar(value="All Levels")
        opt_level = ctk.CTkOptionMenu(
            filter_row1,
            values=["All Levels", "Lv. 50", "Lv. 65", "Lv. 80", "Lv. 90"],
            variable=self.gear_level_filter_var,
            command=lambda _: self.apply_gear_filter(),
            width=95, height=24, font=ctk.CTkFont(size=11)
        )
        opt_level.pack(side="left", padx=4, pady=2)

        # Filter: Status
        tk.Label(filter_row1, text="Status:", font=("Segoe UI", 9, "bold"), bg="#181c2e", fg="#8892b0").pack(side="left", padx=(8, 4), pady=2)
        self.gear_status_filter_var = ctk.StringVar(value="All Statuses")
        opt_status = ctk.CTkOptionMenu(
            filter_row1,
            values=[
                "All Statuses",
                "🟢 Confirmed Detected",
                "📁 Listed in SS (Not Detected)",
                "❌ Missing from SS",
                "⚠️ Size Outliers (<45px)"
            ],
            variable=self.gear_status_filter_var,
            command=lambda _: self.apply_gear_filter(),
            width=175, height=24, font=ctk.CTkFont(size=11)
        )
        opt_status.pack(side="left", padx=4, pady=2)

        # Search Entry
        self.gear_search_var = ctk.StringVar(value="")
        self.gear_search_var.trace_add("write", lambda *args: self.apply_gear_filter())
        search_entry = ctk.CTkEntry(
            filter_row1,
            placeholder_text="Search gear...",
            textvariable=self.gear_search_var,
            width=110, height=24, font=ctk.CTkFont(size=11)
        )
        search_entry.pack(side="left", padx=6, pady=2)

        filter_row2 = tk.Frame(filter_bar, bg="#181c2e")
        filter_row2.pack(fill="x", padx=4, pady=(1, 4))

        btn_refresh = ctk.CTkButton(
            filter_row2, text="🔄 Refresh",
            command=self.refresh_gear_checklist_data,
            fg_color="#303548", hover_color="#404660",
            font=ctk.CTkFont(size=10, weight="bold"), width=70, height=24
        )
        btn_refresh.pack(side="left", padx=(4, 4), pady=2)

        btn_test_scan = ctk.CTkButton(
            filter_row2, text="🖼 Test Scan",
            command=self.test_scan_and_confirm_action,
            fg_color="#1f538d", hover_color="#2b6cb0",
            font=ctk.CTkFont(size=10, weight="bold"), width=95, height=24
        )
        btn_test_scan.pack(side="left", padx=2, pady=2)

        btn_snip_selected = ctk.CTkButton(
            filter_row2, text="✂ Snip",
            command=self.snip_selected_gear_action,
            fg_color="#0d9488", hover_color="#0f766e",
            font=ctk.CTkFont(size=10, weight="bold"), width=75, height=24
        )
        btn_snip_selected.pack(side="left", padx=2, pady=2)

        btn_reset = ctk.CTkButton(
            filter_row2, text="🧹 Reset",
            command=self.reset_confirmed_gears_action,
            fg_color="#3a2028", hover_color="#552835",
            font=ctk.CTkFont(size=10, weight="bold"), width=75, height=24
        )
        btn_reset.pack(side="left", padx=2, pady=2)

        # 3. Native Dark-Mode Treeview
        tree_container = ctk.CTkFrame(self.tab_gear_checklist, fg_color="#10121c", corner_radius=6)
        tree_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        tree_style = ttk.Style()
        try:
            tree_style.theme_use("clam")
        except Exception:
            pass

        tree_style.configure(
            "Gear.Treeview",
            background="#141724",
            foreground="#e0e6ed",
            fieldbackground="#10121c",
            rowheight=26,
            font=("Segoe UI", 10),
            borderwidth=0
        )
        tree_style.configure(
            "Gear.Treeview.Heading",
            background="#1e2438",
            foreground="#00e5ff",
            font=("Segoe UI", 10, "bold"),
            relief="flat"
        )
        tree_style.map(
            "Gear.Treeview",
            background=[("selected", "#1f538d")],
            foreground=[("selected", "#ffffff")]
        )

        columns = ("level", "rarity", "ss_status", "confirm")
        self.gear_tree = ttk.Treeview(
            tree_container,
            columns=columns,
            style="Gear.Treeview",
            selectmode="browse",
            show="tree headings"
        )

        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.gear_tree.yview)
        self.gear_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")
        self.gear_tree.pack(side="left", fill="both", expand=True)

        self.gear_tree.heading("#0", text="GEAR TYPE", anchor="w")
        self.gear_tree.column("#0", width=150, minwidth=120, anchor="w")

        self.gear_tree.heading("level", text="LEVEL", anchor="center")
        self.gear_tree.column("level", width=55, minwidth=45, anchor="center")

        self.gear_tree.heading("rarity", text="RARITY", anchor="center")
        self.gear_tree.column("rarity", width=75, minwidth=60, anchor="center")

        self.gear_tree.heading("ss_status", text="SS TEMPLATE", anchor="w")
        self.gear_tree.column("ss_status", width=120, minwidth=90, anchor="w")

        self.gear_tree.heading("confirm", text="CONFIRMATION", anchor="w")
        self.gear_tree.column("confirm", width=140, minwidth=100, anchor="w")

        self.gear_tree.tag_configure("detected", foreground="#38ef7d")
        self.gear_tree.tag_configure("listed", foreground="#60a5fa")
        self.gear_tree.tag_configure("outlier", foreground="#ffa500")
        self.gear_tree.tag_configure("missing", foreground="#ff6b6b")

        self.gear_tree.bind("<Double-1>", self.on_gear_tree_double_click)

        # Pre-build data list for the 144 items
        self.all_gear_items = []
        for r_code, r_name, r_color in RARITIES_ORDER:
            for lv in LEVELS_ORDER:
                for g_name in GEAR_NAMES:
                    fn = f"{r_code}-{lv}-{g_name}.png"
                    icon = GEAR_ICONS.get(g_name, "🗡️")
                    display_name = f"{icon} {g_name.capitalize()}"
                    self.all_gear_items.append({
                        "filename": fn,
                        "gear_name": g_name,
                        "display_name": display_name,
                        "rarity": r_name,
                        "r_code": r_code,
                        "r_color": r_color,
                        "level": lv
                    })

        self.refresh_gear_checklist_data()

    def refresh_gear_checklist_data(self):
        """Scans SS/ directory, measures image dimensions, checks confirmed records, and updates treeview."""
        if not hasattr(self, "all_gear_items") or not self.all_gear_items:
            return

        total_items = len(self.all_gear_items)
        in_ss_count = 0
        confirmed_count = 0
        missing_count = 0
        outlier_count = 0

        for itm in self.all_gear_items:
            fn = itm["filename"]
            path = os.path.join(self.ss_dir, fn)
            file_exists = os.path.exists(path)

            dims = self.ss_file_cache.get(fn)
            if file_exists:
                in_ss_count += 1
                if dims is None:
                    img = cv2.imread(path)
                    if img is not None:
                        dims = (img.shape[1], img.shape[0])
                        self.ss_file_cache[fn] = dims
                    else:
                        dims = (0, 0)

                w, h = dims
                if w > 0 and (w < 45 or h < 45):
                    itm["is_outlier"] = True
                    outlier_count += 1
                    itm["ss_text"] = f"⚠️ {w}x{h} px (Small Outlier)"
                else:
                    itm["is_outlier"] = False
                    itm["ss_text"] = f"📁 {w}x{h} px (Standard)"
            else:
                itm["is_outlier"] = False
                missing_count += 1
                itm["ss_text"] = "❌ Missing from SS"

            if fn in self.confirmed_gears and self.confirmed_gears[fn].get("confirmed"):
                confirmed_count += 1
                cdata = self.confirmed_gears[fn]
                pct = int(cdata.get("score", 1.0) * 100)
                conf_details = f" ({pct}%)" if pct > 0 else ""
                itm["conf_text"] = f"🟢 Confirmed Detected ✅{conf_details}"
                itm["state_key"] = "detected"
                itm["tag"] = "detected"
            elif file_exists:
                itm["conf_text"] = "⬜ Listed in SS (Not Detected Yet)"
                itm["state_key"] = "listed"
                itm["tag"] = "outlier" if itm["is_outlier"] else "listed"
            else:
                itm["conf_text"] = "❌ Missing from SS"
                itm["state_key"] = "missing"
                itm["tag"] = "missing"

        if hasattr(self, "lbl_badge_in_ss") and self.lbl_badge_in_ss.winfo_exists():
            self.lbl_badge_in_ss.configure(text=f"📁 In SS: {in_ss_count} / {total_items}")
            self.lbl_badge_confirmed.configure(text=f"🟢 Confirmed Detected: {confirmed_count} / {total_items}")
            self.lbl_badge_missing.configure(text=f"❌ Missing from SS: {missing_count}")
            self.lbl_badge_outliers.configure(text=f"⚠️ Size Outliers (<45px): {outlier_count}")

        self.apply_gear_filter()

    def apply_gear_filter(self):
        """Filters the 144 checklist rows by Rarity, Level, Status, and Search query and repopulates Treeview."""
        if not hasattr(self, "gear_tree") or not hasattr(self, "all_gear_items"):
            return

        sel_rarity = self.gear_rarity_filter_var.get()
        sel_level = self.gear_level_filter_var.get()
        sel_status = self.gear_status_filter_var.get()
        search_q = self.gear_search_var.get().strip().lower()

        self.gear_tree.delete(*self.gear_tree.get_children())

        visible_count = 0
        for itm in self.all_gear_items:
            fn = itm["filename"]

            if sel_level != "All Levels" and f"Lv. {itm['level']}" != sel_level:
                continue

            if sel_rarity != "All Rarities" and itm["rarity"] != sel_rarity:
                continue

            if sel_status != "All Statuses":
                if sel_status == "🟢 Confirmed Detected" and itm["state_key"] != "detected":
                    continue
                elif sel_status == "📁 Listed in SS (Not Detected)" and itm["state_key"] != "listed":
                    continue
                elif sel_status == "❌ Missing from SS" and itm["state_key"] != "missing":
                    continue
                elif sel_status == "⚠️ Size Outliers (<45px)" and not itm["is_outlier"]:
                    continue

            if search_q and search_q not in itm["gear_name"].lower() and search_q not in fn.lower():
                continue

            self.gear_tree.insert(
                "", "end",
                iid=fn,
                text=itm["display_name"],
                values=(f"Lv.{itm['level']}", itm["rarity"], itm["ss_text"], itm["conf_text"]),
                tags=(itm["tag"],)
            )
            visible_count += 1

        if hasattr(self, "lbl_gear_showing_count") and self.lbl_gear_showing_count.winfo_exists():
            self.lbl_gear_showing_count.configure(text=f"Showing: {visible_count} / {len(self.all_gear_items)} gears")

    def on_gear_tree_double_click(self, event):
        item_id = self.gear_tree.identify_row(event.y)
        if item_id:
            self.gear_tree.selection_set(item_id)
            self.snip_selected_gear_action()

    def snip_selected_gear_action(self):
        """Snips the gear currently selected in the Treeview."""
        selected = self.gear_tree.selection()
        if not selected:
            messagebox.showinfo("Select Gear", "Please click on a gear item in the table to select it before snipping.")
            return

        fn = selected[0]
        item_meta = next((item for item in self.all_gear_items if item["filename"] == fn), None)
        title = f"{item_meta['rarity']} Lv.{item_meta['level']} {item_meta['gear_name']}" if item_meta else fn
        self.snip_gear_to_ss_action(fn, title)

    def snip_gear_to_ss_action(self, filename: str, display_title: str):
        """Opens snipping overlay to capture and crop reference gear image directly into SS/."""
        def on_done(res):
            w, h = res.get("width", 0), res.get("height", 0)
            self.ss_file_cache[filename] = (w, h)
            self.bot.vision.reload_reference_gear_library()
            self.refresh_gear_checklist_data()
            self.append_log(f"Snipped and saved gear template to SS/{filename} ({w}x{h} px).", "info")
            messagebox.showinfo("Gear Snipped", f"Successfully captured and saved SS/{filename} ({w}x{h} px)!\nReference library reloaded.")

        self.calibrator.snip_gear_to_ss(
            filename=filename,
            title=display_title,
            ss_dir=self.ss_dir,
            callback=on_done
        )

    def reset_confirmed_gears_action(self):
        """Clears all confirmed gear detections and saves empty state."""
        if messagebox.askyesno("Reset Detections", "Are you sure you want to clear all confirmed gear detections?"):
            self.confirmed_gears = {}
            self.save_confirmed_gears()
            self.refresh_gear_checklist_data()
            self.append_log("All confirmed gear detections have been cleared.", "info")

    def test_scan_and_confirm_action(self):
        """Runs instant test scan on current visible inventory and auto-confirms all detected items."""
        self.append_log("Scanning visible inventory for gear confirmation...", "info")
        inv_roi = self.bot.vision.get_inventory_roi()
        items = self.bot.vision.scan_visible_inventory(inv_roi)
        self.record_detected_items(items)

        counts: Dict[Tuple[str, str], int] = {
            (b, r): 0
            for b in ["65", "80_90"]
            for r in ["Common", "Uncommon", "Rare", "Legendary"]
        }
        for itm in items:
            b = itm["bracket"]
            r = itm["rarity"]
            if (b, r) in counts:
                counts[(b, r)] += 1
        self.bot._sync_and_publish_counts(counts)

        count = len(items)
        self.append_log(f"Test Scan detected {count} matching items on screen and auto-confirmed them.", "info")
        messagebox.showinfo("Scan Completed", f"Scan finished! Found {count} matching items.\nChecklist and live buckets have been updated.")

    # ---------------------------------------------------------
    # Tab 4: Materials Auto-Stash & Checklist (High-Performance Native Treeview)
    # ---------------------------------------------------------
    def _build_materials_tab(self):
        # 1. Header Card
        top_card = ctk.CTkFrame(self.tab_materials, fg_color="#181c2e", corner_radius=6)
        top_card.pack(fill="x", padx=6, pady=(4, 4))

        title_row = tk.Frame(top_card, bg="#181c2e")
        title_row.pack(fill="x", padx=10, pady=(6, 2))

        ctk.CTkLabel(
            title_row,
            text="📦 MATERIAL LIBRARY & AUTO-STASH (42 TEMPLATES IN SS_materials/)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00e5ff"
        ).pack(side="left")

        stats_btn_row = tk.Frame(top_card, bg="#181c2e")
        stats_btn_row.pack(fill="x", padx=10, pady=(2, 6))

        mat_stats = self.bot.vision.get_material_library_stats()
        self.lbl_mat_status = NativeLabel(
            stats_btn_row,
            text=f"Total: 42 | Loaded: {mat_stats['total']} / 42 templates",
            font=("Segoe UI", 10, "bold"),
            bg="#181c2e",
            fg="#38ef7d" if mat_stats["loaded"] else "#ff5555"
        )
        self.lbl_mat_status.pack(side="left", padx=(0, 10))

        btn_test_mat = ctk.CTkButton(
            stats_btn_row,
            text="🧪 Test Stash",
            command=self.run_test_material_stash_action,
            fg_color="#0284c7",
            hover_color="#0369a1",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=90,
            height=24
        )
        btn_test_mat.pack(side="right", padx=2)

        btn_reload = ctk.CTkButton(
            stats_btn_row,
            text="🔄 Reload",
            command=self.reload_materials_library_action,
            fg_color="#303548",
            hover_color="#404660",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=75,
            height=24
        )
        btn_reload.pack(side="right", padx=2)

        # 2. Material Name Editor & Snip Toolbar Card
        edit_card = ctk.CTkFrame(self.tab_materials, fg_color="#181c2e", corner_radius=6)
        edit_card.pack(fill="x", padx=6, pady=(0, 4))

        edit_row = tk.Frame(edit_card, bg="#181c2e")
        edit_row.pack(fill="x", padx=8, pady=4)

        tk.Label(edit_row, text="Selected:", font=("Segoe UI", 9, "bold"), bg="#181c2e", fg="#8892b0").pack(side="left", padx=(2, 4))
        self.lbl_selected_mat_fn = NativeLabel(
            edit_row, text="(select row)",
            font=("Consolas", 10, "bold"),
            bg="#181c2e",
            fg="#00e5ff", width=12, anchor="w"
        )
        self.lbl_selected_mat_fn.pack(side="left", padx=(0, 6))

        tk.Label(edit_row, text="Name:", font=("Segoe UI", 9, "bold"), bg="#181c2e", fg="#8892b0").pack(side="left", padx=(4, 4))
        self.mat_name_edit_var = ctk.StringVar(value="")
        self.entry_mat_name = ctk.CTkEntry(edit_row, textvariable=self.mat_name_edit_var, font=ctk.CTkFont(size=11), width=160, height=24)
        self.entry_mat_name.pack(side="left", padx=(0, 4))
        self.entry_mat_name.bind("<Return>", lambda e: self.apply_selected_material_name())

        btn_save_one = ctk.CTkButton(
            edit_row,
            text="💾 Save Name",
            command=self.apply_selected_material_name,
            fg_color="#059669",
            hover_color="#047857",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=85,
            height=24
        )
        btn_save_one.pack(side="left", padx=2)

        btn_snip_selected = ctk.CTkButton(
            edit_row,
            text="✂ Snip Selected",
            command=self.snip_selected_material_action,
            fg_color="#0d9488",
            hover_color="#0f766e",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=95,
            height=24
        )
        btn_snip_selected.pack(side="left", padx=4)

        # 3. Native Dark-Mode Treeview
        tree_container = ctk.CTkFrame(self.tab_materials, fg_color="#10121c", corner_radius=6)
        tree_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        tree_style = ttk.Style()
        try:
            tree_style.theme_use("clam")
        except Exception:
            pass

        tree_style.configure(
            "Mat.Treeview",
            background="#121625",
            foreground="#d0d5e2",
            fieldbackground="#121625",
            borderwidth=0,
            font=("Segoe UI", 10),
            rowheight=24
        )
        tree_style.configure(
            "Mat.Treeview.Heading",
            background="#1e2438",
            foreground="#00e5ff",
            font=("Segoe UI", 10, "bold"),
            borderwidth=1,
            relief="flat"
        )
        tree_style.map(
            "Mat.Treeview",
            background=[("selected", "#2d3754")],
            foreground=[("selected", "#ffffff")]
        )

        columns = ("rarity", "filename", "status")
        self.mat_tree = ttk.Treeview(
            tree_container,
            columns=columns,
            style="Mat.Treeview",
            selectmode="browse",
            show="tree headings"
        )

        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.mat_tree.yview)
        self.mat_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")
        self.mat_tree.pack(side="left", fill="both", expand=True)

        self.mat_tree.heading("#0", text="MATERIAL NAME", anchor="w")
        self.mat_tree.column("#0", width=180, minwidth=130, anchor="w")

        self.mat_tree.heading("rarity", text="RARITY", anchor="center")
        self.mat_tree.column("rarity", width=95, minwidth=70, anchor="center")

        self.mat_tree.heading("filename", text="FILENAME", anchor="w")
        self.mat_tree.column("filename", width=120, minwidth=90, anchor="w")

        self.mat_tree.heading("status", text="TEMPLATE STATUS", anchor="w")
        self.mat_tree.column("status", width=140, minwidth=110, anchor="w")

        self.mat_tree.tag_configure("uncommon", foreground="#38ef7d")
        self.mat_tree.tag_configure("rare", foreground="#60a5fa")
        self.mat_tree.tag_configure("legendary", foreground="#ffa500")
        self.mat_tree.tag_configure("immortal", foreground="#ff3366")
        self.mat_tree.tag_configure("missing", foreground="#ff5555")

        self.mat_tree.bind("<<TreeviewSelect>>", self.on_mat_tree_select)
        self.mat_tree.bind("<Double-1>", lambda e: self.snip_selected_material_action())

        self.refresh_materials_checklist_data()

    def refresh_materials_checklist_data(self):
        """Populates or refreshes all 42 material rows in self.mat_tree."""
        if not hasattr(self, "mat_tree") or not self.mat_tree.winfo_exists():
            return
        self.mat_tree.delete(*self.mat_tree.get_children())
        cat_order = [
            ("uncommon", "🟢 Uncommon"),
            ("rare", "🔵 Rare"),
            ("legendary", "🟠 Legendary"),
            ("immortal", "🔴 Immortal")
        ]
        for cat_key, rarity_label in cat_order:
            items = self.materials_manifest.get(cat_key, [])
            for item in items:
                fn = item["filename"]
                mat_name = item["name"]
                fp = os.path.join(self.materials_dir, fn)
                is_loaded = os.path.isfile(fp)
                if is_loaded:
                    try:
                        img = cv2.imread(fp)
                        h, w = img.shape[:2]
                        st_text = f"✅ Loaded ({w}x{h})"
                        tag = cat_key
                    except Exception:
                        st_text = "✅ Loaded"
                        tag = cat_key
                else:
                    st_text = "❌ Missing"
                    tag = "missing"

                self.mat_tree.insert(
                    "", "end",
                    iid=fn,
                    text=mat_name,
                    values=(rarity_label, fn, st_text),
                    tags=(tag,)
                )

    def on_mat_tree_select(self, event=None):
        if not hasattr(self, "mat_tree") or not self.mat_tree.winfo_exists():
            return
        selected = self.mat_tree.selection()
        if not selected:
            return
        fn = selected[0]
        item = self.mat_tree.item(fn)
        mat_name = item["text"]
        self.lbl_selected_mat_fn.configure(text=fn)
        self.mat_name_edit_var.set(mat_name)

    def apply_selected_material_name(self):
        if not hasattr(self, "mat_tree") or not self.mat_tree.winfo_exists():
            return
        selected = self.mat_tree.selection()
        if not selected:
            messagebox.showinfo("Select Material", "Please click a material in the table first.")
            return
        fn = selected[0]
        new_name = self.mat_name_edit_var.get().strip()
        if not new_name:
            return
        for cat_key, items in self.materials_manifest.items():
            for itm in items:
                if itm["filename"] == fn:
                    itm["name"] = new_name
                    break
        self.save_materials_manifest()
        self.bot.vision.clear_cache()
        # Update row text in Treeview
        self.mat_tree.item(fn, text=new_name)
        self.append_log(f"Updated material name: {fn} -> '{new_name}'", "info")

    def snip_selected_material_action(self):
        if not hasattr(self, "mat_tree") or not self.mat_tree.winfo_exists():
            return
        selected = self.mat_tree.selection()
        if not selected:
            messagebox.showinfo("Select Material", "Please select a material row to snip.")
            return
        fn = selected[0]
        item = self.mat_tree.item(fn)
        mat_name = item["text"]
        def on_done(res):
            self.bot.vision.clear_cache()
            self.reload_materials_library_action()
            self.append_log(f"Snipped & saved material template '{fn}' ({res['width']}x{res['height']}).", "info")
            messagebox.showinfo("Material Snipped", f"Successfully captured and saved SS_materials/{fn} ({res['width']}x{res['height']} px)!\nMaterial library reloaded.")
        self.calibrator.snip_material_to_ss(fn, f"{mat_name} ({fn})", materials_dir=self.materials_dir, callback=on_done)

    def toggle_auto_stash_materials(self):
        val = self.var_auto_stash_mat.get()
        self.config_data["auto_stash_materials"] = val
        self.save_config()
        self.bot.reload_config()
        st = "ENABLED" if val else "DISABLED"
        self.append_log(f"Auto-Stash Materials feature set to: {st}", "info")

    def toggle_full_inv_anticipation(self):
        val = self.var_full_inv_anticipation.get()
        self.config_data["full_inventory_anticipation"] = val
        self.save_config()
        self.bot.reload_config()
        st = "ENABLED (bot stashes 1 item to free a slot before synthesis)" if val else "DISABLED (bot synthesizes directly without stash transfer)"
        self.append_log(f"Full Inventory Anticipation feature set to: {st}", "info")

    def on_material_name_changed(self, cat_key: str, filename: str, new_name: str):
        clean_name = new_name.strip()
        if not clean_name:
            return
        items = self.materials_manifest.get(cat_key, [])
        changed = False
        for itm in items:
            if itm["filename"] == filename:
                if itm["name"] != clean_name:
                    itm["name"] = clean_name
                    changed = True
                break
        if changed:
            self.save_materials_manifest()
            self.bot.vision.clear_cache()
            self.append_log(f"Updated material name: {filename} -> '{clean_name}'", "info")

    def save_all_material_names_action(self):
        """Saves any modified material names from the manifest to materials_manifest.json."""
        self.save_materials_manifest()
        self.bot.vision.clear_cache()
        self.refresh_materials_checklist_data()
        self.append_log("Saved material names manifest.", "info")
        messagebox.showinfo("Material Names Saved", "All material names have been saved and applied successfully!")

    def snip_material_action(self, filename: str, name: str, status_widget: Optional[ctk.CTkLabel] = None):
        current_name = name
        def on_done(res):
            self.bot.vision.clear_cache()
            self.reload_materials_library_action()
            self.append_log(f"Snipped & saved material template '{filename}' ({res['width']}x{res['height']}).", "info")
            messagebox.showinfo("Material Snipped", f"Successfully captured and saved SS_materials/{filename} ({res['width']}x{res['height']} px)!\nMaterial library reloaded.")

        self.calibrator.snip_material_to_ss(filename, f"{current_name} ({filename})", materials_dir=self.materials_dir, callback=on_done)

    def reload_materials_library_action(self):
        stats = self.bot.vision.reload_material_library()
        if hasattr(self, "lbl_mat_status") and self.lbl_mat_status.winfo_exists():
            self.lbl_mat_status.configure(
                text=f"Total: 42 | Loaded: {stats['total']} / 42 templates",
                text_color="#38ef7d" if stats["loaded"] else "#ff5555"
            )
        self.refresh_materials_checklist_data()
        self.append_log(f"Reloaded Materials library: {stats['total']} templates active.", "info")

    def run_test_material_stash_action(self):
        self.bot.reset_abort_state()
        def _worker():
            self.append_log("Starting Material Stash Test: scanning visible inventory for materials and executing Ctrl+Right Click...", "info")
            stashed = self.bot.test_material_stash()
            if stashed > 0:
                self.append_log(f"Test Material Stash Complete: Successfully moved {stashed} material(s) into Stash!", "info")
                messagebox.showinfo("Material Stash Test", f"Successfully detected and moved {stashed} material(s) to Stash via Ctrl+Right Click!")
            else:
                self.append_log("Test Material Stash: No materials detected to stash.", "info")
                messagebox.showinfo("Material Stash Test", "No matching materials detected in visible inventory.\n\nTip: Make sure material templates are snipped into SS_materials/.")
        threading.Thread(target=_worker, daemon=True).start()
