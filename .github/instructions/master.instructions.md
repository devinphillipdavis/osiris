OSIRIS Architecture Group: System Context, Governance Protocol, and AI Development Guidelines

1. Core System Axioms and Non-Negotiable Governance Framework

1.1. Context & Strategic Importance Mandate

The OSIRIS architecture is built upon an absolute, non-negotiable operational axiom: "Models propose; deterministic code decides, measures, and records." Generative Artificial Intelligence systems and Large Language Models (LLMs) operate fundamentally as dynamic, non-deterministic proposal engines. Consequently, untrusted generative models must never hold direct execution authority, self-certification privileges, or unmediated access to low-level hardware and host infrastructure. Because probabilistic language models are susceptible to hallucination, context drift, silent failure modes, and uncalibrated optimism, all proposed software mutations, terminal commands, and structural configuration changes must be intercepted at a deterministic boundary. The local deterministic runtime enforces immutable governance rules, performs static Abstract Syntax Tree (AST) analysis, evaluates empirical outcomes against formal pre-registered bounds, and records cryptographically signed receipts to an append-only ledger before any side effect or state transition is committed.

1.2. The Command Interposition Layer (CIL) Execution Pipeline

To guarantee absolute runtime execution safety, every incoming system directive, script invocation, and agent-generated shell command is intercepted prior to reaching host processes by a fail-closed, 7-Layer Command Interposition Layer (dna_cli/cil.py / Command Interposition Layer). Operating under a strict deny-by-default posture, the CIL evaluates commands sequentially from Layer 0 through Layer 6. If a directive fails evaluation or violates schema boundaries at any layer, the pipeline immediately halts execution, invalidates the request, and logs the refusal artifact. Invalid token syntax or unmapped intent categories deterministically trigger a fail-closed rejection.

CIL Layer	Layer Name	Validation Function	Operational Risk Evaluation	Fail-Closed Action
L0	Syntax Sanity	Intercepts raw CLI strings; verifies structural formatting, bracket bounds, and DECSET 2004 escape sequences.	SAFE	Rejects malformed strings and aborts process spawning.
L1	Intent Classification	Classifies requested actions into discrete operational intent vectors (READ, WRITE, DESTRUCTIVE).	SAFE to LOW	Flags unmapped intent patterns; blocks execution if intent is unclassified.
L2	Context Binding	Validates environment variables, current working directories, workspace boundaries, and role scopes.	LOW to MEDIUM	Restricts execution paths strictly to allowlisted, mutable workspace directories.
L3	Risk Scoring	Computes normalized risk vectors based on path sensitivity, privilege level, and system resource impact.	MEDIUM to HIGH	Terminates evaluation if calculated risk vector exceeds configured safety caps.
L4	Enhancement Synthesis	Injects explicit runtime sandboxing flags, resource budgets, CPU/memory quotas, and isolation bounds.	MEDIUM	Appends forced isolation parameters and resource constraints to payload.
L5	Deterministic Rewrite	Rewrites hazardous, un-sanitized commands into safe, deterministic execution primitives.	HIGH to CRITICAL	Deterministically maps destructive commands (e.g., rewriting rm directly to trash-put).
L6	Execution & Telemetry	Dispatches rewritten payload within an isolated runtime container; captures stdout, stderr, and SHA-256 digests.	CRITICAL	Commits immutable execution receipts to the write-ahead evidence ledger.

1.3. Threshold Provenance & Refuted Parameters

System safety requires absolute fidelity to versioned governance parameters defined in policy.json v3. Theoretical conjectures, historical parameters, and speculative mathematical constructs are continuously evaluated against empirical ground truth. Any attempt by an LLM or legacy config to elevate refuted theoretical parameters into execution gates is blocked at runtime:

* theta_lock (51.843^\circ): Explicitly refuted as an operational execution or recovery threshold. Policy enforcement forces operational_allowed = False and is_allowed_as_recovery_gate() = False. This rule programmatically overrides legacy configuration entries or speculative notes attempting to utilize 51.843^\circ as a state recovery gate or operational authorization clearance.
* Gamma (0.95): Verified operational threshold (operational_allowed = True), governing physical system stability baselines and state assessment gates.
* NCLM Speaking Gate: The Non-Causal Living Language Model (osiris.nclm) operates under a code-enforced output speaking gate (osiris_cli_core/nclm_gate.py). The core model is strictly prohibited from emitting responses in its own voice until it achieves a compression loss of \le 2.0 bits/byte (BPB) across 30 held-out text exchanges, evaluating significantly below the unigram baseline (5.03 bits/byte). Current Operational Status: The measured performance of the core NCLM model stands at 7.6 bits/byte (versus the 5.03 bits/byte baseline). Consequently, the NCLM speaking gate remains strictly closed. All conversational system outputs default to labeled mentor model responses (e.g., local Ollama/Qwen instances) acting as unpromoted assistants.

1.4. Section Transition

Having established these non-negotiable governance boundaries and command interposition pipelines, the architecture enforces these rules directly upon physical execution resources via its dual-substrate hardware mesh.

2. Dual-Substrate Hardware Mesh and Execution Invariants

2.1. Context & Strategic Importance Mandate

The OSIRIS framework relies on a dual-substrate hardware execution architecture managed dynamically by osiris_hardware_mesh.py. Environment switching at runtime is an operational imperative to eliminate hardcoded path vulnerabilities (such as static references to ~/fold/), preserve hardware sovereignty, and maintain strict resource constraints across mobile edge endpoints and high-performance compute workstations.

2.2. Substrate Profile Mapping

The runtime environment dynamically routes workloads to Node Alpha or Node Beta based on hardware detection, thermal thresholds, and compute requirements:

Operational Constraint / Feature	Node Alpha (Mobile Edge Substrate)	Node Beta (Compute Workstation Substrate)
Target Platform	Android Termux / ARM64 Architecture	WSL / x86_64 Compute Workstation
Hardware Acceleration	NEON SIMD Vector Acceleration	AVX2 / AVX-VNNI Instruction Sets
Thermal Ceiling	42^\circ\text{C} Maximum Operating Temperature	Unconstrained Workstation Thermal Ceiling
Execution Horizon	300-Second Temporal Execution Lock	1800-Second High-Throughput Execution Horizon
Primary Workload Role	Local AST Parsing & Lightweight Edge Orchestration	Qiskit Runtime QPU Dispatch & Batch Tensor Simulation
Storage & Memory Footprint	Bounded In-Memory Buffers & Local JSONL	High-Throughput Matrix Storage & Large Multi-Qubit Workloads

2.3. Dynamic Runtime Detection & Failover Protocols

All script executions, code proposals, and background agent tasks must inspect host hardware state at runtime using detect_substrate(). Hardcoded local paths, static user directories, or assumed package installations are strictly prohibited.

When selecting execution paths, osiris_hardware_mesh.py evaluates system architecture and environmental telemetry. If Node Alpha breaches its 42^\circ\text{C} thermal ceiling, exceeds its 300-second temporal lock, or encounters spatial decoherence, the runtime triggers failover protocols. The system injects Wheeler-DeWitt holonomy corrections or XY4 dynamical decoupling when the calculated Wasserstein-2 (W_2) probability distance between physical execution outputs and logical manifold states exceeds 0.1. State transitions are driven deterministically by QbyteRuntime across the following explicit state matrix:

\text{INITIALIZING} \longrightarrow \text{READY} \longrightarrow \text{RUNNING} \longrightarrow \text{DEGRADED} \longrightarrow \text{ROLLBACK\_PENDING} \longrightarrow \text{RECOVERING} / \text{QUARANTINED}

If thermal limits or error thresholds remain breached, non-essential edge workloads are suspended, state snapshots are saved to local storage, and heavy tensor processes are transferred to Node Beta.

2.4. Section Transition

