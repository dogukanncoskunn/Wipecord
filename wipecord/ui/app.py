"""The Wipecord window.

Threading contract: the engine runs on a worker thread and only ever puts
events on a queue. This module drains that queue on a tkinter timer and is the
only place that touches widgets. Background lookups (token verification,
channel lookup) follow the same rule by posting a UiCallback rather than
calling back directly.
"""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from .. import config
from ..client import DiscordClient, Redactor
from ..engine import DeletionEngine, Job
from ..events import (
    DoneEvent,
    LogEvent,
    PreviewEvent,
    ProgressEvent,
    State,
    StateEvent,
)
from ..i18n import LANGUAGE_NAMES, get_language, set_language, t
from ..ratelimit import RateLimiter, Sleeper
from ..scanner import Mode, ScanCriteria, Scanner
from . import theme
from .widgets import (
    ConfirmDialog,
    DisclaimerDialog,
    LogConsole,
    SecretEntry,
    TokenHelpDialog,
    bring_to_front,
    button,
    entry,
    field_label,
    hint_label,
    section_label,
)

ICON_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "wipecord.ico"

MODES = (Mode.ALL, Mode.LAST_N, Mode.DATE_RANGE)
MODE_KEYS = {Mode.ALL: "mode.all", Mode.LAST_N: "mode.last_n", Mode.DATE_RANGE: "mode.date_range"}


