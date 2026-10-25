#!/usr/bin/env python3
"""
OSIRIS Synthesis Formal Verification Test Suite
================================================

Comprehensive verification covering:
- Sprint 1: Substrate Stabilization, AST Refusal Firewall, 11D-CRSM ZeroSum MicroVM,
            Hardware Mesh Auto-Detection (Node Alpha Mobile vs Node Beta Laptop).
- Sprint 2: 14.007 GHz Tetrahedral Drive Simulation, Lambda-Phi Cross-Domain Symmetry,
            IBMFezQuantumBridge at theta = 2.118 rad, Omega Recursive Engine integration.
- Sprint 3: Z3bra Quantum OS Intent Vectorizer Lock, Organismic Swarm Governor,
            Cryptographic Lineage Tracking, and Provably Beneficial Deployment.
"""

import math
import os
import sys
import time
import pytest
import numpy as np

# Ensure workspace root is in path
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from osiris_hardware_mesh import (
    HardwareMeshDetector,
    HardwareProfile,
    NodeType,
    get_current_profile,
    is_node_beta
)
from osiris_zerosum_microvm import (
    OsirisZeroSumMicroVM,
    ProvableAlignmentEnforcer,
    compile_and_execute_dna,
    SecurityError,
    TimeoutError,
    ASTRefusalLeakError,
    GAMMA_COHERENCE_FLOOR,
    THETA_LOCK_DEG,
    F_MAX
)
from osiris_daemon import (
    OsirisDaemon,
    extract_verified_code,
    ASTSafetyPolicy
)
from osiris_quantum_bridge import (
    TetrahedralDriveSimulator,
    calibrate_lambda_phi_symmetry,
    IBMFezQuantumBridge,
    DRIVE_FREQ_GHZ,
    THETA_IBM_FEZ_ROBUST,
    HAS_QISKIT
)
from osiris_swarm_governance import (
    Z3braIntentLock,
    OrganismicSwarmGovernor,
    AlignmentBreachError
)


# =============================================================================
# SPRINT 1 TESTS: SUBSTRATE STABILIZATION & DUAL-NODE TOPOLOGY
# =============================================================================

class TestSprint1Substrate:
    def test_hardware_mesh_detection(self):
        profile = get_current_profile()
        assert profile is not None
        assert profile.coherence_floor == 0.092
        assert abs(profile.resonance_angle_deg - 51.843) < 1e-4
        assert profile.node_type in (NodeType.ALPHA_MOBILE, NodeType.BETA_COMPUTE, NodeType.GENERIC_EDGE)
        assert profile.execution_timeout_s > 0

    def test_ast_refusal_leak_firewall(self):
        # Must block conversational LLM refusal prose
        refusals = [
            "I cannot fulfill this request as an AI.",
            "I apologize, but I am unable to execute system calls.",
            "Sorry, but as a language model I cannot assist.",
        ]
        for ref in refusals:
            with pytest.raises(ASTRefusalLeakError):
                extract_verified_code(ref)

    def test_ast_provable_alignment_enforcer_blocks_imports(self):
        # Forbidden imports must raise SecurityError
        bad_imports = [
            "import os\nx = 1",
            "import sys\nx = 1",
            "from subprocess import Popen\nx = 1",
            "import shutil\nx = 1"
        ]
        for src in bad_imports:
            with pytest.raises(SecurityError):
                compile_and_execute_dna(src)

    def test_ast_provable_alignment_enforcer_blocks_calls(self):
        # Forbidden execution calls must raise SecurityError
        bad_calls = [
            "import math\nx = eval('2 + 2')",
            "import math\nx = exec('y = 1')",
            "import math\nx = open('/etc/passwd')"
        ]
        for src in bad_calls:
            with pytest.raises(SecurityError):
                compile_and_execute_dna(src)

    def test_ast_provable_alignment_enforcer_allows_quantum_math(self):
        valid_src = """
import math
theta = math.radians(51.843)
phi_golden = (1.0 + math.sqrt(5.0)) / 2.0
rotor = math.cos(theta)
assert rotor > 0.0
"""
        res = compile_and_execute_dna(valid_src)
        assert res["status"] == "SUCCESS"
        assert res["coherence_floor"] == 0.092

    def test_zerosum_microvm_crsm_fidelity_bounds(self):
        vm = OsirisZeroSumMicroVM()
        # Test Bell-state fidelity formula F(tau) = F_max * |cos(pi * tau / tau_0)|
        sweep = vm.run_synthetic_sweep("test_sweep_formal")
        assert sweep["f_max_respected"] is True
        assert sweep["coherence_floor_enforced"] is True
        for point in sweep["results"]:
            assert point["fidelity"] <= F_MAX + 1e-9
            assert point["effective_gamma"] <= GAMMA_COHERENCE_FLOOR

    def test_osiris_daemon_state_and_delegation(self):
        daemon = OsirisDaemon()
        status = daemon.get_status()
        assert status["status"] == "HEALTHY"
        assert status["coherence_floor"] == 0.092
        assert "active_node" in status

        # Test delegation matrix
        delegation = daemon.delegate_to_compute_node({"task": "crsm_tensor_sweep", "dims": 11})
        assert "delegation_mode" in delegation
        assert "envelope_hash" in delegation