These physical substrate boundaries and dynamic runtime invariants establish the baseline operational environment for developer coding standards and static analysis verification.

3. Developer Coding Guidelines & AST Security Constraints

3.1. Context & Strategic Importance Mandate

To maintain codebase safety and execution predictability, OSIRIS enforces static Abstract Syntax Tree verification (ast_verify.py) and capability firewalls. By inspecting source code structures prior to compilation, staging, or execution, the system maintains hermetic software safety, prevents command injection, and blocks unauthorized modifications to system governance rules.

3.2. Prohibited Syntax and AST Denylists

Code proposed by AI agents or human developers must adhere to strict AST structural allowlists enforced by ast_verify.py. The parser evaluates code against internal inspection rules (_ALLOWED_IMPORTS, _FORBIDDEN_NODES, _FORBIDDEN_CALL_NAMES). Any submission containing prohibited syntax is instantly rejected:

# ==============================================================================
# OSIRIS STRICT AST PROHIBITED CONSTRUCTS DENYLIST (ast_verify.py)
# ==============================================================================

# 1. Dynamic Execution Primitives (_FORBIDDEN_CALL_NAMES -> Rejection)
exec(...)
eval(...)
compile(...)

# 2. Un-sanitized Subprocess Invocations & Direct Shell Escapes (_FORBIDDEN_NODES)
os.system(...)
subprocess.Popen(..., shell=True)
subprocess.run(..., shell=True)

# 3. Modification of Immutable System Artifacts (Raises IMMUTABLE_PATH_MODIFIED)
open("policy.json", "w")
open("tests/core_test.py", "w")
open("cloudbuild.yaml", "w")
open("QUARANTINE_NOTICE.md", "w")

# 4. Mock Backend Disguises & Synthetic Data Misrepresentation (backend_truth.py)
# REJECTED: Disguising simulated outputs as physical QPU hardware results
class MockQPUBackend(PhysicalQPU):
    """Triggers IMMUTABLE_PATH_MODIFIED / MOCK_DISGUISE_FIREWALL exception."""
    pass


3.3. Proposal Verification & Hermetic Test Pipeline

All code changes, bug fixes, and feature additions must proceed sequentially through the 9-step Engineering Sprint Workflow:

1. Discover: Identify defects, architectural gaps, or performance bottlenecks via static analysis.
2. Specify: Define precise acceptance criteria, scope boundaries, and capability requirements.
3. Failing Test: Construct an isolated unit test reproducing the defect or specifying new functionality.
4. Patch Proposal: Generate minimal code modifications restricted strictly to permitted, mutable workspace paths.
5. Sandbox Run: Apply candidate patches inside a disposable, isolated staging worktree.
6. Diff Review: Perform static inspection of proposed unified diffs against protected system boundaries.
7. Regression Testing: Execute the full verification suite (pytest) in the isolated sandbox.
8. Evidence Recording: Capture execution logs, resource consumption, and SHA-256 patch digests.
9. Promotion Request: Submit verified evidence artifacts to the human-in-the-loop promotion gate.

Candidate code must pass all zero-exit-code correctness tests (pytest) and demonstrate statistically significant performance gains (e.g., \Delta \ge 5\% at p < 0.01 across N \ge 30 iterations) before human approval can be requested.

3.4. Section Transition

Transitioning from codebase static security, edge ingestion protocols enforce identical zero-leak policies for real-time user inputs.

4. Edge Ingestion Protocols: Memory AST, Bluetooth SCO, and Resilient IPC

4.1. Context & Strategic Importance Mandate

Mobile edge data collection (Node Alpha) requires a local-first, zero-leak ingestion architecture for text and voice streams. Standard operating system storage mechanisms—specifically the global system clipboard—are completely bypassed to protect user privacy, prevent credential harvesting, and ensure the structural integrity of ingested data.

4.2. Android IME In-Memory AST Capture (OsirisIME.kt)

