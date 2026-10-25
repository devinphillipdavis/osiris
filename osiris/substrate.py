"""OSIRIS Dual-Substrate Invariant Namespace Proxy.

Single resolution point for substrate-dependent execution parameters. Probes
``osiris_hardware_mesh`` first; if that root module is unavailable it falls back
to ``platform``/``os`` probes so callers never hardcode a horizon or an arch.

Node Alpha (ARM64 / Termux edge)  -> 300.0 s horizon, NEON SIMD, UTF-8 unbuffered stdout
Node Beta  (x86_64 / WSL compute) -> 1800.0 s horizon, AVX2 / AVX-VNNI, batch QPU dispatch
"""

from __future__ import annotations

import os
import platform
from typing import Any, Dict, Optional

ALPHA_TIMEOUT_S = 300.0
BETA_TIMEOUT_S = 1800.0

try:
    from osiris_hardware_mesh import (  # noqa: F401
        CURRENT_PROFILE,
        HardwareMeshDetector,
        HardwareProfile,
        NodeType,
        detect_hardware,
        get_current_profile,
        get_substrate_context,
        is_node_alpha,
        is_node_beta,
    )

    _MESH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only on partial installs
    _MESH_AVAILABLE = False

    CURRENT_PROFILE = None
    HardwareMeshDetector = None
    HardwareProfile = None
    NodeType = None

    def _fallback_arch() -> str:
        return platform.machine().lower()

    def is_node_alpha() -> bool:
        """ARM64 / Termux edge, detected without the hardware mesh."""
        return bool(
            os.environ.get("TERMUX_VERSION")
            or os.path.exists("/data/data/com.termux")
            or _fallback_arch() in ("aarch64", "arm64")
        )

    def is_node_beta() -> bool:
        """x86_64 compute node, detected without the hardware mesh."""
        return _fallback_arch() in ("x86_64", "amd64") and not is_node_alpha()

    def get_current_profile():  # type: ignore[misc]
        return None

    def detect_hardware():  # type: ignore[misc]
        return None

    def get_substrate_context() -> Dict[str, Any]:
        return {
            "node_type": node_type(),
            "machine_arch": _fallback_arch(),
            "cpu_cores": os.cpu_count() or 1,
            "execution_timeout_s": execution_timeout_s(),
            "mesh_available": False,
        }


def mesh_available() -> bool:
    """True when ``osiris_hardware_mesh`` resolved and full telemetry is present."""
    return _MESH_AVAILABLE


def node_type() -> str:
    """Substrate label: NODE_ALPHA_MOBILE, NODE_BETA_COMPUTE or NODE_GENERIC_EDGE."""
    if _MESH_AVAILABLE:
        return get_current_profile().node_type.value
    if is_node_alpha():
        return "NODE_ALPHA_MOBILE"
    if is_node_beta():
        return "NODE_BETA_COMPUTE"
    return "NODE_GENERIC_EDGE"


def execution_timeout_s(override: Optional[float] = None) -> float:
    """Resolve the substrate execution horizon in seconds.

    ``override`` wins when given, so callers can tighten but never silently
    inherit a hardcoded constant.
    """
    if override is not None:
        return float(override)
    if _MESH_AVAILABLE:
        return float(get_current_profile().execution_timeout_s)
    return BETA_TIMEOUT_S if is_node_beta() else ALPHA_TIMEOUT_S


def simd_profile() -> Dict[str, bool]:
    """Vector ISA availability used to pick NCLM kernel paths."""
    if _MESH_AVAILABLE:
        p = get_current_profile()
        return {"neon": p.has_neon, "avx2": p.has_avx2, "avx_vnni": p.has_avx_vnni}
    alpha = is_node_alpha()
    return {"neon": alpha, "avx2": not alpha, "avx_vnni": False}


def configure_stdio() -> None:
    """Enforce unbuffered UTF-8 stdout on Node Alpha so dna::}{::lang topology survives."""
    if node_type() == "NODE_ALPHA_MOBILE":
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        os.environ.setdefault("PYTHONUNBUFFERED", "1")


__all__ = [
    "ALPHA_TIMEOUT_S",
    "BETA_TIMEOUT_S",
    "CURRENT_PROFILE",
    "HardwareMeshDetector",
    "HardwareProfile",
    "NodeType",
    "configure_stdio",
    "detect_hardware",
    "execution_timeout_s",
    "get_current_profile",
    "get_substrate_context",
    "is_node_alpha",
    "is_node_beta",
    "mesh_available",
    "node_type",
    "simd_profile",
]
