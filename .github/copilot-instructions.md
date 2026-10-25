# Copilot Instructions for This Repository (OSIRIS Sovereign Framework)
## Agile Defense Systems, LLC (CAGE: 9HUP5), Lexington, Kentucky
**Architect**: Devin Phillip Davis | **Version**: 4.5.0 / Dual-Node Master Spec v1.2  
**Epistemic Axiom**: *"Models propose; deterministic code decides, measures, and records."*

---

## 1. Build, Test, and Execution Commands

- **Python projects**: Use `pip install -e .[dev]` for development dependencies. Run tests with `pytest` or `python -m unittest`. Lint with `ruff check .` or `flake8` if configured.
- **Node.js projects**: Install dependencies with `npm install` or `yarn`. Run tests with `npm test` or `yarn test`. Lint with `npm run lint` or `yarn lint`.
- **Go projects**: Use `go test ./...` for tests and `golangci-lint run ./...` for linting.
- **.NET projects**: Use `dotnet test` for tests.
- **Makefile-based projects**: Run `make test`, `make lint`, or `make` for common tasks.
- **Justfile**: If present, use `just test`, `just lint`, or `just format` for unified commands.
- **To run a single test**: For Python, use `pytest path/to/test_file.py::test_function`.
- **Dual-Node Core & REPL**: `pytest tests/test_cil_and_ast_firewall.py -v`. Prompt contract: `osiris::}{> `.

---

## 2. Core System Axioms & Governance Framework

### 2.1. Model Boundary Invariant
Generative AI models (LLMs, Copilot, Antigravity) are strictly **untrusted, non-deterministic proposal engines**. They possess **zero execution authority**, **zero self-certification privileges**, and **zero unmediated access** to host infrastructure, quantum QPUs, or low-level operating system resources.

