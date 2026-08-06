# 🤖 AMBU-CovAgent

> **LLM-driven functional coverage closure agent for hardware verification on SystemVerilog RTL (`cocotb` + Verilator).**

Given real RTL and a base testbench, this agent automatically generates
targeted directed tests to close functional coverage gaps — including
hard, CDC-timing-dependent bins that traditionally require manual
engineering effort. Verified across three architecturally distinct
designs (async FIFO, UART TX, AHB2APB bridge), reaching **100% coverage
on all three** with zero data-integrity failures in the base stimulus.

---

## 📄 Documentation

- 🔬 **[Research & Implementation Report](./AMBU-CovAgent_Research_and_Implementation_Report.md)**
  — full technical history: every bottleneck found, its root cause, its
  fix, its verification evidence, and the published research that
  informed it (v2.2 through v2.10.3.1).
- 🛡️ **[Phase 2 Roadmap](./ROADMAP_PHASE_2.md)**
  — planned future work: independent data-integrity verification of
  LLM-generated directed tests, and bounded, safeguarded LLM hardening.

---

## 🚀 Quick Start (GitHub Codespaces)

1. **Open in Codespaces:** Code → Codespaces → Create codespace on
   main.

   *The first build compiles Verilator, installs Python dependencies,
   and builds cocotb from scratch — this typically takes around **10
   minutes**. This is expected; it isn't stuck.*
2. **Confirm the environment**, once the Codespace finishes building:

```bash
which verilator
python3 -c "import cocotb; print(cocotb.__version__)"
```

   You should see a real path for `verilator` and `2.0.1` (or later)
   printed for cocotb. If either fails, the build likely hasn't
   finished yet — wait a little longer and try again.
   
3. **Get an API key.** Want to try the full agent yourself? Get a
   free/trial Claude API key at
   [console.anthropic.com](https://console.anthropic.com) — it only
   takes a minute.
   
5. **Add it as a Codespaces secret:**
   - Go to your GitHub account's
     [Codespaces secrets settings](https://github.com/settings/codespaces).
   - Click **New repository secret**.
   - **Name it exactly `ANTHROPIC_API_KEY`** — this matches what the
     agent's code reads directly (see the naming note below if you use
     a different name).
   - Paste your key as the value, and select this repository under
     "Repository access."
6. If your Codespace was already open before adding the secret, **stop
   and reopen it** — secrets are only injected into newly-started
   Codespaces, not live ones.

**Note on secret naming:** if your secret uses a custom name (for
example, `AMBU_API`), alias it in your terminal session rather than
renaming the secret itself:

```bash
export ANTHROPIC_API_KEY=$AMBU_API
```

**Verify your key is available:**

```bash
echo $ANTHROPIC_API_KEY | head -c 10
```

This should print the start of your real key (`sk-ant-api...`). If it
prints nothing, the secret isn't set correctly yet.

---

## ⚡ Running the Agent

### Option A — Full coverage-closure loop (requires an API key)

```bash
# Async FIFO
cd /workspaces/AMBU-CovAgent
rm -f LESSONS.md
python3 agent/agent.py config.yaml

# UART TX
cd designs/uart_tx && rm -f LESSONS.md && python3 ../../agent/agent.py config.yaml

# AHB2APB Bridge
cd designs/ahb2apb && rm -f LESSONS.md && python3 ../../agent/agent.py config.yaml
```

The agent measures starting coverage, queries the LLM to target
uncovered bins, runs the generated tests against the real RTL via
Verilator, and reports merged coverage until 100% closure is reached —
typically 2–4 iterations per design.

### Option B — Explore the testbenches (no API key required)

You do not need an API key to explore the testbench structure, run
real Verilator simulations, or see the reactive scoreboard monitor's
live data-integrity output:

```bash
make SIM=verilator MODULE=tb.tb_fifo
```

This runs the base random-stimulus testbench against the real FIFO
RTL, prints real functional coverage results, and shows the reactive
monitor's live output — all without spending any API budget. This is
the recommended way to first explore the project's testbenches and
coverage model before running the full agent.

---

## 🖥️ Example Output

*A real run's output will be added here, pasted directly from a fresh
Codespace invocation of `python3 agent/agent.py config.yaml`.*

```
[PASTE REAL AGENT OUTPUT HERE]
```

---

## 🏗️ Architecture

```
                      AMBU-CovAgent Closed-Loop Flow

  ┌─────────────────┐        ┌──────────────────┐        ┌──────────────────┐
  │ SystemVerilog    │ ─────► │ cocotb Testbench │ ─────► │ Coverage Parser  │
  │ RTL + Verilator  │        │  + Scoreboard    │        │  (real YAML,     │
  └─────────────────┘        └──────────────────┘        │  cocotb-coverage)│
           ▲                                              └────────┬─────────┘
           │                                                       │
           │ Directed Stimulus                     Uncovered Bins, │
           │                                        Real Results   │
           │                                                       ▼
  ┌─────────────────┐        ┌──────────────────┐        ┌──────────────────┐
  │ Generated Test   │ ◄───── │    LLM Agent     │ ◄───── │  Single-Bin      │
  │ (cocotb/Python)  │        │ (Claude Sonnet)  │        │  Target Selector │
  └─────────────────┘        └──────────────────┘        └──────────────────┘
```

1. **Baseline profiling:** the base testbench runs constrained-random
   stimulus, producing a real, parsed coverage result — never a
   self-report from the LLM.
2. **Bin selection:** one specific uncovered bin is chosen as this
   iteration's target (not the full uncovered list at once) — a
   design choice with direct research backing (see the Research
   Report).
3. **Directed synthesis:** a prompt containing the real RTL and the
   target bin is sent to Claude, which generates a directed cocotb
   test.
4. **Validation and accumulation:** the generated test runs against
   the real RTL via Verilator. If it closes real coverage, the result
   is accumulated (per-bin `max()`, never decreasing) into the running
   merged result. On the FIFO design, a reactive scoreboard monitor
   independently checks the base testbench's data integrity in real
   time throughout.

*Note: the diagram separates "Single-Bin Target Selector" (deciding
WHICH bin to pursue this iteration) from the coverage-accumulation
logic (remembering WHICH bins have ever been proven, across
iterations) — these are two distinct mechanisms in the real
implementation, detailed separately in the Research Report.*

---

## 🛠️ Toolchain Requirements

- Python 3.11+
- [cocotb](https://www.cocotb.org/) 2.0.1+
- [Verilator](https://www.veripool.org/verilator/) 5.048+
- A Claude API key (required only for the full autonomous
  coverage-closure loop — not required to explore the testbenches
  directly, see Option B above)

---

## 📬 Contact & Research Collaboration

**Venkata Krishna Kumar Vedantam**

[vedantam@pdx.edu](mailto:vedantam@pdx.edu)

For questions about setup, architecture, or research collaboration in
LLM-driven EDA and functional verification.

---

## 📜 License

Distributed under the **BSD 3-Clause License**, matching the license
of [cocotb](https://www.cocotb.org/), this project's core dependency.
See [`LICENSE`](./LICENSE) for the full text.
