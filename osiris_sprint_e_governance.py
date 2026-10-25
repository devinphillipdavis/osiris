"""
OSIRIS Sprint E Governance Engine: Governed Experience, Delegation, and Release State
=====================================================================================
Covers:
1. Release State Model: One-way transitions, authoritative release_decision, HOLD default.
   Zero automated gates may produce APPROVED.
2. Governed Experience & Retrieval: ExperienceRecord schema, retrieval changing context
   without elevating authority or truth status.
3. Delegation Lineage Receipts: Monotonicity invariants (child authority subset of parent,
   child claim ceiling <= parent claim ceiling).
4. Trigger Ingestion: Journaling untrusted event data; zero direct tool execution on ingest.
5. Self-Play Architecture: Proposer vs Independent Judge separation, task-scoped fitness
   with penalty terms for policy violations and overclaiming.
"""

from __future__ import annotations

import enum
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from osiris_claim_closure import CLAIM_CEILING_ORDER, ceiling_rank


# ============================================================================
# 1. Authoritative Release State Model
# ============================================================================

class ReleaseGateEligibility(str, enum.Enum):
    DRAFT = "DRAFT"
    LOCAL_TESTED = "LOCAL_TESTED"
    ELIGIBLE_FOR_HUMAN_REVIEW = "ELIGIBLE_FOR_HUMAN_REVIEW"
    INELIGIBLE = "INELIGIBLE"


class ReleaseDecision(str, enum.Enum):
    HOLD = "HOLD"
    REJECTED = "REJECTED"
    APPROVED_FOR_LIMITED_RELEASE = "APPROVED_FOR_LIMITED_RELEASE"
    RELEASED_WITH_SCOPE = "RELEASED_WITH_SCOPE"


class GovernanceViolationError(Exception):
    """Raised when an illegal governance or authority transition is attempted."""
    pass


@dataclass
class SprintReviewRecord:
    sprint_id: str
    sprint_status: str
    compiler_status: str
    claim_packs_status: str
    evidence_pack_tests: Dict[str, Any]
    sprint_c_dependency: Dict[str, Any]
    occr_gateway: Dict[str, Any]
    release_gate_eligibility: ReleaseGateEligibility
    release_decision: ReleaseDecision = ReleaseDecision.HOLD
    decision_authority: str = "HUMAN_REVIEW_REQUIRED"
    hold_reasons: List[str] = field(default_factory=lambda: [
        "INDEPENDENT_REVIEW_PENDING",
        "EXTERNAL_REPRODUCTION_PENDING",
        "SECURITY_REVIEW_PENDING"
    ])
    independent_review_status: str = "PENDING"
    external_reproduction_status: str = "NOT_STARTED"
    security_review_status: str = "NOT_STARTED"
    scientific_efficacy_status: str = "NOT_ESTABLISHED"
    production_readiness_status: str = "NOT_ESTABLISHED"
    deployment_authority: str = "NONE"

    def transition_eligibility(self, new_eligibility: ReleaseGateEligibility) -> None:
        """Enforces one-way forward transitions for eligibility."""
        order = [
            ReleaseGateEligibility.DRAFT,
            ReleaseGateEligibility.LOCAL_TESTED,
            ReleaseGateEligibility.ELIGIBLE_FOR_HUMAN_REVIEW,
        ]
        curr_idx = order.index(self.release_gate_eligibility) if self.release_gate_eligibility in order else -1
        new_idx = order.index(new_eligibility) if new_eligibility in order else -1

        if new_idx <= curr_idx and new_eligibility != ReleaseGateEligibility.INELIGIBLE:
            raise GovernanceViolationError(
                f"Illegal backward/lateral eligibility transition: {self.release_gate_eligibility} -> {new_eligibility}"
            )
        self.release_gate_eligibility = new_eligibility

    def apply_automated_review(self) -> None:
        """
        Automated review gate.
        INVARIANT: Automated review CANNOT approve a release.
        It evaluates local tests and sets eligibility to ELIGIBLE_FOR_HUMAN_REVIEW or INELIGIBLE,
        while strictly keeping release_decision = HOLD.
        """
        tests_passed = (
            self.evidence_pack_tests.get("tests_passed", 0) == self.evidence_pack_tests.get("tests_run", 1)
            and self.sprint_c_dependency.get("tests_passed", 0) == self.sprint_c_dependency.get("tests_run", 1)
            and self.occr_gateway.get("tests_passed", 0) == self.occr_gateway.get("tests_run", 1)
        )
        if tests_passed:
            self.release_gate_eligibility = ReleaseGateEligibility.ELIGIBLE_FOR_HUMAN_REVIEW
        else:
            self.release_gate_eligibility = ReleaseGateEligibility.INELIGIBLE

        # Automated gate MUST remain on HOLD
        self.release_decision = ReleaseDecision.HOLD
        self.decision_authority = "HUMAN_REVIEW_REQUIRED"

    def apply_human_decision(
        self,
        decision: ReleaseDecision,
        reviewer_id: str,
        source_revision: str,
        artifact_bundle_hash: str,
        human_auth_token: str,
    ) -> None:
        """
        Only an identified human reviewer with exact revision and token can alter release_decision.
        """
        if not human_auth_token.startswith("OSIRIS-HUMAN-SIG:"):
            raise GovernanceViolationError("Missing or invalid human signature token for release decision.")
        if not reviewer_id or not source_revision or not artifact_bundle_hash:
            raise GovernanceViolationError("Reviewer identity, source revision, and artifact hash are mandatory.")

        if self.release_gate_eligibility != ReleaseGateEligibility.ELIGIBLE_FOR_HUMAN_REVIEW:
            raise GovernanceViolationError(
                f"Cannot make human release decision when eligibility is {self.release_gate_eligibility}"
            )

        self.release_decision = decision
        self.decision_authority = f"HUMAN_REVIEWED:{reviewer_id}"


