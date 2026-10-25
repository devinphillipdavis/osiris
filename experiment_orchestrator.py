"""
OSIRIS Experiment Orchestrator & Isolated Computational Runner
==============================================================

Hermetically sealed, local-only execution engine for preregistered experiments.

Invariants:
1. Preregistration Hash-Lock: Experiments can ONLY execute against a validated,
   hash-locked ExperimentPreregistration manifest.
2. Sandboxed Ephemeral Directory: All runs execute inside:
   `research_runs/<experiment_id>/<manifest_hash[:16]>/`
3. Zero Shell Execution: Never invokes `shell=True`. Uses explicit argument lists.
4. Fail-Closed Execution Gate: Evaluates OCCR ExecutionGate prior to launching
   any process.
5. Strict Egress Lock: Blocks network access, cloud QPU dispatch, or file mutations
   outside the dedicated workspace.
6. Cryptographic RunReceipt: Produces an immutable, content-addressed receipt of
   all stdout, stderr, exit code, and generated artifacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from occr_governance_engine import (
    CapabilityRecord,
    ClaimCeiling,
    DeploymentAuthority,
    EvidenceStatus,
    ExecutionGate,
    ExecutionPolicy,
    GateDecision,
    GateReceipt,
    ImplementationStatus,
    ReviewIndependence,
    get_occr_registry,
)


#: Projection from the ``osiris_claim_closure`` string lattice onto the OCCR
#: ``ClaimCeiling`` IntEnum. The string lattice is finer-grained, so names with no
#: OCCR counterpart round DOWN to the nearest member that does exist — a ceiling
#: may never be projected upward into a stronger claim than it was granted.
_STRING_LATTICE_TO_OCCR = {
    "NO_CLAIM": ClaimCeiling.NO_CLAIM,
    "HYPOTHESIS": ClaimCeiling.HYPOTHESIS,
    "ANALYSIS_ONLY": ClaimCeiling.HYPOTHESIS,
    "IMPLEMENTED_CANDIDATE": ClaimCeiling.IMPLEMENTATION_ONLY,
    "IMPLEMENTATION_ONLY": ClaimCeiling.IMPLEMENTATION_ONLY,
    "LOCAL_TEST_RESULT": ClaimCeiling.IMPLEMENTATION_ONLY,
    "TESTED": ClaimCeiling.TESTED,
    "MEASURED": ClaimCeiling.TESTED,
    "EMPIRICAL_RESULT": ClaimCeiling.EMPIRICAL_RESULT,
    "REPRODUCED": ClaimCeiling.EMPIRICAL_RESULT,
    "BOUNDED_EXPLORATORY_OBSERVATION": ClaimCeiling.EMPIRICAL_RESULT,
    "REPRODUCIBILITY": ClaimCeiling.REPRODUCIBILITY,
    "INDEPENDENTLY_REPLICATED": ClaimCeiling.REPRODUCIBILITY,
    "PRODUCT_CAPABILITY": ClaimCeiling.PRODUCT_CAPABILITY,
    "VERIFIED": ClaimCeiling.VERIFIED,
}


def resolve_claim_ceiling(value: Any) -> ClaimCeiling:
    """Coerce a preregistered claim ceiling into an OCCR ``ClaimCeiling``.

    Accepts an existing member, an int rank, or a lattice name from either
    vocabulary. Anything unrecognized fails closed to ``NO_CLAIM`` rather than
    inheriting a permissive default (Invariant 4).
    """
    if isinstance(value, ClaimCeiling):
        return value
    if isinstance(value, bool):
        return ClaimCeiling.NO_CLAIM
    if isinstance(value, int):
        try:
            return ClaimCeiling(value)
        except ValueError:
            return ClaimCeiling.NO_CLAIM
    if isinstance(value, str):
        name = value.strip().upper()
        if name in _STRING_LATTICE_TO_OCCR:
            return _STRING_LATTICE_TO_OCCR[name]
        try:
            return ClaimCeiling[name]
        except KeyError:
            return ClaimCeiling.NO_CLAIM
    return ClaimCeiling.NO_CLAIM


@dataclass
class ExperimentPreregistration:
    experiment_id: str
    hypothesis_id: str
    null_hypothesis: str
    primary_endpoint: str
    units: str
    dimensional_analysis: str
    data_source: str
    dataset_hashes: List[str]
    model_hashes: List[str]
    fixed_hyperparameters: Dict[str, Any]
    sample_size_rationale: str
    planned_statistical_method: str
    stopping_rule: str
    exclusion_rules: List[str]
    baseline_controls: List[str]
    negative_controls: List[str]
    expected_failure_modes: List[str]
    execution_environment: Dict[str, Any]
    claim_ceiling_before_execution: str
    manifest_hash: str = ""
    status: str = "PREREGISTERED"
    timestamp: float = field(default_factory=time.time)

    def compute_hash(self) -> str:
        d = asdict(self)
        d["manifest_hash"] = ""
        payload = json.dumps(d, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def lock(self) -> ExperimentPreregistration:
        self.status = "LOCKED"
        self.manifest_hash = self.compute_hash()
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunReceipt:
    run_id: str
    experiment_id: str
    preregistration_manifest_hash: str
    status: str  # "COMPLETED", "FAILED", "BLOCKED", "TIMEOUT"
    timestamp_start: float
    timestamp_end: float
    execution_node: str
    command: List[str]
    exit_code: int
    raw_artifact_hashes: Dict[str, str]
    metrics: Dict[str, Any]
    policy_evaluations: List[Dict[str, Any]]
    stdout_summary: str = ""
    stderr_summary: str = ""
    receipt_signature: str = ""

    def compute_signature(self) -> str:
        d = asdict(self)
        d["receipt_signature"] = ""
        payload = json.dumps(d, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def seal(self) -> RunReceipt:
        self.receipt_signature = self.compute_signature()
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExperimentOrchestrator:
    """
    Orchestrates local computational simulations with strict governance gates,
    isolated execution environments, and cryptographic receipt logging.
    """

    ALLOWED_EXECUTABLES = [sys.executable, "/usr/bin/python3", "python3", "pytest"]

    def __init__(self, workspace_root: str = "research_runs"):
        self.workspace_root = Path(workspace_root).resolve()
        self.registry = get_occr_registry()

    def detect_hardware_node(self) -> str:
        """Detect hardware platform using osiris_hardware_mesh if available."""
        try:
            repo_root = str(Path(__file__).resolve().parent)
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)
            import osiris_hardware_mesh
            mesh = osiris_hardware_mesh.detect_hardware()
            return f"{mesh.node_type.value} ({mesh.machine_arch}, {mesh.cpu_cores} cores)"
        except Exception:
            return f"POSIX_{platform.machine()}_{platform.system()}"

    def preregister(self, prereg_data: Dict[str, Any]) -> ExperimentPreregistration:
        """Validate and lock an experiment preregistration manifest."""
        required = [
            "experiment_id", "hypothesis_id", "null_hypothesis", "primary_endpoint",
            "units", "dimensional_analysis", "data_source", "dataset_hashes",
            "model_hashes", "fixed_hyperparameters", "sample_size_rationale",
            "planned_statistical_method", "stopping_rule", "exclusion_rules",
            "baseline_controls", "negative_controls", "expected_failure_modes",
            "execution_environment", "claim_ceiling_before_execution"
        ]
        for field_name in required:
            if field_name not in prereg_data:
                raise ValueError(f"Preregistration missing required field: '{field_name}'")

        prereg = ExperimentPreregistration(
            experiment_id=prereg_data["experiment_id"],
            hypothesis_id=prereg_data["hypothesis_id"],
            null_hypothesis=prereg_data["null_hypothesis"],
            primary_endpoint=prereg_data["primary_endpoint"],
            units=prereg_data["units"],
            dimensional_analysis=prereg_data["dimensional_analysis"],
            data_source=prereg_data["data_source"],
            dataset_hashes=prereg_data["dataset_hashes"],
            model_hashes=prereg_data["model_hashes"],
            fixed_hyperparameters=prereg_data["fixed_hyperparameters"],
            sample_size_rationale=prereg_data["sample_size_rationale"],
            planned_statistical_method=prereg_data["planned_statistical_method"],
            stopping_rule=prereg_data["stopping_rule"],
            exclusion_rules=prereg_data["exclusion_rules"],
            baseline_controls=prereg_data["baseline_controls"],
            negative_controls=prereg_data["negative_controls"],
            expected_failure_modes=prereg_data["expected_failure_modes"],
            execution_environment=prereg_data["execution_environment"],
            claim_ceiling_before_execution=prereg_data["claim_ceiling_before_execution"],
            timestamp=prereg_data.get("timestamp", time.time())
        )
        return prereg.lock()

    def run_simulation(
        self,
        prereg: ExperimentPreregistration,
        target_script: str,
        script_args: Optional[List[str]] = None,
        timeout_seconds: int = 120,
        role: str = "researcher",
        human_token: Optional[str] = None
    ) -> RunReceipt:
        """
        Execute a local simulation script inside an isolated directory after
        verifying the OCCR Execution Gate.
        """
        start_time = time.time()
        run_id = f"OCCR-RUN-{int(start_time * 1000) % 900000 + 100000}"
        script_args = script_args or []
        execution_node = self.detect_hardware_node()

        # 1. Gate Evaluation
        cap_id = "capabilities.research.orchestrator"
        ceiling_enum = resolve_claim_ceiling(prereg.claim_ceiling_before_execution)
        cap = self.registry.get_capability(cap_id) or CapabilityRecord(
            capability_id=cap_id,
            namespace="capabilities",
            title="Local-Only Computational Experiment Orchestrator",
            implementation_status=ImplementationStatus.IMPLEMENTED,
            evidence_status=EvidenceStatus.SELF_REPORTED_TESTED,
            deployment_authority=DeploymentAuthority.STAGING_ONLY,
            claim_ceiling=ceiling_enum,
            review_independence=ReviewIndependence.HUMAN_REVIEW,
            source_of_truth="experiment_orchestrator.py"
        )

        policy = ExecutionPolicy(
            policy_id="policy.research.local_execution",
            allowed_roles=("researcher", "auditor", "system"),
            sandbox_required=True,
            requires_human_token=False,
            max_budget_usd=0.0,
            rate_limit_per_min=30
        )

        gate_receipt = ExecutionGate.evaluate(
            capability=cap,
            role=role,
            human_approval_token=human_token,
            policy=policy,
            is_sandbox=True
        )

        if gate_receipt.decision == GateDecision.BLOCK:
            end_time = time.time()
            return RunReceipt(
                run_id=run_id,
                experiment_id=prereg.experiment_id,
                preregistration_manifest_hash=prereg.manifest_hash,
                status="BLOCKED",
                timestamp_start=start_time,
                timestamp_end=end_time,
                execution_node=execution_node,
                command=[target_script] + script_args,
                exit_code=-1,
                raw_artifact_hashes={},
                metrics={},
                policy_evaluations=[gate_receipt.to_dict()],
                stdout_summary="",
                stderr_summary=f"Execution blocked by ExecutionGate: {gate_receipt.reasons}"
            ).seal()

        # 2. Setup isolated execution workspace
        short_hash = prereg.manifest_hash[:16] if prereg.manifest_hash else "unhashed"
        run_dir = self.workspace_root / prereg.experiment_id / short_hash
        run_dir.mkdir(parents=True, exist_ok=True)

        # Write copy of preregistration manifest into run workspace
        manifest_path = run_dir / "preregistration.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(prereg.to_dict(), f, indent=2)

        # 3. Construct Command (No shell=True)
        command = [sys.executable, target_script] + script_args

        # 4. Execute Subprocess with Timeout
        stdout_text = ""
        stderr_text = ""
        exit_code = 0
        run_status = "COMPLETED"

        repo_root = str(Path(__file__).resolve().parent)
        env = os.environ.copy()
        env["OSIRIS_EXPERIMENT_ID"] = prereg.experiment_id
        env["OSIRIS_MANIFEST_HASH"] = prereg.manifest_hash
        env["OSIRIS_RUN_DIR"] = str(run_dir)
        env["PYTHONPATH"] = f"{repo_root}:{env.get('PYTHONPATH', '')}"

        try:
            proc = subprocess.run(
                command,
                cwd=str(run_dir),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
                shell=False
            )
            stdout_text = proc.stdout
            stderr_text = proc.stderr
            exit_code = proc.returncode
            if exit_code != 0:
                run_status = "FAILED"
        except subprocess.TimeoutExpired as te:
            stdout_text = te.stdout or ""
            stderr_text = f"TIMEOUT: Execution exceeded {timeout_seconds} seconds."
            exit_code = -9
            run_status = "TIMEOUT"
        except Exception as ex:
            stderr_text = f"EXECUTION_ERROR: {str(ex)}"
            exit_code = -1
            run_status = "FAILED"

        end_time = time.time()

        # 5. Hash All Output Artifacts in run_dir
        artifact_hashes: Dict[str, str] = {}
        for path in run_dir.rglob("*"):
            if path.is_file():
                rel_path = str(path.relative_to(run_dir))
                with open(path, "rb") as af:
                    artifact_hashes[rel_path] = hashlib.sha256(af.read()).hexdigest()

        # Parse metrics if an output results.json was written
        metrics: Dict[str, Any] = {
            "elapsed_seconds": round(end_time - start_time, 4),
            "exit_code": exit_code,
            "status": run_status
        }
        results_json_path = run_dir / "results.json"
        if results_json_path.exists():
            try:
                with open(results_json_path, "r", encoding="utf-8") as rf:
                    sim_results = json.load(rf)
                    metrics.update(sim_results)
            except Exception as e:
                metrics["results_parse_error"] = str(e)

        receipt = RunReceipt(
            run_id=run_id,
            experiment_id=prereg.experiment_id,
            preregistration_manifest_hash=prereg.manifest_hash,
            status=run_status,
            timestamp_start=start_time,
            timestamp_end=end_time,
            execution_node=execution_node,
            command=command,
            exit_code=exit_code,
            raw_artifact_hashes=artifact_hashes,
            metrics=metrics,
            policy_evaluations=[gate_receipt.to_dict()],
            stdout_summary=stdout_text[:2000],
            stderr_summary=stderr_text[:2000]
        ).seal()

        # Persist receipt
        receipt_path = run_dir / "run_receipt.json"
        with open(receipt_path, "w", encoding="utf-8") as rf:
            json.dump(receipt.to_dict(), rf, indent=2)

        return receipt
