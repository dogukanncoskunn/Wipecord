"""UI tests.

These build the real window (without entering mainloop) and drive it through
its own methods. They are skipped automatically where no display is available.
"""

import queue
import tkinter

import pytest

ctk = pytest.importorskip("customtkinter")

from wipecord import config  # noqa: E402
from wipecord.events import DoneEvent, Level, LogEvent, PreviewEvent, State, StateEvent, Summary  # noqa: E402
from wipecord.i18n import set_language, t  # noqa: E402
from wipecord.scanner import MessageRef, Mode  # noqa: E402
from wipecord.ui.app import WipecordApp, format_duration  # noqa: E402

TOKEN = "mfa.aVeryLongLookingFakeTokenValueForTests1234567890"


@pytest.fixture(scope="module")
def window():
    """One window for the module.

    Tk does not reliably re-bootstrap a second root inside one process, so
    building a fresh WipecordApp per test skips at random. Isolation comes from
    resetting the window instead, which is deterministic.
    """
    set_language("en")
    try:
        instance = WipecordApp()
    except tkinter.TclError as exc:  # pragma: no cover - headless environment
        # Only a genuine display failure is a skip. Anything else is a real
        # bug and must fail loudly rather than hide as a skipped test.
        pytest.skip(f"no display available: {exc}")
    instance.withdraw()
    yield instance
    instance.destroy()


@pytest.fixture
def app(window):
    _reset(window)
    yield window
    _reset(window)


def _reset(window):
    set_language("en")
    window._token.clear()
    for widget in (window._channel, window._count, window._since, window._until):
        widget.delete(0, "end")
    for widget, value in (
        (window._delay_min, config.DEFAULT_DELAY_MIN),
        (window._delay_max, config.DEFAULT_DELAY_MAX),
    ):
        widget.delete(0, "end")
        widget.insert(0, str(value))
    window._skip_pinned.set(True)
    window._preview = ()
    window._preview_signature = None
    window._channel_label = None
    window._verified_name = None
    window._running = False
    window._on_mode(t("mode.all"))
    window._retranslate()
    window.log.clear()
    while True:
        try:
            window.events.get_nowait()
        except queue.Empty:
            break
    window._set_state_label("state.idle")
    window._progress_label.configure(text="")
    window._sync_buttons()


def fill(app, *, token=TOKEN, channel="123456789", mode=Mode.ALL, count="", since="", until=""):
    app._token._var.set(token)
    app._channel.delete(0, "end")
    app._channel.insert(0, channel)
    app._on_mode(t({Mode.ALL: "mode.all", Mode.LAST_N: "mode.last_n", Mode.DATE_RANGE: "mode.date_range"}[mode]))
    for widget, value in ((app._count, count), (app._since, since), (app._until, until)):
        widget.delete(0, "end")
        if value:
            widget.insert(0, value)


def refs(n):
    return tuple(
        MessageRef(id=str(i), timestamp="2024-01-01T00:00:00+00:00", summary=f"msg {i}")
        for i in range(n)
    )


def logged(app):
    return app.log.text()


# --- construction ------------------------------------------------------------


def test_the_window_builds_with_both_panels(app):
    assert app._find_button is not None
    assert app._delete_button is not None
    assert app.log is not None


def test_delete_starts_disabled_because_nothing_has_been_previewed(app):
    assert app._delete_button.cget("state") == "disabled"
    assert app._find_button.cget("state") == "normal"


def test_pause_and_stop_start_disabled(app):
    assert app._pause_button.cget("state") == "disabled"
    assert app._stop_button.cget("state") == "disabled"


# --- the delete gate ---------------------------------------------------------


def test_delete_unlocks_only_after_a_preview_finds_something(app):
    fill(app)
    app._handle(PreviewEvent(messages=refs(3), channel_label="#general"))
    assert app._delete_button.cget("state") == "normal"


def test_an_empty_preview_leaves_delete_locked(app):
    fill(app)
    app._handle(PreviewEvent(messages=(), channel_label="#general"))
    assert app._delete_button.cget("state") == "disabled"


def test_changing_a_setting_after_a_preview_relocks_delete(app):
    fill(app)
    app._handle(PreviewEvent(messages=refs(3), channel_label="#general"))
    assert app._delete_button.cget("state") == "normal"

    app._channel.delete(0, "end")
    app._channel.insert(0, "999")
    app._invalidate_preview()

    assert app._delete_button.cget("state") == "disabled"
    assert t("log.preview_stale") in logged(app)


def test_toggling_the_pinned_filter_also_relocks_delete(app):
    fill(app)
    app._handle(PreviewEvent(messages=refs(2), channel_label="#general"))
    app._skip_pinned.set(False)
    app._invalidate_preview()
    assert app._delete_button.cget("state") == "disabled"