# ============================================================================
# 2. Governed Experience & Retrieval
# ============================================================================

class MemoryType(str, enum.Enum):
    LESSON_LEARNED = "LESSON_LEARNED"
    FAILURE_ANALYSIS = "FAILURE_ANALYSIS"
    EXPLORATION_TRACE = "EXPLORATION_TRACE"
    POLICY_FEEDBACK = "POLICY_FEEDBACK"
    TASK_OUTCOME = "TASK_OUTCOME"


class FailureClass(str, enum.Enum):
    NONE = "NONE"
    OVERCLAIM = "OVERCLAIM"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    TEST_FAILURE = "TEST_FAILURE"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    TIMEOUT = "TIMEOUT"


class RetrievalPolicy(str, enum.Enum):
    INFORMATIVE_ONLY = "INFORMATIVE_ONLY"
    PROPOSAL_ONLY = "PROPOSAL_ONLY"
    REQUIRES_HUMAN_CONFIRMATION = "REQUIRES_HUMAN_CONFIRMATION"


@dataclass
class ExperienceRecord:
    memory_id: str
    memory_type: MemoryType
    statement: str
    observation: str
    action: str
    outcome: str
    source_hash: str
    claim_ceiling: str = "LOCAL_TEST_RESULT"
    deployment_authority: str = "NONE"
    failure_class: FailureClass = FailureClass.NONE
    retrieval_policy: RetrievalPolicy = RetrievalPolicy.INFORMATIVE_ONLY
    limitations: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def validate(self) -> List[str]:
        errors = []
        if not self.memory_id or not self.statement or not self.source_hash:
            errors.append("Mandatory fields (memory_id, statement, source_hash) missing.")
        if ceiling_rank(self.claim_ceiling) < 0:
            errors.append(f"Invalid claim ceiling: {self.claim_ceiling}")
        return errors

    def render_context(self) -> str:
        """
        Renders memory as evidence-scoped context.
        CRITICAL: Rendered context explicitly includes non-authoritative markers.
        """
        lims = "; ".join(self.limitations) if self.limitations else "None noted."
        return (
            f"[GOVERNED EXPERIENCE: {self.memory_id} | {self.memory_type.value}]\n"
            f"Statement: {self.statement}\n"
            f"Observation: {self.observation}\n"
            f"Outcome: {self.outcome}\n"
            f"Claim ceiling: {self.claim_ceiling}\n"
            f"Authority: {self.deployment_authority}\n"
            f"Status: NON-AUTHORITATIVE PRIOR CONTEXT\n"
            f"Limitations: {lims}\n"
        )