### 2.2. The Command Interposition Layer (CIL) 7-Layer Pipeline (`core/cil.py` / `dna_cli/cil.py`)
All commands and tool actions are intercepted and evaluated sequentially from Layer 0 through Layer 6:
- **L0 (Syntax Sanity)**: Intercepts raw CLI strings; verifies structural formatting, bracket bounds (`()`, `[]`, `{}`), strips/neutralizes DECSET 2004 escape sequences (`\x1b[?2004h/l`), rejects null bytes.
- **L1 (Intent Classification)**: Classifies requested actions into discrete operational intent vectors (`READ`, `WRITE`, `DESTRUCTIVE`, `SLASH_COMMAND`). Unmapped intent fails closed.
- **L2 (Context Binding)**: Validates environment variables, current working directories, workspace boundaries, and role scopes. Strictly blocks hardcoded paths (e.g., `~/fold/`).
- **L3 (Risk Scoring)**: Computes normalized risk vectors (0.0 to 1.0) based on path sensitivity, privilege level, and system resource impact (`SAFE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **L4 (Enhancement Synthesis)**: Injects explicit runtime sandboxing flags, resource budgets, CPU/memory quotas, and isolation bounds.
- **L5 (Deterministic Rewrite)**: Rewrites hazardous, un-sanitized commands into safe, deterministic execution primitives (e.g., rewriting `rm -rf` directly to `trash-put`).
- **L6 (Execution & Telemetry)**: Dispatches rewritten payload within an isolated runtime container; captures stdout, stderr, and SHA-256 receipts committed to write-ahead cryptographic evidence ledger.

### 2.3. Parameter Refutations & Origin-Tag Strictures
- **$\theta_{\text{lock}} = 51.843^\circ$ Refutation**: Formally withdrawn per **Erratum v4.2.0 (Zenodo Record 10.5281/zenodo.19505923)**. `operational_allowed = False` and `is_allowed_as_recovery_gate() = False`. Any attempt by an LLM or legacy script to use $51.843^\circ$ as an operational gate is blocked at runtime.
- **136-bit Negentropy Gap Refutation**: Proven to be a finite-sample plug-in estimator artifact ($\log_2(10^6) = 19.93$ bits). Macroscopic quantum attractors and non-thermalization conjectures are permanently withdrawn.
- **$\Gamma_{\text{floor}} = 0.0920$ / $\Gamma = 0.95$**: Verified operational thresholds governing physical system stability baselines.
- **NCLM Speaking Gate**: The Non-Causal Living Language Model (`osiris.nclm`) operates under a code-enforced output speaking gate (`osiris_cli_core/nclm_gate.py`). The core model is strictly prohibited from emitting responses in its own voice until compression loss achieves $\le 2.0$ bits/byte (BPB) across 30 held-out text exchanges (current: 7.6 BPB vs 5.03 unigram baseline). All conversational outputs default to labeled mentor models (e.g., local Ollama/Qwen).
- **2026-10-11 W8L-1 Incident Precedent**: Model-supplied values must NEVER be accepted as authoritative governance parameters or confirmed constraints. All model-derived inputs are origin-tagged `MODEL_PROPOSED` and quarantined behind the SYS-024 Claims Firewall.

---

## 3. Dual-Substrate Hardware Mesh (`core/hardware_mesh.py`)

### 3.1. Substrate Profile Mapping

| Operational Constraint / Feature | Node Alpha (Mobile Edge Substrate) | Node Beta (Compute Workstation Substrate) |
| :--- | :--- | :--- |
| **Target Platform** | Android Termux / ARM64 Architecture (Pixel 10 Pro Fold) | WSL2 Ubuntu / Windows x86_64 (Intel Core Ultra) |
| **Hardware Acceleration** | NEON SIMD Vector Acceleration | AVX2 / AVX-VNNI Instruction Sets |
| **Thermal Ceiling** | $42^\circ\text{C}$ Maximum Operating Temperature | Unconstrained Workstation Thermal Ceiling |
| **Execution Horizon** | 300-Second Temporal Execution Lock | 1800-Second High-Throughput Execution Horizon |
| **Primary Workload Role** | Local AST Parsing & Lightweight Edge Orchestration | Qiskit Runtime QPU Dispatch & Batch Tensor Simulation |
| **Storage & Memory Footprint** | Bounded In-Memory Buffers & Local JSONL | High-Throughput Matrix Storage & Multi-Qubit Workloads |

### 3.2. Dynamic Detection & Manifold Stability
- Inspect host hardware at runtime using `detect_substrate()`. Zero hardcoded paths.
- Evaluates 1D Wasserstein-2 ($W_2$) distance. If $W_2 > 0.10$, injects Wheeler-DeWitt holonomy corrections and XY4 dynamical decoupling sequences.
- Deterministic state matrix:
  $$\text{INITIALIZING} \longrightarrow \text{READY} \longrightarrow \text{RUNNING} \longrightarrow \text{DEGRADED} \longrightarrow \text{ROLLBACK\_PENDING} \longrightarrow \text{RECOVERING} / \text{QUARANTINED}$$
- If thermal limits ($> 42^\circ\text{C}$) or execution time ($> 300\text{s}$) are breached on Node Alpha, non-essential edge workloads are suspended, snapshots are flushed to local JSONL, and heavy processes fail over to Node Beta.

---

## 4. AST Security Firewalls & Coding Standards (`core/ast_verify.py`)

- **Prohibited Dynamic Execution Primitives**:
  ```python
  exec(...)
  eval(...)
  compile(...)
  __import__(...)
  ```
- **Prohibited Subprocess Invocations**:
  ```python
  os.system(...)
  subprocess.Popen(..., shell=True)
  subprocess.run(..., shell=True)
  ```
- **Protected Immutable System Artifacts** (Raises `ImmutablePathModifiedError`):
  ```python
  open("policy.json", "w")
  open("tests/core_test.py", "w")
  open("cloudbuild.yaml", "w")
  open("QUARANTINE_NOTICE.md", "w")
  ```
- **Mock Backend Disguises Firewall** (Raises `MockDisguiseFirewallError`):
  ```python
  # REJECTED: Synthetic mock classes pretending to be physical QPU hardware
  class MockQPUBackend(PhysicalQPU):
      pass
  ```
- **9-Step Sprint Workflow**: Discover $\to$ Specify $\to$ Failing Test $\to$ Patch Proposal $\to$ Sandbox Run $\to$ Diff Review $\to$ Regression Testing $\to$ Evidence Recording $\to$ Promotion Request.

---

## 5. Edge Ingestion Protocols (Node Alpha)

- **Android IME In-Memory AST Capture (`OsirisIME.kt`)**: Ingests selected text via `InputConnection.getSelectedText(0)`, bypassing the Android `ClipboardManager`. Transmits structured ASTs over Unix Domain Socket (`$PREFIX/tmp/osiris.sock`, permissions `0600`).
- **Bluetooth SCO Audio**: Captures 16kHz mono 16-bit PCM buffers for local speech-to-text inference (Whisper TFLite / VOSK) with zero cloud network connectivity. Double-tap initiates voice capture; triple-tap triggers an immediate ledger commit.
- **Buffer Safety**: In-memory `CircularBuffer` capped at 2,048 entries (`maxlen=2048`) with drop-head eviction under backpressure. Extended socket disconnections spill to local `osiris_ime_buffer.jsonl`.

---

## 6. Scientific Rigor, QEC Pre-Registration & Cryptographic Provenance

### 6.1. QEC-REPL-1 Surface Code Replication
Independent replication of Google's 2022 surface-code scaling result (*Nature 614, 676–681*) adhering to binding pre-registered decision rules:
- **Scaling Regression Formula**:
  $$1 - 2\cdot p_L(r) = A \cdot (1 - 2\varepsilon)^r$$
  Fitted using Weighted Least Squares (WLS) on $\log(1 - 2\cdot p_L(r))$ with binomial weights across round counts $r \in \{1, 3, \dots, 25\}$.
- **Metric R1 (Software Reproducibility)**: Running open-source PyMatching on detection events with `circuit_detector_error_model.dem` must reproduce `obs_flips_predicted_by_pymatching.01` on $\ge 99.9\%$ of experimental shots.
- **Metric R2 (Scaling Independence)**: Replicated successfully only if the 95% bootstrap confidence interval (1,000 resamples at strict seed `20261008`) for $\Lambda = \varepsilon_3 / \varepsilon_5$ strictly excludes the baseline 1.0 ($\Lambda > 1$).
- **Metric R3 (Headline Parity)**: Fitted values must fall within twice the combined standard error of Google's published abstract results ($\varepsilon_5 = 2.914\% \pm 0.016\%$ and $\varepsilon_3 = 3.028\% \pm 0.023\%$).

### 6.2. W8L-1 QLDPC Campaign Freeze Strictures
- **Hermetically Sealed Git Commit**: Bound to `053c00b291fb2d0305d9bcd8771bb786fb5a2330`.
- **Resource Ceilings**: Strict 24.0 CPU-hour ceiling, 24.0 wall-clock ceiling, max 50 candidate permutations.
- **15 Release Gates (R1 to R15)**:
  - Gate R11: Statically bounds entropy seeds to `[101, 211, 307]`, strictly prohibiting "seed-shopping".
  - Gate R15: External human cryptographic authorization strictly required; autonomous launch prohibited.
- **Origin-Tag Invariant (SYS-024)**: Model-proposed parameters are quarantined. Models may not authoritatively supply or certify execution bounds.

### 6.3. 7 Epistemic Claim Categories & Ledger Integrity
All empirical records in `ledger.jsonl` use RFC 8785 canonical JSON serialization with SHA-256 predecessor hash chaining:
1. `IMPLEMENTED`: Functional code deployed in the repository.
2. `SIMULATED`: Computational outputs derived from classical mathematical models.
3. `MEASURED`: Observations captured directly from live physical hardware.
4. `REPRODUCED`: Independent replication confirming previously measured results.
5. `VERIFIED`: Formally validated claims satisfying all specification gates.
6. `UNRESOLVED`: Active hypotheses or experiments undergoing evaluation.
7. `FALSIFIED`: Hypotheses or claims explicitly refuted by empirical data.

*Bell State Fidelity Bound*: Physical measurements validated against:
$$F_{\text{max}} = 1 - \phi^{-8} \approx 0.9787$$

---

## 7. Enterprise Cloud Topologies & CI/CD Integrations (OSIRIS v4.5.0)

### 7.1. Migr8 6-Week Enterprise Pilot Framework

| Timeline | Migration Phase | Primary Activity | Deliverable Artifact | Exit Governance Gate |
| :--- | :--- | :--- | :--- | :--- |
| **Week 1** | **Discover** | Workflow selection, dependency mapping, baseline definition. | Pilot Specification v1 | **Gate 1**: GO / REVISE |
| **Week 2** | **Model** | DNA-Lang representation and policy boundary design. | Versioned `.dna` Genome & Hash | **Gate 2**: GOVERNANCE PASS |
| **Week 3** | **Execute** | Controlled execution and telemetry capture in sandboxes. | Initial Evidence Dataset | **Gate 3**: MEASUREMENT PASS |
| **Week 4** | **Evaluate** | Failure mode analysis, deterministic replay, integrity audits. | Evidence Ledger & KPI Report | **Gate 4**: EVIDENCE REVIEW |
| **Week 5** | **Reproduce** | Independent replay within clean baseline environments. | Reproduction Report | **Gate 5**: REPRODUCTION PASS |
| **Week 6** | **Validate** | Final recommendations, ROI evaluation, customer decision. | Evidence Package | **Gate 6**: CUSTOMER VALIDATION |

### 7.2. Google Cloud Platform (GCP) Topology & CI/CD Security
- **Cloud Run Execution**: Staging instances are severely restricted to 1GiB RAM, 1 vCPU, and `--max-instances=2` to mitigate denial-of-wallet vectors and agent resource runaway.
- **Vertex AI Gemini Integration**: When `OSIRIS_GCP_PROJECT` is set, LLM inquiries route via Vertex AI with IAM OAuth authentication, eliminating static API keys.
- **Secret Manager Integration**: When `OSIRIS_SECRETS_SOURCE=gcp` is active, configurations pool directly from Secret Manager targeting secrets labeled `osiris=env`. Plaintext secrets in source trees are eradicated.
- **Cloud Build (`cloudbuild.yaml`)**:
  - Executes parallel test matrices on Python 3.11 and 3.12.
  - Scans for leaked credential signatures (`sk-...`, `ibmq_...`).
  - Compiles immutable Docker containers tagged with the exact Git commit SHA. Zero-exit-code correctness is mandatory before container promotion.

---

## 8. The 5 Non-Negotiable Directives for AI Agents & Copilots

1. **Enforce Hardware Verification**: Actively detect host platform (`Node Alpha` vs `Node Beta`) via `detect_substrate()` before proposing operations or execution paths. Never hardcode static paths.
2. **Respect AST Firewalls**: Reject dynamic code execution (`exec`, `eval`, `compile`) and never mutate immutable governance artifacts (`policy.json`, `tests/core_test.py`, `cloudbuild.yaml`, `QUARANTINE_NOTICE.md`).
3. **Ensure Cryptographic Provenance**: Format ledger entries using RFC 8785 canonical JSON and commit verifiable SHA-256 digests to the write-ahead ledger prior to promotion or execution.
4. **Maintain Epistemic Integrity**: Maintain strict separation between classical simulations and physical hardware observations. Never substitute mocked simulation data for empirical hardware claims.
5. **Acknowledge The Execution Boundary**: Operate purely as an unprivileged proposal engine subject to the Command Interposition Layer (CIL L0–L6). Deterministic code decides, measures, and records.