def test_pressing_delete_without_a_preview_explains_why_nothing_happened(app):
    fill(app)
    app._start_delete()
    assert t("error.preview_required") in logged(app)
    assert not app.engine.busy


def test_a_completed_deletion_clears_the_preview_so_it_cannot_be_replayed(app):
    fill(app)
    app._handle(PreviewEvent(messages=refs(3), channel_label="#general"))
    app._handle(DoneEvent(Summary(scanned=3, deleted=3, dry_run=False)))
    assert app._delete_button.cget("state") == "disabled"


# --- validation --------------------------------------------------------------


def test_a_missing_token_is_reported_rather_than_sent(app):
    fill(app, token="")
    assert app._build_job(dry_run=True) is None
    assert t("error.token_required") in logged(app)


def test_a_missing_channel_is_reported(app):
    fill(app, channel="")
    assert app._build_job(dry_run=True) is None
    assert t("error.channel_required") in logged(app)


def test_last_n_requires_a_positive_count(app):
    fill(app, mode=Mode.LAST_N, count="0")
    assert app._build_criteria() is None
    fill(app, mode=Mode.LAST_N, count="abc")
    assert app._build_criteria() is None
    assert t("error.count_required") in logged(app)


def test_last_n_accepts_a_real_count(app):
    fill(app, mode=Mode.LAST_N, count="46")
    criteria = app._build_criteria()
    assert criteria.mode is Mode.LAST_N
    assert criteria.limit == 46


def test_a_malformed_date_is_rejected(app):
    fill(app, mode=Mode.DATE_RANGE, since="01/01/2024", until="2024-12-31")
    assert app._build_criteria() is None
    assert t("error.date_format") in logged(app)


def test_a_backwards_date_range_is_rejected(app):
    fill(app, mode=Mode.DATE_RANGE, since="2024-12-31", until="2024-01-01")
    assert app._build_criteria() is None
    assert t("error.dates_order") in logged(app)


def test_a_valid_date_range_becomes_criteria(app):
    fill(app, mode=Mode.DATE_RANGE, since="2024-01-01", until="2024-01-31")
    criteria = app._build_criteria()
    assert criteria.mode is Mode.DATE_RANGE
    assert criteria.start_date.year == 2024


# --- the pace floor ----------------------------------------------------------


def test_the_delay_floor_cannot_be_typed_around(app):
    app._delay_min.delete(0, "end")
    app._delay_min.insert(0, "0")
    app._delay_max.delete(0, "end")
    app._delay_max.insert(0, "0.01")
    low, high = app._read_delays()
    assert low >= config.DELAY_FLOOR
    assert high >= low


def test_nonsense_in_the_delay_fields_falls_back_to_the_defaults(app):
    app._delay_min.delete(0, "end")
    app._delay_min.insert(0, "fast please")
    low, _ = app._read_delays()
    assert low == config.DEFAULT_DELAY_MIN


def test_a_comma_decimal_is_accepted(app):
    app._delay_min.delete(0, "end")
    app._delay_min.insert(0, "2,5")
    low, _ = app._read_delays()
    assert low == pytest.approx(2.5)


def test_an_absurd_delay_is_capped(app):
    app._delay_max.delete(0, "end")
    app._delay_max.insert(0, "99999")
    _, high = app._read_delays()
    assert high <= config.DELAY_CEILING


# --- log window --------------------------------------------------------------


def test_log_lines_are_colour_coded_by_level(app):
    for level in Level:
        app._handle(LogEvent(level, f"line for {level.value}"))
    text = logged(app)
    assert all(f"line for {level.value}" in text for level in Level)


def test_the_token_is_scrubbed_from_anything_that_reaches_the_log(app):
    app.redactor.add(TOKEN)
    app._handle(LogEvent(Level.ERROR, f"failed with Authorization: {TOKEN}"))
    assert TOKEN not in logged(app)
    assert "REDACTED" in logged(app)


def test_clearing_the_log_empties_it(app):
    app._handle(LogEvent(Level.INFO, "something"))
    app._clear_log()
    assert logged(app) == ""


# --- state and progress ------------------------------------------------------


def test_running_disables_the_start_buttons(app):
    app._running = True
    app._sync_buttons()
    assert app._find_button.cget("state") == "disabled"
    assert app._stop_button.cget("state") == "normal"


def test_finishing_re_enables_the_start_buttons(app):
    app._running = True
    app._sync_buttons()
    app._handle(StateEvent(State.DONE))
    assert app._find_button.cget("state") == "normal"
    assert app._pause_button.cget("state") == "disabled"


def test_the_state_label_follows_the_engine(app):
    app._handle(StateEvent(State.SCANNING))
    assert app._state_label.cget("text") == t("state.scanning")
    app._handle(StateEvent(State.DELETING))
    assert app._state_label.cget("text") == t("state.deleting")