@dataclass
class UiCallback:
    """Work that must run on the UI thread, posted from a background thread."""

    fn: Callable[[], None]


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class WipecordApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")

        self.title(t("app.title"))
        self.configure(fg_color=theme.BG_MAIN)
        self._fit_to_screen()
        try:
            if ICON_PATH.exists():
                self.iconbitmap(str(ICON_PATH))
        except Exception:  # pragma: no cover - platform/display dependent
            pass

        self.events: queue.Queue = queue.Queue()
        self.engine = DeletionEngine(self.events)
        self.redactor = Redactor()

        self._translatables: list[tuple] = []
        self._mode = Mode.ALL
        self._channel_label: str | None = None
        self._preview: tuple = ()
        self._preview_signature: tuple | None = None
        self._verified_name: str | None = None
        self._running = False

        self._build()
        self._retranslate()
        self._sync_buttons()
        self.after(100, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _fit_to_screen(self) -> None:
        """Size and centre the window so it always fits on screen.

        CustomTkinter multiplies the geometry by the display's scaling factor
        (1.25 on a typical 125%-DPI Windows setup), so a fixed "1120x740"
        becomes 1400x925 actual pixels — taller than a 1536x864 screen, which
        pushes the action buttons off the bottom edge. Everything here is
        computed in logical units (what geometry() expects); the clamp uses the
        real screen size divided back by the scaling factor.
        """
        try:
            scaling = ctk.ScalingTracker.get_window_scaling(self) or 1.0
        except Exception:  # pragma: no cover - platform/display dependent
            scaling = 1.0

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        # Leave room for the taskbar and the window's own title bar.
        avail_w = (screen_w - 80) / scaling
        avail_h = (screen_h - 110) / scaling

        logical_w = int(min(1120, avail_w))
        logical_h = int(min(740, avail_h))
        min_w = int(min(880, logical_w))
        min_h = int(min(560, logical_h))

        x = max(0, int((screen_w / scaling - logical_w) / 2))
        y = max(0, int((screen_h / scaling - logical_h) / 2) - 12)

        self.minsize(min_w, min_h)
        self.geometry(f"{logical_w}x{logical_h}+{x}+{y}")

    # --- translation registry ------------------------------------------------

    def _tr(self, widget, key: str, *, upper: bool = False, attr: str = "text"):
        self._translatables.append((widget, key, upper, attr))
        return widget

    def _retranslate(self) -> None:
        for widget, key, upper, attr in self._translatables:
            value = t(key)
            widget.configure(**{attr: value.upper() if upper else value})
        self._mode_selector.configure(values=[t(MODE_KEYS[m]) for m in MODES])
        self._mode_selector.set(t(MODE_KEYS[self._mode]))
        self._pace_hint.configure(text=t("hint.pace", floor=config.DELAY_FLOOR))
        self._dates_hint.configure(text=t("hint.dates"))
        # The pause button label is dynamic (Pause/Resume), so it is not in the
        # _tr registry and has to be refreshed here explicitly.
        self._pause_button.configure(
            text=t("btn.resume") if self.engine.paused else t("btn.pause")
        )
        self.title(t("app.title"))
        self._set_state_label(self._current_state_key)

    def _on_language(self, choice: str) -> None:
        for code, name in LANGUAGE_NAMES.items():
            if name == choice:
                set_language(code)
                break
        self._retranslate()

    # --- layout --------------------------------------------------------------

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._current_state_key = "state.idle"

        sidebar = ctk.CTkScrollableFrame(
            self, fg_color=theme.BG_SIDEBAR, corner_radius=0, width=380
        )
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_columnconfigure(0, weight=1)
        self._build_sidebar(sidebar)

        main = ctk.CTkFrame(self, fg_color=theme.BG_MAIN, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        self._build_main(main)

    def _build_sidebar(self, parent) -> None:
        row = 0
        pad = {"padx": 18, "sticky": "ew"}

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=row, column=0, pady=(18, 2), **pad)
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Wipecord",
            font=(theme.FONT_FAMILY, 20, "bold"),
            text_color=theme.TEXT_HEADING,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        language = ctk.CTkOptionMenu(
            header,
            values=list(LANGUAGE_NAMES.values()),
            command=self._on_language,
            width=104,
            height=28,
            fg_color=theme.BG_CARD,
            button_color=theme.BG_CARD,
            button_hover_color=theme.BORDER,
            text_color=theme.TEXT,
            font=(theme.FONT_FAMILY, 11),
        )
        language.set(LANGUAGE_NAMES[get_language()])
        language.grid(row=0, column=1, sticky="e")
        row += 1

        self._tr(
            ctk.CTkLabel(
                parent,
                text="",
                font=(theme.FONT_FAMILY, 11),
                text_color=theme.TEXT_MUTED,
                anchor="w",
                wraplength=340,
                justify="left",
            ),
            "app.subtitle",
        ).grid(row=row, column=0, pady=(0, 14), **pad)
        row += 1

        # --- account ---------------------------------------------------------
        self._tr(section_label(parent, "section.account"), "section.account", upper=True).grid(
            row=row, column=0, pady=(4, 6), **pad
        )
        row += 1
        self._tr(field_label(parent, "label.token"), "label.token").grid(
            row=row, column=0, pady=(0, 4), **pad
        )
        row += 1
        self._token = SecretEntry(
            parent, t("label.token.placeholder"), on_change=self._invalidate_preview
        )
        self._token.grid(row=row, column=0, pady=(0, 4), **pad)
        row += 1
        self._token_help = ctk.CTkButton(
            parent,
            text=t("help.token.link"),
            command=self._show_token_help,
            fg_color="transparent",
            hover_color=theme.BG_CARD,
            text_color=theme.TEXT_LINK,
            font=(theme.FONT_FAMILY, 11, "underline"),
            height=22,
            anchor="w",
        )
        self._tr(self._token_help, "help.token.link")
        self._token_help.grid(row=row, column=0, pady=(0, 6), padx=18, sticky="w")
        row += 1
        self._verify_button = self._tr(
            button(parent, t("btn.verify"), self._verify_token), "btn.verify"
        )
        self._verify_button.grid(row=row, column=0, pady=(0, 4), **pad)
        row += 1
        self._account_status = hint_label(parent)
        self._account_status.grid(row=row, column=0, pady=(0, 14), **pad)
        row += 1

        # --- target ----------------------------------------------------------
        self._tr(section_label(parent, "section.target"), "section.target", upper=True).grid(
            row=row, column=0, pady=(4, 6), **pad
        )
        row += 1
        self._tr(field_label(parent, "label.channel"), "label.channel").grid(
            row=row, column=0, pady=(0, 4), **pad
        )
        row += 1
        self._channel = entry(parent, t("label.channel.placeholder"))
        self._channel.bind("<KeyRelease>", lambda _e: self._invalidate_preview())
        self._channel.grid(row=row, column=0, pady=(0, 6), **pad)
        row += 1
        self._lookup_button = self._tr(
            button(parent, t("btn.fetch_channel"), self._lookup_channel), "btn.fetch_channel"
        )
        self._lookup_button.grid(row=row, column=0, pady=(0, 4), **pad)
        row += 1
        self._channel_status = hint_label(parent)
        self._channel_status.grid(row=row, column=0, pady=(0, 14), **pad)
        row += 1

        # --- mode ------------------------------------------------------------
        self._tr(section_label(parent, "section.mode"), "section.mode", upper=True).grid(
            row=row, column=0, pady=(4, 6), **pad
        )
        row += 1
        self._mode_selector = ctk.CTkSegmentedButton(
            parent,
            values=[t(MODE_KEYS[m]) for m in MODES],
            command=self._on_mode,
            fg_color=theme.BG_DARKEST,
            selected_color=theme.BLURPLE,
            selected_hover_color=theme.BLURPLE_HOVER,
            unselected_color=theme.BG_DARKEST,
            unselected_hover_color=theme.BG_CARD,
            text_color=theme.TEXT,
            font=(theme.FONT_FAMILY, 11),
            height=32,
        )
        self._mode_selector.set(t(MODE_KEYS[Mode.ALL]))
        self._mode_selector.grid(row=row, column=0, pady=(0, 8), **pad)
        row += 1

        self._count_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._count_frame.grid(row=row, column=0, **pad)
        self._count_frame.grid_columnconfigure(0, weight=1)
        self._tr(field_label(self._count_frame, "label.count"), "label.count").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self._count = entry(self._count_frame, "46")
        self._count.bind("<KeyRelease>", lambda _e: self._invalidate_preview())
        self._count.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        row += 1

        self._dates_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._dates_frame.grid(row=row, column=0, **pad)
        self._dates_frame.grid_columnconfigure((0, 1), weight=1)
        self._tr(field_label(self._dates_frame, "label.since"), "label.since").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self._tr(field_label(self._dates_frame, "label.until"), "label.until").grid(
            row=0, column=1, sticky="w", padx=(8, 0), pady=(0, 4)
        )
        self._since = entry(self._dates_frame, "2024-01-01")
        self._since.bind("<KeyRelease>", lambda _e: self._invalidate_preview())
        self._since.grid(row=1, column=0, sticky="ew")
        self._until = entry(self._dates_frame, "2024-12-31")
        self._until.bind("<KeyRelease>", lambda _e: self._invalidate_preview())
        self._until.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        self._dates_hint = hint_label(self._dates_frame, t("hint.dates"))
        self._dates_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 10))
        row += 1

        # --- filters ---------------------------------------------------------
        self._tr(section_label(parent, "section.filters"), "section.filters", upper=True).grid(
            row=row, column=0, pady=(6, 6), **pad
        )
        row += 1
        self._skip_pinned = ctk.BooleanVar(value=True)
        self._tr(
            ctk.CTkCheckBox(
                parent,
                text=t("filter.skip_pinned"),
                variable=self._skip_pinned,
                command=self._invalidate_preview,
                font=(theme.FONT_FAMILY, 12),
                text_color=theme.TEXT,
                fg_color=theme.BLURPLE,
                hover_color=theme.BLURPLE_HOVER,
                border_color=theme.BORDER,
                checkbox_width=20,
                checkbox_height=20,
            ),
            "filter.skip_pinned",
        ).grid(row=row, column=0, pady=(0, 14), **pad)
        row += 1

        # --- pace ------------------------------------------------------------
        self._tr(section_label(parent, "section.pace"), "section.pace", upper=True).grid(
            row=row, column=0, pady=(4, 6), **pad
        )
        row += 1
        pace = ctk.CTkFrame(parent, fg_color="transparent")
        pace.grid(row=row, column=0, **pad)
        pace.grid_columnconfigure((0, 1), weight=1)
        self._tr(field_label(pace, "label.delay_min"), "label.delay_min").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self._tr(field_label(pace, "label.delay_max"), "label.delay_max").grid(
            row=0, column=1, sticky="w", padx=(8, 0), pady=(0, 4)
        )
        self._delay_min = entry(pace, str(config.DEFAULT_DELAY_MIN))
        self._delay_min.insert(0, str(config.DEFAULT_DELAY_MIN))
        self._delay_min.grid(row=1, column=0, sticky="ew")
        self._delay_max = entry(pace, str(config.DEFAULT_DELAY_MAX))
        self._delay_max.insert(0, str(config.DEFAULT_DELAY_MAX))
        self._delay_max.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        self._pace_hint = hint_label(pace, t("hint.pace", floor=config.DELAY_FLOOR))
        self._pace_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 4))
        self._estimate = hint_label(pace)
        self._estimate.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 18))
        row += 1

        self._on_mode(t(MODE_KEYS[Mode.ALL]))

    def _build_main(self, parent) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        bar.grid_columnconfigure(0, weight=1)

        self._state_label = ctk.CTkLabel(
            bar,
            text=t("state.idle"),
            font=(theme.FONT_FAMILY, 14, "bold"),
            text_color=theme.TEXT_HEADING,
            anchor="w",
        )
        self._state_label.grid(row=0, column=0, sticky="w")
        self._clear_button = self._tr(
            button(bar, t("btn.clear_log"), self._clear_log, width=90), "btn.clear_log"
        )
        self._clear_button.grid(row=0, column=1, padx=(8, 0))
        self._save_button = self._tr(
            button(bar, t("btn.save_log"), self._save_log, width=110), "btn.save_log"
        )
        self._save_button.grid(row=0, column=2, padx=(8, 0))
        self._export_button = self._tr(
            button(bar, t("btn.export"), self._export_preview, width=150), "btn.export"
        )
        self._export_button.grid(row=0, column=3, padx=(8, 0))

        self.log = LogConsole(parent)
        self.log.grid(row=1, column=0, sticky="nsew", padx=18)

        progress = ctk.CTkFrame(parent, fg_color="transparent")
        progress.grid(row=2, column=0, sticky="ew", padx=18, pady=(10, 4))
        progress.grid_columnconfigure(0, weight=1)
        self._progress = ctk.CTkProgressBar(
            progress, progress_color=theme.BLURPLE, fg_color=theme.BG_DARKEST, height=8
        )
        self._progress.set(0)
        self._progress.grid(row=0, column=0, sticky="ew")
        self._progress_label = hint_label(progress)
        self._progress_label.configure(wraplength=600)
        self._progress_label.grid(row=1, column=0, sticky="w", pady=(6, 0))

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=(4, 18))
        actions.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._find_button = self._tr(
            button(actions, t("btn.find"), self._start_preview, kind="primary", height=40),
            "btn.find",
        )
        self._find_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._delete_button = self._tr(
            button(actions, t("btn.delete"), self._start_delete, kind="danger", height=40),
            "btn.delete",
        )
        self._delete_button.grid(row=0, column=1, sticky="ew", padx=6)
        self._pause_button = button(actions, t("btn.pause"), self._toggle_pause, height=40)
        self._pause_button.grid(row=0, column=2, sticky="ew", padx=6)
        self._stop_button = self._tr(
            button(actions, t("btn.stop"), self._stop, height=40), "btn.stop"
        )
        self._stop_button.grid(row=0, column=3, sticky="ew", padx=(6, 0))

    # --- input handling ------------------------------------------------------

    def _on_mode(self, choice: str) -> None:
        for mode in MODES:
            if t(MODE_KEYS[mode]) == choice:
                self._mode = mode
                break
        self._count_frame.grid_remove()
        self._dates_frame.grid_remove()
        if self._mode is Mode.LAST_N:
            self._count_frame.grid()
        elif self._mode is Mode.DATE_RANGE:
            self._dates_frame.grid()
        self._invalidate_preview()

    def _signature(self) -> tuple:
        """Everything that changes what a run would delete.

        The Delete button is only live while this matches the signature the
        preview was produced under.
        """
        return (
            self._token.get(),
            self._channel.get().strip(),
            self._mode.value,
            self._count.get().strip(),
            self._since.get().strip(),
            self._until.get().strip(),
            bool(self._skip_pinned.get()),
        )

    def _invalidate_preview(self) -> None:
        if self._preview_signature is None:
            return
        if self._signature() != self._preview_signature:
            self._preview_signature = None
            self._preview = ()
            self.log.append("warn", t("log.preview_stale"))
            self._sync_buttons()

    # --- validation ----------------------------------------------------------

    def _read_delays(self) -> tuple[float, float]:
        def parse(widget, fallback: float) -> float:
            try:
                return float((widget.get() or "").replace(",", "."))
            except ValueError:
                return fallback

        low = parse(self._delay_min, config.DEFAULT_DELAY_MIN)
        high = parse(self._delay_max, config.DEFAULT_DELAY_MAX)
        # The floor is not negotiable, whatever was typed.
        low = min(max(low, config.DELAY_FLOOR), config.DELAY_CEILING)
        high = min(max(high, low), config.DELAY_CEILING)
        return low, high

    def _build_criteria(self) -> ScanCriteria | None:
        if self._mode is Mode.LAST_N:
            raw = self._count.get().strip()
            if not raw.isdigit() or int(raw) <= 0:
                self._fail("error.count_required")
                return None
            return ScanCriteria(
                mode=Mode.LAST_N, limit=int(raw), skip_pinned=bool(self._skip_pinned.get())
            )

        if self._mode is Mode.DATE_RANGE:
            since, until = self._since.get().strip(), self._until.get().strip()
            if not since or not until:
                self._fail("error.dates_required")
                return None
            try:
                start = datetime.strptime(since, "%Y-%m-%d").date()
                end = datetime.strptime(until, "%Y-%m-%d").date()
            except ValueError:
                self._fail("error.date_format")
                return None
            if start > end:
                self._fail("error.dates_order")
                return None
            return ScanCriteria(
                mode=Mode.DATE_RANGE,
                start_date=start,
                end_date=end,
                skip_pinned=bool(self._skip_pinned.get()),
            )

        return ScanCriteria(mode=Mode.ALL, skip_pinned=bool(self._skip_pinned.get()))

    def _build_job(self, dry_run: bool) -> Job | None:
        token = self._token.get()
        if not token:
            self._fail("error.token_required")
            return None
        channel_id = self._channel.get().strip()
        if not channel_id:
            self._fail("error.channel_required")
            return None
        criteria = self._build_criteria()
        if criteria is None:
            return None
        low, high = self._read_delays()
        self.redactor.add(token)
        return Job(
            token=token,
            channel_id=channel_id,
            criteria=criteria,
            delay_min=low,
            delay_max=high,
            dry_run=dry_run,
        )

    def _fail(self, key: str) -> None:
        self.log.append("error", t(key))

    # --- background lookups --------------------------------------------------

    def _in_background(self, work: Callable[[], None]) -> None:
        threading.Thread(target=work, daemon=True).start()

    def _post(self, fn: Callable[[], None]) -> None:
        self.events.put(UiCallback(fn))

    def _throwaway_client(self, token: str) -> DiscordClient:
        """A short-lived client for one lookup, paced like any other request."""
        self.redactor.add(token)
        limiter = RateLimiter(sleeper=Sleeper(threading.Event()))
        return DiscordClient(token, limiter, redactor=self.redactor)

    def _show_token_help(self) -> None:
        TokenHelpDialog.show(self)

    def _verify_token(self) -> None:
        token = self._token.get()
        if not token:
            self._fail("error.token_required")
            return
        self._account_status.configure(text=t("status.verifying"), text_color=theme.TEXT_MUTED)

        def work() -> None:
            client = self._throwaway_client(token)
            try:
                me = client.verify_token()
                name = me.get("global_name") or me.get("username") or me.get("id")
                self._post(lambda: self._show_verified(str(name)))
            except Exception as exc:
                text = self.redactor(exc)
                self._post(lambda: self._show_verify_failed(text))
            finally:
                client.close()

        self._in_background(work)

    def _show_verified(self, name: str) -> None:
        self._verified_name = name
        self._account_status.configure(
            text=t("status.verified", name=name), text_color=theme.SUCCESS
        )
        self.log.append("success", t("status.verified", name=name))

    def _show_verify_failed(self, error: str) -> None:
        self._verified_name = None
        self._account_status.configure(
            text=t("status.verify_failed", error=error), text_color=theme.DANGER
        )

    def _lookup_channel(self) -> None:
        token, channel_id = self._token.get(), self._channel.get().strip()
        if not token:
            self._fail("error.token_required")
            return
        if not channel_id:
            self._fail("error.channel_required")
            return

        def work() -> None:
            client = self._throwaway_client(token)
            try:
                me = client.verify_token()
                info = Scanner(client, str(me.get("id"))).describe_channel(channel_id)
                self._post(lambda: self._show_channel(info.label, info.is_dm))
            except Exception as exc:
                text = self.redactor(exc)
                self._post(lambda: self._show_channel_failed(text))
            finally:
                client.close()

        self._in_background(work)

    def _show_channel(self, label: str, is_dm: bool) -> None:
        self._channel_label = label
        text = t("status.channel", label=label, kind=t("kind.dm" if is_dm else "kind.guild"))
        self._channel_status.configure(text=text, text_color=theme.SUCCESS)
        self.log.append("info", text)

    def _show_channel_failed(self, error: str) -> None:
        self._channel_label = None
        self._channel_status.configure(
            text=t("status.channel_failed", error=error), text_color=theme.DANGER
        )

    # --- running -------------------------------------------------------------

    def _start_preview(self) -> None:
        job = self._build_job(dry_run=True)
        if job is None or self.engine.busy:
            return
        self._preview = ()
        self._preview_signature = None
        self._running = True
        self._sync_buttons()
        self.engine.start(job)

    def _start_delete(self) -> None:
        if self._preview_signature is None:
            self._fail("error.preview_required")
            return
        if self._signature() != self._preview_signature:
            self._invalidate_preview()
            return
        if not self._preview:
            self._fail("error.nothing_found")
            return

        label = self._channel_label or self._channel.get().strip()
        confirmed = ConfirmDialog.ask(
            self,
            label=label,
            count=len(self._preview),
            # Deleting everything is the one that cannot be scoped back, so it
            # needs the channel name typed out rather than a single click.
            require_typing=self._mode is Mode.ALL,
        )
        if not confirmed:
            return

        job = self._build_job(dry_run=False)
        if job is None or self.engine.busy:
            return
        self._running = True
        self._sync_buttons()
        self.engine.start(job)

    def _toggle_pause(self) -> None:
        if not self.engine.busy:
            return
        if self.engine.paused:
            self.engine.resume()
        else:
            self.engine.pause()
        self._sync_buttons()

    def _stop(self) -> None:
        if self.engine.busy:
            self.engine.stop()

    def _sync_buttons(self) -> None:
        running = self._running
        can_delete = (not running) and bool(self._preview) and self._preview_signature is not None
        self._find_button.configure(state="disabled" if running else "normal")
        self._delete_button.configure(state="normal" if can_delete else "disabled")
        self._pause_button.configure(state="normal" if running else "disabled")
        self._stop_button.configure(state="normal" if running else "disabled")
        self._verify_button.configure(state="disabled" if running else "normal")
        self._lookup_button.configure(state="disabled" if running else "normal")
        self._pause_button.configure(
            text=t("btn.resume") if self.engine.paused else t("btn.pause")
        )
        self._export_button.configure(state="normal" if self._preview else "disabled")

    # --- event pump ----------------------------------------------------------

    def _drain(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle(event)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._drain)

    def _handle(self, event) -> None:
        if isinstance(event, UiCallback):
            event.fn()
        elif isinstance(event, LogEvent):
            self.log.append(event.level.value, self.redactor(event.text))
        elif isinstance(event, StateEvent):
            self._on_state(event.state)
        elif isinstance(event, ProgressEvent):
            self._on_progress(event)
        elif isinstance(event, PreviewEvent):
            self._on_preview(event)
        elif isinstance(event, DoneEvent):
            self._on_done(event)

    def _set_state_label(self, key: str) -> None:
        self._current_state_key = key
        self._state_label.configure(text=t(key))

    def _on_state(self, state: State) -> None:
        self._set_state_label(f"state.{state.value}")
        if state is State.DONE:
            self._running = False
        self._sync_buttons()

    def _on_progress(self, event: ProgressEvent) -> None:
        total = event.total or 0
        self._progress.set(min(1.0, event.done / total) if total else 0)
        text = t("progress.counts", done=event.done, total=total or event.done)
        if event.elapsed:
            text += " · " + t(
                "progress.eta",
                elapsed=format_duration(event.elapsed),
                eta=format_duration(event.eta or 0),
            )
        self._progress_label.configure(text=text)

    def _on_preview(self, event: PreviewEvent) -> None:
        self._preview = event.messages
        self._preview_signature = self._signature() if event.messages else None
        if event.messages:
            self._set_state_label("state.preview")
            for ref in event.messages[:200]:
                self.log.append("info", f"  {ref.timestamp[:19]}  {ref.summary}")
            if len(event.messages) > 200:
                self.log.append("info", f"  … +{len(event.messages) - 200}")
            low, high = self._read_delays()
            average = (low + high) / 2
            self._estimate.configure(
                text=t(
                    "hint.estimate",
                    count=len(event.messages),
                    duration=format_duration(len(event.messages) * average),
                )
            )
        self._sync_buttons()

    def _on_done(self, event: DoneEvent) -> None:
        summary = event.summary
        self._running = False
        if summary.dry_run:
            self.log.append("success", t("summary.dry_run", scanned=summary.scanned))
        elif summary.stopped:
            self.log.append("warn", t("summary.stopped", deleted=summary.deleted))
        else:
            self.log.append(
                "success",
                t(
                    "summary.done",
                    duration=format_duration(summary.duration),
                    deleted=summary.deleted,
                    skipped=summary.skipped,
                    failed=summary.failed,
                ),
            )
        if not summary.dry_run:
            # The messages are gone; a stale preview must not re-arm Delete.
            self._preview = ()
            self._preview_signature = None
        self._sync_buttons()

    # --- output --------------------------------------------------------------

    def _clear_log(self) -> None:
        self.log.clear()

    def _save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            initialfile=f"wipecord-{datetime.now():%Y%m%d-%H%M%S}.log",
            filetypes=[("Log", "*.log"), ("Text", "*.txt")],
        )
        if not path:
            return
        # Redacted again on the way out: a saved file outlives the session.
        Path(path).write_text(self.redactor(self.log.text()), encoding="utf-8")
        self.log.append("info", t("log.saved", path=path))

    def _export_preview(self) -> None:
        if not self._preview:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=f"wipecord-preview-{datetime.now():%Y%m%d-%H%M%S}.json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        payload = {
            "channel": self._channel_label or self._channel.get().strip(),
            "generated_at": datetime.now().astimezone().isoformat(),
            "messages": [ref.__dict__ for ref in self._preview],
        }
        Path(path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.log.append("info", t("log.exported", path=path))

    def _on_close(self) -> None:
        if self.engine.busy:
            self.engine.stop()
            self.engine.join(3)
        self.destroy()


def launch() -> None:
    ctk.set_appearance_mode("dark")
    app = WipecordApp()
    app.update_idletasks()
    # The main window is shown immediately, not withdrawn. A window that starts
    # hidden and is deiconified later is exactly the case Windows blocks from
    # taking the foreground, which made the app "disappear" after the notice.
    # A freshly launched, already-visible window is allowed to the front; the
    # disclaimer then sits on top of it as a modal.
    bring_to_front(app)
    if not DisclaimerDialog.ask(app):
        app.destroy()
        return
    bring_to_front(app)
    app.mainloop()