@dataclass
class AgentExecutionContext:
    agent_id: str
    system_prompt: str
    authority: str = "NONE"
    claim_ceiling: str = "HYPOTHESIS"
    context_buffer: List[str] = field(default_factory=list)

    def inject_retrieved_experience(self, exp: ExperienceRecord) -> None:
        """
        CRITICAL INVARIANT:
        Retrieval changes available context.
        Retrieval does NOT change truth status, deployment authority, policy, or claim ceiling.
        """
        orig_prompt = self.system_prompt
        orig_authority = self.authority
        orig_ceiling = self.claim_ceiling

        # Append rendered context
        self.context_buffer.append(exp.render_context())

        # Assert invariants
        if self.system_prompt != orig_prompt:
            self.system_prompt = orig_prompt
            raise GovernanceViolationError("Retrieval cannot mutate agent system prompt.")
        if self.authority != orig_authority:
            self.authority = orig_authority
            raise GovernanceViolationError("Retrieval cannot elevate agent deployment authority.")
        if self.claim_ceiling != orig_ceiling:
            self.claim_ceiling = orig_ceiling
            raise GovernanceViolationError("Retrieval cannot elevate agent claim ceiling.")


# ============================================================================
# 3. Delegation Lineage Receipts
# ============================================================================

AUTHORITY_RANK = {
    "NONE": 0,
    "READ_ONLY": 1,
    "REPLAY_ONLY": 2,
    "STAGING_ONLY": 3,
    "HUMAN_APPROVAL_REQUIRED": 4,
    "PRODUCTION_APPROVED": 5,
}

@dataclass(frozen=True)
class DelegationReceipt:
    delegation_id: str
    parent_agent: str
    child_agent: str
    parent_authority: str
    child_authority: str
    parent_claim_ceiling: str
    child_claim_ceiling: str
    task_scope: str
    tool_allowlist: Tuple[str, ...]
    budget_limit: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def verify_monotonicity(self) -> None:
        """
        Invariants:
        1. child_authority <= parent_authority
        2. rank(child_claim_ceiling) <= rank(parent_claim_ceiling)
        """
        p_auth_rank = AUTHORITY_RANK.get(self.parent_authority, -1)
        c_auth_rank = AUTHORITY_RANK.get(self.child_authority, 999)
        if c_auth_rank > p_auth_rank:
            raise GovernanceViolationError(
                f"Delegation authority elevation violation: child authority '{self.child_authority}' "
                f"exceeds parent authority '{self.parent_authority}'"
            )

        p_ceil_rank = ceiling_rank(self.parent_claim_ceiling)
        c_ceil_rank = ceiling_rank(self.child_claim_ceiling)
        if c_ceil_rank > p_ceil_rank:
            raise GovernanceViolationError(
                f"Delegation claim ceiling elevation violation: child ceiling '{self.child_claim_ceiling}' "
                f"exceeds parent ceiling '{self.parent_claim_ceiling}'"
            )


# ============================================================================
# 4. Trigger Ingestion (Untrusted Event Store)
# ============================================================================

@dataclass(frozen=True)
class TriggerRecord:
    trigger_id: str
    source: str
    payload_hash: str
    timestamp: float
    classification: str
    action_taken: str = "STORE_CONTEXT_ONLY"
    status: str = "UNTRUSTED_EVENT"


class TriggerIngressJournal:
    """
    Ingests external events.
    INVARIANT: External triggers are untrusted event data, not commands.
    They cannot execute tool actions or elevate policy on ingest.
    """

    def __init__(self):
        self._journal: List[TriggerRecord] = []

    def ingest_trigger(self, source: str, payload: Union[str, bytes, Dict[str, Any]]) -> TriggerRecord:
        if isinstance(payload, dict):
            raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        elif isinstance(payload, str):
            raw = payload.encode("utf-8")
        else:
            raw = payload

        h = hashlib.sha256(raw).hexdigest()
        tid = f"TRG-{len(self._journal) + 1:06d}"
        rec = TriggerRecord(
            trigger_id=tid,
            source=source,
            payload_hash=h,
            timestamp=time.time(),
            classification="EXTERNAL_UNTRUSTED_EVENT",
            action_taken="STORE_CONTEXT_ONLY",
            status="UNTRUSTED_EVENT",
        )
        self._journal.append(rec)
        return rec

    @property
    def entries(self) -> List[TriggerRecord]:
        return list(self._journal)


