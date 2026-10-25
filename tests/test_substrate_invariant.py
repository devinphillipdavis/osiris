"""Dual-substrate execution invariant and claim-ceiling projection.

These must hold on Node Alpha (ARM64/Termux edge), Node Beta (x86_64/WSL compute)
and an unclassified generic edge node, so nothing here asserts a specific host.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from osiris import substrate
from experiment_orchestrator import resolve_claim_ceiling
from occr_governance_engine import ClaimCeiling

VALID_NODES = {"NODE_ALPHA_MOBILE", "NODE_BETA_COMPUTE", "NODE_GENERIC_EDGE"}


def test_node_type_is_a_known_substrate():
    assert substrate.node_type() in VALID_NODES


def test_timeout_horizon_matches_node_classification():
    """Alpha and generic edge are capped at 300 s; only Beta gets the 1800 s horizon."""
    node = substrate.node_type()
    timeout = substrate.execution_timeout_s()
    if node == "NODE_BETA_COMPUTE":
        assert timeout == substrate.BETA_TIMEOUT_S == 1800.0
    else:
        assert timeout == substrate.ALPHA_TIMEOUT_S == 300.0


def test_timeout_override_is_honoured():
    """Callers may tighten the horizon but never silently inherit a constant."""
    assert substrate.execution_timeout_s(42.0) == 42.0
    assert substrate.execution_timeout_s(None) == substrate.execution_timeout_s()


def test_simd_profile_reports_the_substrate_vector_isa():
    profile = substrate.simd_profile()
    assert set(profile) == {"neon", "avx2", "avx_vnni"}
    assert all(isinstance(v, bool) for v in profile.values())
    if substrate.node_type() == "NODE_ALPHA_MOBILE":
        assert profile["neon"], "Node Alpha must expose NEON for vectorized NCLM kernels"


def test_substrate_context_is_derived_not_hardcoded():
    """Paths must be resolved from the module location, never baked in as literals."""
    ctx = substrate.get_substrate_context()
    assert ctx["execution_timeout_s"] == substrate.execution_timeout_s()
    assert ctx["node_type"] in VALID_NODES

    workspace_root = ctx.get("workspace_root")
    if workspace_root is not None:
        resolved = Path(workspace_root)
        assert resolved.is_absolute()
        assert resolved.is_dir()
        # Derived from where the mesh module actually lives, not a fixed home dir.
        assert resolved == _ROOT


def test_configure_stdio_is_idempotent():
    substrate.configure_stdio()
    substrate.configure_stdio()


def test_antigravity_adapter_imports_without_the_optional_sdk():
    """ReplayAdapter and collection must not depend on google_antigravity."""
    from osiris.agents.gateway.adapters import AntigravityAdapter, ReplayAdapter

    assert ReplayAdapter is not None
    assert isinstance(AntigravityAdapter.is_available(), bool)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("NO_CLAIM", ClaimCeiling.NO_CLAIM),
        ("HYPOTHESIS", ClaimCeiling.HYPOTHESIS),
        ("LOCAL_TEST_RESULT", ClaimCeiling.LOCAL_TEST_RESULT),
        ("TESTED", ClaimCeiling.TESTED),
        ("BOUNDED_EXPLORATORY_OBSERVATION", ClaimCeiling.MEASURED),
        ("VERIFIED", ClaimCeiling.VERIFIED),
    ],
)
def test_claim_ceiling_projects_both_lattices(name, expected):
    assert resolve_claim_ceiling(name) is expected


@pytest.mark.parametrize("bad", ["", "garbage", "TESTED!", None, 99, -1, True, object()])
def test_unknown_claim_ceiling_fails_closed(bad):
    """Invariant 4: an unrecognized ceiling must never inherit a permissive default."""
    assert resolve_claim_ceiling(bad) is ClaimCeiling.NO_CLAIM


def test_claim_ceiling_never_projects_upward():
    """A string-lattice name must not map to a stronger OCCR claim than it asserts."""
    from osiris_claim_closure import CLAIM_CEILING_ORDER

    occr_names = [c.name for c in ClaimCeiling]
    for name in CLAIM_CEILING_ORDER:
        projected = resolve_claim_ceiling(name)
        if name in occr_names:
            assert projected is ClaimCeiling[name]
        else:
            # Projected down onto a weaker-or-equal rung that actually exists.
            assert int(projected) < int(ClaimCeiling[occr_names[-1]])


# ── Interactive vs batch horizons ──────────────────────────────────────────────

def test_interactive_horizon_defaults_to_120s(monkeypatch):
    monkeypatch.delenv(substrate.INTERACTIVE_TIMEOUT_ENV, raising=False)
    assert substrate.interactive_timeout_s() == 120.0


def test_interactive_horizon_env_override(monkeypatch):
    monkeypatch.setenv(substrate.INTERACTIVE_TIMEOUT_ENV, "45")
    assert substrate.interactive_timeout_s() == 45.0
    assert substrate.interactive_timeout_s(10.0) == 10.0  # explicit override wins


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "nan", "inf", ""])
def test_malformed_interactive_override_falls_back_not_disables(monkeypatch, raw):
    monkeypatch.setenv(substrate.INTERACTIVE_TIMEOUT_ENV, raw)
    assert substrate.interactive_timeout_s() == 120.0


def test_interactive_horizon_never_exceeds_batch_horizon(monkeypatch):
    monkeypatch.setenv(substrate.INTERACTIVE_TIMEOUT_ENV, "999999")
    assert substrate.interactive_timeout_s() == substrate.execution_timeout_s()


def test_command_runner_uses_interactive_horizon(monkeypatch, tmp_path):
    from osiris_cli.command_runner import CommandRunner

    monkeypatch.setenv(substrate.INTERACTIVE_TIMEOUT_ENV, "33")
    assert CommandRunner(tmp_path).timeout_seconds == 33.0
    assert CommandRunner(tmp_path, timeout_seconds=7).timeout_seconds == 7


# ── Telemetry frame shape ──────────────────────────────────────────────────────

def test_telemetry_frame_carries_the_same_keys_on_every_node():
    ctx = substrate.get_substrate_context()
    assert set(substrate.TELEMETRY_KEYS) <= set(ctx)
    assert ctx["horizon_s"] == substrate.execution_timeout_s()
    assert ctx["node_id"] == substrate.node_id()
    # Unmeasured NCLM metrics are present but never synthesized.
    assert ctx["w2_distance"] is None and ctx["shannon_entropy"] is None


def test_node_id_is_stable_and_does_not_publish_the_hostname():
    import platform

    assert substrate.node_id() == substrate.node_id()
    assert platform.node() not in substrate.node_id() or not platform.node()


def test_telemetry_frame_records_supplied_metrics():
    ctx = substrate.get_substrate_context(w2_distance=0.125, shannon_entropy=2.0)
    assert ctx["w2_distance"] == 0.125 and ctx["shannon_entropy"] == 2.0


@pytest.mark.parametrize("kwargs", [{"w2_distance": -1.0}, {"shannon_entropy": float("nan")}])
def test_telemetry_frame_rejects_invalid_metrics(kwargs):
    with pytest.raises(ValueError):
        substrate.get_substrate_context(**kwargs)
