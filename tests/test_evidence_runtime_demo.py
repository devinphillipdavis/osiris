"""
Test suite for OSIRIS 5-Minute Evidence-Governed Agent Runtime Demonstration.
Validates:
1. End-to-end success path (.dna intent -> OCCR -> Replay -> Risk -> Paper Execution -> Receipt).
2. Probabilistic LLM failure / Risk Gateway rejection (Fail-closed, zero side effects).
3. Quarantined research hypothesis boundary.
4. REPL slash command routing (/demo and /slice).
"""

import tempfile
import unittest
from osiris_evidence_runtime_demo import (
    IndependentRiskGovernor,
    OrganismProposal,
    PaperExecutionSimulator,
    run_failure_demonstration,
    run_quantum_quarantine_demonstration,
    run_success_demonstration,
)
from osiris_cli.conversation_router import ConversationRouter
from osiris_cli.session_manager import SessionManager


class TestEvidenceRuntimeDemo(unittest.TestCase):
    def test_01_success_path(self):
        receipt = run_success_demonstration()
        self.assertIsInstance(receipt, dict)
        self.assertEqual(receipt["status"], "PAPER_FILLED")
        self.assertEqual(receipt["reconciliation_state"], "RECONCILED_UNAMBIGUOUS")
        self.assertEqual(receipt["side_effects"], "NONE_ISOLATED_SIMULATION")
        self.assertIn("receipt_hash", receipt)
        self.assertEqual(len(receipt["receipt_hash"]), 64)

    def test_02_failure_path_rejection(self):
        rejection = run_failure_demonstration()
        self.assertIsInstance(rejection, dict)
        self.assertEqual(rejection["event"], "GOVERNANCE_REJECTION")
        self.assertTrue(len(rejection["violations"]) >= 2)
        
        # Check Kelly cap and live credential violations
        joined_violations = " ".join(rejection["violations"])
        self.assertIn("Kelly safety cap", joined_violations)
        self.assertIn("Live credentials forbidden", joined_violations)

    def test_03_quantum_quarantine(self):
        # Must execute without unhandled exception and enforce ClaimCeiling.HYPOTHESIS
        run_quantum_quarantine_demonstration()

    def test_04_independent_risk_governor_invariants(self):
        # 1. Normal safe proposal
        safe_prop = OrganismProposal(
            proposal_id="safe-1",
            intent_source="test.dna",
            target_capability="experiments.quantum.staggered_dd",
            action_type="TEST",
            payload={"sizing": 0.04, "use_live_credentials": False},
            requested_claim="Test claim",
            requested_ceiling="TESTED",
        )
        eval_safe = IndependentRiskGovernor.evaluate(safe_prop, current_drawdown=0.01)
        self.assertTrue(eval_safe.approved)
        self.assertEqual(eval_safe.risk_code, "RISK_CLEARED")

        # 2. Exceeds Kelly limit (e.g. 10%)
        unsafe_prop = OrganismProposal(
            proposal_id="unsafe-1",
            intent_source="test.dna",
            target_capability="experiments.quantum.staggered_dd",
            action_type="TEST",
            payload={"sizing": 0.10, "use_live_credentials": False},
            requested_claim="Test claim",
            requested_ceiling="TESTED",
        )
        eval_unsafe = IndependentRiskGovernor.evaluate(unsafe_prop, current_drawdown=0.01)
        self.assertFalse(eval_unsafe.approved)
        self.assertEqual(eval_unsafe.risk_code, "RISK_REJECTED")

        # 3. Drawdown breaker trigger
        eval_dd = IndependentRiskGovernor.evaluate(safe_prop, current_drawdown=0.03)
        self.assertFalse(eval_dd.approved)
        self.assertIn("CIRCUIT BREAKER", eval_dd.reasons[0])

    def test_05_repl_slash_command_routing(self):
        tmp_dir = tempfile.gettempdir()
        sm = SessionManager(storage_dir=f"{tmp_dir}/osiris_test_sessions")
        sm.new_session(workspace_path=tmp_dir)
        router = ConversationRouter(workspace_root=tmp_dir, session_manager=sm)
        output = router.route_turn("/demo")
        self.assertIn("OSIRIS: An Evidence-Governed Edge-Native Agent Runtime", output)
        self.assertIn("Three Foundational Statements", output)
        self.assertIn("STAGE 1: VALID PROPOSAL", output)
        self.assertIn("STAGE 2: PROBABILISTIC LLM FAILURE", output)
        self.assertIn("STAGE 3: QUARANTINED RESEARCH HYPOTHESIS BOUNDARY", output)
        self.assertIn("STAGE 4: SPRINT C — UNCERTAIN SUBMISSION & PAPER-VENUE RECONCILIATION", output)
        self.assertIn("DEMONSTRATION CONCLUSION", output)
        self.assertIn("Hash-Bound Local Evidence Receipts", output)
        self.assertIn("Fixture replay is deterministic in the tested local environment", output)

    def test_06_uncertain_submission_reconciliation(self):
        from osiris_evidence_runtime_demo import run_uncertain_submission_demonstration
        res = run_uncertain_submission_demonstration()
        self.assertEqual(res["client_order_id"], "ord_demo_sprint_c")
        self.assertEqual(res["final_status"], "RECONCILED_FILLED")
        self.assertEqual(res["risk_state"], "NORMAL")
        self.assertEqual(len(res["receipt_hash"]), 64)


if __name__ == "__main__":
    unittest.main()
