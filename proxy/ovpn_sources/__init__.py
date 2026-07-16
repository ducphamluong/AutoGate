"""OpenVPN config source adapters for AutoGate refresh."""

from .base import OvpnConfig
from .registry import get_source, list_source_keys, register_builtin_sources

__all__ = [
    "OvpnConfig",
    "get_source",
    "list_source_keys",
    "register_builtin_sources",
]
