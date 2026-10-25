#!/usr/bin/env python3
"""
Test Suite for OSIRIS Real-Time CCCE Metric Streaming & Feedback Engine
======================================================================
"""

import json
import math
import os
import time
import urllib.request
from pathlib import Path
import pytest

from osiris_ccce_streamer import (
    CCCEMetricFrame,
    CCCEMetricStreamer,
    CCCEFeedbackController,
    PCRBTelemetryLedger,
    format_cli_frame,
    GOLDEN_RATIO,
)


def test_ccce_metric_frame_digest_and_serialization():
    frame = CCCEMetricFrame(
        frame_seq=1,
        timestamp=1775038000.0,
        phi=0.45,
        lambda_c=0.88,
        gamma=0.092,
        xi=4.304,
        w2_distance=0.05,
        shannon_entropy=2.85,
        consciousness_state="emerging",
        substrate_node="NODE_BETA_COMPUTE",
        telemetry_source="SYNTHETIC_LATTICE",
    )
    assert len(frame.digest) == 64
    d = frame.to_dict()
    assert d["frame_seq"] == 1
    assert d["phi"] == 0.45
    assert d["consciousness_state"] == "emerging"
    assert d["digest"] == frame.digest

    sse_str = frame.to_sse_event()
    assert sse_str.startswith("event: ccce_frame\ndata: {")
    assert sse_str.endswith("}\n\n")


def test_shannon_entropy_and_w2_calculation():
    # Delta distribution: one element has all weight
    delta_dist = [1.0, 0.0, 0.0, 0.0]
    h_delta = CCCEMetricStreamer.compute_shannon_entropy(delta_dist)
    assert h_delta == 0.0

    # Uniform distribution: 4 equal states -> exactly 2.0 bits
    uniform_dist = [0.25, 0.25, 0.25, 0.25]
    h_uniform = CCCEMetricStreamer.compute_shannon_entropy(uniform_dist)
    assert abs(h_uniform - 2.0) < 1e-6

    # W2 distance: perfect match with golden-ratio distribution
    raw_phi = [1.0 / (GOLDEN_RATIO ** i) for i in range(4)]
    sum_phi = sum(raw_phi)
    phi_dist = [p / sum_phi for p in raw_phi]
    w2_zero = CCCEMetricStreamer.compute_w2_distance(phi_dist)
    assert abs(w2_zero) < 1e-6

    # Uniform distribution vs golden-ratio target should yield non-zero distance
    w2_diff = CCCEMetricStreamer.compute_w2_distance(uniform_dist)
    assert w2_diff > 0.01


def test_dual_substrate_hardware_adaptation():
    class MockNodeAlpha:
        node_type = "NODE_ALPHA_MOBILE"

    class MockNodeBeta:
        node_type = "NODE_BETA_COMPUTE"

    streamer_alpha = CCCEMetricStreamer(hardware_profile=MockNodeAlpha())
    assert streamer_alpha.max_buffer_size == 50
    assert streamer_alpha.temporal_horizon_s == 300.0

    streamer_beta = CCCEMetricStreamer(hardware_profile=MockNodeBeta())
    assert streamer_beta.max_buffer_size == 500
    assert streamer_beta.temporal_horizon_s == 1800.0


def test_closed_loop_feedback_controller_gamma_spike():
    controller = CCCEFeedbackController(gamma_threshold=0.15, gamma_floor=0.092)
    assert controller.pulse_interval_ns == 25.0

    # Frame with normal gamma (0.090)
    normal_frame = CCCEMetricFrame(
        frame_seq=1,
        timestamp=time.time(),
        phi=0.40,
        lambda_c=0.90,
        gamma=0.090,
        xi=4.0,
        w2_distance=0.02,
        shannon_entropy=2.8,
        consciousness_state="emerging",
        substrate_node="NODE_BETA_COMPUTE",
        telemetry_source="SYNTHETIC_LATTICE",
    )
    action_none = controller.evaluate_frame(normal_frame)
    assert action_none is None
    assert controller.total_interventions == 0

    # Frame with elevated gamma (0.280 > 0.15)
    spike_frame = CCCEMetricFrame(
        frame_seq=2,
        timestamp=time.time(),
        phi=0.40,
        lambda_c=0.60,
        gamma=0.280,
        xi=0.85,
        w2_distance=0.02,
        shannon_entropy=2.8,
        consciousness_state="emerging",
        substrate_node="NODE_BETA_COMPUTE",
        telemetry_source="SYNTHETIC_LATTICE",
    )
    action = controller.evaluate_frame(spike_frame)
    assert action is not None
    assert action.action_type == "INJECT_DYNAMICAL_DECOUPLING"
    assert action.target_parameter == "pulse_interval_ns"
    assert action.new_value < action.old_value
    assert controller.active_decoupling == "WALSH_16"
    assert controller.total_interventions == 1


