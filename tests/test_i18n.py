"""i18n coverage. No display needed."""

import pytest

from wipecord import i18n
from wipecord.i18n import DEFAULT_LANGUAGE, STRINGS, set_language, t


@pytest.fixture(autouse=True)
def _restore_language():
    yield
    set_language(DEFAULT_LANGUAGE)


def test_english_is_the_source_of_truth_and_present():
    assert DEFAULT_LANGUAGE == "en"
    assert "en" in STRINGS


def test_every_language_defines_exactly_the_same_keys():
    english = set(STRINGS["en"])
    for code, table in STRINGS.items():
        missing = english - set(table)
        extra = set(table) - english
        assert not missing, f"{code} is missing {missing}"
        assert not extra, f"{code} has stray keys {extra}"


def test_a_known_key_translates_per_language():
    set_language("en")
    assert t("btn.delete") == "Delete"
    set_language("tr")
    assert t("btn.delete") == "Sil"


def test_a_missing_translation_falls_back_to_english(monkeypatch):
    monkeypatch.setitem(STRINGS, "tr", dict(STRINGS["tr"]))
    del STRINGS["tr"]["btn.delete"]
    set_language("tr")
    assert t("btn.delete") == "Delete"


def test_an_unknown_key_returns_the_key_itself():
    assert t("no.such.key") == "no.such.key"


def test_placeholders_are_filled():
    set_language("en")
    assert "42" in t("progress.counts", done=42, total=100)


def test_a_bad_placeholder_does_not_crash():
    # A format call missing an argument returns the raw template, never raises.
    set_language("en")
    assert t("progress.counts") == STRINGS["en"]["progress.counts"]


def test_setting_an_unknown_language_is_ignored():
    set_language("en")
    set_language("klingon")
    assert i18n.get_language() == "en"


def test_the_token_help_text_carries_the_phishing_warning():
    # This warning is a safety feature, not decoration; assert it exists in both.
    for code in STRINGS:
        set_language(code)
        assert t("help.token.warning").strip()
        assert "discord.com" in t("help.token.warning")