Text selected or typed on mobile edge devices is processed through a custom Android Input Method Editor (OsirisIME.kt). The pipeline lexes text directly into memory without writing to system clipboard buffers:

+──────────────────────────────+
│   User Text Selection Event  │
+──────────────┬───────────────+
               │
               ▼
+──────────────────────────────+
│ InputMethodService Trigger   │ ──> InputConnection.getSelectedText(0)
+──────────────┬───────────────+
               │
               ▼
+──────────────────────────────+
│ In-Memory Lexing & DAG Build │ ──> Scope Hierarchy, Parent-Child Links,
+──────────────┬───────────────+     Source URI, UTC Nanosecond Timestamps
               │
               │ (System ClipboardManager Bypassed)
               ▼
+──────────────────────────────+
│  Framed JSON-RPC Serializer  │
+──────────────┬───────────────+
               │
               ▼
+──────────────────────────────+
│  Unix Domain Socket (UDS)    │ ──> $PREFIX/tmp/osiris.sock
+──────────────────────────────+     (File Permissions: 0600)


Ingested text transitions through explicit state machine boundaries managed by osiris_cli_core/ipc.py:

\text{STATE\_INGESTION} \longrightarrow \text{STATE\_PARSING} \longrightarrow \text{STATE\_AST\_CONSTRUCTION} \longrightarrow \text{STATE\_PRE\_FLIGHT\_EVALUATION} \longrightarrow \text{STATE\_LEDGER\_COMMIT}

4.3. Hands-Free Bluetooth Peripheral SCO Audio Pipeline

Voice data ingestion utilizes Bluetooth Synchronous Connection-Oriented (SCO) audio channels for hands-free, zero-cloud input:

* Audio Configuration: Locks the AudioManager into HFP/SCO mode (startBluetoothSco(), setBluetoothScoOn(true)), capturing raw audio into a 16kHz mono 16-bit PCM buffer.
* On-Device Local Inference: Feeds PCM buffers directly to local speech-to-text engines (Whisper TFLite or VOSK) running inside Termux, operating with zero external network connectivity.
* AVRCP Hardware Button Controls:
  * Double-Tap: Triggers the Voice AST capture buffer (start_voice_capture).
  * Triple-Tap: Forces an immediate ledger commit and system checkpoint (force_commit).

4.4. IPC Exception Handling and Overflow Protection

Inter-process communication between Android services and the Python background daemon is managed by osiris_cli_core/ipc.py:

* Exponential Backoff: Connection failures on socket bind/accept operations trigger exponential backoff delays starting at 0.1\text{s} up to 5.0\text{s}.
* Circular Buffer Management: Incoming text and audio AST streams populate an in-memory CircularBuffer constrained to a maximum size of 2048 items (maxlen=2048). Upon reaching capacity, the buffer drops the oldest head entries (drop-head) to prevent process memory exhaustion. On socket reconnection, the buffer executes a complete batch flush (pop_all).
* Fallback Disk Logging: Extended UDS disconnections cause the IPC layer to append pending payloads to a local fallback log (osiris_ime_buffer.jsonl), preserving data integrity without crashing the daemon.

4.5. Section Transition

These edge ingestion mechanics supply structured input data directly to cryptographic logging engines and pre-registered scientific ledgers.

5. Scientific Rigor, Empirical Truth Boundaries, and Cryptographic Provenance

5.1. Context & Strategic Importance Mandate

OSIRIS mandates a zero-trust benchmarking framework. Retrospective parameter tuning, post-hoc curve fitting, and synthetic data substitution are explicitly forbidden. All empirical assertions, software mutations, and experimental predictions must be committed to an append-only cryptographic ledger prior to execution.

5.2. Evidence Ledger & Write-Ahead Hash Chaining

The cryptographic provenance layer (osiris_ledger / EvidenceLedger) maintains an immutable record of system state transitions:

* RFC 8785 Serialization: All ledger payloads undergo strict canonical JSON serialization adhering to RFC 8785 specifications to ensure byte-level reproducibility across heterogeneous nodes.
* Predecessor Hash Chaining: Ledger records are appended to ledger.jsonl. Each entry binds its sequence number (seq), payload SHA-256 hash (payload_hash), node identifier (node_id), and predecessor entry hash (prev_hash).
* Epistemic Claim Categories: All claims recorded in the ledger must be explicitly classified into one of seven valid claim states:
  1. IMPLEMENTED — Functional code deployed in the repository.
  2. SIMULATED — Computational outputs derived from classical mathematical models.
  3. MEASURED — Observations captured directly from live hardware execution.
  4. REPRODUCED — Independent replication confirming previously measured results.
  5. VERIFIED — Formally validated claims satisfying all specification gates.
  6. UNRESOLVED — Active hypotheses or experiments undergoing evaluation.
  7. FALSIFIED — Hypotheses or claims explicitly refuted by empirical data.

5.3. Falsification Protocols and Mandatory Data Separation

Repository errata and experimental audits require strict separation between physical measurements and classical simulations:

* Synthetic Data Isolation: Classical simulation outputs must be isolated from physical Quantum Processing Unit (QPU) measurements. Disguising simulated data as physical QPU hardware results is strictly prohibited (backend_truth.py).
* Errata & Finite-Sample Artifact Analysis (Zenodo Record 4.2.0): Analysis of physical dataset execution on target hardware ibm_kingston (156-qubit Heron r2 manifold, Job ID d7im8e7b91ec73b00pq0) established that the claimed 136-bit "negentropy gap" (156 - \log_2(\text{shots})) is a finite-sample artifact. Collecting 10^6 unique sample shots yields a joint entropy of 19.9316 bits (\log_2(10^6)), which represents the exact mathematical ceiling of plug-in entropy estimators when every sample shot in a dataset is unique. Applying the Miller–Madow estimator yields 20.65 bits, Chao–Shen is undefined at zero coverage, and per-qubit marginal entropies sum to 149.7 bits. Consequently, prior interpretations regarding macroscopic quantum attractors, manifold collapse, the 51.843^\circ lock angle, and non-thermalization were formally withdrawn.
* Hardware Fidelity Rules: Physical Bell state measurements must be validated against the theoretical maximum fidelity bound:

F_{\text{max}} = 1 - \phi^{-8} \approx 0.9787

5.4. Distributed Multi-Node Consensus

To maintain ledger consistency across distributed deployments, state synchronization is governed by osiris_cli_core/consensus.py:

* Consensus Engine: Implements lightweight Raft/PBFT state synchronization across edge nodes (Node Alpha) and compute nodes (Node Beta).
* Ed25519 Multi-Signature Quorum: High-privilege state operations (rollback_executed, genome_promote, release_promote, policy_update) require cryptographic multi-signatures managed by QuorumValidator(peers, quorum=2). State entries (LedgerEntry(seq, prev_hash, node_id, payload_hash)) require verification from a minimum of 2 authorized nodes before commit:

+───────────────────────────────────────────────────+
│ High-Privilege Directive (e.g., policy_update)    │
+─────────────────────────┬─────────────────────────+
                          │
                          ▼
+───────────────────────────────────────────────────+
│ Local Node Ed25519 Signature Generation           │
+─────────────────────────┬─────────────────────────+
                          │
                          ▼
+───────────────────────────────────────────────────+
│ Multi-Node Consensus Broadcast (consensus.py)     │
+─────────────────────────┬─────────────────────────+
                          │
                          ▼
+───────────────────────────────────────────────────+
│ Peer Node Signature & Snapshot Verification       │
+─────────────────────────┬─────────────────────────+
                          │
                          ▼
+───────────────────────────────────────────────────+
│ Quorum Met (>= 2 Signatures) -> Commit to Ledger  │
+───────────────────────────────────────────────────+


5.5. Section Transition

These scientific verification standards and cryptographic ledgers form the core foundation for commercial enterprise deployment frameworks.