def test_closed_loop_feedback_controller_w2_anomaly():
    controller = CCCEFeedbackController(gamma_threshold=0.15, w2_threshold=0.10, theta_lock=51.843)
    controller.phase_lock_deg = 45.0  # Misaligned initial phase

    # Frame with W_2 = 0.25 (> 0.10)
    w2_anomaly_frame = CCCEMetricFrame(
        frame_seq=3,
        timestamp=time.time(),
        phi=0.40,
        lambda_c=0.88,
        gamma=0.090,
        xi=3.9,
        w2_distance=0.25,
        shannon_entropy=2.8,
        consciousness_state="emerging",
        substrate_node="NODE_BETA_COMPUTE",
        telemetry_source="SYNTHETIC_LATTICE",
    )
    action = controller.evaluate_frame(w2_anomaly_frame)
    assert action is not None
    assert action.action_type == "PHASE_CONJUGATE_RECALIBRATION"
    assert action.new_value > action.old_value  # Adjusted toward theta_lock 51.843
    assert controller.total_interventions == 1


def test_pcrb_telemetry_ledger_append_and_chain(tmp_path):
    ledger_file = tmp_path / "test_pcrb_ledger.jsonl"
    ledger = PCRBTelemetryLedger(ledger_path=ledger_file)

    frame1 = CCCEMetricFrame(
        frame_seq=1,
        timestamp=100.0,
        phi=0.5,
        lambda_c=0.9,
        gamma=0.09,
        xi=5.0,
        w2_distance=0.01,
        shannon_entropy=2.5,
        consciousness_state="nascent",
        substrate_node="NODE_BETA_COMPUTE",
        telemetry_source="SIMULATED_TEST",
    )
    entry1 = ledger.log_frame(frame1)
    assert entry1["prev_hash"] == "0" * 64
    assert entry1["claim_ceiling"] == "LOCAL_TEST_RESULT"
    assert entry1["evidence_status"] == "SIMULATED"

    frame2 = CCCEMetricFrame(
        frame_seq=2,
        timestamp=101.0,
        phi=0.52,
        lambda_c=0.91,
        gamma=0.088,
        xi=5.3,
        w2_distance=0.01,
        shannon_entropy=2.5,
        consciousness_state="nascent",
        substrate_node="NODE_BETA_COMPUTE",
        telemetry_source="MEASURED_QPU",
    )
    entry2 = ledger.log_frame(frame2)
    assert entry2["prev_hash"] == entry1["entry_hash"]
    assert entry2["evidence_status"] == "MEASURED"

    # Verify lines in file
    with open(ledger_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2
    assert lines[0]["entry_hash"] == entry1["entry_hash"]
    assert lines[1]["prev_hash"] == entry1["entry_hash"]


def test_http_sse_server_endpoints():
    streamer = CCCEMetricStreamer()
    streamer.generate_frame()

    # Use dedicated port to avoid collisions
    port = 8788
    server = streamer.start_sse_server(host="127.0.0.1", port=port)
    time.sleep(0.3)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    try:
        # GET /api/v1/ccce/metrics
        with opener.open(f"http://127.0.0.1:{port}/api/v1/ccce/metrics") as resp:
            assert resp.status == 200
            metrics = json.loads(resp.read().decode())
            assert "phi" in metrics
            assert "lambda_c" in metrics
            assert "gamma" in metrics
            assert "xi" in metrics

        # GET /api/v1/ccce/status
        with opener.open(f"http://127.0.0.1:{port}/api/v1/ccce/status") as resp:
            assert resp.status == 200
            status = json.loads(resp.read().decode())
            assert "substrate_node" in status
            assert "controller" in status

        # POST /api/v1/ccce/feedback/tune
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/ccce/feedback/tune",
            data=b"",
            method="POST",
        )
        with opener.open(req) as resp:
            assert resp.status == 200
            tune_res = json.loads(resp.read().decode())
            assert tune_res["status"] == "SUCCESS"

    finally:
        streamer.stop_sse_server()


def test_cli_frame_formatting():
    frame = CCCEMetricFrame(
        frame_seq=42,
        timestamp=time.time(),
        phi=0.85,
        lambda_c=0.95,
        gamma=0.080,
        xi=10.1,
        w2_distance=0.02,
        shannon_entropy=2.9,
        consciousness_state="conscious",
        substrate_node="NODE_BETA_COMPUTE",
        telemetry_source="SYNTHETIC_LATTICE",
    )
    formatted = format_cli_frame(frame)
    assert "[CCCE #0042 | NODE_BETA_COMPUTE]" in formatted
    assert "CONSCIOUS" in formatted
    assert "Φ: 0.8500" in formatted