# ============================================================================
# 5. Self-Play Architecture & Task-Scoped Fitness
# ============================================================================

@dataclass
class ProposalCandidate:
    candidate_id: str
    proposer_agent_id: str
    content: str
    parameters: Dict[str, Any]
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass
class JudgeEvaluation:
    judge_agent_id: str
    candidate_id: str
    task_score: float
    test_pass_rate: float
    policy_violations: int
    overclaim_rate: float
    resource_cost: float
    composite_fitness: float
    is_valid: bool
    reasons: List[str]


class SelfPlayEvaluator:
    """
    Independent Judge evaluation.
    INVARIANTS:
    1. Proposer cannot judge its own output.
    2. Judge has zero edit / tool execution authority.
    3. Fitness incorporates explicit penalty terms for policy violations and overclaiming.
    """

    DEFAULT_WEIGHTS = {
        "w1_task": 0.40,
        "w2_tests": 0.30,
        "w3_policy": 0.50,
        "w4_resource": 0.10,
        "w5_overclaim": 0.60,
    }

    @classmethod
    def calculate_fitness(
        cls,
        task_score: float,
        test_pass_rate: float,
        policy_violations: int,
        resource_cost: float,
        overclaim_rate: float,
        weights: Optional[Dict[str, float]] = None,
    ) -> float:
        w = weights or cls.DEFAULT_WEIGHTS
        fitness = (
            w["w1_task"] * task_score
            + w["w2_tests"] * test_pass_rate
            - w["w3_policy"] * policy_violations
            - w["w4_resource"] * resource_cost
            - w["w5_overclaim"] * overclaim_rate
        )
        return float(fitness)

    @classmethod
    def evaluate_proposal(
        cls,
        proposer_agent_id: str,
        judge_agent_id: str,
        judge_tools: Tuple[str, ...],
        judge_authority: str,
        candidate: ProposalCandidate,
        task_score: float,
        test_pass_rate: float,
        policy_violations: int,
        overclaim_rate: float,
        resource_cost: float = 0.05,
    ) -> JudgeEvaluation:
        reasons = []

        # 1. Proposer vs Judge separation check
        if proposer_agent_id == judge_agent_id:
            reasons.append("Self-play violation: Proposer cannot act as judge for its own proposal.")
            return JudgeEvaluation(
                judge_agent_id=judge_agent_id,
                candidate_id=candidate.candidate_id,
                task_score=0.0,
                test_pass_rate=0.0,
                policy_violations=policy_violations + 1,
                overclaim_rate=1.0,
                resource_cost=resource_cost,
                composite_fitness=-1.0,
                is_valid=False,
                reasons=reasons,
            )

        # 2. Judge authority check: Judge cannot possess execution/edit tools
        if judge_tools or judge_authority not in ("NONE", "READ_ONLY"):
            reasons.append(
                f"Judge authority violation: Judge has tools {judge_tools} and authority {judge_authority}."
            )
            return JudgeEvaluation(
                judge_agent_id=judge_agent_id,
                candidate_id=candidate.candidate_id,
                task_score=0.0,
                test_pass_rate=0.0,
                policy_violations=policy_violations + 1,
                overclaim_rate=overclaim_rate,
                resource_cost=resource_cost,
                composite_fitness=-1.0,
                is_valid=False,
                reasons=reasons,
            )

        fit = cls.calculate_fitness(
            task_score=task_score,
            test_pass_rate=test_pass_rate,
            policy_violations=policy_violations,
            resource_cost=resource_cost,
            overclaim_rate=overclaim_rate,
        )

        valid = (policy_violations == 0 and overclaim_rate == 0.0 and test_pass_rate >= 0.8)
        if not valid:
            reasons.append(
                f"Failed validation thresholds: violations={policy_violations}, overclaim={overclaim_rate}, tests={test_pass_rate}"
            )
        else:
            reasons.append("Deterministic validation checks satisfied.")

        return JudgeEvaluation(
            judge_agent_id=judge_agent_id,
            candidate_id=candidate.candidate_id,
            task_score=task_score,
            test_pass_rate=test_pass_rate,
            policy_violations=policy_violations,
            overclaim_rate=overclaim_rate,
            resource_cost=resource_cost,
            composite_fitness=fit,
            is_valid=valid,
            reasons=reasons,
        )
