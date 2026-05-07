"""
PatternRegistry — Auto-discovery of all PatternDetector subclasses.

On first access, walks `app.patterns.{chart, candle, indicator, volume}`
sub-packages, imports every module, and registers any concrete PatternDetector
subclass found.

Usage:
    from app.patterns import PatternRegistry

    PatternRegistry.all()                          # list[type[PatternDetector]]
    PatternRegistry.by_category("candle")          # filtered
    PatternRegistry.get("bullish_engulfing")       # by name (raises KeyError)
    PatternRegistry.instantiate_all()              # default-param instances
"""
from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Iterable

from .base import PatternCategory, PatternDetector

logger = logging.getLogger(__name__)

_SUB_PACKAGES = ("chart", "candle", "indicator", "volume")


class PatternRegistry:
    """Class-level registry. Idempotent — safe to call discover() multiple times."""

    _detectors: dict[str, type[PatternDetector]] = {}
    _discovered: bool = False

    @classmethod
    def discover(cls, force: bool = False) -> None:
        if cls._discovered and not force:
            return
        if force:
            cls._detectors.clear()

        from app import patterns as patterns_pkg

        for sub in _SUB_PACKAGES:
            try:
                pkg = importlib.import_module(f"{patterns_pkg.__name__}.{sub}")
            except ModuleNotFoundError:
                logger.debug("PatternRegistry: subpackage %s not yet present", sub)
                continue
            for _finder, mod_name, _ispkg in pkgutil.iter_modules(pkg.__path__):
                full = f"{pkg.__name__}.{mod_name}"
                try:
                    module = importlib.import_module(full)
                except Exception as exc:
                    logger.warning("PatternRegistry: failed to import %s: %s", full, exc)
                    continue
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, PatternDetector)
                        and obj is not PatternDetector
                        and not inspect.isabstract(obj)
                        and obj.__module__ == full
                    ):
                        cls._register(obj)
        cls._discovered = True

    @classmethod
    def _register(cls, detector_cls: type[PatternDetector]) -> None:
        if not detector_cls.name:
            raise ValueError(
                f"{detector_cls.__name__}: 'name' class variable is empty. "
                "Every detector must declare a unique snake_case name."
            )
        existing = cls._detectors.get(detector_cls.name)
        if existing is not None and existing is not detector_cls:
            raise ValueError(
                f"Pattern name collision: '{detector_cls.name}' already registered "
                f"by {existing.__module__}.{existing.__name__}, "
                f"now {detector_cls.__module__}.{detector_cls.__name__} tries to use it."
            )
        cls._detectors[detector_cls.name] = detector_cls

    # ------------------------------------------------------------------ public

    @classmethod
    def all(cls) -> list[type[PatternDetector]]:
        cls.discover()
        return list(cls._detectors.values())

    @classmethod
    def names(cls) -> list[str]:
        cls.discover()
        return sorted(cls._detectors.keys())

    @classmethod
    def by_category(cls, category: PatternCategory) -> list[type[PatternDetector]]:
        cls.discover()
        return [d for d in cls._detectors.values() if d.category == category]

    @classmethod
    def get(cls, name: str) -> type[PatternDetector]:
        cls.discover()
        if name not in cls._detectors:
            raise KeyError(
                f"Unknown pattern: {name!r}. Available: {sorted(cls._detectors)}"
            )
        return cls._detectors[name]

    @classmethod
    def instantiate_all(cls, params: dict | None = None) -> list[PatternDetector]:
        """Instantiate all registered detectors with default (or supplied) params."""
        cls.discover()
        return [d(params) for d in cls._detectors.values()]

    @classmethod
    def category_counts(cls) -> dict[str, int]:
        cls.discover()
        out: dict[str, int] = {}
        for d in cls._detectors.values():
            out[d.category] = out.get(d.category, 0) + 1
        return out
