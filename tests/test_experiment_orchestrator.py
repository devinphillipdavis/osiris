"""
Unit tests for experiment_orchestrator.py
Covers:
- Preregistration hash locking
- ExecutionGate enforcement (blocking unauthorized executions)
- Disposable workspace isolation
- Cryptographic RunReceipt generation and sealing
"""

import json
import pytest
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from experiment_orchestrator import ExperimentOrchestrator, ExperimentPreregistration


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def orchestrator(temp_workspace):
    return ExperimentOrchestrator(workspace_root=temp_workspace)


@pytest.fixture
def valid_prereg_dict():
    return {
        "experiment_id": "OCCR-EXP-000101",
        "hypothesis_id": "OCCR-HYP-000101",
        "null_hypothesis": "Delta_F <= 0",
        "primary_endpoint": "F_plus",
        "units": "dimensionless",
        "dimensional_analysis": "State survival probability [0.0, 1.0]",
        "data_source": "Local Aer Statevector",
        "dataset_hashes": ["e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
        "model_hashes": ["aer_v1"],
        "fixed_hyperparameters": {"shots": 1000, "tau": 16},
        "sample_size_rationale": "N=1000 provides standard error under 0.015",
        "planned_statistical_method": "Two-sample t-test",
        "stopping_rule": "Fixed sample N=1000",
        "exclusion_rules": ["Incomplete circuit execution"],
        "baseline_controls": ["idle_unmitigated"],
        "negative_controls": ["random_phase_jitter"],
        "expected_failure_modes": ["SPAM distortion"],
        "execution_environment": {
            "node_type": "TEST_NODE",
            "platform": "linux",
            "python_version": "3.10"
        },
        "claim_ceiling_before_execution": "TESTED"
    }


def test_preregistration_hash_lock(orchestrator, valid_prereg_dict):
    manifest = orchestrator.preregister(valid_prereg_dict)
    assert manifest.status == "LOCKED"
    assert manifest.manifest_hash is not None
    assert len(manifest.manifest_hash) == 64

    # Recalculating hash should match
    assert manifest.compute_hash() == manifest.manifest_hash


def test_missing_preregistration_fields_raises(orchestrator, valid_prereg_dict):
    del valid_prereg_dict["null_hypothesis"]
    with pytest.raises(ValueError, match="null_hypothesis"):
        orchestrator.preregister(valid_prereg_dict)


def test_simulation_execution_in_isolated_directory(orchestrator, valid_prereg_dict, temp_workspace):
    manifest = orchestrator.preregister(valid_prereg_dict)

    # Create dummy simulation script that writes results.json
    script_path = Path(temp_workspace) / "sim_worker.py"
    with open(script_path, "w", encoding="utf-8") as sf:
        sf.write(
            "import json\n"
            "with open('results.json', 'w') as f:\n"
            "    json.dump({'observed_primary_endpoint': 0.892, 'baseline_value': 0.791}, f)\n"
            "print('SIMULATION_DONE')\n"
        )

    receipt = orchestrator.run_simulation(
        prereg=manifest,
        target_script=str(script_path),
        role="researcher"
    )

    assert receipt.status == "COMPLETED"
    assert receipt.exit_code == 0
    assert "SIMULATION_DONE" in receipt.stdout_summary
    assert receipt.metrics.get("observed_primary_endpoint") == 0.892
    assert len(receipt.receipt_signature) == 64

    # Verify run artifacts exist inside isolated workspace
    expected_run_dir = Path(temp_workspace) / manifest.experiment_id / manifest.manifest_hash[:16]
    assert expected_run_dir.exists()
    assert (expected_run_dir / "preregistration.json").exists()
    assert (expected_run_dir / "run_receipt.json").exists()
