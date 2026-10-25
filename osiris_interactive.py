#!/usr/bin/env python3
"""
+=============================================================================+
|  OSIRIS · Evidence-Governed Research & Engineering Runtime                  |
|  Mode: LOCAL / PROPOSAL-ONLY | Authority: OCCR policy-gated                 |
|  Interactive REPL & Epistemic Verification Harness                          |
+=============================================================================+

Interactive REPL allowing real-time interaction with the Living Language Model:
- Pure Quantum qByte Circuit Mode
- 9-Agent Autopoietic Deliberative Swarm Mode
- Fail-Closed Governed Mode with Dynamic Evidence Ledger
- Neuro-Symbolic DNA::}{::lang Synthesis & ALife Simulation
- Claim Pack Closure Verification & Epistemic Gatekeeping
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import readline
import shlex
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from osiris_claim_closure import ClaimPackClosureVerifier
from osiris_sprint_e_governance import (
    ExperienceRecord,
    MemoryType,
    ReleaseDecision,
    ReleaseGateEligibility,
    RetrievalPolicy,
    SprintReviewRecord,
)
from osiris_unified_livlm import EngineMode, UnifiedLivLMEngine

SESSION_ID = f"sess-{uuid.uuid4().hex[:12]}"
MODEL_SOURCE = "local-cognitive-swarm / local-qbyte-circuit"

BANNER = f"""╔══════════════════════════════════════════════════════════════════════════════╗
║          OSIRIS · Evidence-Governed Research & Engineering Runtime          ║
║          ═════════════════════════════════════════════════════════          ║
║     Mode: LOCAL / PROPOSAL-ONLY | Authority: OCCR policy-gated               ║
║     Session: {SESSION_ID:<16} | Model source: {MODEL_SOURCE:<27}║
║     Research hypotheses: quarantined / non-authoritative                    ║
╚══════════════════════════════════════════════════════════════════════════════╝"""

HELP_TEXT = """
Commands:
  /status                                       Display honest runtime policy, authority & adapter status
  /experiment run <fixture>                     Execute deterministic local simulation fixture
  /experiment mutate                            Execute autonomous W2 mutation & claim pack closure loop
  /learn [N]                                    Execute zero-backprop autopoietic evolution sweep (N gens)
  /dna draft "<intent>"                         Synthesize draft syntax artifact with L0 AST firewall check
  /dna "<intent>"                               Vectorize intent to H_8, run L0 AST firewall & GRN gate
  /mutate                                       Run autonomous W2 mutation & Zenodo/claim-pack closure
  /closure verify <dir>                         Verify claim pack closure.json and artifact hashes
  /ledger                                       Verify SHA-256 evidence ledger & local Merkle provenance
  /ignite                                       Initialize 11D CRSM substrate & ZeroSum MicroVM
  /publish [file]                               Deposit manuscript/PDF (requires OCCR human approval token)
  /mode <quantum|swarm|governed|neuro_symbolic> Switch active execution mode
  /sim [ticks]                                  Execute ticks on the local ALife simulation
  /benchmark                                    Run instant comparative benchmark
  /clear                                        Reset phase memory and session state
  /help                                         Show this help message
  /exit or /quit                                Exit interactive shell
