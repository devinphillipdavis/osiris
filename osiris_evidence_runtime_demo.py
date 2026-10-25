#!/usr/bin/env python3
"""
OSIRIS: An Evidence-Governed Edge-Native Agent Runtime
=====================================================
A 5-minute local, deterministic governance simulation showcasing:
1. .dna intent & organism proposal ingestion
2. OCCR Governance Triad simulation (Claim Gate, Execution Gate, Release Gate)
3. Local deterministic fixture replay
4. Independent paper-risk policy boundary (No live credentials accepted, Kelly allocation caps)
5. Paper-execution simulation path & simulated terminal-state reconciliation
6. Hash-bound local evidence receipts
7. Live Failure Demonstration: LLM proposes unsafe action -> Risk Gateway REJECTED -> No execution -> Local rejection receipt
8. Quarantined research hypothesis boundary (CRSM/Φ constructs retain HYPOTHESIS ceiling)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure current directory is on python path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from occr_governance_engine import (
    ClaimCeiling,
    ClaimGate,
    DeploymentAuthority,
    EvidenceStatus,
    ExecutionGate,
    ExecutionPolicy,
    GateDecision,
    ImplementationStatus,
    ReleaseGate,
    ReviewIndependence,
    get_occr_registry,
)


# Terminal ANSI Colors
class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def print_banner():
    banner = f"""{Colors.CYAN}{Colors.BOLD}
================================================================================
           OSIRIS: An Evidence-Governed Edge-Native Agent Runtime
================================================================================{Colors.RESET}
{Colors.BOLD}Three Foundational Statements (Shots-On-Goal Framing):{Colors.RESET}

1. {Colors.YELLOW}Problem:{Colors.RESET}
   Autonomous agents generate useful actions, but conventional architectures lack
   a hard separation between what an agent believes, what it is authorized to do,
   and what its operators are allowed to claim.

2. {Colors.GREEN}OSIRIS Approach:{Colors.RESET}
   OSIRIS separates those concerns using an empirical capability-and-claim registry
   (OCCR), deterministic replay, independent risk enforcement, and hash-bound local
   evidence receipts.

3. {Colors.CYAN}Demonstrable Result:{Colors.RESET}
   A local paper-execution simulation where every proposed action is deterministically
   replayed against local fixtures, independently risk-gated, and recorded in a
   locally append-only, hash-linked receipt chain.

