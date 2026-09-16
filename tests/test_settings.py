"""Tests for persisted conversion settings."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtCore import QSettings

from documenttools.settings import (
    ENGINE_AUTO,
    ConversionSettings,
    load_settings,
    save_settings,
)


@pytest.fixture
def storage(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)


def test_defaults(storage):
    config = load_settings(storage)
    assert config.engine == ENGINE_AUTO
    assert config.timeout_seconds == 120
    assert config.preferred_engine_kind() is None


def test_round_trip(storage):
    saved = save_settings(ConversionSettings(engine="wps", timeout_seconds=200), storage)
    assert saved.engine == "wps"
    assert saved.timeout_seconds == 200

    reloaded = load_settings(storage)
    assert reloaded == saved
    assert reloaded.preferred_engine_kind().value == "wps"


def test_invalid_values_fall_back_to_defaults(storage):
    storage.setValue("conversion/engine", "nonexistent-engine")
    storage.setValue("conversion/timeout_seconds", "not-a-number")
    storage.sync()

    config = load_settings(storage)
    assert config.engine == ENGINE_AUTO
    assert config.timeout_seconds == 120


def test_timeout_is_clamped(storage):
    save_settings(ConversionSettings(timeout_seconds=1), storage)
    assert load_settings(storage).timeout_seconds == 30
    save_settings(ConversionSettings(timeout_seconds=99999), storage)
    assert load_settings(storage).timeout_seconds == 600


def test_settings_no_longer_carry_pdf_a_or_word_backend(storage):
    """PDF/A and the PDF->Word backend were removed; stale keys are ignored."""
    assert not hasattr(ConversionSettings(), "pdf_a")
    assert not hasattr(ConversionSettings(), "pdf_to_word_backend")

    # A configuration written by an older build must still load cleanly.
    storage.setValue("conversion/pdf_a", True)
    storage.setValue("conversion/pdf_to_word_backend", "local_engine")
    storage.sync()
    assert load_settings(storage) == ConversionSettings()
