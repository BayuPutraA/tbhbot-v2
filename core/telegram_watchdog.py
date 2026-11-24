from __future__ import annotations
import os
import sys
import time
import json
import uuid
import threading
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Dict, List, Tuple, Any
import cv2
import numpy as np


class SendResult(tuple):
    """
    Backwards-compatible 2-tuple (ok, description) that also exposes .message_id.
    Unpacks as `ok, err = client.send_message(...)` without breaking any caller.
    """
    def __new__(cls, ok: bool, desc: str, message_id: Optional[int] = None):
        return super().__new__(cls, (ok, desc))

    def __init__(self, ok: bool, desc: str, message_id: Optional[int] = None):
        self.ok = ok
        self.description = desc
        self.message_id = message_id


class TelegramClient:
    """
    Lightweight, zero-dependency Telegram Bot API client using standard urllib.
    Supports text messages, HTML formatting, multipart photo uploads, long polling,
    in-place message editing, and anti-clutter message deletion.
    """
    API_BASE = "https://api.telegram.org/bot"

    def __init__(self, token: str, chat_id: str):
        self.token = (token or "").strip()
        self.chat_id = str(chat_id or "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def _api_url(self, method: str) -> str:
        return f"{self.API_BASE}{self.token}/{method}"

    def get_me(self) -> Tuple[bool, Dict[str, Any]]:
        """Validates token by retrieving bot profile."""
        if not self.token:
            return False, {"error": "Bot token not configured"}
        url = self._api_url("getMe")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TaskBarHeroBot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res.get("ok"):
                    return True, res.get("result", {})
                return False, {"error": res.get("description", "Unknown error")}
        except urllib.error.HTTPError as e:
            try:
                err_json = json.loads(e.read().decode("utf-8"))
                return False, {"error": err_json.get("description", str(e))}
            except Exception:
                return False, {"error": f"HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return False, {"error": str(e)}

    def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        target_chat_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Sends a text message to chat_id."""
        cid = target_chat_id or self.chat_id
        if not self.token or not cid:
            return False, "Token or Chat ID not configured"

        payload = {
            "chat_id": cid,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        url = self._api_url("sendMessage")
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TaskBarHeroBot/1.0"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res.get("ok"):
                    mid = res.get("result", {}).get("message_id")
                    return SendResult(True, "Message sent successfully", message_id=mid)
                return SendResult(False, res.get("description", "Failed to send message"), message_id=None)
        except urllib.error.HTTPError as e:
            try:
                err_json = json.loads(e.read().decode("utf-8"))
                return SendResult(False, err_json.get("description", str(e)), message_id=None)
            except Exception:
                return SendResult(False, f"HTTP Error {e.code}: {e.reason}", message_id=None)
        except Exception as e:
            return SendResult(False, str(e), message_id=None)

    def send_photo(
        self,
        photo_source: Any,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        target_chat_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Sends photo as multipart/form-data.
        photo_source can be:
          - numpy.ndarray (BGR image from OpenCV / ScreenCapture)
          - str (filepath to .png / .jpg)
          - bytes (raw image bytes)
        """
        cid = target_chat_id or self.chat_id
        if not self.token or not cid:
            return False, "Token or Chat ID not configured"

        image_bytes: Optional[bytes] = None
        if isinstance(photo_source, np.ndarray):
            ok, buf = cv2.imencode(".jpg", photo_source, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok:
                image_bytes = buf.tobytes()
        elif isinstance(photo_source, str) and os.path.isfile(photo_source):
            with open(photo_source, "rb") as f:
                image_bytes = f.read()
        elif isinstance(photo_source, bytes):
            image_bytes = photo_source

        if not image_bytes:
            return False, "Invalid image source or encoding failed"

        boundary = f"----TBHBoundary{uuid.uuid4().hex}"
        body = bytearray()

        def add_field(name: str, value: str):
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.extend(f"{value}\r\n".encode("utf-8"))

        add_field("chat_id", cid)
        if caption:
            add_field("caption", caption)
        if parse_mode:
            add_field("parse_mode", parse_mode)
        if reply_markup:
            add_field("reply_markup", json.dumps(reply_markup))

        # Add image file part
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="photo"; filename="screenshot.jpg"\r\n')
        body.extend(b"Content-Type: image/jpeg\r\n\r\n")
        body.extend(image_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        url = self._api_url("sendPhoto")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "TaskBarHeroBot/1.0"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res.get("ok"):
                    mid = res.get("result", {}).get("message_id")
                    return SendResult(True, "Photo sent successfully", message_id=mid)
                return SendResult(False, res.get("description", "Failed to send photo"), message_id=None)
        except urllib.error.HTTPError as e:
            try:
                err_json = json.loads(e.read().decode("utf-8"))
                return SendResult(False, err_json.get("description", str(e)), message_id=None)
            except Exception:
                return SendResult(False, f"HTTP Error {e.code}: {e.reason}", message_id=None)
        except Exception as e:
            return SendResult(False, str(e), message_id=None)

    def edit_message_text(
        self,
        text: str,
        message_id: int,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        target_chat_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Edits an existing text message in-place to prevent chat clutter."""
        cid = target_chat_id or self.chat_id
        if not self.token or not cid or not message_id:
            return False, "Token, Chat ID or Message ID missing"

        payload = {
            "chat_id": cid,
            "message_id": int(message_id),
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        url = self._api_url("editMessageText")
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TaskBarHeroBot/1.0"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res.get("ok"):
                    return True, "Message edited successfully"
                return False, res.get("description", "Failed to edit message")
        except urllib.error.HTTPError as e:
            try:
                err_json = json.loads(e.read().decode("utf-8"))
                desc = err_json.get("description", str(e))
                if "message is not modified" in desc.lower():
                    return True, "Message not modified"
                return False, desc
            except Exception:
                return False, f"HTTP Error {e.code}: {e.reason}"
        except Exception as e:
            return False, str(e)

    def edit_message_caption(
        self,
        caption: str,
        message_id: int,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        target_chat_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Edits caption of an existing photo/document in-place."""
        cid = target_chat_id or self.chat_id
        if not self.token or not cid or not message_id:
            return False, "Token, Chat ID or Message ID missing"

        payload = {
            "chat_id": cid,
            "message_id": int(message_id),
            "caption": caption,
            "parse_mode": parse_mode
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        url = self._api_url("editMessageCaption")
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TaskBarHeroBot/1.0"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res.get("ok"):
                    return True, "Caption edited successfully"
                return False, res.get("description", "Failed to edit caption")
        except urllib.error.HTTPError as e:
            try:
                err_json = json.loads(e.read().decode("utf-8"))
                desc = err_json.get("description", str(e))
                if "message is not modified" in desc.lower():
                    return True, "Caption not modified"
                return False, desc
            except Exception:
                return False, f"HTTP Error {e.code}: {e.reason}"
        except Exception as e:
            return False, str(e)

    def delete_message(
        self,
        message_id: int,
        target_chat_id: Optional[str] = None
    ) -> bool:
        """Deletes a message from chat to keep Telegram clean."""
        cid = target_chat_id or self.chat_id
        if not self.token or not cid or not message_id:
            return False

        payload = {
            "chat_id": cid,
            "message_id": int(message_id)
        }
        url = self._api_url("deleteMessage")
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TaskBarHeroBot/1.0"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                res = json.loads(response.read().decode("utf-8"))
                return bool(res.get("ok"))
        except Exception:
            return False

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> bool:
        """Acknowledges button press so the phone stops showing loading spinner."""
        if not self.token or not callback_query_id:
            return False
        url = self._api_url("answerCallbackQuery")
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json", "User-Agent": "TaskBarHeroBot/1.0"}
            )
            with urllib.request.urlopen(req, timeout=8):
                return True
        except Exception:
            return False

    def get_updates(self, offset: Optional[int] = None, timeout: int = 5) -> List[Dict[str, Any]]:
        """Long polls for incoming messages and button clicks."""
        if not self.token:
            return []
        url = self._api_url(f"getUpdates?timeout={timeout}")
        if offset is not None:
            url += f"&offset={offset}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TaskBarHeroBot/1.0"})
            with urllib.request.urlopen(req, timeout=timeout + 10) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res.get("ok"):
                    return res.get("result", [])
                return []
        except Exception:
            return []


class TelegramWatchdog:
    """
    Automated Watchdog & Remote Management Controller.
    - Monitors bot loop state and detects stuck conditions.
    - Captures game screenshot and pushes proactive emergency alerts to phone.
    - Listens for remote Telegram commands (/screenshot, /stash, /status, /pause, /resume, /unstick).
    - Provides interactive Telegram inline keyboard buttons.
    """

    def __init__(self, bot_engine, config: Optional[Dict[str, Any]] = None):
        self.bot = bot_engine
        self.config = config or {}
        tg_cfg = self.config.get("telegram", {})

        self.enabled = bool(tg_cfg.get("enabled", False))
        self.bot_token = tg_cfg.get("bot_token", "")
        self.chat_id = tg_cfg.get("chat_id", "")
        self.notify_on_stuck = bool(tg_cfg.get("notify_on_stuck", True))
        self.stuck_timeout_seconds = int(tg_cfg.get("stuck_timeout_seconds", 180))
        self.notify_on_synth = bool(tg_cfg.get("notify_on_synth", True))
        self.send_screenshot_on_stuck = bool(tg_cfg.get("send_screenshot_on_stuck", True))
        self.periodic_heartbeat_minutes = int(tg_cfg.get("periodic_heartbeat_minutes", 0))

        self.client = TelegramClient(self.bot_token, self.chat_id)

        # State tracking & persistent clean chat tracking
        self.last_progress_time = time.time()
        self.last_status = "Initialized"
        self.is_stuck_alert_sent = False
        self.last_heartbeat_sent = time.time()
        self._stop_event = threading.Event()
        self._listener_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._last_update_id = 0

        # Anti-clutter message IDs
        self.last_dashboard_msg_id: Optional[int] = None
        self.last_photo_msg_id: Optional[int] = None

        # Live Session Tracking
        self.session_stats: Dict[str, Any] = {
            "start_time": time.time(),
            "cycles_completed": 0,
            "syntheses": {"Common": 0, "Uncommon": 0, "Rare": 0, "total": 0},
            "lvl50_stashed": 0,
            "stuck_incidents": 0,
        }

    def reload_config(self, full_config: Dict[str, Any]):
        """Reloads settings from latest config dict and updates client."""
        self.config = full_config
        tg_cfg = self.config.get("telegram", {})
        old_enabled = self.enabled
        old_token = self.bot_token
        old_chat_id = self.chat_id

        self.enabled = bool(tg_cfg.get("enabled", False))
        self.bot_token = tg_cfg.get("bot_token", "").strip()
        self.chat_id = str(tg_cfg.get("chat_id", "")).strip()
        self.notify_on_stuck = bool(tg_cfg.get("notify_on_stuck", True))
        self.stuck_timeout_seconds = max(30, int(tg_cfg.get("stuck_timeout_seconds", 180)))
        self.notify_on_synth = bool(tg_cfg.get("notify_on_synth", True))
        self.send_screenshot_on_stuck = bool(tg_cfg.get("send_screenshot_on_stuck", True))
        self.periodic_heartbeat_minutes = int(tg_cfg.get("periodic_heartbeat_minutes", 0))

        self.client = TelegramClient(self.bot_token, self.chat_id)

        # Restart threads if enabled state or credentials changed
        if (self.enabled != old_enabled or self.bot_token != old_token or self.chat_id != old_chat_id):
            self.stop()
            if self.enabled and self.client.is_configured:
                self.start()

    def start(self):
        """Starts watchdog monitor and remote command listener threads."""
        if not self.enabled or not self.client.is_configured:
            return

        self._stop_event.clear()
        self.last_progress_time = time.time()
        self.is_stuck_alert_sent = False

        if not self._listener_thread or not self._listener_thread.is_alive():
            self._listener_thread = threading.Thread(target=self._listener_loop, name="TelegramListener", daemon=True)
            self._listener_thread.start()

        if not self._watchdog_thread or not self._watchdog_thread.is_alive():
            self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="TelegramWatchdog", daemon=True)
            self._watchdog_thread.start()

        self._log("Telegram Watchdog & Remote Service started.", "info")

    def stop(self):
        """Signals background threads to terminate gracefully."""
        self._stop_event.set()
        self._listener_thread = None
        self._watchdog_thread = None

    # ---------------------------------------------------------
    # Anti-Clutter Dashboard & Photo Presentation Helpers
    # ---------------------------------------------------------
    def send_or_edit_dashboard(
        self,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        edit_msg_id: Optional[int] = None
    ):
        """
        Presents the dashboard in-place whenever possible to avoid message stacking.
        If edit_msg_id is given (from inline callback), edits that message directly.
        Otherwise, tries to edit self.last_dashboard_msg_id.
        If editing fails or no existing dashboard exists, cleans up old dashboard and sends a fresh one.
        """
        if not self.enabled or not self.client.is_configured:
            return

        target_mid = edit_msg_id or self.last_dashboard_msg_id
        if target_mid:
            ok, _ = self.client.edit_message_text(text, message_id=target_mid, reply_markup=reply_markup)
            if ok:
                self.last_dashboard_msg_id = target_mid
                return
            # If editing failed (e.g. message was deleted or was a photo), try deleting old message
            try:
                self.client.delete_message(target_mid)
            except Exception:
                pass

        # Send fresh dashboard and record ID
        res = self.client.send_message(text, reply_markup=reply_markup)
        if getattr(res, "message_id", None):
            self.last_dashboard_msg_id = res.message_id

    def send_photo_cleaned(
        self,
        photo_source: Any,
        caption: str = "",
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Sends photo while deleting the previous photo so images don't stack up.
        """
        if not self.enabled or not self.client.is_configured:
            return SendResult(False, "Telegram not enabled or configured", None)

        if self.last_photo_msg_id:
            try:
                self.client.delete_message(self.last_photo_msg_id)
            except Exception:
                pass
            self.last_photo_msg_id = None

        res = self.client.send_photo(photo_source, caption=caption, reply_markup=reply_markup)
        if getattr(res, "message_id", None):
            self.last_photo_msg_id = res.message_id
        return res

    def _dismiss_photo_action(self, edit_msg_id: Optional[int] = None):
        """Deletes photo message and clears reference."""
        target = edit_msg_id or self.last_photo_msg_id
        if target:
            self.client.delete_message(target)
            if self.last_photo_msg_id == target:
                self.last_photo_msg_id = None

    def _dismiss_dashboard_action(self, edit_msg_id: Optional[int] = None):
        """Deletes dashboard panel and clears reference."""
        target = edit_msg_id or self.last_dashboard_msg_id
        if target:
            self.client.delete_message(target)
            if self.last_dashboard_msg_id == target:
                self.last_dashboard_msg_id = None

    # ---------------------------------------------------------
    # Progress & Session Tracking Hooks
    # ---------------------------------------------------------
    def record_progress(self, status: str):
        """Called whenever bot advances a step or status changes."""
        self.last_progress_time = time.time()
        self.last_status = status

        if self.is_stuck_alert_sent:
            self.is_stuck_alert_sent = False
            if self.enabled and self.client.is_configured:
                msg = f"✅ <b>[BOT RECOVERED]</b>\nBot resumed active loop!\n<b>Current Step:</b> {status}"
                self.send_or_edit_dashboard(msg, self.get_main_inline_keyboard())

    def record_cycle_completed(self):
        """Called when a full bot automation cycle finishes."""
        self.session_stats["cycles_completed"] = self.session_stats.get("cycles_completed", 0) + 1

    def record_stashed(self, count: int):
        """Called when Lv. 50 items are stashed."""
        self.session_stats["lvl50_stashed"] = self.session_stats.get("lvl50_stashed", 0) + int(count)

    def record_stuck_incident(self):
        """Called when stuck watchdog triggers."""
        self.session_stats["stuck_incidents"] = self.session_stats.get("stuck_incidents", 0) + 1

    def notify_synthesis(self, rarity: str, count: int, tier: str = "50"):
        """Sends notification when a Cube synthesis occurs."""
        syn = self.session_stats.setdefault("syntheses", {"Common": 0, "Uncommon": 0, "Rare": 0, "total": 0})
        syn[rarity] = syn.get(rarity, 0) + 1
        syn["total"] = syn.get("total", 0) + 1

        if not self.enabled or not self.notify_on_synth or not self.client.is_configured:
            return

        msg = (
            f"⚗ <b>[CUBE SYNTHESIS COMPLETE]</b>\n"
            f"• <b>Tier:</b> Lv.{tier}\n"
            f"• <b>Rarity:</b> {rarity}\n"
            f"• <b>Items Loaded:</b> {count}/9\n"
            f"• <b>Time:</b> {time.strftime('%H:%M:%S')}"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📊 Session Stats", "callback_data": "screen_stats"},
                    {"text": "🔙 Main Menu", "callback_data": "screen_main"}
                ],
                [
                    {"text": "🗑️ Dismiss Alert", "callback_data": "cmd_dismiss_dashboard"}
                ]
            ]
        }
        self.send_or_edit_dashboard(msg, reply_markup=keyboard)

    # ---------------------------------------------------------
    # Screen Text Builders & Keyboards
    # ---------------------------------------------------------
    def _build_main_dashboard_text(self) -> str:
        cycle_active = bool(getattr(self.bot, "cycle_running", False))
        state_icon = "🟢 RUNNING" if cycle_active else "⚪ IDLE / PAUSED"
        elapsed_stuck = int(time.time() - self.last_progress_time)

        auto_loop = bool(getattr(self.bot, "auto_loop_enabled", False))
        sec_rem = getattr(self.bot, "seconds_remaining", 0)
        h, rem = divmod(max(0, sec_rem), 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}"

        unstopped = getattr(self.bot, "unstopped_loops", 0)
        target_af = int(self.config.get("autofill_synth_every_loops", 5))
        af_enabled = self.config.get("autofill_synth_enabled", True)
        af_str = f"{unstopped}/{target_af} loops" if af_enabled else "OFF ❌"

        return (
            f"🤖 <b>TASKBAR HERO — MISSION CONTROL</b>\n\n"
            f"• <b>Engine State:</b> {state_icon}\n"
            f"• <b>Current Step:</b> <code>{self.last_status}</code>\n"
            f"• <b>Step Duration:</b> {elapsed_stuck}s\n"
            f"• <b>Auto-Loop:</b> {'ACTIVE ✅' if auto_loop else 'DISABLED ❌'} (<code>{time_str}</code>)\n"
            f"• <b>Auto-Fill Synth:</b> <code>{af_str}</code>\n"
            f"• <b>Low-Level (Lv. 50):</b> {'ON ✅' if self.config.get('low_level_stashing_enabled') else 'OFF ❌'}\n"
            f"• <b>Server Time:</b> {time.strftime('%H:%M:%S')}\n\n"
            f"<i>Tap below to navigate or manage bot live:</i>"
        )

    def get_main_inline_keyboard(self) -> Dict[str, Any]:
        """Compact, feature-rich main menu."""
        is_l50 = bool(self.config.get("low_level_stashing_enabled", False))
        l50_label = f"⚙️ Lv.50: {'ON ✅' if is_l50 else 'OFF ❌'}"
        return {
            "inline_keyboard": [
                [
                    {"text": "📊 Session Stats", "callback_data": "screen_stats"},
                    {"text": "⏱ Timer & Loop", "callback_data": "screen_timer"}
                ],
                [
                    {"text": "📦 Chest Cam", "callback_data": "cmd_chest_cam"},
                    {"text": "🗄 Stash Cam", "callback_data": "cmd_stash_cam"}
                ],
                [
                    {"text": "🎒 Full Inv Scan", "callback_data": "cmd_full_inv_scan"},
                    {"text": "📸 Full Screenshot", "callback_data": "cmd_screenshot"}
                ],
                [
                    {"text": "🗄 Stash Inspector", "callback_data": "screen_stash"},
                    {"text": "🔄 Unstick / Reset", "callback_data": "cmd_unstick"}
                ],
                [
                    {"text": "⚗ Auto-Fill Synth", "callback_data": "cmd_autofill_synth"},
                    {"text": l50_label, "callback_data": "cmd_toggle_lvl50"}
                ],
                [
                    {"text": "⏸ Pause Bot", "callback_data": "cmd_pause"},
                    {"text": "▶ Run Now", "callback_data": "cmd_run_now"}
                ],
                [
                    {"text": "🗑️ Close Dashboard", "callback_data": "cmd_dismiss_dashboard"}
                ]
            ]
        }

    def _build_stats_text(self) -> str:
        uptime_sec = int(time.time() - self.session_stats["start_time"])
        uh, urem = divmod(uptime_sec, 3600)
        um, us = divmod(urem, 60)
        uptime_str = f"{uh}h {um:02d}m {us:02d}s"

        syn = self.session_stats.get("syntheses", {})
        c_cnt = syn.get("Common", 0)
        u_cnt = syn.get("Uncommon", 0)
        r_cnt = syn.get("Rare", 0)
        tot_syn = syn.get("total", 0)

        cycles = self.session_stats.get("cycles_completed", 0)
        stashed = self.session_stats.get("lvl50_stashed", 0)
        stuck = self.session_stats.get("stuck_incidents", 0)

        return (
            f"📊 <b>SESSION STATISTICS</b>\n\n"
            f"• <b>Session Uptime:</b> <code>{uptime_str}</code>\n"
            f"• <b>Full Cycles Completed:</b> <b>{cycles}</b>\n"
            f"• <b>Lv. 50 Items Stashed:</b> <b>{stashed}</b>\n"
            f"• <b>Stuck Incidents Recovered:</b> <b>{stuck}</b>\n\n"
            f"<b>⚗️ Cube Syntheses (Session Total):</b>\n"
            f"  • Common:    {c_cnt}\n"
            f"  • Uncommon:  {u_cnt}\n"
            f"  • Rare:      {r_cnt}\n"
            f"  • <b>Total Syntheses:</b> <b>{tot_syn}</b> (freed ~{tot_syn * 8} slots)\n\n"
            f"<i>Live tracking since application started.</i>"
        )

    def get_stats_inline_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "🔄 Refresh Stats", "callback_data": "screen_stats"},
                    {"text": "⏱ Timer & Loop", "callback_data": "screen_timer"}
                ],
                [
                    {"text": "🔙 Back to Main Menu", "callback_data": "screen_main"}
                ]
            ]
        }

    def _build_timer_text(self) -> str:
        auto_loop = bool(getattr(self.bot, "auto_loop_enabled", False))
        sec_rem = getattr(self.bot, "seconds_remaining", 0)
        int_sec = getattr(self.bot, "interval_seconds", 5400)
        int_min = int_sec // 60

        h, rem = divmod(max(0, sec_rem), 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}"

        cycle_active = bool(getattr(self.bot, "cycle_running", False))

        return (
            f"⏱ <b>AUTO-LOOP & TIMER CONTROL</b>\n\n"
            f"• <b>Auto-Loop State:</b> {'🟢 ACTIVE' if auto_loop else '⚪ DISABLED'}\n"
            f"• <b>Configured Interval:</b> {int_min} min ({int_min / 60:.1f} hours)\n"
            f"• <b>Time Until Next Run:</b> <code>{time_str}</code>\n"
            f"• <b>Engine State:</b> {'Executing cycle now' if cycle_active else 'Idle - waiting for timer'}\n\n"
            f"<i>Tap below to toggle auto-loop or start a run now:</i>"
        )

    def get_timer_inline_keyboard(self) -> Dict[str, Any]:
        auto_loop = bool(getattr(self.bot, "auto_loop_enabled", False))
        loop_lbl = "⏸ Pause Auto-Loop" if auto_loop else "▶ Start Auto-Loop"
        return {
            "inline_keyboard": [
                [
                    {"text": loop_lbl, "callback_data": "cmd_toggle_loop"},
                    {"text": "▶ Run Now", "callback_data": "cmd_run_now"}
                ],
                [
                    {"text": "🔄 Reset Timer", "callback_data": "cmd_reset_timer"},
                    {"text": "🔄 Refresh", "callback_data": "screen_timer"}
                ],
                [
                    {"text": "🔙 Back to Main Menu", "callback_data": "screen_main"}
                ]
            ]
        }

    def _build_stash_inspector_text(self) -> str:
        stash_roi = self.config.get("rois", {}).get("stash_grid")
        c_cnt, u_cnt, r_cnt, tot, ready_str = 0, 0, 0, 0, ""
        try:
            if hasattr(self.bot, "vision"):
                res = self.bot.vision.scan_stash_for_lvl50(stash_roi)
                if isinstance(res, dict):
                    counts = res.get("counts", {})
                    c_cnt = int(counts.get("Common", 0) or 0)
                    u_cnt = int(counts.get("Uncommon", 0) or 0)
                    r_cnt = int(counts.get("Rare", 0) or 0)
                    tot = int(res.get("total", 0) or 0)
                    if res.get("is_ready"):
                        ready_str = f"🔥 <b>[READY FOR SYNTH: {res.get('ready_rarity')} >= 9]</b>\n"
        except Exception:
            pass

        cycle_active = bool(getattr(self.bot, "cycle_running", False))

        return (
            f"🗄 <b>STASH INSPECTOR (Tabs 1, 2 & Materials)</b>\n\n"
            f"<b>Stash 1 (Lv. 50 Synthesis Queue):</b>\n"
            f"• <b>Common:</b>   {c_cnt}/9 {'✅' if c_cnt >= 9 else ''}\n"
            f"• <b>Uncommon:</b> {u_cnt}/9 {'✅' if u_cnt >= 9 else ''}\n"
            f"• <b>Rare:</b>     {r_cnt}/9 {'✅' if r_cnt >= 9 else ''}\n"
            f"{ready_str}"
            f"• <b>Total Lv. 50 in View:</b> {tot} items\n\n"
            f"<b>Stash 2 & Materials:</b>\n"
            f"• Stash 2 stores High-Tier (Legendary/Immortal).\n"
            f"• Material tab stores crafting materials.\n\n"
            f"<i>State: {'⚡ Cycle Active (passive view)' if cycle_active else '🟢 Idle (safe to scan tabs)'}</i>"
        )

    def get_stash_inline_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "📸 Stash Grid Screenshot", "callback_data": "cmd_stash_cam"},
                    {"text": "🔍 Scan Stash 1", "callback_data": "cmd_scan_stash_1"}
                ],
                [
                    {"text": "🔍 Scan Stash 2", "callback_data": "cmd_scan_stash_2"},
                    {"text": "💎 Scan Materials", "callback_data": "cmd_scan_mat"}
                ],
                [
                    {"text": "🔄 Refresh", "callback_data": "screen_stash"},
                    {"text": "🔙 Back to Main Menu", "callback_data": "screen_main"}
                ]
            ]
        }

    def _build_inventory_scan_text(self) -> str:
        inv_roi = self.bot.vision.get_inventory_roi() if hasattr(self.bot, "vision") else self.config.get("rois", {}).get("inventory_grid")
        l50_c, l50_u, l50_r, l50_h, mat_count = 0, 0, 0, 0, 0
        try:
            if hasattr(self.bot, "vision"):
                lvl50_items = self.bot.vision.scan_visible_lvl50_items(inv_roi)
                l50_c = sum(1 for x in lvl50_items if x.get("rarity") == "Common")
                l50_u = sum(1 for x in lvl50_items if x.get("rarity") == "Uncommon")
                l50_r = sum(1 for x in lvl50_items if x.get("rarity") == "Rare")
                l50_h = sum(1 for x in lvl50_items if x.get("rarity") in ("Legendary", "Immortal"))
                mat_items = self.bot.vision.scan_visible_materials(inv_roi)
                mat_count = len(mat_items)
        except Exception:
            pass

        tot_l50 = l50_c + l50_u + l50_r + l50_h
        cycle_active = bool(getattr(self.bot, "cycle_running", False))

        return (
            f"🎒 <b>INVENTORY SCAN (Visible Grid)</b>\n\n"
            f"• <b>Lv. 50 Items Visible:</b> <b>{tot_l50}</b>\n"
            f"  - Common: {l50_c} | Uncommon: {l50_u} | Rare: {l50_r}\n"
            f"  - High-Tier (Leg/Imm): {l50_h}\n"
            f"• <b>Materials Visible:</b> <b>{mat_count}</b> stacks\n"
            f"• <b>Tracked Items Total:</b> <b>{tot_l50 + mat_count}</b> slots\n"
            f"• <b>Engine State:</b> {'🟢 Running' if cycle_active else '⚪ Idle'}\n\n"
            f"<i>Tap 'Inventory Cam' below to view visual overlay.</i>"
        )

    def get_inventory_inline_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "🔍 Run Full Scroll Scan", "callback_data": "cmd_full_inv_scan"},
                    {"text": "📸 Inventory Cam", "callback_data": "cmd_inv_cam"}
                ],
                [
                    {"text": "🔄 Quick Scan", "callback_data": "screen_inventory"},
                    {"text": "🔙 Back to Main Menu", "callback_data": "screen_main"}
                ]
            ]
        }

    # ---------------------------------------------------------
    # Background Watchdog Loop
    # ---------------------------------------------------------
    def _watchdog_loop(self):
        while not self._stop_event.is_set():
            time.sleep(4.0)
            if self._stop_event.is_set():
                break

            # 1. Check if bot cycle is active
            cycle_active = bool(getattr(self.bot, "cycle_running", False))
            if not cycle_active:
                self.last_progress_time = time.time()
                self.is_stuck_alert_sent = False
                continue

            # 2. Check elapsed time without progress
            elapsed = time.time() - self.last_progress_time
            if elapsed > self.stuck_timeout_seconds and not self.is_stuck_alert_sent:
                self._handle_stuck_condition(elapsed)

            # 3. Optional periodic heartbeat
            if self.periodic_heartbeat_minutes > 0:
                hb_interval = self.periodic_heartbeat_minutes * 60
                if (time.time() - self.last_heartbeat_sent) > hb_interval:
                    self.last_heartbeat_sent = time.time()
                    self._send_heartbeat_status()

    def _handle_stuck_condition(self, elapsed: float):
        """Triggered when bot exceeds stuck timeout."""
        self.is_stuck_alert_sent = True
        self.record_stuck_incident()
        self._log(f"[Telegram Watchdog] Detected STUCK state ({int(elapsed)}s without progress). Pausing clicking...", "warning")

        # Safely pause bot clicking to prevent rogue clicks
        try:
            self.bot.trigger_emergency_stop()
        except Exception:
            pass

        if not self.notify_on_stuck or not self.client.is_configured:
            return

        alert_msg = (
            f"⚠️ <b>[BOT STUCK ALERT]</b>\n"
            f"The bot appears to have stalled in the game!\n\n"
            f"• <b>Last Status:</b> <code>{self.last_status}</code>\n"
            f"• <b>Stalled For:</b> {int(elapsed)} seconds\n"
            f"• <b>Action:</b> Automated clicking safely paused.\n\n"
            f"<i>Tap below to unstick focus or view a fresh screenshot:</i>"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔄 Unstick & Reset Focus", "callback_data": "cmd_unstick"},
                    {"text": "📸 New Screenshot", "callback_data": "cmd_screenshot"}
                ],
                [
                    {"text": "▶ Resume Loop", "callback_data": "cmd_run_now"},
                    {"text": "🔙 Main Menu", "callback_data": "screen_main"}
                ]
            ]
        }

        # Send photo with alert if enabled
        if self.send_screenshot_on_stuck:
            try:
                screen = self._capture_screen_with_banner("⚠️ STUCK ALERT - Clicking Paused")
                res = self.send_photo_cleaned(screen, caption=alert_msg, reply_markup=keyboard)
                if not res[0]:
                    self.send_or_edit_dashboard(alert_msg, reply_markup=keyboard)
            except Exception:
                self.send_or_edit_dashboard(alert_msg, reply_markup=keyboard)
        else:
            self.send_or_edit_dashboard(alert_msg, reply_markup=keyboard)

    def _send_heartbeat_status(self):
        """Sends periodic healthy ping / dashboard update."""
        self.send_or_edit_dashboard(self._build_main_dashboard_text(), self.get_main_inline_keyboard())

    # ---------------------------------------------------------
    # Background Remote Listener (Long Polling)
    # ---------------------------------------------------------
    def _listener_loop(self):
        while not self._stop_event.is_set():
            if not self.client.is_configured:
                time.sleep(3.0)
                continue

            try:
                updates = self.client.get_updates(offset=self._last_update_id + 1, timeout=5)
                for up in updates:
                    uid = up.get("update_id", 0)
                    if uid > self._last_update_id:
                        self._last_update_id = uid

                    # 1. Handle incoming text commands
                    if "message" in up:
                        msg_obj = up["message"]
                        from_id = str(msg_obj.get("chat", {}).get("id", ""))
                        text = msg_obj.get("text", "").strip()
                        mid = msg_obj.get("message_id")

                        # Security check: only allow configured chat_id
                        if self.chat_id and from_id != self.chat_id:
                            self._log(f"[Telegram Security] Rejected message from unauthorized chat_id: {from_id}", "warning")
                            continue

                        # Clean chat UX: delete user's command message automatically
                        if mid:
                            try:
                                self.client.delete_message(mid)
                            except Exception:
                                pass

                        if text:
                            self._handle_command(text)

                    # 2. Handle button clicks (callback queries)
                    elif "callback_query" in up:
                        cb = up["callback_query"]
                        cb_id = cb.get("id")
                        msg_dict = cb.get("message", {})
                        from_id = str(msg_dict.get("chat", {}).get("id", ""))
                        cb_msg_id = msg_dict.get("message_id")
                        data = cb.get("data", "")

                        if self.chat_id and from_id != self.chat_id:
                            self.client.answer_callback_query(cb_id, text="Unauthorized")
                            continue

                        self.client.answer_callback_query(cb_id)
                        self._handle_callback(data, edit_msg_id=cb_msg_id)

            except Exception:
                time.sleep(3.0)

    # ---------------------------------------------------------
    # Command & Button Handlers
    # ---------------------------------------------------------
    def _handle_command(self, cmd_text: str):
        cmd = cmd_text.split()[0].lower()
        if cmd in ("/start", "/help", "/menu", "/dashboard"):
            self.send_or_edit_dashboard(self._build_main_dashboard_text(), self.get_main_inline_keyboard())

        elif cmd in ("/stats", "/statistics", "/session"):
            self.send_or_edit_dashboard(self._build_stats_text(), self.get_stats_inline_keyboard())

        elif cmd in ("/timer", "/loop", "/countdown"):
            self.send_or_edit_dashboard(self._build_timer_text(), self.get_timer_inline_keyboard())

        elif cmd in ("/chest", "/chestcam", "/box"):
            self._send_chest_cam_action()

        elif cmd in ("/stashcam", "/stashpic", "/stashgrid", "/stash_photo", "/stash_cam"):
            self._send_stash_cam_action()

        elif cmd in ("/stash", "/condition"):
            self.send_or_edit_dashboard(self._build_stash_inspector_text(), self.get_stash_inline_keyboard())

        elif cmd in ("/inv", "/inventory", "/scan", "/scan_inv", "/inv_full", "/full_inv"):
            self._execute_full_inventory_scan_action()

        elif cmd in ("/screenshot", "/pic"):
            self._send_screenshot_action()

        elif cmd in ("/status", "/state"):
            self.send_or_edit_dashboard(self._build_main_dashboard_text(), self.get_main_inline_keyboard())

        elif cmd in ("/unstick", "/reset"):
            self._execute_unstick_action()

        elif cmd in ("/autofill", "/autofill_synth", "/af", "/synth_autofill"):
            self._execute_autofill_synth_action()

        elif cmd in ("/lvl50", "/toggle_lvl50"):
            self._toggle_lvl50_action()

        elif cmd in ("/pause", "/stop"):
            self.bot.trigger_emergency_stop()
            self.send_or_edit_dashboard("⏸ <b>Bot cycle safely PAUSED remotely.</b>", self.get_main_inline_keyboard())

        elif cmd in ("/resume", "/start_cycle", "/play", "/run_now"):
            self.bot.reset_abort_state()
            self.bot.start_cycle_async()
            self.send_or_edit_dashboard("▶ <b>Bot cycle RESUMED remotely!</b>", self.get_main_inline_keyboard())

        elif cmd in ("/dismiss", "/close"):
            self._dismiss_dashboard_action()

        elif cmd in ("/log", "/logs", "/verbosity"):
            parts = cmd_text.split()
            if len(parts) > 1:
                target_mode = parts[1].capitalize()
                if target_mode in ("Clean", "Normal", "Verbose"):
                    self.config["log_verbosity"] = target_mode
                    try:
                        with open("config.json", "w", encoding="utf-8") as f:
                            json.dump(self.config, f, indent=4)
                    except Exception:
                        pass
                    if hasattr(self.bot, "reload_config"):
                        self.bot.reload_config()
                    self.send_or_edit_dashboard(f"📝 <b>Log Verbosity set to:</b> <code>{target_mode}</code>", self.get_main_inline_keyboard())
                else:
                    self.send_or_edit_dashboard("Usage: <code>/log clean</code>, <code>/log normal</code>, or <code>/log verbose</code>", self.get_main_inline_keyboard())
            else:
                curr = self.config.get("log_verbosity", "Clean")
                self.send_or_edit_dashboard(f"📝 <b>Current Log Verbosity:</b> <code>{curr}</code>\nTo change: <code>/log clean</code>, <code>/log normal</code>, or <code>/log verbose</code>", self.get_main_inline_keyboard())

        else:
            self.send_or_edit_dashboard(f"❓ Unknown command <code>{cmd}</code>. Tap a button below:", self.get_main_inline_keyboard())

    def _handle_callback(self, data: str, edit_msg_id: Optional[int] = None):
        # 1. Navigation Screens
        if data == "screen_main":
            self.send_or_edit_dashboard(self._build_main_dashboard_text(), self.get_main_inline_keyboard(), edit_msg_id=edit_msg_id)
        elif data == "screen_stats":
            self.send_or_edit_dashboard(self._build_stats_text(), self.get_stats_inline_keyboard(), edit_msg_id=edit_msg_id)
        elif data == "screen_timer":
            self.send_or_edit_dashboard(self._build_timer_text(), self.get_timer_inline_keyboard(), edit_msg_id=edit_msg_id)
        elif data == "screen_stash":
            self.send_or_edit_dashboard(self._build_stash_inspector_text(), self.get_stash_inline_keyboard(), edit_msg_id=edit_msg_id)
        elif data == "screen_inventory":
            self.send_or_edit_dashboard(self._build_inventory_scan_text(), self.get_inventory_inline_keyboard(), edit_msg_id=edit_msg_id)

        # 2. Cams & Photos
        elif data == "cmd_chest_cam":
            self._send_chest_cam_action()
        elif data == "cmd_stash_cam":
            self._send_stash_cam_action()
        elif data == "cmd_inv_cam":
            self._send_inventory_cam_action()
        elif data == "cmd_full_inv_scan":
            self._execute_full_inventory_scan_action(edit_msg_id=edit_msg_id)
        elif data == "cmd_screenshot":
            self._send_screenshot_action()

        # 3. Stash Grid Actions
        elif data == "cmd_scan_stash_1":
            self._scan_specific_stash_tab("1", edit_msg_id=edit_msg_id)
        elif data == "cmd_scan_stash_2":
            self._scan_specific_stash_tab("2", edit_msg_id=edit_msg_id)
        elif data == "cmd_scan_mat":
            self._scan_specific_stash_tab("material", edit_msg_id=edit_msg_id)

        # 4. Bot Engine Controls
        elif data == "cmd_toggle_loop":
            self._toggle_loop_action(edit_msg_id=edit_msg_id)
        elif data == "cmd_reset_timer":
            if hasattr(self.bot, "scheduler"):
                self.bot.scheduler.reset_timer()
            self.send_or_edit_dashboard(self._build_timer_text(), self.get_timer_inline_keyboard(), edit_msg_id=edit_msg_id)
        elif data == "cmd_run_now":
            self.bot.reset_abort_state()
            if hasattr(self.bot, "scheduler"):
                self.bot.scheduler.reset_timer()
            self.bot.start_cycle_async()
            self.send_or_edit_dashboard("▶ <b>Cycle started immediately!</b>", self.get_main_inline_keyboard(), edit_msg_id=edit_msg_id)
        elif data == "cmd_pause":
            self.bot.trigger_emergency_stop()
            self.send_or_edit_dashboard("⏸ <b>Bot cycle PAUSED.</b>", self.get_main_inline_keyboard(), edit_msg_id=edit_msg_id)
        elif data == "cmd_resume":
            self.bot.reset_abort_state()
            self.bot.start_cycle_async()
            self.send_or_edit_dashboard("▶ <b>Bot cycle RESUMED.</b>", self.get_main_inline_keyboard(), edit_msg_id=edit_msg_id)
        elif data == "cmd_unstick":
            self._execute_unstick_action()
        elif data == "cmd_autofill_synth":
            self._execute_autofill_synth_action(edit_msg_id=edit_msg_id)
        elif data == "cmd_toggle_lvl50":
            self._toggle_lvl50_action(edit_msg_id=edit_msg_id)

        # 5. Dismissals
        elif data == "cmd_dismiss_photo":
            self._dismiss_photo_action(edit_msg_id=edit_msg_id)
        elif data == "cmd_dismiss_dashboard":
            self._dismiss_dashboard_action(edit_msg_id=edit_msg_id)

    # ---------------------------------------------------------
    # Remote Actions
    # ---------------------------------------------------------
    def _toggle_loop_action(self, edit_msg_id: Optional[int] = None):
        if hasattr(self.bot, "scheduler"):
            self.bot.scheduler.toggle_auto_loop()
        self.send_or_edit_dashboard(self._build_timer_text(), self.get_timer_inline_keyboard(), edit_msg_id=edit_msg_id)

    def _toggle_lvl50_action(self, edit_msg_id: Optional[int] = None):
        curr = bool(self.config.get("low_level_stashing_enabled", False))
        new_val = not curr
        self.config["low_level_stashing_enabled"] = new_val
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass
        if hasattr(self.bot, "reload_config"):
            self.bot.reload_config()
        self.send_or_edit_dashboard(self._build_main_dashboard_text(), self.get_main_inline_keyboard(), edit_msg_id=edit_msg_id)

    def _send_screenshot_action(self):
        try:
            banner = f"Status: {self.last_status} | Time: {time.strftime('%H:%M:%S')}"
            img = self._capture_screen_with_banner(banner)
            caption = f"📸 <b>Live Screen Capture</b>\n<b>Status:</b> {self.last_status}"
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🔄 Refresh Screen", "callback_data": "cmd_screenshot"},
                        {"text": "🔙 Main Menu", "callback_data": "screen_main"}
                    ],
                    [
                        {"text": "🗑️ Close Photo", "callback_data": "cmd_dismiss_photo"}
                    ]
                ]
            }
            res = self.send_photo_cleaned(img, caption=caption, reply_markup=keyboard)
            if not res[0]:
                self.send_or_edit_dashboard(f"❌ Failed to send screenshot: {res[1]}", self.get_main_inline_keyboard())
        except Exception as e:
            self.send_or_edit_dashboard(f"❌ Error taking screenshot: {e}", self.get_main_inline_keyboard())

    def _send_chest_cam_action(self):
        """Captures a high-contrast zoomed crop of the chest area with state classification."""
        try:
            chest_roi = self.config.get("rois", {}).get("chest_region")
            if not chest_roi:
                self.send_or_edit_dashboard("❌ Chest ROI not configured in config.json.", self.get_main_inline_keyboard())
                return

            chest_state = self.bot.vision.detect_chest_state(chest_roi) if hasattr(self.bot, "vision") else {}
            full_screen = self.bot.vision.capture_screen() if hasattr(self.bot, "vision") else None
            if full_screen is None:
                from vision.screen import ScreenCapture
                full_screen = ScreenCapture.capture_screen()

            cx = int(chest_roi.get("x", 1265))
            cy = int(chest_roi.get("y", 886))
            cw = int(chest_roi.get("width", 209))
            ch = int(chest_roi.get("height", 66))
            pad = 20
            hf, wf = full_screen.shape[:2]
            x1, y1 = max(0, cx - pad), max(0, cy - pad)
            x2, y2 = min(wf, cx + cw + pad), min(hf, cy + ch + pad)

            crop = full_screen[y1:y2, x1:x2].copy()

            # Status styling
            if chest_state.get("inv_full_found"):
                b_col = (0, 0, 255)  # Red for Inven Full
                st_label = "INVENTORY FULL OVER CHEST"
            elif chest_state.get("chest_found"):
                b_col = (0, 255, 255)  # Yellow for Available Chest
                st_label = f"CHEST AVAILABLE ({chest_state.get('chest_type', 'chest')})"
            elif chest_state.get("empty_found"):
                b_col = (180, 180, 180)  # Gray for Empty Floor
                st_label = "EMPTY FLOOR CONFIRMED"
            else:
                b_col = (56, 239, 125)  # Green
                st_label = "UNVERIFIED CHEST AREA"

            ch_c, cw_c = crop.shape[:2]
            banner_h = 24
            overlay = crop.copy()
            cv2.rectangle(overlay, (0, ch_c - banner_h), (cw_c, ch_c), (18, 18, 22), -1)
            cv2.addWeighted(overlay, 0.8, crop, 0.2, 0, crop)
            cv2.rectangle(crop, (0, 0), (cw_c - 1, ch_c - 1), b_col, 2)
            cv2.putText(
                crop,
                f"CHEST CAM | {st_label}",
                (8, ch_c - 7),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                b_col,
                1,
                cv2.LINE_AA
            )

            caption = (
                f"📦 <b>CHEST AREA MONITOR</b>\n\n"
                f"• <b>Status:</b> <b>{st_label}</b>\n"
                f"• <b>Type:</b> <code>{chest_state.get('chest_type', 'None')}</code>\n"
                f"• <b>Inventory Over Chest:</b> {'⚠️ FULL' if chest_state.get('inv_full_found') else 'OK'}\n"
                f"• <b>Floor Verification:</b> {'Empty' if chest_state.get('empty_found') else 'Contains Chest'}\n"
                f"• <b>Capture Time:</b> {time.strftime('%H:%M:%S')}"
            )
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🔄 Refresh Chest Cam", "callback_data": "cmd_chest_cam"},
                        {"text": "🔙 Main Menu", "callback_data": "screen_main"}
                    ],
                    [
                        {"text": "🗑️ Close Photo", "callback_data": "cmd_dismiss_photo"}
                    ]
                ]
            }
            self.send_photo_cleaned(crop, caption=caption, reply_markup=keyboard)
        except Exception as e:
            self.send_or_edit_dashboard(f"❌ Error generating Chest Cam: {e}", self.get_main_inline_keyboard())

    def _send_inventory_cam_action(self):
        """Captures inventory ROI crop with debug overlays."""
        try:
            inv_roi = self.bot.vision.get_inventory_roi() if hasattr(self.bot, "vision") else self.config.get("rois", {}).get("inventory_grid")
            if not inv_roi:
                self.send_or_edit_dashboard("❌ Inventory ROI not configured.", self.get_main_inline_keyboard())
                return

            full_screen = self.bot.vision.capture_screen() if hasattr(self.bot, "vision") else None
            if full_screen is None:
                from vision.screen import ScreenCapture
                full_screen = ScreenCapture.capture_screen()

            ix = int(inv_roi.get("x", 1243))
            iy = int(inv_roi.get("y", 639))
            iw = int(inv_roi.get("width", 289))
            ih = int(inv_roi.get("height", 122))
            pad = 12
            hf, wf = full_screen.shape[:2]
            x1, y1 = max(0, ix - pad), max(0, iy - pad)
            x2, y2 = min(wf, ix + iw + pad), min(hf, iy + ih + pad)

            crop = full_screen[y1:y2, x1:x2].copy()

            ch_c, cw_c = crop.shape[:2]
            banner_h = 24
            overlay = crop.copy()
            cv2.rectangle(overlay, (0, ch_c - banner_h), (cw_c, ch_c), (18, 18, 22), -1)
            cv2.addWeighted(overlay, 0.8, crop, 0.2, 0, crop)
            cv2.rectangle(crop, (0, 0), (cw_c - 1, ch_c - 1), (56, 239, 125), 2)
            cv2.putText(
                crop,
                f"INVENTORY CAM | {time.strftime('%H:%M:%S')}",
                (8, ch_c - 7),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )

            caption = (
                f"🎒 <b>INVENTORY CAM (Live Crop)</b>\n"
                f"• <b>ROI:</b> ({ix}, {iy}, {iw}x{ih})\n"
                f"• <b>Engine State:</b> {'Running' if getattr(self.bot, 'cycle_running', False) else 'Idle'}\n"
                f"• <b>Capture Time:</b> {time.strftime('%H:%M:%S')}"
            )
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🔄 Refresh Cam", "callback_data": "cmd_inv_cam"},
                        {"text": "🔙 Main Menu", "callback_data": "screen_main"}
                    ],
                    [
                        {"text": "🗑️ Close Photo", "callback_data": "cmd_dismiss_photo"}
                    ]
                ]
            }
            self.send_photo_cleaned(crop, caption=caption, reply_markup=keyboard)
        except Exception as e:
            self.send_or_edit_dashboard(f"❌ Error generating Inventory Cam: {e}", self.get_main_inline_keyboard())

    def _send_stash_cam_action(self):
        """Captures a screenshot of the Stash Grid ROI and sends with quick tab actions."""
        try:
            stash_roi = self.config.get("rois", {}).get("stash_grid")
            if not stash_roi:
                self.send_or_edit_dashboard("❌ Stash ROI not configured in config.json.", self.get_main_inline_keyboard())
                return

            full_screen = self.bot.vision.capture_screen() if hasattr(self.bot, "vision") else None
            if full_screen is None:
                from vision.screen import ScreenCapture
                full_screen = ScreenCapture.capture_screen()

            sx = int(stash_roi.get("x", 912))
            sy = int(stash_roi.get("y", 523))
            sw = int(stash_roi.get("width", 297))
            sh = int(stash_roi.get("height", 299))
            pad = 12
            hf, wf = full_screen.shape[:2]
            x1, y1 = max(0, sx - pad), max(0, sy - pad)
            x2, y2 = min(wf, sx + sw + pad), min(hf, sy + sh + pad)

            crop = full_screen[y1:y2, x1:x2].copy()

            # Decorative border & banner
            ch_c, cw_c = crop.shape[:2]
            banner_h = 24
            overlay = crop.copy()
            cv2.rectangle(overlay, (0, ch_c - banner_h), (cw_c, ch_c), (18, 18, 22), -1)
            cv2.addWeighted(overlay, 0.8, crop, 0.2, 0, crop)
            cv2.rectangle(crop, (0, 0), (cw_c - 1, ch_c - 1), (0, 229, 255), 2)
            cv2.putText(
                crop,
                f"STASH GRID CAM | {time.strftime('%H:%M:%S')}",
                (8, ch_c - 7),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (0, 229, 255),
                1,
                cv2.LINE_AA
            )

            # Check Lv. 50 counts in this grid
            c_cnt, u_cnt, r_cnt, tot, ready_str = 0, 0, 0, 0, ""
            try:
                if hasattr(self.bot, "vision"):
                    res = self.bot.vision.scan_stash_for_lvl50(stash_roi)
                    if isinstance(res, dict):
                        counts = res.get("counts", {})
                        c_cnt = int(counts.get("Common", 0) or 0)
                        u_cnt = int(counts.get("Uncommon", 0) or 0)
                        r_cnt = int(counts.get("Rare", 0) or 0)
                        tot = int(res.get("total", 0) or 0)
                        if res.get("is_ready"):
                            ready_str = f"🔥 <b>Ready for Synth: {res.get('ready_rarity')}</b>\n"
            except Exception:
                pass

            caption = (
                f"🗄 <b>STASH GRID SNAPSHOT</b>\n\n"
                f"• <b>ROI:</b> ({sx}, {sy}, {sw}x{sh})\n"
                f"• <b>Lv. 50 in View:</b> <b>{tot}</b> (C: {c_cnt} | U: {u_cnt} | R: {r_cnt})\n"
                f"{ready_str}"
                f"• <b>Engine State:</b> {'🟢 Running' if getattr(self.bot, 'cycle_running', False) else '⚪ Idle'}\n"
                f"• <b>Capture Time:</b> {time.strftime('%H:%M:%S')}"
            )
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🔄 Refresh Stash Cam", "callback_data": "cmd_stash_cam"},
                        {"text": "🔍 Scan Stash 1", "callback_data": "cmd_scan_stash_1"}
                    ],
                    [
                        {"text": "🔍 Scan Stash 2", "callback_data": "cmd_scan_stash_2"},
                        {"text": "💎 Scan Materials", "callback_data": "cmd_scan_mat"}
                    ],
                    [
                        {"text": "🔙 Main Menu", "callback_data": "screen_main"},
                        {"text": "🗑️ Close Photo", "callback_data": "cmd_dismiss_photo"}
                    ]
                ]
            }
            self.send_photo_cleaned(crop, caption=caption, reply_markup=keyboard)
        except Exception as e:
            self.send_or_edit_dashboard(f"❌ Error generating Stash Cam: {e}", self.get_main_inline_keyboard())

    def _execute_full_inventory_scan_action(self, edit_msg_id: Optional[int] = None):
        """
        Executes a complete top-to-bottom scroll scan of the inventory and lists
        detected gear broken down by Lv. 65 and Lv. 80 tiers.
        """
        if getattr(self.bot, "cycle_running", False):
            self.send_or_edit_dashboard(
                "⚠️ <b>Action Blocked While Cycle Running</b>\n\n"
                f"The bot is actively executing a cycle (Step: <code>{self.last_status}</code>).\n"
                "A full inventory scan scrolls through the inventory top-to-bottom and requires mouse control.\n\n"
                "Please pause the bot first with <b>Pause Bot</b> or wait for the current cycle to complete.",
                self.get_inventory_inline_keyboard(),
                edit_msg_id=edit_msg_id
            )
            return

        # Show scanning progress message
        self.send_or_edit_dashboard(
            "⏳ <b>SCANNING FULL INVENTORY (Top to Bottom)...</b>\n\n"
            "• Focusing inventory slot (0,0)\n"
            "• Scrolling to top row\n"
            "• Analyzing Lv. 65 and Lv. 80 gear across all pages...\n\n"
            "<i>Please wait ~3-5 seconds...</i>",
            self.get_inventory_inline_keyboard(),
            edit_msg_id=edit_msg_id
        )

        try:
            if hasattr(self.bot, "scan_full_inventory_items"):
                items = self.bot.scan_full_inventory_items()
            else:
                roi = self.bot.vision.get_inventory_roi() if hasattr(self.bot, "vision") else None
                items = self.bot.vision.scan_visible_inventory(roi) if hasattr(self.bot, "vision") else []

            report_text = self._format_gear_scan_report(items)
            self.send_or_edit_dashboard(report_text, self.get_inventory_inline_keyboard(), edit_msg_id=edit_msg_id)
        except Exception as e:
            self.send_or_edit_dashboard(
                f"❌ Error during full inventory scan: {e}",
                self.get_inventory_inline_keyboard(),
                edit_msg_id=edit_msg_id
            )

    def _format_gear_scan_report(self, items: List[Dict[str, Any]]) -> str:
        """Formats full inventory scan into an organized breakdown of Lv. 65 and Lv. 80 gear."""
        by_level: Dict[str, List[Dict[str, Any]]] = {"65": [], "80": [], "50": [], "90": [], "other": []}
        for itm in items:
            lv = str(itm.get("level", "")).strip()
            if lv in by_level:
                by_level[lv].append(itm)
            else:
                by_level["other"].append(itm)

        def group_by_rarity_and_name(gear_list: List[Dict[str, Any]]) -> str:
            if not gear_list:
                return "  <i>None detected</i>\n"
            rarity_order = ["Common", "Uncommon", "Rare", "Legendary", "Immortal"]
            lines = []
            for r in rarity_order:
                r_items = [x for x in gear_list if x.get("rarity") == r]
                if not r_items:
                    continue
                name_counts: Dict[str, int] = {}
                for x in r_items:
                    gn = str(x.get("gear_name", "gear")).capitalize()
                    name_counts[gn] = name_counts.get(gn, 0) + 1
                names_str = ", ".join(f"{name} ({cnt})" if cnt > 1 else name for name, cnt in sorted(name_counts.items()))
                lines.append(f"  • <b>{r} ({len(r_items)}):</b> {names_str}")
            return "\n".join(lines) + "\n" if lines else "  <i>None detected</i>\n"

        tot_65 = len(by_level["65"])
        tot_80 = len(by_level["80"])
        tot_50 = len(by_level["50"])
        tot_90 = len(by_level["90"])

        txt = (
            f"🎒 <b>FULL INVENTORY GEAR SCAN</b>\n\n"
            f"• <b>Total Gear Verified:</b> <b>{len(items)}</b> items\n\n"
            f"⚔️ <b>LEVEL 65 GEAR (Total: {tot_65})</b>\n"
            f"{group_by_rarity_and_name(by_level['65'])}\n"
            f"🛡️ <b>LEVEL 80 GEAR (Total: {tot_80})</b>\n"
            f"{group_by_rarity_and_name(by_level['80'])}\n"
            f"📦 <b>Other Level Brackets:</b>\n"
            f"  • Lv. 50: {tot_50} items\n"
            f"  • Lv. 90: {tot_90} items\n"
        )
        if by_level["other"]:
            txt += f"  • Other / Unclassified: {len(by_level['other'])} items\n"
        txt += f"\n<i>Scan completed top-to-bottom and restored to top row.</i>"
        return txt

    def _scan_specific_stash_tab(self, tab_name: str, edit_msg_id: Optional[int] = None):
        """Safely scans Stash 1, Stash 2, or Material tab when bot is idle/paused."""
        if getattr(self.bot, "cycle_running", False):
            self.send_or_edit_dashboard(
                "⚠️ <b>Action Blocked While Cycle Running</b>\n\n"
                "The bot is actively executing a cycle. Live mouse tab-switching is paused to prevent disrupting game actions.\n\n"
                "Pause the bot first or view passive status.",
                self.get_stash_inline_keyboard(),
                edit_msg_id=edit_msg_id
            )
            return

        btn_coords = self.config.get("button_coords", {})
        stash_roi = self.config.get("rois", {}).get("stash_grid")
        target_tab = btn_coords.get(f"stash_tab_{tab_name}")
        mat_tab = btn_coords.get("stash_tab_material")

        if not target_tab or not stash_roi:
            self.send_or_edit_dashboard(
                f"❌ Stash tab coords for '{tab_name}' not configured in config.json.",
                self.get_stash_inline_keyboard(),
                edit_msg_id=edit_msg_id
            )
            return

        try:
            # Click target tab
            self.bot.click_point(target_tab["x"], target_tab["y"], delay_after=0.35)
            time.sleep(0.3)

            if tab_name == "material":
                mat_items = self.bot.vision.scan_visible_materials(stash_roi) if hasattr(self.bot, "vision") else []
                res_text = (
                    f"💎 <b>MATERIAL STASH TAB REPORT</b>\n\n"
                    f"• <b>Detected Material Stacks:</b> {len(mat_items)}\n"
                    f"• <b>Scan Time:</b> {time.strftime('%H:%M:%S')}\n\n"
                    f"<i>Grid scanned and restored to default Material tab.</i>"
                )
            else:
                res = self.bot.vision.scan_stash_for_lvl50(stash_roi) if hasattr(self.bot, "vision") else {}
                counts = res.get("counts", {}) if isinstance(res, dict) else {}
                c_cnt = int(counts.get("Common", 0) or 0)
                u_cnt = int(counts.get("Uncommon", 0) or 0)
                r_cnt = int(counts.get("Rare", 0) or 0)
                tot = int(res.get("total", 0) or 0)
                ready_str = f"🔥 <b>[READY FOR SYNTHESIS: {res.get('ready_rarity')} >= 9]</b>\n" if res.get("is_ready") else ""

                tab_label = "Stash 1 (Synthesis Pool)" if tab_name == "1" else "Stash 2 (High-Tier Archive)"
                res_text = (
                    f"🗄 <b>{tab_label.upper()} REPORT</b>\n\n"
                    f"• <b>Common:</b>   {c_cnt}/9 {'✅' if c_cnt >= 9 else ''}\n"
                    f"• <b>Uncommon:</b> {u_cnt}/9 {'✅' if u_cnt >= 9 else ''}\n"
                    f"• <b>Rare:</b>     {r_cnt}/9 {'✅' if r_cnt >= 9 else ''}\n"
                    f"{ready_str}"
                    f"• <b>Total Lv. 50 in View:</b> {tot}\n"
                    f"• <b>Scan Time:</b> {time.strftime('%H:%M:%S')}\n\n"
                    f"<i>Grid scanned and restored to default Material tab.</i>"
                )

            # Restore to material tab
            if mat_tab and "x" in mat_tab and "y" in mat_tab:
                self.bot.click_point(mat_tab["x"], mat_tab["y"], delay_after=0.25)

            self.send_or_edit_dashboard(res_text, self.get_stash_inline_keyboard(), edit_msg_id=edit_msg_id)
        except Exception as e:
            self.send_or_edit_dashboard(f"❌ Error during stash tab inspection: {e}", self.get_stash_inline_keyboard(), edit_msg_id=edit_msg_id)

    def _execute_unstick_action(self):
        try:
            if hasattr(self.bot, "execute_unstick_routine"):
                self.bot.execute_unstick_routine()
            else:
                self._fallback_unstick()

            time.sleep(0.5)
            img = self._capture_screen_with_banner("Unstick Complete - Focus Restored")
            caption = "✅ <b>Unstick procedure finished!</b>\nGame focus and stash tab have been reset."
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🔙 Main Menu", "callback_data": "screen_main"},
                        {"text": "🗑️ Close Photo", "callback_data": "cmd_dismiss_photo"}
                    ]
                ]
            }
            self.send_photo_cleaned(img, caption=caption, reply_markup=keyboard)
        except Exception as e:
            self.send_or_edit_dashboard(f"❌ Error during unstick: {e}", self.get_main_inline_keyboard())

    def _execute_autofill_synth_action(self, edit_msg_id: Optional[int] = None):
        """Executes native Auto-Fill Synthesis flow (Lv. 80~90) remotely via Telegram."""
        if getattr(self.bot, "cycle_running", False):
            self.send_or_edit_dashboard(
                "⚠️ <b>Action Blocked While Cycle Running</b>\n\n"
                f"The bot is actively executing a cycle (Step: <code>{self.last_status}</code>).\n"
                "Auto-Fill Synthesis controls the Cube and mouse clicks.\n\n"
                "Please pause the bot first with <b>Pause Bot</b> or wait for the current cycle to complete.",
                self.get_main_inline_keyboard(),
                edit_msg_id=edit_msg_id
            )
            return

        def _worker():
            try:
                self.send_or_edit_dashboard(
                    "⚗ <b>EXECUTING AUTO-FILL SYNTHESIS (Lv. 80~90)...</b>\n\n"
                    "• Switching Cube to Synthesis mode\n"
                    "• Selecting Tier Lv.80~90\n"
                    "• Clicking Auto Fill button\n"
                    "• Pressing Synthesize\n"
                    "• Pressing Return button above Auto Fill\n\n"
                    "<i>Please wait ~3-4 seconds...</i>",
                    self.get_main_inline_keyboard(),
                    edit_msg_id=edit_msg_id
                )

                if hasattr(self.bot, "execute_autofill_synthesis_flow"):
                    ok = self.bot.execute_autofill_synthesis_flow()
                elif hasattr(self.bot, "synthesis") and hasattr(self.bot.synthesis, "execute_autofill_synthesis_flow"):
                    ok = self.bot.synthesis.execute_autofill_synthesis_flow()
                else:
                    ok = False

                # Reset unstopped loop count after explicit manual autofill synth
                if hasattr(self.bot, "unstopped_loops"):
                    self.bot.unstopped_loops = 0

                time.sleep(0.5)
                banner_text = "Auto-Fill Synthesis Complete" if ok else "Auto-Fill Synth Incomplete"
                img = self._capture_screen_with_banner(banner_text)
                status_icon = "✅" if ok else "⚠️"
                caption = (
                    f"{status_icon} <b>Auto-Fill Synthesis (Lv. 80~90) Finished!</b>\n\n"
                    f"• <b>Status:</b> {'Success' if ok else 'Incomplete / Error'}\n"
                    f"• <b>Action:</b> Auto-filled items, synthesized, and returned to inventory.\n"
                    f"• <b>Unstopped Loops:</b> Reset to 0\n\n"
                    f"<i>Timer continues as usual.</i>"
                )
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "📸 New Screenshot", "callback_data": "cmd_screenshot"},
                            {"text": "🔙 Main Menu", "callback_data": "screen_main"}
                        ]
                    ]
                }
                self.send_photo_cleaned(img, caption=caption, reply_markup=keyboard)
            except Exception as e:
                self.send_or_edit_dashboard(f"❌ Error during Auto-Fill Synthesis: {e}", self.get_main_inline_keyboard())

        threading.Thread(target=_worker, daemon=True).start()

    def _fallback_unstick(self):
        """Fallback unstick if bot engine lacks method."""
        try:
            from pynput.keyboard import Controller as KeyController, Key
            kb = KeyController()
            kb.press(Key.esc)
            time.sleep(0.08)
            kb.release(Key.esc)
            time.sleep(0.2)
            kb.press(Key.esc)
            time.sleep(0.08)
            kb.release(Key.esc)
            time.sleep(0.3)

            # Click material tab if present
            sm = self.config.get("button_coords", {}).get("stash_tab_material")
            if sm and "x" in sm and "y" in sm:
                self.bot.click_point(sm["x"], sm["y"], delay_after=0.25)

            # Double click inventory slot (0,0)
            inv_roi = self.bot.vision.get_inventory_roi()
            self.bot.activate_scroll_with_double_click(inv_roi)
            self.bot.vision.clear_cache()
        except Exception as e:
            self._log(f"Fallback unstick failed: {e}", "warning")

    def _capture_screen_with_banner(self, banner_text: str) -> np.ndarray:
        """Captures full screen and embeds a clean translucent info banner at bottom."""
        img = None
        if hasattr(self.bot, "vision") and hasattr(self.bot.vision, "capture_screen"):
            try:
                img = self.bot.vision.capture_screen()
            except Exception:
                img = None

        if img is None or img.size == 0:
            from vision.screen import ScreenCapture
            img = ScreenCapture.capture_screen()

        if img is None or img.size == 0:
            img = np.zeros((600, 800, 3), dtype=np.uint8)

        h, w = img.shape[:2]
        # Translucent banner bar at bottom
        banner_h = 36
        overlay = img.copy()
        cv2.rectangle(overlay, (0, h - banner_h), (w, h), (20, 20, 24), -1)
        cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)

        # Text on banner
        cv2.putText(
            img,
            f"TBH BOT | {banner_text}",
            (14, h - 11),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (56, 239, 125),
            1,
            cv2.LINE_AA
        )
        return img

    def _log(self, msg: str, level: str = "info"):
        if hasattr(self.bot, "log"):
            self.bot.log(msg, level)
        else:
            print(f"[{level.upper()}] {msg}")
