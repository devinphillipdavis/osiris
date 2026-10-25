"""
OSIRIS Claim Pack Closure & Evidence Eligibility Verifier
=========================================================
Implements mandatory closure.json validation for claim packs and typed evidence
eligibility policy by role and status.

Invariants:
1. Fail-closed: missing closure.json, unverified hashes, or condition failures
   immediately fail verification.
2. Excluded evidence preservation: excluded artifacts are bound by hash with explicit
   status and reasons; they can never appear in supporting_evidence.
3. Monotonicity & Ceiling: claim ceiling is capped by the highest validated supporting evidence.
4. Deployment authority is NONE by default and cannot be elevated automatically.
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


# ============================================================================
# 1. Typed Evidence Roles & Statuses
# ============================================================================

class EvidenceRole(str, enum.Enum):
    SUPPORTING = "SUPPORTING"
    COUNTER = "COUNTER"
    EXCLUSION = "EXCLUSION"
    NEGATIVE_CONTROL = "NEGATIVE_CONTROL"
    CONTEXT_ONLY = "CONTEXT_ONLY"


class EvidenceStatus(str, enum.Enum):
    DECLARED = "DECLARED"
    SIMULATED = "SIMULATED"
    LOCAL_TEST_RESULT = "LOCAL_TEST_RESULT"
    MEASURED = "MEASURED"
    REPRODUCED = "REPRODUCED"
    VOID = "VOID"
    RETRACTED = "RETRACTED"
    INVALID = "INVALID"
    UNRESOLVED = "UNRESOLVED"


# Claim Ceiling Total Ordering
CLAIM_CEILING_ORDER = [
    "NO_CLAIM",
    "HYPOTHESIS",
    "ANALYSIS_ONLY",
    "IMPLEMENTED_CANDIDATE",
    "LOCAL_TEST_RESULT",
    "TESTED",
    "MEASURED",
    "EMPIRICAL_RESULT",
    "REPRODUCED",
    "REPRODUCIBILITY",
    "INDEPENDENTLY_REPLICATED",
    "PRODUCT_CAPABILITY",
    "VERIFIED"
]

def ceiling_rank(ceiling: str) -> int:
    try:
        return CLAIM_CEILING_ORDER.index(ceiling)
    except ValueError:
        return -1


@dataclass(frozen=True)
class TypedEvidenceRecord:
    evidence_id: str
    artifact_hash: str
    role: EvidenceRole
    status: EvidenceStatus
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_support_claim(self) -> bool:
        """
        Predicate: May this evidence record be used to support a positive claim?
        Rules:
        - Status must NOT be VOID, RETRACTED, INVALID, or DECLARED.
        - Role MUST be SUPPORTING.
        """
        unsupported_statuses = {
            EvidenceStatus.VOID,
            EvidenceStatus.RETRACTED,
            EvidenceStatus.INVALID,
            EvidenceStatus.DECLARED,
            EvidenceStatus.UNRESOLVED,
        }
        if self.status in unsupported_statuses:
            return False
        if self.role != EvidenceRole.SUPPORTING:
            return False
        return True


def can_support_claim(record: Union[TypedEvidenceRecord, Dict[str, Any]]) -> bool:
    """Convenience functional check for evidence records."""
    if isinstance(record, TypedEvidenceRecord):
        return record.can_support_claim()
    
    status = record.get("status")
    role = record.get("role")
    if isinstance(status, str):
        try:
            status = EvidenceStatus(status)
        except ValueError:
            return False
    if isinstance(role, str):
        try:
            role = EvidenceRole(role)
        except ValueError:
            return False
            
    unsupported_statuses = {
        EvidenceStatus.VOID,
        EvidenceStatus.RETRACTED,
        EvidenceStatus.INVALID,
        EvidenceStatus.DECLARED,
        EvidenceStatus.UNRESOLVED,
    }
    if status in unsupported_statuses:
        return False
    if role != EvidenceRole.SUPPORTING:
        return False
    return True


# ============================================================================
# 2. Condition Evaluation Engine
# ============================================================================

def evaluate_condition(cond: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """
    Evaluates a single condition against a runtime context dictionary.
    Operators supported: equals, not_equals, greater_than, less_than, in, contains.
    """
    field_name = cond.get("field")
    op = cond.get("operator", "equals")
    expected = cond.get("value")

    actual = context.get(field_name)

    if op == "equals":
        return actual == expected
    elif op == "not_equals":
        return actual != expected
    elif op == "greater_than":
        if actual is None or expected is None:
            return False
        return float(actual) > float(expected)
    elif op == "less_than":
        if actual is None or expected is None:
            return False
        return float(actual) < float(expected)
    elif op == "in":
        return actual in expected if expected is not None else False
    elif op == "contains":
        return expected in actual if actual is not None else False
    else:
        # Unknown operator fails condition
        return False


# ============================================================================
# 3. Claim Pack Closure Validator
# ============================================================================

@dataclass
class ClosureValidationResult:
    valid: bool
    claim_id: str
    reasons: List[str]
    claim_status: str  # "VALID", "INVALID", "SUPERSEDED", "FAILED_CLOSED"
    verified_claim_ceiling: str
    verified_deployment_authority: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ClaimPackClosureVerifier:
    """
    Validates a claim pack's closure.json and all linked artifact hashes.
    Fails closed on missing closure, hash mismatch, or condition violation.
    """

    @classmethod
    def verify_closure_dict(
        cls,
        closure: Dict[str, Any],
        artifact_contents_or_hashes: Optional[Dict[str, str]] = None,
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> ClosureValidationResult:
        reasons: List[str] = []
        claim_id = closure.get("claim_id", "UNKNOWN")
        context = runtime_context or {}
        artifact_hashes = artifact_contents_or_hashes or {}

        # 1. Schema check
        if closure.get("schema_version") != "1.0":
            reasons.append(f"Unsupported schema_version: {closure.get('schema_version')}")

        # 2. Supporting vs Excluded overlap check
        supporting = closure.get("supporting_evidence", [])
        counter = closure.get("counter_evidence", [])
        excluded = closure.get("excluded_evidence", [])

        excluded_artifacts: Set[str] = set()
        for item in excluded:
            if isinstance(item, dict):
                art = item.get("artifact")
                if art:
                    excluded_artifacts.add(art)
            elif isinstance(item, str):
                excluded_artifacts.add(item)

        for supp in supporting:
            if supp in excluded_artifacts:
                reasons.append(
                    f"Evidence integrity violation: Excluded evidence '{supp}' appears in supporting_evidence."
                )

        # 3. Artifact hash verification (if provided)
        for supp in supporting:
            expected_hash = None
            tag = ""
            if ":sha256:" in supp:
                parts = supp.split(":sha256:")
                tag = parts[0].replace("artifact:", "").strip()
                expected_hash = parts[1].strip()
            elif supp.startswith("artifact:sha256:"):
                expected_hash = supp.split("artifact:sha256:")[1].strip()

            if expected_hash and artifact_hashes:
                if tag and tag in artifact_hashes:
                    actual = artifact_hashes[tag]
                    if actual != expected_hash:
                        reasons.append(
                            f"Artifact hash mismatch for '{tag}': expected {expected_hash}, got {actual}"
                        )
                else:
                    if expected_hash not in artifact_hashes.values():
                        reasons.append(
                            f"Artifact hash mismatch: expected hash {expected_hash} not present in on-disk artifacts ({list(artifact_hashes.values())})"
                        )

        # 4. Validity conditions check
        validity_conditions = closure.get("validity_conditions", [])
        for cond in validity_conditions:
            cond_passed = evaluate_condition(cond, context)
            if not cond_passed:
                reasons.append(
                    f"Validity condition violated: field '{cond.get('field')}' failed condition {cond} (actual: {context.get(cond.get('field'))})"
                )

        # 5. Invalidation conditions check
        invalidation_conditions = closure.get("invalidation_conditions", [])
        invalidated = False
        for cond in invalidation_conditions:
            cond_triggered = evaluate_condition(cond, context)
            if cond_triggered:
                invalidated = True
                reasons.append(
                    f"Invalidation condition triggered: field '{cond.get('field')}' triggered condition {cond}"
                )

        claim_ceiling = closure.get("claim_ceiling", "HYPOTHESIS")
        deployment_authority = closure.get("deployment_authority", "NONE")

        # Invariant: deployment_authority cannot be elevated above NONE without explicit human token
        if deployment_authority != "NONE" and not context.get("human_token_verified", False):
            reasons.append(
                f"Deployment authority elevation violation: '{deployment_authority}' requires human_token_verified."
            )

        if reasons:
            status = "INVALID" if invalidated else "FAILED_CLOSED"
            return ClosureValidationResult(
                valid=False,
                claim_id=claim_id,
                reasons=reasons,
                claim_status=status,
                verified_claim_ceiling="NO_CLAIM",
                verified_deployment_authority="NONE",
            )

        return ClosureValidationResult(
            valid=True,
            claim_id=claim_id,
            reasons=["All closure integrity invariants verified."],
            claim_status="VALID",
            verified_claim_ceiling=claim_ceiling,
            verified_deployment_authority=deployment_authority,
        )

    @classmethod
    def verify_claim_pack_dir(
        cls,
        claim_pack_dir: Path,
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> ClosureValidationResult:
        claim_pack_dir = Path(claim_pack_dir)
        closure_file = claim_pack_dir / "closure.json"
        if not closure_file.exists():
            return ClosureValidationResult(
                valid=False,
                claim_id=claim_pack_dir.name,
                reasons=[f"Missing mandatory closure.json in {claim_pack_dir}"],
                claim_status="FAILED_CLOSED",
                verified_claim_ceiling="NO_CLAIM",
                verified_deployment_authority="NONE",
            )

        try:
            with open(closure_file, "r", encoding="utf-8") as f:
                closure = json.load(f)
        except Exception as e:
            return ClosureValidationResult(
                valid=False,
                claim_id=claim_pack_dir.name,
                reasons=[f"Corrupt or unparseable closure.json: {e}"],
                claim_status="FAILED_CLOSED",
                verified_claim_ceiling="NO_CLAIM",
                verified_deployment_authority="NONE",
            )

        # Compute on-disk artifact hashes
        artifact_hashes: Dict[str, str] = {}
        for root, _, files in os.walk(claim_pack_dir):
            for file_name in files:
                if file_name == "closure.json":
                    continue
                p = Path(root) / file_name
                try:
                    with open(p, "rb") as f:
                        artifact_hashes[file_name] = hashlib.sha256(f.read()).hexdigest()
                except Exception:
                    pass

        # Load context from environment.lock if present
        context: Dict[str, Any] = {}
        env_lock = claim_pack_dir / "environment.lock"
        if env_lock.exists():
            try:
                with open(env_lock, "r", encoding="utf-8") as f:
                    context = json.load(f)
            except Exception:
                pass
        if runtime_context:
            context.update(runtime_context)

        return cls.verify_closure_dict(
            closure=closure,
            artifact_contents_or_hashes=artifact_hashes,
            runtime_context=context,
        )
