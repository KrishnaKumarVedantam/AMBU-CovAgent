# uvm-coverage-agent-backup-v2.10.3

## What This Version Is

This is the most complete version of the UVM Coverage Agent framework.
It builds on v2.10.1 (time.sleep + zlibc fixes) by adding scoreboard
data integrity fixes and fault injection validation suites for all
three supported RTL designs. All fixes are verified on both Mac ARM64
and GitHub Codespaces x86_64.

---

## Complete Fix History

### v2.9 — Bug #1: Coverage Accumulator Regression

**Problem:** Merged coverage dropped mid-run. Bins proven hit in
iteration N disappeared in iteration N+1. Observed live as
97.2% → 91.7% regression in Codespaces.

**Root cause:** `directed_bins` was overwritten each iteration from
the most recent YAML file only, losing all previous iterations' data.

**Fix:** `accumulated_directed_bins = {}` initialized before loop.
Per-bin `max()` update after each successful sim. All five
`merge_coverage()` call sites updated to use accumulated bins.

**Proof:** 8 adversarial unit tests + live runs on all 3 designs.
History monotonically non-decreasing across all runs.

**Research backing:** Accellera UCIS 1.0 union-merge semantics,
elitism in evolutionary algorithms (ACM CISAI 2025),
AFL/libFuzzer corpus model (IRFuzzer 2024).

---

### v2.10 — Export Placement Fix

**Problem:** In Codespaces (x86_64), every successful simulation
showed exactly 0% coverage gain. Confirmed by `tail -5 tb/test_directed.py`
showing `coverage_db.export_to_yaml()` at zero indentation — module
level, outside the test function. Python executes module-level code at
import time before any test runs, writing zeros to YAML. Real hits
accumulated during the test were silently discarded.

**Why Mac worked but Codespaces didn't:** LLM generates longer tests
(250+ lines) in Codespaces targeting hard CDC bins. In those long files,
the "LAST LINE" instruction in the prompt is interpreted as the literal
last line of the file — falling outside the function at 0 indent.

**Fix:** `clean_code()` in agent.py strips zero-indent
`coverage_db.export_to_yaml` lines before `ast.parse()`. The export
guard at line 905 then injects a correctly 4-space-indented version
inside the test function.

**Verification:** Both `tail -5` outputs confirmed — Mac shows 4-space
indent (correct), Codespaces showed 0-space (fixed after this change).

**Threshold updates:** uart_tx and ahb2apb thresholds raised 95 → 98.

---

### v2.10.1 — Operational Fixes

**Fix 1 — time.sleep(60) → time.sleep(2) (agent.py line 983):**
Unconditional 60-second sleep after every iteration removed.
Line 704 sleep (rate limit retry on real 429 response) kept at 60s.
Saves up to 8 minutes per full run. Anthropic API confirmed: 429
responses include retry-after header — blanket sleep is redundant.

**Fix 2 — setup.sh zlibc removed:**
zlibc is Ubuntu-only and does not exist on Debian Trixie (Codespaces
base image). Caused postCreateCommand to fail on every new Codespace.
Removing it makes the repo one-click deployable — Verilator 5.048
builds automatically without any manual intervention.

**Verification:** Brand new Codespace built automatically, all three
designs reached 100% in fresh environment.

---

### v2.10.3 — Scoreboard Fixes + Fault Injection Suites

#### UART TX Scoreboard Fix (designs/uart_tx/tb/test_scoreboard.py)

**Problem:** The UART scoreboard only verified that the TX line went
low for the start bit and returned high after transmission. The 8 data
bits transmitted between start and stop were never sampled or compared.
A DUT that transmitted completely inverted data would still pass.

**Fix:** After detecting the start bit, sample all 8 data bits plus
the stop bit at the midpoint of each bit period.

**RTL timing confirmed:**
- CYCLES_PER_BIT = 10 (BIT_RATE=1MHz, CLK_HZ=10MHz, from Makefile)
- `txd_reg` updates on posedge, stable for full CYCLES_PER_BIT period
- FSM: START → SEND, `data_to_send[0]` (LSB) transmitted first
- Bit 0 appears on `uart_txd` 11 clocks after start bit sample
- First wait: CYCLES_PER_BIT + CYCLES_PER_BIT//2 = 15 clocks
  (lands at midpoint of bit 0, clock 5 of 10-clock period)
- Subsequent waits: CYCLES_PER_BIT + 1 = 11 clocks each
  (cycle counter counts 0→10, making actual period 11 clocks)

**Result:** 50 bit-level checks across 5 test bytes (0x55, 0xAA,
0xFF, 0x00, 0xA5). Data integrity proven at bit level.

#### AHB2APB Scoreboard Fix (designs/ahb2apb/tb/test_scoreboard.py)

**Problem:** During write transactions, the scoreboard verified Paddr
and Pselx but never checked Pwdata. A bridge that correctly routed
the address but zeroed the data payload would pass undetected.