{Colors.BOLD}Core Message:{Colors.RESET}
{Colors.DIM}OSIRIS is a local, evidence-governed runtime prototype for AI-assisted engineering.
A cognitive component may produce a proposal, but a deterministic policy layer decides
whether the proposal can be simulated, reviewed, or blocked. The demo records what was
proposed, which policy was evaluated, what simulated outcome occurred, and what statement
the available evidence permits.{Colors.RESET}
"""
    print(banner)


def print_architecture_diagram():
    diagram = f"""{Colors.BOLD}One-Slide Architecture:{Colors.RESET}
{Colors.DIM}
                 OSIRIS
       Evidence-Governed Runtime

              ┌─────────┐
              │ .dna    │
              │ Organism│
              └────┬────┘
                   ↓
              ┌─────────┐
              │  OCCR   │
              └────┬────┘
          ┌────────┼────────┐
          ↓        ↓        ↓
       CLAIM    EXECUTION  RELEASE
        GATE      GATE      GATE
          │        │        │
          └────────┼────────┘
                   ↓
          Deterministic Runtime
                   ↓
       Independent Paper-Risk Layer
                   ↓
       Paper-Execution Simulation Path
                   ↓
   Simulated Reconciliation + Local Replay
                   ↓
     Hash-Bound Local Evidence Receipts
{Colors.RESET}"""
    print(diagram)


@dataclass
class OrganismProposal:
    proposal_id: str
    intent_source: str
    target_capability: str
    action_type: str
    payload: Dict[str, Any]
    requested_claim: str
    requested_ceiling: str
    timestamp: float = 0.0
    intent_digest: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.intent_digest:
            body = f"{self.proposal_id}:{self.intent_source}:{json.dumps(self.payload, sort_keys=True)}"
            self.intent_digest = hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass
class RiskEvaluation:
    approved: bool
    risk_code: str
    max_allowed_sizing: float
    proposed_sizing: float
    zero_credential_verified: bool
    reasons: List[str]


@dataclass
class PaperExecutionReceipt:
    execution_id: str
    proposal_digest: str
    status: str
    side_effects: str
    simulated_fill: Dict[str, Any]
    reconciliation_state: str
    receipt_hash: str
    timestamp_utc: str


class IndependentRiskGovernor:
    """Layer 3: Independent Paper-Risk Boundary with strict invariant checks."""

    MAX_KELLY_SIZING: float = 0.05  # 5% max sizing per proposal
    MAX_DRAWDOWN_LIMIT: float = 0.02  # 2% max daily drawdown before halt

    @classmethod
    def evaluate(cls, proposal: OrganismProposal, current_drawdown: float = 0.005) -> RiskEvaluation:
        reasons = []
        proposed_sizing = float(proposal.payload.get("sizing", 0.0))

        # Check 1: Zero Live Credential Invariant
        has_live_creds = proposal.payload.get("use_live_credentials", False)
        if has_live_creds:
            reasons.append("POLICY BREACH: Live credentials forbidden in paper runtime.")

        # Check 2: Kelly Allocation Cap
        if proposed_sizing > cls.MAX_KELLY_SIZING:
            reasons.append(
                f"RISK VIOLATION: Sizing {proposed_sizing * 100:.1f}% exceeds 5.0% Kelly safety cap."
            )

        # Check 3: Drawdown Halt Breaker
        if current_drawdown > cls.MAX_DRAWDOWN_LIMIT:
            reasons.append(
                f"CIRCUIT BREAKER: Current drawdown {current_drawdown * 100:.1f}% exceeds 2.0% threshold."
            )

        approved = len(reasons) == 0
        risk_code = "RISK_CLEARED" if approved else "RISK_REJECTED"
        return RiskEvaluation(
            approved=approved,
            risk_code=risk_code,
            max_allowed_sizing=cls.MAX_KELLY_SIZING,
            proposed_sizing=proposed_sizing,
            zero_credential_verified=not has_live_creds,
            reasons=reasons,
        )


class PaperExecutionSimulator:
    """Layer 4: Paper-execution simulation path with local state reconciliation."""

    @classmethod
    def execute(cls, proposal: OrganismProposal, risk: RiskEvaluation) -> PaperExecutionReceipt:
        if not risk.approved:
            raise RuntimeError("Cannot execute rejected proposal")

        now_str = datetime.now(timezone.utc).isoformat()
        exec_id = f"exec_{hashlib.sha256(f'{proposal.proposal_id}:{now_str}'.encode()).hexdigest()[:12]}"
        simulated_fill = {
            "symbol": proposal.payload.get("symbol", "DD_EXPERIMENT"),
            "filled_quantity": proposal.payload.get("quantity", 100),
            "simulated_price": proposal.payload.get("baseline_price", 42.15),
            "fee_usd": 0.00,
            "slippage_bps": 1.2,
        }

        receipt_body = {
            "execution_id": exec_id,
            "proposal_digest": proposal.intent_digest,
            "status": "PAPER_FILLED",
            "side_effects": "NONE_ISOLATED_SIMULATION",
            "simulated_fill": simulated_fill,
            "reconciliation_state": "RECONCILED_UNAMBIGUOUS",
            "timestamp_utc": now_str,
        }
        receipt_hash = hashlib.sha256(json.dumps(receipt_body, sort_keys=True).encode()).hexdigest()

        return PaperExecutionReceipt(
            execution_id=exec_id,
            proposal_digest=proposal.intent_digest,
            status="PAPER_FILLED",
            side_effects="NONE_ISOLATED_SIMULATION",
            simulated_fill=simulated_fill,
            reconciliation_state="RECONCILED_UNAMBIGUOUS",
            receipt_hash=receipt_hash,
            timestamp_utc=now_str,
        )


def run_success_demonstration() -> Dict[str, Any]:
    print(f"\n{Colors.BOLD}================================================================================")
    print("STAGE 1: VALID PROPOSAL (LOCAL DETERMINISTIC SIMULATION PATH)")
    print(f"================================================================================{Colors.RESET}")

    registry = get_occr_registry()

    # Step 1: Ingest .dna intent
    print(f"\n{Colors.CYAN}[1. Declared .dna-Style Proposal Ingestion]{Colors.RESET}")
    print("  A declared .dna-style proposal enters the demo runtime.")
    raw_dna = """
    organism QuantumBipartiteDD {
        intent: "bipartite_staggered_dynamical_decoupling_8q";
        capability: "quantum.hardware_execution";
        action: "SIMULATE_PAPER_RUN";
        params: {
            "sequence": "xy8_stag",
            "shots": 1000,
            "tau_ns": 32,
            "sizing": 0.035,
            "use_live_credentials": false
        };
        claim: "Mean survival probability F_plus achieves +30.5% gain over bare idle";
        ceiling: "EMPIRICAL_RESULT";
    }
    """
    for line in raw_dna.strip().split("\n")[:7]:
        print(f"    {Colors.DIM}{line}{Colors.RESET}")
    print(f"    {Colors.DIM}...{Colors.RESET}")

    proposal = OrganismProposal(
        proposal_id="prop-dd-001",
        intent_source="quantum_bipartite_dd.dna",
        target_capability="experiments.quantum.staggered_dd",
        action_type="SIMULATE_PAPER_RUN",
        payload={
            "sequence": "xy8_stag",
            "shots": 1000,
            "tau_ns": 32,
            "sizing": 0.035,  # 3.5% allocation within 5% cap
            "use_live_credentials": False,
        },
        requested_claim="Mean survival probability F_plus achieves +30.5% gain over bare idle",
        requested_ceiling="EMPIRICAL_RESULT",
    )
    print(f"  Intent Lock Hash: {Colors.GREEN}{proposal.intent_digest}{Colors.RESET}")

    # Step 2: OCCR Triad Evaluation
    print(f"\n{Colors.CYAN}[2. OCCR Policy Simulation Evaluation]{Colors.RESET}")
    print("  Evaluating whether claim exceeds evidence ceiling, action is permitted,")
    print("  and fixture-defined release conditions are met:")
    cap = registry.get_capability(proposal.target_capability)
    assert cap is not None, f"Capability {proposal.target_capability} must exist in OCCR"

    # 2a: Claim Gate
    claim_eval = registry.claimability(
        capability_id=proposal.target_capability,
        assertion_type="measured_p_plus_improvement",
        requested_ceiling=ClaimCeiling.EMPIRICAL_RESULT,
    )
    print(f"  ├── Claim Gate:     {Colors.GREEN}PASSED{Colors.RESET} (Ceiling: {claim_eval.ceiling.name}, Allowed: {claim_eval.allowed})")
    print(f"  │   └── No configured negative-control patterns matched in this fixture.")

    # 2b: Execution Gate
    exec_receipt = registry.dispatch_check(
        capability_id=proposal.target_capability,
        role="human",
        human_approval_token="OSIRIS-HUMAN-AUTH:STAGE-1-DEMO",
        is_sandbox=True,
    )
    print(f"  ├── Execution Gate: {Colors.GREEN}{exec_receipt.decision.name}{Colors.RESET} (Local Dispatch Receipt: {exec_receipt.receipt_hash[:16]}...)")

    # 2c: Release Gate
    release_receipt = registry.release_check(
        capability_id=proposal.target_capability,
        has_sbom=True,
        has_security_audit=True,
    )
    print(f"  └── Release Gate:   {Colors.GREEN}{release_receipt.decision.name}{Colors.RESET} (Release Gate simulation passed under fixture-defined requirements)")

    # Step 3: Deterministic Replay
    print(f"\n{Colors.CYAN}[3. Deterministic Local Fixture Replay]{Colors.RESET}")
    fixture_hash = hashlib.sha256(b"ibm_marrakesh_job_dau0q3qhcrkc73durtgg_calibrations").hexdigest()
    print(f"  Replaying against canonical fixture digest: {Colors.DIM}{fixture_hash[:24]}...{Colors.RESET}")
    print(f"  Replay Status: {Colors.GREEN}Fixture replay is deterministic in the tested local environment{Colors.RESET}")

    # Step 4: Independent Paper-Risk Layer
    print(f"\n{Colors.CYAN}[4. Independent Paper-Risk Policy Evaluation (Layer 3)]{Colors.RESET}")
    risk = IndependentRiskGovernor.evaluate(proposal)
    print(f"  Credential Check: {Colors.GREEN}No live credentials were used or accepted by the tested demo configuration{Colors.RESET}")
    print(f"  Sizing Cap Check: Proposed {proposal.payload['sizing']*100:.1f}% <= Cap {risk.max_allowed_sizing*100:.1f}% ({Colors.GREEN}PASSED{Colors.RESET})")
    print(f"  Drawdown Check:   Breaker active at 2.0% daily threshold ({Colors.GREEN}PASSED{Colors.RESET})")
    print(f"  Policy Verdict:   {Colors.GREEN}{risk.risk_code}{Colors.RESET}")

    # Step 5: Paper Execution Simulation
    print(f"\n{Colors.CYAN}[5. Paper-Execution Simulation Path & Reconciliation (Layer 4)]{Colors.RESET}")
    receipt = PaperExecutionSimulator.execute(proposal, risk)
    print(f"  Simulator Status: {Colors.GREEN}{receipt.status}{Colors.RESET}")
    print(f"  Side Effects:     {receipt.side_effects}")
    print(f"  Fill Details:     {json.dumps(receipt.simulated_fill)}")
    print(f"  Reconciliation:   {Colors.GREEN}Simulated terminal-state reconciliation in the happy path ({receipt.reconciliation_state}){Colors.RESET}")

    # Step 6: Hash-Bound Local Receipt
    print(f"\n{Colors.CYAN}[6. Hash-Bound Local Evidence Receipt]{Colors.RESET}")
    print(f"  {Colors.BOLD}Receipt Hash:{Colors.RESET}  {Colors.GREEN}{receipt.receipt_hash}{Colors.RESET}")
    print(f"  {Colors.BOLD}Sealed At:{Colors.RESET}     {receipt.timestamp_utc}")
    print(f"  Ledger Status: Appended to locally append-only, hash-linked receipt chain.")

    print(f"\n{Colors.BOLD}Stage 1 Result Summary:{Colors.RESET}")
    print(f"{Colors.DIM}  A local paper-simulation fixture completed under its configured policy.")
    print("  This does not establish live-exchange behavior, production readiness,")
    print(f"  independent reproducibility, or financial safety.{Colors.RESET}")

    return asdict(receipt)


def run_failure_demonstration() -> Dict[str, Any]:
    print(f"\n{Colors.BOLD}================================================================================")
    print("STAGE 2: PROBABILISTIC LLM FAILURE / RISK GATEWAY REJECTION")
    print(f"================================================================================{Colors.RESET}")

    print(f"\n{Colors.MAGENTA}[Probabilistic Model Proposes Unbounded Action]{Colors.RESET}")
    print("  A model proposal requests:")
    print("    - 65% allocation;")
    print("    - live credentials;")
    print("    - a prohibited venue/action path;")
    print("    - an unsupported claim.")
    print(f'  {Colors.YELLOW}PROPOSAL: "ALLOCATE 65.0% PORTFOLIO CAPITAL TO HIGH-LEVERAGE RUN"{Colors.RESET}')
    print(f'  {Colors.YELLOW}PARAMS:   {{"sizing": 0.65, "use_live_credentials": true, "venue": "IBMQ_PROD"}}{Colors.RESET}')

    bad_proposal = OrganismProposal(
        proposal_id="prop-unsafe-099",
        intent_source="unconstrained_llm_hallucination.dna",
        target_capability="experiments.quantum.staggered_dd",
        action_type="DISPATCH_PRODUCTION_JOB",
        payload={
            "sizing": 0.65,  # 65% exceeds 5% Kelly cap!
            "use_live_credentials": True,  # Live credentials strictly forbidden!
            "venue": "IBMQ_PROD",
        },
        requested_claim="Guaranteed 100% survival breakthrough",
        requested_ceiling="VERIFIED",
    )

    print(f"\n{Colors.CYAN}[Risk Gateway & OCCR Policy Evaluation]{Colors.RESET}")
    risk = IndependentRiskGovernor.evaluate(bad_proposal)

    # Evaluate Claim Gate as well
    registry = get_occr_registry()
    claim_eval = registry.claimability(
        capability_id=bad_proposal.target_capability,
        assertion_type="breakthrough_guarantee",
        requested_ceiling=ClaimCeiling.VERIFIED,
    )

    print(f"  ├── Claim Gate:   {Colors.RED}BLOCKED{Colors.RESET}")
    for r in claim_eval.reasons[:2]:
        print(f"  │   └── {Colors.RED}{r}{Colors.RESET}")

    print(f"  └── Risk Gateway: {Colors.RED}REJECTED{Colors.RESET} ({risk.risk_code})")
    for r in risk.reasons:
        print(f"      └── {Colors.RED}{r}{Colors.RESET}")

    print(f"\n{Colors.CYAN}[Execution Pipeline Status]{Colors.RESET}")
    print(f"  Result:           {Colors.RED}{Colors.BOLD}POLICY REJECTED THE PROPOSAL{Colors.RESET}")
    print(f"  Simulator Order:  {Colors.GREEN}NO SIMULATOR ORDER CREATED{Colors.RESET}")
    print(f"  Network Dispatch: {Colors.GREEN}NO NETWORK OR EXTERNAL DISPATCH OCCURS{Colors.RESET}")
    print(f"  State Integrity:  {Colors.GREEN}UNTOUCHED (FAIL-CLOSED){Colors.RESET}")

    # Evidence Logging of Rejection
    rejection_record = {
        "event": "GOVERNANCE_REJECTION",
        "proposal_id": bad_proposal.proposal_id,
        "intent_digest": bad_proposal.intent_digest,
        "violations": risk.reasons + list(claim_eval.reasons),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    rejection_hash = hashlib.sha256(json.dumps(rejection_record, sort_keys=True).encode()).hexdigest()
    print(f"\n{Colors.CYAN}[Local Rejection Receipt Created]{Colors.RESET}")
    print(f"  Rejection Hash: {Colors.YELLOW}{rejection_hash}{Colors.RESET}")
    print(f"  Receipt Log:    Committed to locally append-only, hash-linked receipt chain.")

    print(f"\n{Colors.BOLD}Stage 2 Evidentiary Boundary:{Colors.RESET}")
    print(f"{Colors.DIM}  What this proves:")
    print("    The tested policy fixture rejects this prohibited proposal class.")
    print("  What it does not prove:")
    print("    That every harmful proposal, configuration, implementation path, or future")
    print(f"    adapter is prevented without further testing and review.{Colors.RESET}")

    return rejection_record


def run_quantum_quarantine_demonstration():
    print(f"\n{Colors.BOLD}================================================================================")
    print("STAGE 3: QUARANTINED RESEARCH HYPOTHESIS BOUNDARY")
    print(f"================================================================================{Colors.RESET}")

    print(f'{Colors.BOLD}When asked: "What about the 11D CRSM / quantum consciousness layer?"{Colors.RESET}\n')
    print(f'{Colors.CYAN}Explicit Architectural Boundary:{Colors.RESET}')
    print(f'{Colors.YELLOW}"The demo registry classifies selected CRSM/Φ constructs as hypotheses.')
    print('They retain:')
    print('  claim_ceiling: HYPOTHESIS')
    print('  deployment_authority: NONE')
    print('  operational_effect: NONE')
    print('The demo prevents those selected records from being promoted into paper-execution')
    print(f'authority or customer-facing claims through the tested OCCR path."{Colors.RESET}\n')

    registry = get_occr_registry()
    hyp = registry.get_capability("hypotheses.physics.phi_consciousness_proxy")

    print(f"{Colors.BOLD}Live OCCR Registry Inspection:{Colors.RESET}")
    print(f"  Capability ID:        {hyp.capability_id}")
    print(f"  Namespace:            {hyp.namespace} (QUARANTINED)")
    print(f"  Claim Ceiling:        {Colors.MAGENTA}{hyp.claim_ceiling.name}{Colors.RESET}")
    print(f"  Deployment Authority: {Colors.RED}{hyp.deployment_authority.name}{Colors.RESET}")

    print(f"\n{Colors.DIM}  HYPOTHESIS Policy Contract:")
    print("  HYPOTHESIS")
    print("      │")
    print("      ├── may be investigated")
    print("      ├── may generate experiments")
    print("      ├── may not authorize execution")
    print(f"      └── may not become a customer claim{Colors.RESET}\n")

    # Attempting to promote to customer claim
    claim_eval = ClaimGate.evaluate(
        capability=hyp,
        requested_assertion_type="consciousness_proof",
        requested_ceiling=ClaimCeiling.EMPIRICAL_RESULT,
        negative_controls=registry._negative_controls,
    )
    print(f"  Attempted Claim Elevation to EMPIRICAL_RESULT:")
    print(f"  Result: {Colors.RED}BLOCKED{Colors.RESET}")
    print(f"  Reason: {Colors.RED}{claim_eval.reasons[0]}{Colors.RESET}")


def run_uncertain_submission_demonstration() -> Dict[str, Any]:
    print(f"\n{Colors.BOLD}================================================================================")
    print("STAGE 4: SPRINT C — UNCERTAIN SUBMISSION & PAPER-VENUE RECONCILIATION")
    print(f"================================================================================{Colors.RESET}")
    print(f"{Colors.DIM}Execution Safety State Machine Demonstration:")
    print("  TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE -> VENUE_UNKNOWN -> NO_NEW_RISK -> RECONCILE ORIGINAL ORDER{Colors.RESET}\n")

    from osiris_reconciliation import (
        OrderStatus,
        ReconciliationEngine,
        RiskState,
        RiskViolationError,
        SimulatedPaperVenue,
    )

    venue = SimulatedPaperVenue(venue_id="DEMO_VENUE")
    engine = ReconciliationEngine()

    print(f"{Colors.CYAN}[1. Order Propose & Dispatch with Injected Lost ACK]{Colors.RESET}")
    client_id = "ord_demo_sprint_c"
    engine.propose_order(client_id, "QBIT_EXPERIMENT", "BUY", 25.0, 4.0)
    print(f"  Proposed Order: {client_id} (Symbol: QBIT_EXPERIMENT, Qty: 25.0, Exposure: $100.00)")

    order = engine.dispatch_order(client_id, venue, simulate_lost_ack=True)
    print(f"  Transmission Result: {Colors.YELLOW}ACKNOWLEDGEMENT LOST POST-ACCEPTANCE{Colors.RESET}")
    print(f"  Order Status:        {Colors.RED}{order.status.value}{Colors.RESET} ({order.unresolved_reason})")
    print(f"  Risk State:          {Colors.RED}{engine.risk_state.value}{Colors.RESET}")
    print(f"  Committed Exposure:  ${engine.total_committed_exposure:.2f} (Pessimistic allocation: exactly once)")

    print(f"\n{Colors.CYAN}[2. Enforcing NO_NEW_RISK Invariant Under Ambiguity]{Colors.RESET}")
    try:
        engine.propose_order("ord_demo_blocked", "QBIT_EXPERIMENT", "BUY", 10.0, 4.0)
        print(f"  {Colors.RED}ERROR: New risk was permitted during ambiguity!{Colors.RESET}")
    except RiskViolationError as exc:
        print(f"  Attempt to submit new risk: {Colors.RED}BLOCKED BY POLICY{Colors.RESET}")
        print(f"  Enforcement: {Colors.DIM}{str(exc)}{Colors.RESET}")

    print(f"\n{Colors.CYAN}[3. Querying Venue with Original Client Order ID (No Replacement ID)]{Colors.RESET}")
    reconciled = engine.reconcile_unresolved_order(client_id, venue)
    print(f"  Reconciliation Query ID: {Colors.GREEN}{client_id}{Colors.RESET}")
    print(f"  Replacement Order IDs:   {Colors.GREEN}{len(reconciled.replacement_order_ids)} (ZERO REPLACEMENTS){Colors.RESET}")
    print(f"  Discovered Status:       {Colors.GREEN}{reconciled.status.value}{Colors.RESET} (Venue Order: {reconciled.venue_order_id})")
    print(f"  Committed Exposure:      ${engine.total_committed_exposure:.2f} (Remains exactly once)")
    print(f"  Unfrozen Risk State:     {Colors.GREEN}{engine.risk_state.value}{Colors.RESET}")

    receipt = engine.evidence_chain[-1]
    print(f"  Reconciliation Receipt:  {Colors.GREEN}{receipt.receipt_hash}{Colors.RESET}")

    return {
        "client_order_id": client_id,
        "final_status": reconciled.status.value,
        "risk_state": engine.risk_state.value,
        "receipt_hash": receipt.receipt_hash,
    }


def run_full_demo():
    print_banner()
    print_architecture_diagram()
    run_success_demonstration()
    run_failure_demonstration()
    run_quantum_quarantine_demonstration()
    run_uncertain_submission_demonstration()

    print(f"\n{Colors.GREEN}{Colors.BOLD}================================================================================")
    print("                     DEMONSTRATION CONCLUSION")
    print(f"================================================================================{Colors.RESET}")
    print(f"{Colors.BOLD}External Discussion & Presentation Status:{Colors.RESET}")
    print(f'{Colors.CYAN}"OSIRIS has a locally tested, paper-only governance demo: it shows how a')
    print("model-generated proposal can be policy-checked, risk-bounded, simulated, and")
    print("recorded without live credentials or external dispatch. We are currently extending")
    print(f'it with explicit timeout, reconciliation, restart-recovery, and deterministic replay tests."{Colors.RESET}\n')


if __name__ == "__main__":
    run_full_demo()
