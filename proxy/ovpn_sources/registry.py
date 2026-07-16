"""Source registry — maps OVPN_SOURCES keys to adapter instances."""

from __future__ import annotations

from typing import Dict

from .base import OvpnSource
from .vpngate import VpnGateSource

_REGISTRY: Dict[str, OvpnSource] = {}
_BUILTINS_REGISTERED = False


def register(source: OvpnSource) -> None:
    _REGISTRY[source.key] = source


def register_builtin_sources() -> None:
    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return

    register(VpnGateSource())

    # Optional adapters — import lazily so missing modules don't break core.
    try:
        from .ipspeed import IpSpeedSource

        register(IpSpeedSource())
    except Exception:
        pass

    try:
        from .openproxylist import OpenProxyListSource

        register(OpenProxyListSource())
    except Exception:
        pass

    try:
        from .publicvpnlist import PublicVpnListSource

        register(PublicVpnListSource())
    except Exception:
        pass

    _BUILTINS_REGISTERED = True


def get_source(key: str) -> OvpnSource | None:
    register_builtin_sources()
    return _REGISTRY.get(key.strip().lower())


def list_source_keys() -> list[str]:
    register_builtin_sources()
    return sorted(_REGISTRY.keys())