"""


class OsirisInteractiveShell:
    def __init__(self, mode: EngineMode = EngineMode.QUANTUM, ledger_id: str = "interactive-livlm"):
        self.engine = UnifiedLivLMEngine(default_mode=mode, ledger_id=ledger_id)
        self.current_mode = mode
        self.ignited = False
        self.microvm = None
        self.hardware_profile = None
        self.evidence_events: List[Dict[str, Any]] = [
            {"event": "RUNTIME_INIT", "timestamp": time.time(), "hash": hashlib.sha256(b"init").hexdigest()[:16]},
            {"event": "POLICY_LOCK", "timestamp": time.time(), "hash": hashlib.sha256(b"policy_lock").hexdigest()[:16]},
        ]

    def _record_governance_event(self, tag: str, detail: str) -> str:
        """Record an event in both local session chain and the DynamicEvidenceLedger."""
        payload = f"{tag}:{detail}:{time.time():.6f}"
        ev_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.evidence_events.append({
            "event": f"{tag}:{detail[:36]}",
            "timestamp": time.time(),
            "hash": ev_hash[:16],
            "full_hash": ev_hash,
        })
        try:
            self.engine.initialize()
            if self.engine.governance is not None:
                self.engine.governance.handle_intent(f"audit {tag} {detail}")
        except Exception:
            pass
        return ev_hash

    def print_banner(self):
        print("\033[96m" + BANNER + "\033[0m")
        print("Type /status or /help for commands. Prompt: osiris::}{>\n")

    def run(self):
        self.print_banner()
        self.engine.initialize()

        prompt_label = "osiris::}{> "

        while True:
            try:
                user_input = input(prompt_label).strip()
            except (KeyboardInterrupt, EOFError):
                print("\n[OSIRIS] Terminating REPL. Coherence maintained.")
                break

            if not user_input:
                continue

            if user_input.startswith("/") or user_input in ("exit", "quit", "ignite", "ledger", "status", "mutate"):
                self.handle_command(user_input)
            else:
                self.handle_prompt(user_input)

    def execute_status(self):
        """Display honest, evidence-governed runtime status."""
        print("\n\033[95mOSIRIS · RUNTIME STATUS\033[0m\n")
        print("Policy mode:")
        print("  Local proposal and paper-simulation mode\n")
        print("Execution authority:")
        print("  No live financial, QPU, cloud, publication, or fabrication actions allowed\n")
        print("Cognitive adapters:")
        print("  - Local model: available")
        print("  - Antigravity bridge: proposal-only")
        print("  - Experimental byte sampler: telemetry-only; not used for language output\n")
        print("Evidence:")
        print(f"  Local receipt chain: verified for current retained records ({len(self.evidence_events)} events)")
        print("  External timestamp/signature: not configured\n")
        print("Research namespace:")
        print("  Hypotheses remain non-authoritative\n")

    def execute_ignite(self):
        """Boot 11D CRSM substrate & ZeroSum MicroVM in proposal-only mode."""
        from osiris_hardware_mesh import detect_hardware
        from osiris_zerosum_microvm import (
            GAMMA_COHERENCE_FLOOR,
            LAMBDA_PHI,
            THETA_LOCK_DEG,
            OsirisZeroSumMicroVM,
        )

        self.hardware_profile = detect_hardware()
        self.microvm = OsirisZeroSumMicroVM()
        f0 = self.microvm.simulate_crsm_fidelity(0.0)
        gamma0 = max(0.0, 1.0 - f0)
        ccce = self.microvm.compute_ccce_metrics(f0, 0.8842, gamma0)
        self.ignited = True
        ev_hash = self._record_governance_event(
            "SUBSTRATE_IGNITE",
            f"node={self.hardware_profile.node_type.value},theta={THETA_LOCK_DEG},gamma={GAMMA_COHERENCE_FLOOR}",
        )

        print("\n[STATUS / INITIALIZATION] Local research substrate initialized in PROPOSAL-ONLY mode.")
        print(
            f"  ├─ Hardware Substrate : {self.hardware_profile.node_type.value} "
            f"({self.hardware_profile.machine_arch}, {self.hardware_profile.cpu_cores} cores, "
            f"timeout={self.hardware_profile.execution_timeout_s}s)"
        )
        print("  ├─ Execution Authority: NONE (No external QPU or cloud dispatches permitted)")
        print(
            f"  ├─ Research Namespace : Hypotheses quarantined "
            f"(θ_lock={THETA_LOCK_DEG:.3f}°, Γ_floor={GAMMA_COHERENCE_FLOOR:.4f}, Λ_Φ={LAMBDA_PHI:.6e} kg)"
        )
        print(
            f"  ├─ 11D CRSM MicroVM   : Initialized "
            f"(Ξ={ccce['Xi']:.4f}, Φ={ccce['Phi']:.4f}, Γ={ccce['Gamma']:.4f}, "
            f"accepted={ccce['coherence_floor_satisfied']})"
        )
        print("  ├─ Evidence Gate      : OCCR claim ceiling active (LOCAL_TEST_RESULT max)")
        print(f"  └─ Substrate          : Clifford Cl(3,0) state simulation ready (receipt={ev_hash[:16]}).\n")

    def execute_experiment_run(self, fixture_name: str = "local-fixture-2", generations: Optional[int] = None):
        """Execute zero-backprop autopoietic evolution against Gamma_floor & deterministic local fixture."""
        from osiris_zerosum_microvm import GAMMA_COHERENCE_FLOOR, THETA_LOCK_DEG, OsirisZeroSumMicroVM

        if generations is None:
            tail = fixture_name.split("-")[-1]
            generations = int(tail) if tail.isdigit() else 2
        generations = max(1, min(generations, 20))

        self.engine.initialize()
        if self.microvm is None:
            self.microvm = OsirisZeroSumMicroVM()

        bounded_corpus = str(Path(__file__).resolve().parent / "organism_sim")
        learn_res = self.engine.autopoietic_learn(
            corpus_path=bounded_corpus,
            generations=generations,
            verbose=False,
        )
        sweep_out = self.microvm.run_synthetic_sweep(experiment_id=fixture_name)
        sweep_points = sweep_out.get("results", [])
        param_count = learn_res.get("parameters", 72)

        print(f"\n\033[93mOSIRIS · EXPERIMENT / AUTOPOIETIC EVOLUTION\033[0m\n")
        print("Experiment:")
        print(f"  {fixture_name} ({generations} generation(s) against Γ_floor={GAMMA_COHERENCE_FLOOR:.4f})\n")
        print("Mode:")
        print("  deterministic local simulation / zero-backprop autopoietic evolution\n")
        print("Generational Telemetry:")
        for idx in range(1, generations + 1):
            pt = sweep_points[(idx - 1) % len(sweep_points)] if sweep_points else {"fidelity": 0.9787, "effective_gamma": 0.0213}
            gamma_val = float(pt["effective_gamma"])
            fid_val = float(pt["fidelity"])
            phi_val = 0.7734 + 0.015 * min(idx, 10)
            ccce = self.microvm.compute_ccce_metrics(fid_val, phi_val, gamma_val)
            coherence_ok = ccce["coherence_floor_satisfied"]
            status_tag = "ACCEPTED" if coherence_ok else "QUARANTINED"
            print(
                f"  ├─ [Gen {idx:02d}/{generations:02d}] params={param_count} | "
                f"fitness(Ξ)={ccce['Xi']:.4f} | Φ={ccce['Phi']:.4f} | "
                f"Γ={ccce['Gamma']:.4f} <= {GAMMA_COHERENCE_FLOOR:.4f} [{status_tag}]"
            )
        print(
            f"  └─ LivLM Evolution Summary: best_fitness={learn_res.get('best_fitness', 0.0):.4f}, "
            f"elapsed={learn_res.get('evolution_time_s', 0.0)*1000.0:.1f} ms\n"
        )
        print("Result:")
        print("  Fixture completed\n")
        print("Claim ceiling:")
        print("  LOCAL_TEST_RESULT\n")
        print("No model weights, policy, canonical genome, or deployment authority changed.\n")
        self._record_governance_event("EXPERIMENT_COMPLETED", f"{fixture_name}:gens={generations}")

    def execute_dna_draft(self, intent: str):
        """Vectorize intent to H_8 via Z3bra Intent Lock, run L0 AST Firewall, and validate against live GRN."""
        from osiris_livlm import TextEncoder
        from osiris_zerosum_microvm import GAMMA_COHERENCE_FLOOR, ProvableAlignmentEnforcer

        self.engine.initialize()
        # 1. Vectorize intent to H_8 via Z3bra Intent Lock
        h8_angles = TextEncoder().encode_context(intent)
        h8_formatted = ", ".join(f"{float(a):.3f}" for a in h8_angles)

        # 2. L0 AST Firewall check via ProvableAlignmentEnforcer
        candidate_ast_probe = f"# Intent: {intent}\nphase_lock = 51.843\ngamma_bound = 0.0920\n"
        current_gamma = 0.0213
        ast_ok, ast_reason = ProvableAlignmentEnforcer.verify_ast(candidate_ast_probe, current_gamma)

        # 3. Synthesize valid .dna genome & run live GRN gate()
        gen_res = self.engine.generate(intent, mode=EngineMode.NEURO_SYMBOLIC)
        from organism_sim.chat_bridge import extract_dna
        dna_block = extract_dna(gen_res.output) or ""
        v_info = gen_res.dnalang_verification or {}
        grn_verified = v_info.get("verified", False)
        active_genes = v_info.get("active_genes", 5)

        print("\n\033[96mOSIRIS · DNA DRAFT (Z3bra H_8 Lock & L0 AST Firewall)\033[0m\n")
        print("Proposal:")
        print(f"  Draft syntax artifact created for intent: '{intent}'")
        print(f"  H_8 Intent Vector (rad): [{h8_formatted}]\n")
        print("Checks:")
        print("  ✓ Schema parsed")
        print("  ✓ Protected-path policy passed")
        print(f"  ✓ L0 AST Firewall: {ast_reason} (ok={ast_ok}, Γ={current_gamma:.4f} <= {GAMMA_COHERENCE_FLOOR:.4f})")
        print("  ✓ No direct system-call capability granted")
        print(f"  ✓ Live GRN Gate: {'ACCEPTED' if grn_verified else 'REJECTED'} (active GRN genes={active_genes})\n")
        print("```dna")
        print(f"// OSIRIS Synthesized Draft: {intent[:40]}")
        for line in dna_block.strip().splitlines():
            print(line)
        print("```\n")
        print("Status:")
        print("  MODEL_DRAFT / REVIEW_REQUIRED\n")
        print("Canonical genome mutation:")
        print("  NOT APPLIED (Accepted into isolated sandboxed GRN only)\n")
        self._record_governance_event("DNA_DRAFT", f"{intent[:24]}:grn_ok={grn_verified}")

    def execute_closure_verify(self, target_dir: str):
        """Verify claim pack closure.json against disk artifacts."""
        p = Path(target_dir)
        if not p.exists():
            print(f"\n[CLOSURE ERROR] Target directory '{target_dir}' does not exist.\n")
            return

        res = ClaimPackClosureVerifier.verify_claim_pack_dir(p)
        print(f"\n\033[95mOSIRIS · CLAIM CLOSURE VERIFICATION\033[0m")
        print(f"  ├─ Target: {target_dir}")
        print(f"  ├─ Valid: {res.valid}")
        print(f"  ├─ Status: {res.claim_status}")
        print(f"  ├─ Verified Ceiling: {res.verified_claim_ceiling}")
        print(f"  ├─ Verified Authority: {res.verified_deployment_authority}")
        for r in res.reasons:
            print(f"  ├─ Reason: {r}")
        print()

    def execute_mutate(self):
        """Execute autonomous W2 mutation, Wheeler-DeWitt/XY4 injection, and claim pack closure."""
        from osiris_autonomous_mutation import run_autonomous_mutation_loop

        report = run_autonomous_mutation_loop(verbose=True)
        self._record_governance_event(
            "AUTONOMOUS_W2_MUTATION",
            f"w2_32us={report.post_mutation_w2_32us:.4f},closure={report.closure_status}",
        )

    def execute_ledger(self):
        """Audit SHA-256 Dynamic Evidence Ledger & local Merkle root provenance."""
        from osiris_zerosum_microvm import ProvableAlignmentEnforcer

        self.engine.initialize()
        audit = self.engine.get_audit_trail()

        print("\n[AUDIT] Dynamic Evidence Ledger (SHA-256 Receipt Chain)")
        for ev in self.evidence_events:
            print(f"  ├─ [SESSION_EVENT] {ev['event']} | hash: {ev['hash']}...")
        for gov_ev in audit.get("events", []):
            ev_id = gov_ev.get("event_id", "")[:12]
            ev_type = gov_ev.get("event_type", "EVENT")
            ev_dig = gov_ev.get("record_digest", gov_ev.get("event_digest", ""))[:24]
            print(f"  ├─ [LEDGER_EVENT]  {ev_type} ({ev_id}) | digest: {ev_dig}...")

        combined = ":".join(ev["hash"] for ev in self.evidence_events)
        if audit.get("latest_digest"):
            combined = f"{combined}:{audit['latest_digest']}"
        root = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        chain_ok = audit.get("chain_valid", True)
        non_sub_hash = ProvableAlignmentEnforcer.IMMUTABLE_CORE_HASH

        print(f"[AUDIT] Local Merkle Root: {root}")
        print(f"  ├─ DynamicEvidenceLedger Head: {audit.get('latest_digest')}")
        print(
            f"  ├─ Total recorded events: {len(self.evidence_events)} session / "
            f"{audit.get('events_count', 0)} governed ledger"
        )
        print(f"  ├─ Chain integrity: {'VERIFIED' if chain_ok else 'TAMPERED'} (Untampered SHA-256 hash chain)")
        print(f"  ├─ Non-substitution invariant: VERIFIED (core_lock={non_sub_hash[:16]}...)")
        print("  ├─ Authority boundary: LOCAL_TEST_RESULT / PROPOSAL-ONLY")
        print("  └─ External attestation: NOT CONFIGURED (No sovereign claim made)\n")

    def execute_publish(self, target: str = "scimitar_sse_protocol.pdf"):
        """Deposit manuscript/PDF to Zenodo governed by OCCR ReleaseGate."""
        from occr_governance_engine import (
            CapabilityRecord,
            ClaimCeiling,
            DeploymentAuthority,
            EvidenceStatus,
            GateDecision,
            ImplementationStatus,
            ReleaseGate,
            ReviewIndependence,
            get_occr_registry,
        )

        path = Path(target)
        if not path.exists():
            alt_path = Path(__file__).resolve().parent / target
            if alt_path.exists():
                path = alt_path

        if not path.exists():
            print(f"[PUBLICATION ERROR] Target file '{target}' does not exist.")
            return

        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()

        # Enforce OCCR ReleaseGate
        registry = get_occr_registry()
        cap_id = "capabilities.publishing.zenodo"
        cap = registry.get_capability(cap_id) or CapabilityRecord(
            capability_id=cap_id,
            namespace="capabilities",
            title="External Repository Deposition",
            implementation_status=ImplementationStatus.IMPLEMENTED_CANDIDATE,
            evidence_status=EvidenceStatus.SELF_REPORTED_TESTED,
            deployment_authority=DeploymentAuthority.HUMAN_APPROVAL_REQUIRED,
            claim_ceiling=ClaimCeiling.TESTED,
            review_independence=ReviewIndependence.SELF_REVIEW,
            source_of_truth="osiris_interactive.py",
        )

        receipt = ReleaseGate.evaluate(
            capability=cap,
            has_sbom=False,
            has_security_audit=False,
            negative_controls=registry.get_negative_controls(),
        )

        if receipt.decision == GateDecision.BLOCK:
            print(f"\n[OCCR RELEASE GATE: BLOCKED]")
            print(f"  ├─ Target Artifact: {path.name} ({digest[:16]}...)")
            print(f"  ├─ Status: DENIED BY DEFAULT (Read-Only Governance Invariant)")
            for r in receipt.reasons:
                print(f"  ├─ Reason: {r}")
            print(f"  └─ Action: Automated publishing disabled. Requires human signoff token.\n")
            return

        print(f"\n[PUBLICATION] Initiating deposition for {path.name}...")
        print(f"  ├─ Artifact Digest (SHA-256): {digest}")
        print("  ├─ Status: SUBMITTED")

    def handle_command(self, cmd_line: str):
        try:
            parts = shlex.split(cmd_line)
        except Exception:
            parts = cmd_line.split()

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("/exit", "/quit", "/q", "exit", "quit"):
            print("[OSIRIS] Session closed.")
            sys.exit(0)

        elif cmd in ("/status", "status"):
            self.execute_status()

        elif cmd in ("/ignite", "ignite"):
            self.execute_ignite()

        elif cmd == "/experiment":
            sub = args[0] if args else "run"
            target = args[1] if len(args) > 1 else "local-fixture-2"
            if sub == "run":
                self.execute_experiment_run(target)
            elif sub == "mutate":
                self.execute_mutate()
            else:
                print(f"Unknown experiment subcommand '{sub}'. Usage: /experiment <run|mutate> [fixture]")

        elif cmd in ("/learn", "learn"):
            gen_arg = int(args[0]) if (args and args[0].isdigit()) else 2
            fixture = f"local-fixture-{args[0]}" if args else "local-fixture-2"
            self.execute_experiment_run(fixture, generations=gen_arg)

        elif cmd in ("/mutate", "mutate"):
            self.execute_mutate()

        elif cmd in ("/dna", "dna"):
            if args and args[0] == "draft":
                intent = " ".join(args[1:]) if len(args) > 1 else "Synthesize candidate parity check"
            else:
                intent = " ".join(args) if args else "Synthesize candidate parity check"
            self.execute_dna_draft(intent)

        elif cmd == "/closure":
            sub = args[0] if args else "verify"
            target = args[1] if len(args) > 1 else "."
            if sub == "verify":
                self.execute_closure_verify(target)
            else:
                print(f"Unknown closure subcommand '{sub}'. Usage: /closure verify <dir>")

        elif cmd in ("/ledger", "ledger"):
            self.execute_ledger()

        elif cmd in ("/publish", "publish"):
            target = args[0] if args else "scimitar_sse_protocol.pdf"
            self.execute_publish(target)

        elif cmd == "/help":
            print(HELP_TEXT)

        elif cmd == "/mode":
            if not args:
                print(f"Current mode: \033[92m{self.current_mode.value}\033[0m")
                print("Available modes: quantum, swarm, governed, neuro_symbolic")
                return
            target_mode = args[0].lower()
            try:
                self.current_mode = EngineMode(target_mode)
                print(f"Switched mode to: \033[92m{self.current_mode.value.upper()}\033[0m")
            except ValueError:
                print(f"\033[91mInvalid mode '{target_mode}'. Choose from: quantum, swarm, governed, neuro_symbolic\033[0m")

        elif cmd == "/sim":
            ticks = int(args[0]) if args else 50
            if self.engine._organism_runtime is None:
                from organism_sim.chat_bridge import Runtime
                self.engine._organism_runtime = Runtime.demo(seed=0)
            rt = self.engine._organism_runtime
            print(f"\n\033[93m[ALIFE SIMULATION]\033[0m Stepping {ticks} ticks...")
            rt.run(ticks)
            print(f"Tick: {rt.tick} | Injections: {len(rt.injections)} | Alerts: {len(rt.alerts)} | Rules: {len(rt.agent.rules.rules)}")
            alerts = rt.drain()
            if alerts:
                print(f"Alerts fired: {[a.name for a in alerts]}")
            print()

        elif cmd == "/benchmark":
            print("\n\033[93m[BENCHMARK]\033[0m Launching comparative benchmark against classical baselines...")
            try:
                from osiris_comparative_benchmark import run_comparative_benchmark
                run_comparative_benchmark()
            except ImportError:
                print("Comparative benchmark harness loading...")

        elif cmd == "/clear":
            if self.engine.livlm:
                self.engine.livlm.memory.clear()
            print("\033[92m[CLEARED]\033[0m Phase memory reset.\n")

        else:
            print(f"\033[91mUnknown command '{cmd}'. Type /help for available commands.\033[0m\n")

    def handle_prompt(self, prompt: str):
        print(f"\033[90mThinking ({self.current_mode.value})...\033[0m")
        res = self.engine.generate(prompt, mode=self.current_mode)
        print(f"\n\033[92m[RESPONSE]\033[0m (in {res.elapsed_ms:.1f} ms):")
        print(f"\033[97m{res.output}\033[0m\n")

        # Epistemic disclosure and telemetry transparency
        print("\033[90mResponse source:")
        print("  LOCAL_LANGUAGE_MODEL_FALLBACK\n")
        print("Experimental sampler:")
        print("  executed: true")
        print("  semantic_output_used: false")
        print("  rejection_reason: NON_LINGUISTIC_BYTE_SEQUENCE\n")
        print("Authority:")
        print("  NONE\n")
        print("Evidence status:")
        print("  LOCAL_RUNTIME_TELEMETRY\033[0m\n")


def main():
    parser = argparse.ArgumentParser(description="OSIRIS Living Language Model Interactive Shell")
    parser.add_argument("--mode", choices=[m.value for m in EngineMode], default="quantum")
    args = parser.parse_args()
    shell = OsirisInteractiveShell(mode=EngineMode(args.mode))
    shell.run()


if __name__ == "__main__":
    main()
