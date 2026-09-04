"""Reusable pieces of the interface."""

from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from ..i18n import t
from . import theme


def bring_to_front(win) -> None:
    """Force a window to the foreground on Windows.

    Launched from a shortcut, a new Tk window often opens *behind* whatever had
    focus, because Windows blocks foreground stealing. Toggling the topmost
    attribute on and straight back off bumps the window to the top of the normal
    z-order without leaving it permanently on top, and without depending on a
    timed callback that can fire before the window is mapped.
    """
    try:
        win.deiconify()
        win.lift()
        win.update_idletasks()
        win.attributes("-topmost", True)
        win.update_idletasks()
        win.attributes("-topmost", False)
        win.focus_force()
    except Exception:  # pragma: no cover - platform/display dependent
        pass


def section_label(master, key: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=t(key).upper(),
        font=(theme.FONT_FAMILY, 11, "bold"),
        text_color=theme.TEXT_MUTED,
        anchor="w",
    )


def field_label(master, key: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=t(key),
        font=(theme.FONT_FAMILY, 12),
        text_color=theme.TEXT,
        anchor="w",
    )


def hint_label(master, text: str = "") -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=text,
        font=(theme.FONT_FAMILY, 11),
        text_color=theme.TEXT_MUTED,
        anchor="w",
        justify="left",
        wraplength=320,
    )


def entry(master, placeholder: str = "", **kwargs) -> ctk.CTkEntry:
    return ctk.CTkEntry(
        master,
        placeholder_text=placeholder,
        fg_color=theme.BG_DARKEST,
        border_color=theme.BORDER,
        text_color=theme.TEXT,
        placeholder_text_color=theme.TEXT_MUTED,
        font=(theme.FONT_FAMILY, 12),
        height=32,
        **kwargs,
    )


def button(master, text: str, command=None, *, kind: str = "default", height: int = 32, **kwargs):
    palette = {
        "primary": (theme.BLURPLE, theme.BLURPLE_HOVER, "#ffffff"),
        "danger": (theme.DANGER, theme.DANGER_HOVER, "#ffffff"),
        "default": (theme.BG_CARD, theme.BORDER, theme.TEXT),
    }
    fg, hover, fg_text = palette.get(kind, palette["default"])
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        fg_color=fg,
        hover_color=hover,
        text_color=fg_text,
        text_color_disabled=theme.TEXT_MUTED,
        font=(theme.FONT_FAMILY, 12, "bold"),
        corner_radius=4,
        height=height,
        **kwargs,
    )