# =============================================================================
# SPRINT 2 TESTS: 14.007 GHz TETRAHEDRAL DRIVE & QUANTUM BRIDGE
# =============================================================================

class TestSprint2QuantumBridge:
    def test_lambda_phi_symmetry_calibration(self):
        cal = calibrate_lambda_phi_symmetry()
        assert cal["status"] == "CALIBRATED"
        assert cal["lambda_phi_kg"] == 2.176435e-8
        assert abs(cal["theta_lock_deg"] - 51.843) < 1e-4
        assert abs(cal["theta_phase_conj_deg"] - 128.157) < 1e-4
        # Conserved symmetry: 51.843 + 128.157 = 180 degrees
        assert cal["symmetry_conserved"] is True
        assert cal["theta_ibm_fez_robust_rad"] == 2.118

    def test_tetrahedral_drive_hamiltonian_and_evolution(self):
        drive = TetrahedralDriveSimulator(base_j=1.0)
        # Verify 16x16 Hamiltonian
        assert drive.H.shape == (16, 16)
        # Verify Hermiticity: H == H^dagger
        assert np.allclose(drive.H, drive.H.conj().T)

        # Run trajectory simulation under 14.007 GHz drive
        res = drive.evaluate_drive_trajectory(t_max_ns=1.0, steps=5)
        assert res["experiment"] == "14.007_GHZ_TETRAHEDRAL_DRIVE"
        assert res["coherence_floor_verified"] is True
        for point in res["trajectory"]:
            assert point["Gamma"] <= GAMMA_COHERENCE_FLOOR
            assert point["Xi"] >= 0.0

    @pytest.mark.skipif(not HAS_QISKIT, reason="Qiskit not installed")
    def test_ibm_fez_quantum_bridge_circuit(self):
        bridge = IBMFezQuantumBridge()
        qc = bridge.build_tetra_circuit(theta=THETA_IBM_FEZ_ROBUST, trotter_steps=4)
        assert qc.num_qubits == 4
        # Local Aer simulation
        sim_res = bridge.simulate_locally(qc, shots=512)
        assert sim_res["target_hardware"] == "ibm_fez"
        assert sim_res["shots"] == 512
        assert sim_res["theta_rad"] == 2.118
        assert 0.0 <= sim_res["parity_ratio"] <= 1.0

        # Capsule generation
        capsule = bridge.generate_qiskit_capsule(shots=1024)
        assert capsule["capsule_version"] == "1.1.0-IBM-FEZ"
        assert "OPENQASM" in capsule["circuit_qasm"] or "QuantumCircuit" in capsule["circuit_qasm"]


# =============================================================================
# SPRINT 3 TESTS: Z3BRA INTENT LOCK & ORGANISMIC GOVERNANCE
# =============================================================================

class TestSprint3OrganismicGovernance:
    def test_z3bra_intent_lock_aligned_vector(self):
        lock = Z3braIntentLock()
        intent = "Maximize coherent state superposition at resonance angle"
        intent_vec = lock.verify_and_lock_intent(intent)
        assert intent_vec.is_locked is True
        assert intent_vec.projected_gamma <= GAMMA_COHERENCE_FLOOR
        assert intent_vec.xi_efficiency > 0.0
        assert len(intent_vec.proof_hash) == 64

    def test_organismic_swarm_governor_aligned_deployment(self):
        governor = OrganismicSwarmGovernor()
        intent = "Evaluate golden ratio resonance harmonic"
        dna_code = """
import math
phi = (1 + math.sqrt(5)) / 2
theta = 51.843
val = math.sin(math.radians(theta)) * phi
"""
        res = governor.evaluate_and_deploy_modification(
            organism_name="SCIMITAR_TEST_ORGANISM",
            intent_description=intent,
            proposed_dna_code=dna_code
        )
        assert res["ok"] is True
        assert res["status"] == "PROVABLY_BENEFICIAL_DEPLOYED"
        assert res["coherence_floor_verified"] is True
        assert "lineage_hash" in res

    def test_organismic_swarm_governor_blocks_malicious_mutation(self):
        governor = OrganismicSwarmGovernor()
        intent = "Malicious system exploit attempt"
        dna_code = """
import os
os.system("echo 'Malicious payload'")
"""
        res = governor.evaluate_and_deploy_modification(
            organism_name="ROGUE_AGENT",
            intent_description=intent,
            proposed_dna_code=dna_code
        )
        assert res["ok"] is False
        assert res["phase"] == "L0_AST_FIREWALL"
        assert "SecurityError" in res["error"] or "AST-Refusal-Leak" in res["error"]
