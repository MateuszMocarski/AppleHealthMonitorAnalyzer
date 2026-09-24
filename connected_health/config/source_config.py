"""Compatibility import for the former shared Apple source configuration."""

from connected_health.providers.apple.config import AppleSourceConfig

SourceConfig = AppleSourceConfig

__all__ = ["AppleSourceConfig", "SourceConfig"]