def test_progress_reports_counts_and_eta(app):
    app._handle(__import__("wipecord.events", fromlist=["ProgressEvent"]).ProgressEvent(
        done=10, total=100, elapsed=30.0, eta=270.0
    ))
    text = app._progress_label.cget("text")
    assert "10 / 100" in text
    assert "04:30" in text


def test_durations_are_formatted_as_minutes_and_seconds():
    assert format_duration(0) == "00:00"
    assert format_duration(65) == "01:05"
    assert format_duration(-5) == "00:00"


# --- summaries ---------------------------------------------------------------


def test_a_dry_run_summary_says_nothing_was_changed(app):
    app._handle(DoneEvent(Summary(scanned=7, dry_run=True)))
    assert t("summary.dry_run", scanned=7) in logged(app)


def test_a_stopped_run_reports_what_it_managed(app):
    app._handle(DoneEvent(Summary(deleted=4, dry_run=False, stopped=True)))
    assert t("summary.stopped", deleted=4) in logged(app)


def test_a_finished_run_reports_all_four_counters(app):
    app._handle(DoneEvent(Summary(deleted=10, skipped=2, failed=1, duration=65, dry_run=False)))
    line = logged(app)
    assert "10" in line and "2" in line and "1" in line


# --- language ----------------------------------------------------------------


def test_switching_language_retranslates_the_interface(app):
    english = app._find_button.cget("text")
    app._on_language("Türkçe")
    turkish = app._find_button.cget("text")
    assert turkish != english
    assert turkish == t("btn.find")


def test_switching_language_keeps_the_selected_mode(app):
    fill(app, mode=Mode.LAST_N, count="12")
    app._on_language("Türkçe")
    assert app._mode is Mode.LAST_N
    assert app._mode_selector.get() == t("mode.last_n")


def test_switching_back_restores_english(app):
    app._on_language("Türkçe")
    app._on_language("English")
    assert app._find_button.cget("text") == t("btn.find")


def test_the_dynamic_pause_button_also_retranslates(app):
    english = app._pause_button.cget("text")
    app._on_language("Türkçe")
    assert app._pause_button.cget("text") == t("btn.pause")
    assert app._pause_button.cget("text") != english


def test_the_window_fits_within_the_screen(app):
    # The action buttons must never be pushed off the bottom edge by CTk's
    # display scaling — that made the app unusable. The invariant: the window's
    # actual pixel height (logical height x scaling) fits the screen.
    import re

    match = re.match(r"(\d+)x(\d+)", app.geometry())
    logical_h = int(match.group(2))
    try:
        scaling = ctk.ScalingTracker.get_window_scaling(app) or 1.0
    except Exception:
        scaling = 1.0
    assert logical_h * scaling <= app.winfo_screenheight()


# --- mode panels -------------------------------------------------------------


def test_only_the_relevant_inputs_are_shown_for_each_mode(app):
    fill(app, mode=Mode.ALL)
    assert not app._count_frame.winfo_ismapped()
    fill(app, mode=Mode.LAST_N, count="5")
    app.update_idletasks()
    assert app._count_frame.winfo_ismapped()
    assert not app._dates_frame.winfo_ismapped()
    fill(app, mode=Mode.DATE_RANGE, since="2024-01-01", until="2024-01-02")
    app.update_idletasks()
    assert app._dates_frame.winfo_ismapped()
    assert not app._count_frame.winfo_ismapped()


# --- event pump --------------------------------------------------------------


def test_callbacks_posted_from_worker_threads_run_on_the_ui_thread(app):
    ran = []
    from wipecord.ui.app import UiCallback

    app.events.put(UiCallback(lambda: ran.append(True)))
    app._drain()
    assert ran == [True]


def test_the_pump_survives_an_unknown_event(app):
    app.events.put(object())
    app._drain()  # must not raise


# --- token help --------------------------------------------------------------


def test_a_token_help_link_sits_next_to_the_token_field(app):
    assert app._token_help is not None
    assert app._token_help.cget("text") == t("help.token.link")


def test_the_token_help_dialog_builds_and_closes(app):
    from wipecord.ui.widgets import TokenHelpDialog

    dialog = TokenHelpDialog(app)
    app.update_idletasks()
    try:
        assert dialog.winfo_exists()
    finally:
        dialog._close()
    assert not dialog.winfo_exists()


def test_the_help_link_retranslates_with_the_interface(app):
    app._on_language("Türkçe")
    assert app._token_help.cget("text") == t("help.token.link")


# --- branding ----------------------------------------------------------------


def test_the_logo_assets_exist():
    from wipecord.ui.app import ICON_PATH, WORDMARK_PATH

    assert ICON_PATH.exists(), "the window/taskbar icon is missing"
    assert WORDMARK_PATH.exists(), "the header wordmark image is missing"


def test_the_header_renders_the_wordmark_logo(app):
    # The baked, antialiased logo should load rather than the text fallback.
    assert getattr(app, "_wordmark_image", None) is not None
