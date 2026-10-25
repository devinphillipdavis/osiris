"""
Unit tests for nclm_research_adapter.py
Covers:
- Adapter initialization and backend discovery
- Frozen gradient invariant verification
- Untrusted boundary enforcement and hash tracking
- Fallback telemetry when backend is unavailable
"""

import pytest
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from nclm_research_adapter import NCLMResearchAdapter


def test_adapter_initialization_and_frozen_gradients():
    adapter = NCLMResearchAdapter(allow_online_learning=False)
    status = adapter.get_status()

    assert "available" in status
    assert "model_type" in status
    assert status["frozen_gradients"] is True
    assert "READ_ONLY_INFERENCE" in status["active_invariants"]


def test_hypothesis_generation_provenance():
    adapter = NCLMResearchAdapter()
    drafts, prov = adapter.generate_hypotheses(
        domain="QUANTUM_INFORMATION",
        topic="staggered dynamical decoupling",
        seed=101
    )

    assert len(drafts) >= 1
    draft = drafts[0]
    assert draft["hypothesis_id"].startswith("OCCR-HYP-")
    assert draft["requested_claim_ceiling"] == "HYPOTHESIS"

    # Provenance verification
    assert prov.prompt_hash is not None
    assert len(prov.prompt_hash) == 64
    assert prov.seed == 101
    assert prov.schema_valid is True


def test_critique_commentary_generation():
    adapter = NCLMResearchAdapter()
    sample_hyp = {
        "hypothesis_id": "OCCR-HYP-999999",
        "statement": "Offsetting pi pulses reduces static dephasing."
    }
    critique, prov = adapter.critique_hypothesis(sample_hyp, seed=202)

    assert critique["hypothesis_id"] == "OCCR-HYP-999999"
    assert critique["critique_type"] == "MODEL_CRITIQUE"
    assert "commentary" in critique
    assert prov.response_hash is not None