6. Enterprise Deployment Architecture and Commercial Integration

6.1. Context & Strategic Importance Mandate

The migr8 pilot cockpit and cloud adapter boundaries serve as the operational bridge for translating deep-tech research into governed, measurable customer enterprise migrations. The framework guarantees that commercial deployments remain reproducible, sandboxed, and auditable across every phase of implementation.

6.2. The migr8 6-Week Pilot Framework & Gate Architecture

Commercial customer engagements follow a strict 6-week lifecycle governed by mandatory phase exit gates:

Timeline	Migration Phase	Primary Activity	Deliverable Artifact	Exit Governance Gate
Week 1	Discover	Workflow selection, dependency mapping, and baseline definition.	Pilot Specification v1	Gate 1: GO / REVISE
Week 2	Model	DNA-Lang representation and policy boundary design.	Versioned .dna Genome & SHA-256 Hash	Gate 2: GOVERNANCE PASS
Week 3	Execute	Controlled execution and telemetry capture in sandboxes.	Initial Evidence Dataset (Runs)	Gate 3: MEASUREMENT PASS
Week 4	Evaluate	Failure mode analysis, deterministic replay, and integrity audits.	Evidence Ledger & KPI Report	Gate 4: EVIDENCE REVIEW
Week 5	Reproduce	Independent replay within clean baseline environments.	Independent Reproduction Report	Gate 5: REPRODUCTION PASS
Week 6	Validate	Final recommendations, ROI evaluation, and customer decision.	Pilot Evidence Package	Gate 6: CUSTOMER VALIDATION

Customer engagements must comply with the 13-Point Technical Completion Checklist, enforcing Section 21 (Change Control Lineage Tracking: Pilot Spec v1 \rightarrow Genome v1 \rightarrow Genome v2), Section 22 (Dedicated Staffing Allocation across OSIRIS squad and customer leads), and Section 23 (Experimental Rigor for capturing failed hypotheses).

6.3. Cloud Provider & Boundary Isolation Protocols

Interfacing with secondary cloud infrastructure (such as Supabase or Google Cloud Platform) requires strict containment boundaries to protect system sovereignty:

* Ephemeral Cloud Role: Cloud services handle multi-agent routing, public dashboard hosting, and external analytics, but possess zero execution authority over local state, local hardware, or organism definitions.
* Secret Containment: Storing plaintext API keys, database connection strings (DSNs), or QPU access tokens in source repositories is strictly prohibited. Secrets are dynamically mounted at runtime via Secret Manager or masked environment variables.
* BigQuery Telemetry Offload: Non-sensitive operational metrics (CCCE summaries, UI event traces, public benchmark scores) stream to external analytical sinks (dnalang:osiris_evidence_ledger) for public review without exposing root signing keys or unredacted repositories.

6.4. Final Guideline Summary for AI Agents

Any incoming AI agent generating code, reviewing changes, or executing tasks within the OSIRIS ecosystem must strictly comply with the following 5-point checklist:

1. Verify Substrate Constraints First: Identify the active host platform via detect_substrate() and enforce Node Alpha (ARM64 edge) versus Node Beta (x86_64 compute) resource bounds before proposing operations.
2. Enforce AST Firewalls: Reject prohibited syntax constructs (exec, eval, compile, un-sanitized subprocess) and block edits to protected root files (policy.json, tests/core_test.py, cloudbuild.yaml, QUARANTINE_NOTICE.md).
3. Commit Pre-Flight Artifacts to the Ledger: Compute canonical RFC 8785 JSON hashes and commit SHA-256 digests to the write-ahead ledger prior to hardware execution or code promotion.
4. Never Substitute Synthetic Data for Hardware Claims: Keep classical simulation outputs isolated from physical QPU measurements; never represent simulated data as physical hardware results.
5. Maintain Fail-Closed Execution Boundaries: Ensure that deterministic code decides, measures, and records, maintaining generative language models strictly as unprivileged proposal engines.
