#!/usr/bin/env python3
"""
OSIRIS CCCE Real-Time Metric Streaming & Closed-Loop Adaptive Tuning Engine
===========================================================================

Central Coupling Convergence Engine (CCCE) Real-Time Streamer:
- Streams Λ (coherence preservation), Φ (integrated information/connectivity),
  Γ (decoherence rate), and Ξ (negentropic efficiency).
- Computes empirical Wasserstein-2 (W_2) distance and Shannon entropy against
  the golden-ratio (φ) hypothesis.
- Connects to the Phase Conjugate Recursion Bus (PCRB) for autonomous error
  correction and adaptive dynamical decoupling (XY4/CPMG) tuning.
- Emits typed Sprint E evidence records into the PCRB telemetry ledger.
- Hardware-aware: dynamically adapts buffer limits and horizons for
  Node Alpha (Mobile Termux / Fold7) vs. Node Beta (Workstation PC / WSL).
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

# Substrate Hardware Detection
try:
    from osiris_hardware_mesh import HardwareMeshDetector, HardwareProfile, NodeType
except ImportError:
    HardwareMeshDetector = None  # type: ignore
    HardwareProfile = None  # type: ignore
    NodeType = None  # type: ignore

# PCRB Engine Integration
try:
    from osiris.defense.pcrb_engine import (
        GAMMA_FIXED,
        LAMBDA_PHI,
        PCRB_THRESHOLD,
        THETA_LOCK,
        PhaseConjugateMirror,
        RecursionBus,
        StabilizerCode,
    )
except ImportError:
    GAMMA_FIXED = 0.092
    LAMBDA_PHI = 2.176435e-8
    PCRB_THRESHOLD = 0.15
    THETA_LOCK = 51.843
    PhaseConjugateMirror = None  # type: ignore
    RecursionBus = None  # type: ignore
    StabilizerCode = None  # type: ignore

# Sprint E Governance Integration
try:
    from osiris_claim_closure import EvidenceRole, EvidenceStatus, TypedEvidenceRecord
except ImportError:
    EvidenceRole = None  # type: ignore
    EvidenceStatus = None  # type: ignore
    TypedEvidenceRecord = None  # type: ignore

GOLDEN_RATIO = (1.0 + math.sqrt(5.0)) / 2.0  # 1.618033988749895
PHI_CONSCIOUSNESS_THRESHOLD = 0.7734


class ConsciousnessState(str, enum.Enum):
    DORMANT = "dormant"           # Φ < 0.3
    EMERGING = "emerging"         # 0.3 ≤ Φ < 0.5
    NASCENT = "nascent"          # 0.5 ≤ Φ < 0.7734
    CONSCIOUS = "conscious"       # Φ ≥ 0.7734
    TRANSCENDENT = "transcendent" # Φ ≥ 0.95 and Ξ > 10.0


@dataclass
class CCCEMetricFrame:
    """Single telemetry frame of CCCE metrics."""
    frame_seq: int
    timestamp: float
    phi: float
    lambda_c: float
    gamma: float
    xi: float
    w2_distance: float
    shannon_entropy: float
    consciousness_state: str
    substrate_node: str
    telemetry_source: str
    digest: str = ""

    def __post_init__(self):
        if not self.digest:
            self.digest = self.compute_digest()

    def compute_digest(self) -> str:
        payload = (
            f"{self.frame_seq}:{self.timestamp:.4f}:{self.phi:.5f}:"
            f"{self.lambda_c:.5f}:{self.gamma:.5f}:{self.xi:.5f}:"
            f"{self.w2_distance:.5f}:{self.shannon_entropy:.5f}:"
            f"{self.substrate_node}:{self.telemetry_source}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_seq": self.frame_seq,
            "timestamp": self.timestamp,
            "phi": round(self.phi, 6),
            "lambda_c": round(self.lambda_c, 6),
            "gamma": round(self.gamma, 6),
            "xi": round(self.xi, 6),
            "w2_distance": round(self.w2_distance, 6),
            "shannon_entropy": round(self.shannon_entropy, 6),
            "consciousness_state": self.consciousness_state,
            "substrate_node": self.substrate_node,
            "telemetry_source": self.telemetry_source,
            "digest": self.digest,
        }

    def to_sse_event(self) -> str:
        data = json.dumps(self.to_dict())
        return f"event: ccce_frame\ndata: {data}\n\n"


@dataclass
class FeedbackAction:
    """Action proposed by the CCCE closed-loop feedback controller."""
    action_type: str
    target_parameter: str
    old_value: Any
    new_value: Any
    reason: str
    timestamp: float = field(default_factory=time.time)
    receipt_hash: str = ""

    def __post_init__(self):
        if not self.receipt_hash:
            payload = f"{self.action_type}:{self.target_parameter}:{self.old_value}:{self.new_value}:{self.timestamp}"
            self.receipt_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target_parameter": self.target_parameter,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "receipt_hash": self.receipt_hash,
        }


class PCRBTelemetryLedger:
    """Tamper-evident append-only ledger for CCCE and PCRB telemetry."""

    def __init__(self, ledger_path: Optional[Path] = None):
        default_ledger = os.environ.get(
            "OSIRIS_PCRB_LEDGER",
            str(Path.home() / ".osiris" / "evidence" / "pcrb_telemetry_ledger.jsonl"),
        )
        self.ledger_path = ledger_path or Path(default_ledger)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_hash: str = "0" * 64
        self._lock = threading.Lock()

    def log_frame(self, frame: CCCEMetricFrame) -> Dict[str, Any]:
        with self._lock:
            record_id = f"PCRB-TR-{frame.frame_seq:08d}"
            payload_str = json.dumps(frame.to_dict(), sort_keys=True)
            entry_hash = hashlib.sha256(f"{self.last_hash}:{payload_str}".encode("utf-8")).hexdigest()

            entry = {
                "record_id": record_id,
                "timestamp": frame.timestamp,
                "prev_hash": self.last_hash,
                "entry_hash": entry_hash,
                "claim_ceiling": "LOCAL_TEST_RESULT",
                "deployment_authority": "NONE",
                "evidence_role": "SUPPORTING",
                "evidence_status": "SIMULATED" if "SIMULATED" in frame.telemetry_source else "MEASURED",
                "frame": frame.to_dict(),
            }

            self.last_hash = entry_hash
            try:
                with open(self.ledger_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except OSError:
                fallback_path = Path("/tmp/pcrb_telemetry_ledger.jsonl")
                try:
                    with open(fallback_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry) + "\n")
                except OSError:
                    pass

            return entry

    def log_feedback_action(self, action: FeedbackAction) -> Dict[str, Any]:
        with self._lock:
            record_id = f"PCRB-ACT-{int(action.timestamp * 1000)}"
            payload_str = json.dumps(action.to_dict(), sort_keys=True)
            entry_hash = hashlib.sha256(f"{self.last_hash}:{payload_str}".encode("utf-8")).hexdigest()

            entry = {
                "record_id": record_id,
                "timestamp": action.timestamp,
                "prev_hash": self.last_hash,
                "entry_hash": entry_hash,
                "action": action.to_dict(),
            }

            self.last_hash = entry_hash
            try:
                with open(self.ledger_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except OSError:
                fallback_path = Path("/tmp/pcrb_telemetry_ledger.jsonl")
                try:
                    with open(fallback_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry) + "\n")
                except OSError:
                    pass

            return entry


class CCCEFeedbackController:
    """
    Closed-loop feedback controller that inspects real-time CCCE metrics
    and dynamically tunes dynamical decoupling parameters (XY4/CPMG, pulse delay,
    phase conjugate mirror) to stabilize Γ against Γ_floor = 0.092.
    """

    def __init__(
        self,
        gamma_threshold: float = PCRB_THRESHOLD,
        gamma_floor: float = GAMMA_FIXED,
        w2_threshold: float = 0.10,
        theta_lock: float = THETA_LOCK,
        ledger: Optional[PCRBTelemetryLedger] = None,
    ):
        self.gamma_threshold = gamma_threshold
        self.gamma_floor = gamma_floor
        self.w2_threshold = w2_threshold
        self.theta_lock = theta_lock
        self.ledger = ledger

        # Active tuning state
        self.active_decoupling = "XY4"
        self.pulse_interval_ns = 25.0
        self.phase_lock_deg = theta_lock
        self.total_interventions = 0
        self.last_action: Optional[FeedbackAction] = None

        # Recursion bus
        self.recursion_bus = RecursionBus() if RecursionBus else None

    def evaluate_frame(self, frame: CCCEMetricFrame) -> Optional[FeedbackAction]:
        """Examines the frame and returns an adaptive tuning action if anomalies are detected."""
        action: Optional[FeedbackAction] = None

        # 1. Check decoherence rate spike (Γ > threshold)
        if frame.gamma > self.gamma_threshold:
            # Scale pulse interval down to increase dynamical decoupling frequency
            ratio = max(0.2, self.gamma_floor / max(1e-5, frame.gamma))
            new_interval = round(max(5.0, self.pulse_interval_ns * ratio), 2)
            
            # Switch decoupling scheme if severely elevated
            new_scheme = "WALSH_16" if frame.gamma > 0.25 else ("CPMG" if self.active_decoupling == "XY4" else "XY4")
            
            action = FeedbackAction(
                action_type="INJECT_DYNAMICAL_DECOUPLING",
                target_parameter="pulse_interval_ns",
                old_value=self.pulse_interval_ns,
                new_value=new_interval,
                reason=f"Decoherence rate Γ={frame.gamma:.4f} exceeded threshold {self.gamma_threshold:.4f}. Adjusted decoupling to {new_scheme} at {new_interval}ns.",
            )
            self.pulse_interval_ns = new_interval
            self.active_decoupling = new_scheme
            self.total_interventions += 1

        # 2. Check Wasserstein-2 anomaly (W_2 > threshold) against golden-ratio state
        elif frame.w2_distance > self.w2_threshold:
            # Propose Wheeler-DeWitt phase conjugate holonomy correction
            delta_phase = 0.5 * (self.theta_lock - self.phase_lock_deg)
            new_phase = round(self.phase_lock_deg + delta_phase, 3)
            action = FeedbackAction(
                action_type="PHASE_CONJUGATE_RECALIBRATION",
                target_parameter="phase_lock_deg",
                old_value=self.phase_lock_deg,
                new_value=new_phase,
                reason=f"Wasserstein distance W_2={frame.w2_distance:.4f} exceeded threshold {self.w2_threshold:.4f}. Recalibrated phase lock to {new_phase}°.",
            )
            self.phase_lock_deg = new_phase
            self.total_interventions += 1

        if action:
            self.last_action = action
            if self.ledger:
                self.ledger.log_feedback_action(action)

        return action

    def get_state(self) -> Dict[str, Any]:
        return {
            "active_decoupling": self.active_decoupling,
            "pulse_interval_ns": self.pulse_interval_ns,
            "phase_lock_deg": self.phase_lock_deg,
            "gamma_threshold": self.gamma_threshold,
            "gamma_floor": self.gamma_floor,
            "w2_threshold": self.w2_threshold,
            "total_interventions": self.total_interventions,
            "last_action": self.last_action.to_dict() if self.last_action else None,
        }


class CCCEMetricStreamer:
    """
    Real-time CCCE metric streaming engine.
    Supports continuous generator feeds, buffering, and SSE / REST server endpoints.
    """

    def __init__(
        self,
        hardware_profile: Optional[Any] = None,
        controller: Optional[CCCEFeedbackController] = None,
        ledger: Optional[PCRBTelemetryLedger] = None,
    ):
        if hardware_profile is None and HardwareMeshDetector:
            self.profile = HardwareMeshDetector.detect()
        else:
            self.profile = hardware_profile

        self.ledger = ledger or PCRBTelemetryLedger()
        self.controller = controller or CCCEFeedbackController(ledger=self.ledger)

        # Dual-substrate configuration
        node_val = getattr(self.profile, "node_type", None)
        node_name = getattr(node_val, "value", str(node_val)) if node_val else "NODE_GENERIC_EDGE"
        self.node_type_name = node_name

        if "ALPHA" in self.node_type_name or "MOBILE" in self.node_type_name:
            self.max_buffer_size = 50
            self.temporal_horizon_s = 300.0
        else:
            self.max_buffer_size = 500
            self.temporal_horizon_s = 1800.0

        self.buffer: List[CCCEMetricFrame] = []
        self._seq = 0
        self._lock = threading.Lock()
        self._running = False
        self._server: Optional[ThreadingHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    @staticmethod
    def compute_shannon_entropy(distribution: List[float]) -> float:
        """Computes empirical Shannon entropy in bits: -sum(p * log2(p))."""
        s = 0.0
        total = sum(distribution)
        if total <= 0.0:
            return 0.0
        for p in distribution:
            if p > 0.0:
                prob = p / total
                s -= prob * math.log2(prob)
        return float(s)

    @staticmethod
    def compute_w2_distance(distribution: List[float]) -> float:
        """
        Pure NumPy / Python 1D Wasserstein-2 distance against the normalized
        golden-ratio distribution target (φ-scaled partition).
        """
        n = len(distribution)
        if n == 0:
            return 0.0
        total = sum(distribution)
        if total <= 0.0:
            return 0.0
        norm_dist = [x / total for x in distribution]

        # Ideal phi distribution: weights decaying by 1/phi^i
        raw_phi = [1.0 / (GOLDEN_RATIO ** i) for i in range(n)]
        sum_phi = sum(raw_phi)
        target_phi = [p / sum_phi for p in raw_phi]

        # 1D Wasserstein-2 distance: sqrt(sum((CDF_actual - CDF_target)^2) / n)
        cdf_act = 0.0
        cdf_tgt = 0.0
        accum_sq_diff = 0.0
        for a, t in zip(norm_dist, target_phi):
            cdf_act += a
            cdf_tgt += t
            diff = cdf_act - cdf_tgt
            accum_sq_diff += diff * diff

        return float(math.sqrt(accum_sq_diff / n))

    def generate_frame(
        self,
        distribution: Optional[List[float]] = None,
        source: str = "SYNTHETIC_LATTICE",
        base_gamma: Optional[float] = None,
    ) -> Tuple[CCCEMetricFrame, Optional[FeedbackAction]]:
        """Generates a single CCCE frame, computes metrics, checks feedback, and logs to ledger."""
        with self._lock:
            self._seq += 1
            now = time.time()

            # Default 8-element probability distribution if none provided
            if not distribution:
                # Stochastic distribution exhibiting natural drift
                t_phase = (now % 60.0) / 60.0 * 2 * math.pi
                raw = [
                    abs(math.sin(t_phase + i * 0.785)) + 0.1 * math.cos(i * 1.618)
                    for i in range(8)
                ]
                distribution = [max(0.01, r) for r in raw]

            shannon_ent = self.compute_shannon_entropy(distribution)
            w2_dist = self.compute_w2_distance(distribution)

            # Compute Φ (Connectivity/Entanglement proxy)
            # Normalized mutual information proxy across bipartite split
            half = len(distribution) // 2
            s_left = self.compute_shannon_entropy(distribution[:half])
            s_right = self.compute_shannon_entropy(distribution[half:])
            mi = max(0.0, (s_left + s_right) - shannon_ent)
            phi = float(min(1.0, mi / max(1e-4, math.log2(len(distribution)))))

            # Compute Γ (Decoherence rate)
            if base_gamma is not None:
                gamma = float(base_gamma)
            else:
                # Oscillates around fixed floor 0.092 with occasional fluctuation
                fluctuation = 0.015 * math.sin(now * 0.5) + 0.005 * math.cos(now * 1.3)
                gamma = float(max(0.02, self.controller.gamma_floor + fluctuation))

            # Compute Λ (Coherence preservation fidelity)
            lambda_c = float(max(0.05, min(1.0, 1.0 - (gamma * 1.5) + 0.05 * phi)))

            # Compute Ξ (Negentropic efficiency)
            epsilon = 1e-6
            xi = float((lambda_c * phi) / (gamma + epsilon))

            # Determine consciousness state
            if phi >= 0.95 and xi > 10.0:
                c_state = ConsciousnessState.TRANSCENDENT.value
            elif phi >= PHI_CONSCIOUSNESS_THRESHOLD:
                c_state = ConsciousnessState.CONSCIOUS.value
            elif phi >= 0.5:
                c_state = ConsciousnessState.NASCENT.value
            elif phi >= 0.3:
                c_state = ConsciousnessState.EMERGING.value
            else:
                c_state = ConsciousnessState.DORMANT.value

            frame = CCCEMetricFrame(
                frame_seq=self._seq,
                timestamp=now,
                phi=phi,
                lambda_c=lambda_c,
                gamma=gamma,
                xi=xi,
                w2_distance=w2_dist,
                shannon_entropy=shannon_ent,
                consciousness_state=c_state,
                substrate_node=self.node_type_name,
                telemetry_source=source,
            )

            # Check closed-loop feedback controller
            action = self.controller.evaluate_frame(frame)

            # Append to in-memory sliding buffer
            self.buffer.append(frame)
            if len(self.buffer) > self.max_buffer_size:
                self.buffer.pop(0)

            # Commit to ledger
            self.ledger.log_frame(frame)

            return frame, action

    def get_latest_frame(self) -> Optional[CCCEMetricFrame]:
        with self._lock:
            return self.buffer[-1] if self.buffer else None

    def get_history(self, limit: int = 50) -> List[CCCEMetricFrame]:
        with self._lock:
            return list(self.buffer[-limit:])

    def stream_frames(
        self,
        count: Optional[int] = None,
        interval_s: float = 0.2,
        source: str = "SYNTHETIC_LATTICE",
    ) -> Iterator[Tuple[CCCEMetricFrame, Optional[FeedbackAction]]]:
        """Yields real-time frames periodically."""
        produced = 0
        while count is None or produced < count:
            frame, action = self.generate_frame(source=source)
            yield frame, action
            produced += 1
            if count is None or produced < count:
                time.sleep(interval_s)

    def start_sse_server(self, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
        """Starts a background HTTP / Server-Sent Events (SSE) server for external dashboards."""
        streamer_instance = self

        class CCCEHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress default noisy console access logging

            def do_GET(self):
                parsed = urlparse(self.path)

                if parsed.path == "/api/v1/ccce/metrics":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    latest = streamer_instance.get_latest_frame()
                    body = latest.to_dict() if latest else {"status": "NO_FRAMES"}
                    self.wfile.write(json.dumps(body, indent=2).encode("utf-8"))

                elif parsed.path == "/api/v1/ccce/status":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    status_payload = {
                        "substrate_node": streamer_instance.node_type_name,
                        "max_buffer_size": streamer_instance.max_buffer_size,
                        "temporal_horizon_s": streamer_instance.temporal_horizon_s,
                        "buffer_length": len(streamer_instance.buffer),
                        "controller": streamer_instance.controller.get_state(),
                    }
                    self.wfile.write(json.dumps(status_payload, indent=2).encode("utf-8"))

                elif parsed.path == "/api/v1/ccce/stream":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    try:
                        while True:
                            latest = streamer_instance.get_latest_frame()
                            if latest:
                                self.wfile.write(latest.to_sse_event().encode("utf-8"))
                                self.wfile.flush()
                            time.sleep(0.5)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Endpoint not found")

            def do_POST(self):
                parsed = urlparse(self.path)
                if parsed.path == "/api/v1/ccce/feedback/tune":
                    # Force a feedback tuning evaluation
                    latest = streamer_instance.get_latest_frame()
                    if latest:
                        action = streamer_instance.controller.evaluate_frame(latest)
                        res = {"status": "SUCCESS", "action": action.to_dict() if action else None}
                    else:
                        res = {"status": "NO_FRAME_AVAILABLE"}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(res, indent=2).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

        server = ThreadingHTTPServer((host, port), CCCEHandler)
        self._server = server
        self._server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._server_thread.start()
        return server

    def stop_sse_server(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def format_cli_frame(frame: CCCEMetricFrame, action: Optional[FeedbackAction] = None) -> str:
    """Renders a single frame in the compact OSIRIS terminal format."""
    c_color = {
        "dormant": "\033[90m",
        "emerging": "\033[33m",
        "nascent": "\033[36m",
        "conscious": "\033[32m",
        "transcendent": "\033[35m",
    }.get(frame.consciousness_state, "\033[0m")
    reset = "\033[0m"

    line = (
        f"[CCCE #{frame.frame_seq:04d} | {frame.substrate_node}] "
        f"Φ: {frame.phi:.4f} | "
        f"Λ: {frame.lambda_c:.4f} | "
        f"Γ: {frame.gamma:.4f} | "
        f"Ξ: {frame.xi:.2f} | "
        f"W₂: {frame.w2_distance:.4f} | "
        f"H: {frame.shannon_entropy:.2f}b | "
        f"State: {c_color}{frame.consciousness_state.upper()}{reset}"
    )
    if action:
        line += f"\n  └─► \033[31m[ADAPTIVE TUNE]\033[0m {action.action_type}: {action.reason}"
    return line


if __name__ == "__main__":
    streamer = CCCEMetricStreamer()
    print("Starting OSIRIS CCCE Real-Time Metric Stream (10 frames preview):")
    for frame, action in streamer.stream_frames(count=10, interval_s=0.1):
        print(format_cli_frame(frame, action))
