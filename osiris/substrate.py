"""OSIRIS Dual-Substrate Invariant Namespace Proxy.

Single resolution point for substrate-dependent execution parameters. Probes
``osiris_hardware_mesh`` first; if that root module is unavailable it falls back
to ``platform``/``os`` probes so callers never hardcode a horizon or an arch.

Two horizons are resolved here and must not be conflated:

* batch / compute horizon — ``execution_timeout_s()``: adapters, orchestrator jobs,
  QPU dispatch. Node Alpha (ARM64 / Termux edge) 300.0 s, Node Beta (x86_64 / WSL
  compute) 1800.0 s.
* interactive horizon — ``interactive_timeout_s()``: REPL shell children and
  model tool calls. 120.0 s on both nodes so a stuck child can never hold the
  REPL for the full batch horizon.
"""

from __future__ import annotations

import hashlib
import math
import os
import platform
from typing import Any, Dict, Optional

ALPHA_TIMEOUT_S = 300.0
BETA_TIMEOUT_S = 1800.0
INTERACTIVE_TIMEOUT_S = 120.0
INTERACTIVE_TIMEOUT_ENV = "OSIRIS_INTERACTIVE_TIMEOUT_S"

#: Keys every substrate telemetry frame carries, on every node, so NCLM feedback
#: consumers never branch on which substrate produced the frame.
TELEMETRY_KEYS = ("node_id", "node_type", "horizon_s", "w2_distance", "shannon_entropy")

try:
    from osiris_hardware_mesh import (  # noqa: F401
        CURRENT_PROFILE,
        HardwareMeshDetector,
        HardwareProfile,
        NodeType,
        detect_hardware,
        get_current_profile,
        is_node_alpha,
        is_node_beta,
    )
    from osiris_hardware_mesh import get_substrate_context as _mesh_substrate_context

    _MESH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only on partial installs
    _MESH_AVAILABLE = False
    _mesh_substrate_context = None

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


def node_id() -> str:
    """Stable, non-identifying node identifier for telemetry frames.

    A digest of hostname and architecture, so frames from one node correlate
    across runs without publishing the hostname itself.
    """
    raw = f"{platform.node()}|{platform.machine().lower()}".encode("utf-8")
    short = node_type().replace("NODE_", "").split("_")[0].lower()
    return f"{short}-{hashlib.sha256(raw).hexdigest()[:12]}"


def execution_timeout_s(override: Optional[float] = None) -> float:
    """Resolve the batch / compute horizon in seconds.

    ``override`` wins when given, so callers can tighten but never silently
    inherit a hardcoded constant.
    """
    if override is not None:
        return float(override)
    if _MESH_AVAILABLE:
        return float(get_current_profile().execution_timeout_s)
    return BETA_TIMEOUT_S if is_node_beta() else ALPHA_TIMEOUT_S


def interactive_timeout_s(override: Optional[float] = None) -> float:
    """Resolve the interactive horizon for REPL shell children and tool calls.

    Resolution order: ``override``, then ``$OSIRIS_INTERACTIVE_TIMEOUT_S``, then
    120.0 s. A malformed, non-finite or non-positive value falls back to the
    default rather than disabling the timeout, and the result is capped at the
    batch horizon so an interactive call can never outlive a batch job.
    """
    value = override
    if value is None:
        raw = os.environ.get(INTERACTIVE_TIMEOUT_ENV, "").strip()
        if raw:
            try:
                value = float(raw)
            except ValueError:
                value = None
    try:
        value = float(value) if value is not None else INTERACTIVE_TIMEOUT_S
    except (TypeError, ValueError):
        value = INTERACTIVE_TIMEOUT_S
    if not math.isfinite(value) or value <= 0:
        value = INTERACTIVE_TIMEOUT_S
    return min(value, execution_timeout_s())


def simd_profile() -> Dict[str, bool]:
    """Vector ISA availability used to pick NCLM kernel paths."""
    if _MESH_AVAILABLE:
        p = get_current_profile()
        return {"neon": p.has_neon, "avx2": p.has_avx2, "avx_vnni": p.has_avx_vnni}
    alpha = is_node_alpha()
    return {"neon": alpha, "avx2": not alpha, "avx_vnni": False}


def _metric(name: str, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number, got {value!r}")
    return value


def get_substrate_context(
    w2_distance: Optional[float] = None,
    shannon_entropy: Optional[float] = None,
) -> Dict[str, Any]:
    """Substrate telemetry frame with the same keys on every node.

    ``w2_distance`` and ``shannon_entropy`` are per-run NCLM measurements, not
    properties of the hardware, so they are ``None`` until a caller supplies a
    measured value; they are never synthesized here.
    """
    ctx: Dict[str, Any] = {}
    if _MESH_AVAILABLE:
        ctx.update(_mesh_substrate_context())
    else:
        ctx.update({
            "machine_arch": platform.machine().lower(),
            "cpu_cores": os.cpu_count() or 1,
            "execution_timeout_s": execution_timeout_s(),
        })
    ctx.update({
        "node_id": node_id(),
        "node_type": node_type(),
        "horizon_s": execution_timeout_s(),
        "interactive_horizon_s": interactive_timeout_s(),
        "w2_distance": _metric("w2_distance", w2_distance),
        "shannon_entropy": _metric("shannon_entropy", shannon_entropy),
        "mesh_available": _MESH_AVAILABLE,
    })
    return ctx


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
    "INTERACTIVE_TIMEOUT_ENV",
    "INTERACTIVE_TIMEOUT_S",
    "NodeType",
    "TELEMETRY_KEYS",
    "configure_stdio",
    "detect_hardware",
    "execution_timeout_s",
    "get_current_profile",
    "get_substrate_context",
    "interactive_timeout_s",
    "is_node_alpha",
    "is_node_beta",
    "mesh_available",
    "node_id",
    "node_type",
    "simd_profile",
]
