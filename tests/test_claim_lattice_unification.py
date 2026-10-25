"""One claim lattice: osiris_claim_closure is canonical, OCCR re-exports it."""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import occr_governance_engine as occr
import osiris_claim_closure as canon
from experiment_orchestrator import resolve_claim_ceiling as orchestrator_resolve

ClaimCeiling = canon.ClaimCeiling

#: OCCR's pre-unification rungs, lowest first. Their relative order must survive.
LEGACY_OCCR_ORDER = [
    "NO_CLAIM", "HYPOTHESIS", "IMPLEMENTATION_ONLY", "TESTED",
    "EMPIRICAL_RESULT", "REPRODUCIBILITY", "PRODUCT_CAPABILITY", "VERIFIED",
]


def test_occr_uses_the_canonical_enum():
    assert occr.ClaimCeiling is canon.ClaimCeiling


def test_enum_members_are_exactly_the_canonical_order():
    assert [m.name for m in ClaimCeiling] == canon.CLAIM_CEILING_ORDER


@pytest.mark.parametrize("rank,label", list(enumerate(canon.CLAIM_CEILING_ORDER)))
def test_both_modules_agree_on_every_rank_and_label(rank, label):
    assert canon.ceiling_rank(label) == rank
    assert int(occr.ClaimCeiling[label]) == rank
    assert occr.ClaimCeiling(rank).name == label
    assert canon.ceiling_rank(occr.ClaimCeiling[label]) == rank
    assert canon.resolve_claim_ceiling(label) is ClaimCeiling(rank)
    assert canon.resolve_claim_ceiling(rank) is ClaimCeiling(rank)


def test_legacy_occr_rungs_keep_their_relative_order():
    ranks = [int(ClaimCeiling[name]) for name in LEGACY_OCCR_ORDER]
    assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks)


def test_legacy_label_is_an_alias_not_an_extra_rung():
    assert ClaimCeiling.IMPLEMENTATION_ONLY is ClaimCeiling.IMPLEMENTED_CANDIDATE
    assert "IMPLEMENTATION_ONLY" not in [m.name for m in ClaimCeiling]
    assert canon.ceiling_rank("IMPLEMENTATION_ONLY") == -1  # strict string contract kept


def test_no_phantom_or_foreign_members():
    for label in canon.FOREIGN_CEILING_LABELS:
        assert label not in ClaimCeiling.__members__


def test_foreign_labels_project_down_never_up():
    assert canon.resolve_claim_ceiling("BOUNDED_EXPLORATORY_OBSERVATION") is ClaimCeiling.MEASURED
    assert ClaimCeiling.MEASURED < ClaimCeiling.EMPIRICAL_RESULT


def test_occr_evidence_map_targets_canonical_members():
    for target in occr.ClaimGate.EVIDENCE_CEILING_MAP.values():
        assert target in ClaimCeiling


@pytest.mark.parametrize("bad", ["", "garbage", "TESTED!", None, 99, -1, True, 2.5, object()])
def test_unknown_inputs_fail_closed(bad):
    assert canon.resolve_claim_ceiling(bad) is ClaimCeiling.NO_CLAIM


def test_orchestrator_shim_is_the_canonical_resolver():
    assert orchestrator_resolve is canon.resolve_claim_ceiling
    assert orchestrator_resolve("  tested ") is ClaimCeiling.TESTED
