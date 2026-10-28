"""Control plane SDB (Fase 2) — domain + HTTP, stdlib saja."""

from .store import ControlPlaneError, Store

__all__ = ["ControlPlaneError", "Store"]