class SecretEntry(ctk.CTkFrame):
    """A masked text field with a reveal toggle.

    The value lives in this widget and in the engine's job, and nowhere else.
    It is never written to disk, and the log console redacts it if it somehow
    appears in a message.
    """

    def __init__(self, master, placeholder: str = "", on_change=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._on_change = on_change

        self._var = ctk.StringVar()
        self._var.trace_add("write", lambda *_: self._changed())

        self._entry = entry(self, placeholder, textvariable=self._var, show="•")
        self._entry.grid(row=0, column=0, sticky="ew")

        self._toggle = button(self, t("btn.show"), self.toggle, width=62)
        self._toggle.grid(row=0, column=1, padx=(6, 0))
        self._revealed = False

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def toggle(self) -> None:
        self._revealed = not self._revealed
        self._entry.configure(show="" if self._revealed else "•")
        self._toggle.configure(text=t("btn.hide") if self._revealed else t("btn.show"))

    def get(self) -> str:
        return self._var.get().strip()

    def clear(self) -> None:
        self._var.set("")


class LogConsole(ctk.CTkFrame):
    """Scrolling, colour-coded log.

    Every line is timestamped and passes through the caller's redactor before
    it gets here, so the widget itself never has to know what a token is.
    """

    MAX_LINES = 5000

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_DARKEST, corner_radius=6, **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._box = ctk.CTkTextbox(
            self,
            fg_color=theme.BG_DARKEST,
            text_color=theme.TEXT,
            border_width=0,
            font=(theme.FONT_MONO, 12),
            wrap="word",
        )
        self._box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._box.configure(state="disabled")

        # CTkTextbox wraps a tk.Text; tags are how per-line colour works.
        for level, colour in theme.LEVEL_COLOURS.items():
            self._box._textbox.tag_config(level, foreground=colour)
        self._box._textbox.tag_config("time", foreground=theme.TEXT_MUTED)

        self._lines: list[str] = []

    def append(self, level: str, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._box.configure(state="normal")
        self._box._textbox.insert("end", f"{stamp}  ", ("time",))
        self._box._textbox.insert("end", f"{text}\n", (level,))
        self._lines.append(f"{stamp}  {text}")
        if len(self._lines) > self.MAX_LINES:
            # Keep memory bounded during very long runs.
            self._box._textbox.delete("1.0", "2.0")
            self._lines.pop(0)
        self._box.configure(state="disabled")
        self._box.see("end")

    def clear(self) -> None:
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        self._box.configure(state="disabled")
        self._lines.clear()

    def text(self) -> str:
        return "\n".join(self._lines)


class ConfirmDialog(ctk.CTkToplevel):
    """Modal confirmation that requires typing the channel name.

    A yes/no dialog can be dismissed by reflex. Typing the name forces the user
    to look at which conversation they are about to wipe.
    """

    def __init__(self, master, *, label: str, count: int, require_typing: bool):
        super().__init__(master)
        self.title(t("confirm.title"))
        self.configure(fg_color=theme.BG_MAIN)
        self.resizable(False, False)
        self.result = False
        self._label = label
        self._require_typing = require_typing

        self.grid_columnconfigure(0, weight=1)
        pad = {"padx": 20, "sticky": "ew"}

        ctk.CTkLabel(
            self,
            text=t("confirm.title"),
            font=(theme.FONT_FAMILY, 16, "bold"),
            text_color=theme.TEXT_HEADING,
            anchor="w",
        ).grid(row=0, column=0, pady=(20, 8), **pad)

        ctk.CTkLabel(
            self,
            text=t("confirm.body", count=count, label=label),
            font=(theme.FONT_FAMILY, 12),
            text_color=theme.TEXT,
            anchor="w",
            justify="left",
            wraplength=420,
        ).grid(row=1, column=0, pady=(0, 12), **pad)

        self._error = hint_label(self)
        self._error.configure(text_color=theme.DANGER, wraplength=420)

        if require_typing:
            ctk.CTkLabel(
                self,
                text=t("confirm.type_name"),
                font=(theme.FONT_FAMILY, 12),
                text_color=theme.TEXT_MUTED,
                anchor="w",
            ).grid(row=2, column=0, pady=(0, 4), **pad)
            self._input = entry(self, label)
            self._input.grid(row=3, column=0, pady=(0, 8), **pad)
            self._error.grid(row=4, column=0, pady=(0, 8), **pad)
        else:
            self._input = None

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=5, column=0, padx=20, pady=(4, 20), sticky="e")
        button(buttons, t("confirm.cancel"), self._cancel, width=110).grid(row=0, column=0, padx=(0, 8))
        button(buttons, t("confirm.delete"), self._accept, kind="danger", width=140).grid(row=0, column=1)

        self.update_idletasks()
        self._centre_on(master)
        self.transient(master)
        self.grab_set()
        bring_to_front(self)
        if self._input is not None:
            self._input.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _centre_on(self, master) -> None:
        width, height = self.winfo_width(), self.winfo_height()
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + (master.winfo_height() - height) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _accept(self) -> None:
        if self._require_typing:
            typed = (self._input.get() or "").strip()
            if typed.lstrip("#") != self._label.lstrip("#"):
                self._error.configure(text=t("confirm.mismatch", label=self._label))
                return
        self.result = True
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.result = False
        self.grab_release()
        self.destroy()

    @classmethod
    def ask(cls, master, *, label: str, count: int, require_typing: bool) -> bool:
        dialog = cls(master, label=label, count=count, require_typing=require_typing)
        master.wait_window(dialog)
        return dialog.result


class TokenHelpDialog(ctk.CTkToplevel):
    """Informational: how to read your user token from the browser.

    Opened from a link next to the token field, so the instructions are one
    click from where they are needed rather than buried in the README.
    """

    def __init__(self, master):
        super().__init__(master)
        self.title(t("help.token.title"))
        self.configure(fg_color=theme.BG_MAIN)
        self.resizable(False, False)

        self.grid_columnconfigure(0, weight=1)
        pad = {"padx": 24, "sticky": "ew"}

        ctk.CTkLabel(
            self,
            text=t("help.token.title"),
            font=(theme.FONT_FAMILY, 16, "bold"),
            text_color=theme.TEXT_HEADING,
            anchor="w",
        ).grid(row=0, column=0, pady=(22, 10), **pad)

        ctk.CTkLabel(
            self,
            text=t("help.token.body"),
            font=(theme.FONT_FAMILY, 12),
            text_color=theme.TEXT,
            anchor="w",
            justify="left",
            wraplength=520,
        ).grid(row=1, column=0, pady=(0, 14), **pad)

        warning = ctk.CTkFrame(self, fg_color=theme.BG_DARKEST, corner_radius=6)
        warning.grid(row=2, column=0, pady=(0, 16), **pad)
        warning.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            warning,
            text=t("help.token.warning"),
            font=(theme.FONT_FAMILY, 12),
            text_color=theme.WARNING,
            anchor="w",
            justify="left",
            wraplength=490,
        ).grid(row=0, column=0, padx=14, pady=12, sticky="ew")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, padx=24, pady=(0, 22), sticky="e")
        button(buttons, t("help.close"), self._close, kind="primary", width=130).grid(row=0, column=0)

        self.update_idletasks()
        self.transient(master)
        self.grab_set()
        bring_to_front(self)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self) -> None:
        self.grab_release()
        self.destroy()

    @classmethod
    def show(cls, master) -> None:
        dialog = cls(master)
        master.wait_window(dialog)


