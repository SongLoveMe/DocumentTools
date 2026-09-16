"""Persisted user preferences for DocumentTools.

Settings live in ``QSettings`` so they survive upgrades and always target the
current user, never the machine.  Reading a value that is missing or malformed
falls back to the documented default instead of raising, so a stale
configuration can never block startup.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import QSettings

from .engines import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    EngineKind,
)

ORGANIZATION = "DocumentTools"
APPLICATION = "DocumentTools"

ENGINE_AUTO = "auto"

_VALID_ENGINES = {ENGINE_AUTO, EngineKind.OFFICE.value, EngineKind.WPS.value}


@dataclass
class ConversionSettings:
    """Conversion preferences with safe defaults."""

    engine: str = ENGINE_AUTO
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def preferred_engine_kind(self) -> EngineKind | None:
        """Return the configured engine, or ``None`` for automatic selection."""
        if self.engine in _VALID_ENGINES and self.engine != ENGINE_AUTO:
            return EngineKind(self.engine)
        return None

    def normalized(self) -> "ConversionSettings":
        engine = self.engine if self.engine in _VALID_ENGINES else ENGINE_AUTO
        try:
            timeout = int(self.timeout_seconds)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT_SECONDS
        timeout = max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, timeout))
        return ConversionSettings(engine=engine, timeout_seconds=timeout)


def _storage() -> QSettings:
    return QSettings(ORGANIZATION, APPLICATION)


def load_settings(storage: QSettings | None = None) -> ConversionSettings:
    settings = storage or _storage()
    raw = ConversionSettings(
        engine=str(settings.value("conversion/engine", ENGINE_AUTO) or ENGINE_AUTO),
        timeout_seconds=_as_int(
            settings.value("conversion/timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        ),
    )
    return raw.normalized()


def save_settings(
    config: ConversionSettings, storage: QSettings | None = None
) -> ConversionSettings:
    settings = storage or _storage()
    normalized = config.normalized()
    settings.setValue("conversion/engine", normalized.engine)
    settings.setValue("conversion/timeout_seconds", normalized.timeout_seconds)
    settings.sync()
    return normalized


def _as_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


__all__ = [
    "APPLICATION",
    "ENGINE_AUTO",
    "ORGANIZATION",
    "ConversionSettings",
    "load_settings",
    "save_settings",
]
