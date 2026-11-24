"""
Cycle Scheduler and Countdown Timer Module for Task Bar Hero.
Manages the interval countdown loop, config persistence, and automated background execution.
"""
import time
import json
import threading
from typing import Optional


class CycleScheduler:
    def __init__(self, engine):
        self.engine = engine
        self._stop_scheduler = threading.Event()
        self.scheduler_thread: Optional[threading.Thread] = None

    def start_scheduler_thread(self):
        """Starts the 2-hour scheduler loop in a background daemon thread."""
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return

        def scheduler_loop():
            while not self._stop_scheduler.is_set():
                time.sleep(1)
                if self.engine.auto_loop_enabled and not self.engine.cycle_running:
                    self.engine.seconds_remaining -= 1
                    if self.engine.seconds_remaining <= 0:
                        self.engine.log("Timer elapsed (00:00:00). Initiating 2-hour scheduled cycle...", "info")
                        self.engine.start_cycle_async()
                        self.engine.seconds_remaining = self.engine.interval_seconds

                hours, remainder = divmod(max(0, self.engine.seconds_remaining), 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                try:
                    if self.engine.on_countdown and not self._stop_scheduler.is_set():
                        self.engine.on_countdown(time_str, self.engine.seconds_remaining)
                except Exception:
                    pass

        self.scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        self.scheduler_thread.start()

    def stop_scheduler(self):
        """Stops the scheduler thread."""
        self._stop_scheduler.set()

    def toggle_auto_loop(self) -> bool:
        """Toggles scheduler loop on/off."""
        self.engine.auto_loop_enabled = not self.engine.auto_loop_enabled
        int_min = self.engine.interval_seconds // 60
        if self.engine.auto_loop_enabled:
            self.engine.log(f"Auto Loop Started (Interval: {int_min} min / {int_min / 60:.1f}h).", "info")
            if not self.engine.cycle_running:
                self.engine.set_status("Idle - Waiting for Timer")
        else:
            self.engine.log("Auto Loop Paused.", "warning")
            if not self.engine.cycle_running:
                self.engine.set_status("Paused")
        return self.engine.auto_loop_enabled

    def set_timer_interval(self, minutes: int):
        """Sets the cycle timer interval in minutes and persists to config.json."""
        minutes = max(1, int(minutes))
        self.engine.config["timer_interval_minutes"] = minutes
        self.engine.interval_seconds = minutes * 60
        self.engine.seconds_remaining = self.engine.interval_seconds

        try:
            with open(self.engine.config_path, "r", encoding="utf-8") as f:
                saved_cfg = json.load(f)
            saved_cfg["timer_interval_minutes"] = minutes
            with open(self.engine.config_path, "w", encoding="utf-8") as f:
                json.dump(saved_cfg, f, indent=2)
        except Exception as e:
            self.engine.log(f"Error persisting timer interval: {e}", "warning")

        hours, remainder = divmod(self.engine.seconds_remaining, 3600)
        mins, secs = divmod(remainder, 60)
        time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
        if self.engine.on_countdown:
            self.engine.on_countdown(time_str, self.engine.seconds_remaining)

        self.engine.log(f"Timer interval updated to {minutes} min ({minutes / 60:.1f}h). Countdown reset to {time_str}.", "info")

    def reset_timer(self):
        """Resets timer countdown to configured interval."""
        self.engine.interval_seconds = int(self.engine.config.get("timer_interval_minutes", 120)) * 60
        self.engine.seconds_remaining = self.engine.interval_seconds
