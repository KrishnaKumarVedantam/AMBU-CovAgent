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

   *This project includes a [`.devcontainer`](.devcontainer/) config
   (`devcontainer.json` + `setup.sh`) that automatically compiles
   Verilator, installs Python dependencies, and builds cocotb from
   scratch on first launch — this typically takes around **5-10
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
=======================================================
FINAL REPORT
=======================================================
Design:                    async_fifo
Base coverage (tb.tb_fifo): 91.7%
Merged coverage (total):   100.0%
Agent contribution:        +8.3%
Data failures:             0
Not hit bins:              0
Verified bins:             9
Iterations used:           6
History (merged%):         ['92%', '92%', '97%', '97%', '97%', '100%']

COVERAGE ATTRIBUTION (Option C):

  BIN                                      BASE  AGENT  TOTAL  SOURCE
  -------------------------------------- ------ ------ ------  ------
  cp_empty[0]                               915     90   1005  BOTH
  cp_empty[1]                                13     45     58  BOTH
  cp_full[0]                                922    135   1057  BOTH
  cp_full[1]                                  6     19     25  BOTH
  cp_half_empty[0]                          926    135   1061  BOTH
  cp_half_empty[1]                            2      0      2  BASE
  cp_half_full[0]                           837    135    972  BOTH
  cp_half_full[1]                            91      0     91  BASE
  cp_ren[0]                                 387     75    462  BOTH
  cp_ren[1]                                 541     60    601  BOTH
  cp_rrst[0]                                  2     18     20  BOTH
  cp_rrst[1]                                926    118   1044  BOTH
  cp_wen[0]                                 512     74    586  BOTH
  cp_wen[1]                                 416     61    477  BOTH
  cp_wrst[0]                                  2     19     21  BOTH
  cp_wrst[1]                                926    116   1042  BOTH
  cx_empty_ren[(0,0)]                       378     42    420  BOTH
  cx_empty_ren[(0,1)]                       537     48    585  BOTH
  cx_empty_ren[(1,0)]                         9     33     42  BOTH
  cx_empty_ren[(1,1)]                         4     12     16  BOTH
  cx_full_empty[(0,0)]                      909     90    999  BOTH
  cx_full_empty[(0,1)]                       13     45     58  BOTH
  cx_full_empty[(1,0)]                        6      1      7  BOTH
  cx_full_empty[(1,1)]                        0     18     18  AGENT
  cx_full_wen[(0,0)]                        508     74    582  BOTH
  cx_full_wen[(0,1)]                        414     61    475  BOTH
  cx_full_wen[(1,0)]                          4     19     23  BOTH
  cx_full_wen[(1,1)]                          2      0      2  BASE
  cx_rrst_ren[(0,0)]                          2     18     20  BOTH
  cx_rrst_ren[(0,1)]                          0      8      8  AGENT
  cx_rrst_ren[(1,0)]                        385     66    451  BOTH
  cx_rrst_ren[(1,1)]                        541     52    593  BOTH
  cx_wrst_wen[(0,0)]                          2      6      8  BOTH
  cx_wrst_wen[(0,1)]                          0     13     13  AGENT
  cx_wrst_wen[(1,0)]                        510     68    578  BOTH
  cx_wrst_wen[(1,1)]                        416     48    464  BOTH

  Summary: BASE=3  AGENT=3  BOTH=30
  Graph: /workspaces/AMBU-CovAgent/coverage_reports/coverage_graph.png
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