class DisclaimerDialog(ctk.CTkToplevel):
    """First-run notice. The checkbox has to be ticked before Continue works."""

    def __init__(self, master):
        super().__init__(master)
        self.title(t("tos.title"))
        self.configure(fg_color=theme.BG_MAIN)
        self.resizable(False, False)
        self.result = False

        self.grid_columnconfigure(0, weight=1)
        pad = {"padx": 24, "sticky": "ew"}

        ctk.CTkLabel(
            self,
            text=t("tos.title"),
            font=(theme.FONT_FAMILY, 17, "bold"),
            text_color=theme.WARNING,
            anchor="w",
        ).grid(row=0, column=0, pady=(22, 10), **pad)

        ctk.CTkLabel(
            self,
            text=t("tos.body"),
            font=(theme.FONT_FAMILY, 12),
            text_color=theme.TEXT,
            anchor="w",
            justify="left",
            wraplength=480,
        ).grid(row=1, column=0, pady=(0, 16), **pad)

        self._accepted = ctk.BooleanVar(value=False)
        self._checkbox = ctk.CTkCheckBox(
            self,
            text=t("tos.accept"),
            variable=self._accepted,
            command=self._sync,
            font=(theme.FONT_FAMILY, 12),
            text_color=theme.TEXT,
            fg_color=theme.BLURPLE,
            hover_color=theme.BLURPLE_HOVER,
            border_color=theme.BORDER,
        )
        self._checkbox.grid(row=2, column=0, pady=(0, 18), **pad)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, padx=24, pady=(0, 22), sticky="e")
        button(buttons, t("tos.quit"), self._decline, width=110).grid(row=0, column=0, padx=(0, 8))
        self._continue = button(
            buttons, t("tos.continue"), self._accept, kind="primary", width=140, state="disabled"
        )
        self._continue.grid(row=0, column=1)

        self.update_idletasks()
        self.transient(master)
        self.grab_set()
        bring_to_front(self)
        # Keyboard path: focus the checkbox so Space ticks it, and let Enter
        # confirm once ticked. Space/Enter is also how keyboard-only users get
        # through, not just a hook for automated testing.
        self.after(120, self._focus_checkbox)
        self.bind("<Return>", lambda _e: self._accept())
        self.protocol("WM_DELETE_WINDOW", self._decline)

    def _focus_checkbox(self) -> None:
        try:
            if self.winfo_exists():
                self._checkbox.focus_set()
        except Exception:  # pragma: no cover
            pass

    def _sync(self) -> None:
        self._continue.configure(state="normal" if self._accepted.get() else "disabled")

    def _accept(self) -> None:
        # Guard: Enter must not confirm an unticked notice.
        if not self._accepted.get():
            return
        self.result = True
        self.grab_release()
        self.destroy()

    def _decline(self) -> None:
        self.result = False
        self.grab_release()
        self.destroy()

    @classmethod
    def ask(cls, master) -> bool:
        dialog = cls(master)
        master.wait_window(dialog)
        return dialog.result