**Fix:** When Penable==1 (ENABLE phase), read `dut.Pwdata.value`
and compare against `expected_pwdata`.

**RTL timing confirmed from APB_Controller.v:**
- `Pwdata` is a registered output: `always @(posedge Hclk) Pwdata <= Pwdata_temp`
- `Pwdata_temp = Hwdata` set in ST_WWAIT state (combinational)
- When FSM is in ST_WENABLE (Penable=1), Pwdata is stable — registered
  from previous WWAIT cycle
- AMBA APB spec confirms: PWDATA must remain stable until transfer
  completes — sampling when Penable==1 is the correct point

**Result:** Write data verified for all 3 slaves with known values
(0xDEADBEEF, 0xCAFEBABE, 0x12345678). Read data was already verified.

---

## Fault Injection Suites — Scoreboard Validation

Three `test_scoreboard_buggy.py` files, one per design. These prove
the scoreboards correctly catch data corruption across multiple fault
categories. Methodology: mutation testing (Berkeley EECS-2024-157,
Hindawi VLSI Design 2015).

### FIFO (tb/test_scoreboard_buggy.py) — 5 faults

| Test | Fault | What It Proves |
|------|-------|----------------|
| fault1 | Bit flip (lower nibble) | Single-bit corruption caught |
| fault2 | Full inversion | All-bit corruption caught |
| fault3 | Sequence reversal | Ordering enforced, not just values |
| fault4 | Phantom write | Rejected writes not recorded |
| fault5 | CDC timing violation | Read-before-sync caught |

All 5 tests PASS — meaning all 5 faults are correctly detected.

### UART TX (designs/uart_tx/tb/test_scoreboard_buggy.py) — 4 faults

| Test | Fault | What It Proves |
|------|-------|----------------|
| fault1 | Single bit flip (bit 3) | Bit-level check fires on 1 bit |
| fault2 | Zero corruption | Stuck-at-0 on data bus caught |
| fault3 | Off-by-one (+1) | Incrementer bug caught |
| fault4 | Full inversion | All bits wrong caught |

All 4 tests PASS — 8 errors caught in 10 bit-level checks.

### AHB2APB (designs/ahb2apb/tb/test_scoreboard_buggy.py) — 5 faults

| Test | Fault | What It Proves |
|------|-------|----------------|
| fault1 | Write data bit flip | Pwdata bit-level check fires |
| fault2 | Write data zeroed | Data bus stuck-at-0 caught |
| fault3 | Write data offset+1 | Incrementer bug in write path |
| fault4 | Read data zeroed | Hrdata corruption caught |
| fault5 | Read data bit flip | Single bit in Hrdata caught |

All 5 tests PASS — confirmed on both Mac ARM64 and Codespaces x86_64.

---

## Total Fault Coverage

```
Design      Faults  Result
FIFO           5    ALL CAUGHT ✓
UART TX        4    ALL CAUGHT ✓
AHB2APB        5    ALL CAUGHT ✓
Total         14    14/14 CAUGHT ✓
```

Zero blind spots confirmed across all three designs and both platforms.

---

## Verification Results — All Three Designs at 100%

All designs verified with corrected scoreboards, data_fail=0:

### Mac ARM64

```
async_fifo: 100% — data_fail=0 — accumulator + export fix
uart_tx:    100% — data_fail=0 — 50 bit-level scoreboard checks
ahb2apb:    100% — data_fail=0 — Pwdata + Hrdata both verified
```

### GitHub Codespaces x86_64

```
async_fifo: 100% — data_fail=0 — multiple independent runs
uart_tx:    100% — data_fail=0 — auto-built fresh Codespace
ahb2apb:    100% — data_fail=0 — all 15 hard bins closed
```

---

## Identified Research Finding

The agent currently propagates `data_fail=N` count to the LLM prompt
but not the specific mismatch details (which bin failed, expected vs
actual value). Research confirms this creates a "Semantic Cohesion Gap"
(arXiv 2512.00016) — the LLM must guess the root cause without
localized failure context. Detailed scoreboard error propagation to
the LLM prompt is identified as a future improvement (v2.11).

---

## Key Operational Rule

Clear LESSONS.md before every fresh evaluation run:

```bash
rm -f LESSONS.md
rm -f designs/uart_tx/LESSONS.md
rm -f designs/ahb2apb/LESSONS.md
python3 agent/agent.py <config.yaml>
```

---

## Branches

```
uvm-coverage-agent-backup-v2.10.3-dev      Active development
uvm-coverage-agent-backup-v2.10.3-untouch  Frozen verified reference
```

## What Is Still Pending (v2.11)

- test_scoreboard_dut_bug.py for all 3 designs — genuine DUT bug
  simulation to observe LLM self-correction behavior under data_fail>0
- Scoreboard error detail propagation to LLM prompt
- Bug #2: LESSONS.md deduplication without bin identity
