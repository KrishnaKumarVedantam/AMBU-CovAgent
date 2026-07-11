# UART TX — Second Design Reusability Test
## Claude Code Work Spec

---

## UNDERSTAND THIS FIRST

This is exactly like UVM:
- UVM library = `agent/agent.py` → ONE copy, shared, NEVER touch
- Design env = files you create inside `designs/uart_tx/`
- Your job = create design-specific files, verify base sim runs
- API's job = increase coverage through iterations (NOT your job)

The flow:
```
Your files → agent.py reads them → API generates tests
→ Verilator runs → coverage measured → API iterates
```

**NEVER modify agent/agent.py**
**NEVER touch any existing file in uvm-coverage-agent-backup-v2**
**NEVER touch uvm-coverage-agent-backup-v2.5**

---

## STEP 0 — READ THESE FIRST (before creating anything)

```bash
cd /Users/krishna/uvm-coverage-agent-backup-v2

# 1. RTL — every port, every always block
cat /Users/krishna/uart-design/rtl/uart_tx.v

# 2. Their Verilog TB — extract stimulus patterns
cat /Users/krishna/uart-design/test/tb_tx.v

# 3. Async_fifo TB — understand the EXACT structure to mirror
cat tb/tb_fifo.py

# 4. Async_fifo coverage — understand coverage file structure
cat tb/fifo_coverage.py

# 5. Async_fifo scoreboard — understand scoreboard structure
cat tb/fifo_scoreboard.py

# 6. Async_fifo test_scoreboard — understand scoreboard test structure
cat tb/test_scoreboard.py

# 7. Async_fifo config — understand ALL required config keys
cat config.yaml

# 8. Async_fifo Makefile — understand Makefile structure to mirror
cat Makefile
```

Do NOT create any file until you have read all 8 files above.
Mirror the async_fifo structure exactly for uart_tx.

---

## STEP 1 — Create directory structure (Claude Code does this)

```bash
cd /Users/krishna/uvm-coverage-agent-backup-v2

mkdir -p designs/uart_tx/rtl
mkdir -p designs/uart_tx/tb
mkdir -p designs/uart_tx/coverage_reports
touch designs/uart_tx/tb/__init__.py
touch designs/uart_tx/coverage_reports/.keep

# Copy ONLY uart_tx RTL (not rx, not impl_top)
cp /Users/krishna/uart-design/rtl/uart_tx.v designs/uart_tx/rtl/uart_tx.v

# Verify nothing else was touched
git status 2>/dev/null || echo "not a git repo"
ls designs/uart_tx/
```

agent.py stays exactly where it is: `agent/agent.py`
It is called by path from the uart_tx design directory.

---

## STEP 2 — Create design-specific files

Work only inside `designs/uart_tx/`.
Mirror every file from async_fifo structure.

---

### File 1: designs/uart_tx/Makefile

Mirror the async_fifo Makefile structure.
Critical: MODULE= variable must be used (not COCOTB_TEST_MODULES).
PYTHONPATH must point to the uart_tx directory.
Parameter override for fast simulation (BIT_RATE=9600 default = 5208
cycles/bit = too slow. Override to 10 cycles/bit).

```makefile
SIM           ?= verilator
TOPLEVEL_LANG ?= verilog
VERILOG_SOURCES = $(shell pwd)/rtl/uart_tx.v
TOPLEVEL      = uart_tx
MODULE        = tb.tb_uart_tx

# Speed: 10 cycles/bit instead of default 5208
# BIT_RATE=1MHz, CLK_HZ=10MHz → CYCLES_PER_BIT=10
# One TX = 10 bits × 10 cycles = 100 cycles = 1μs
COMPILE_ARGS  += -GBIT_RATE=1000000 -GCLK_HZ=10000000

PYTHONPATH    = $(shell pwd)
export PYTHONPATH

include $(shell cocotb-config --makefiles)/Makefile.sim
```

---

### File 2: designs/uart_tx/config.yaml

Mirror async_fifo config.yaml exactly.
Read it first to find every required key agent.py needs.
Key uart_tx specific values:

```yaml
design_name:      uart_tx
rtl_file:         designs/uart_tx/rtl/uart_tx.v
base_module:      tb.tb_uart_tx
directed_module:  tb.test_directed
coverpoint_names:
  - top.cp_resetn
  - top.cp_tx_en
  - top.cp_tx_busy
  - top.cp_fsm
  - top.cx_en_busy
  - top.cx_rst_en
threshold:        95
max_iter:         8
yml_cov:          coverage_reports/coverage.yml
yml_base:         coverage_reports/coverage_base.yml
make_cwd:         /Users/krishna/uvm-coverage-agent-backup-v2/designs/uart_tx
sample_function:  sample_coverage
chain_of_thought: false
depth:            0
```

Add any other keys you find in the async_fifo config.yaml.

---

### File 3: designs/uart_tx/tb/uart_coverage.py

Mirror fifo_coverage.py structure exactly.

Design knowledge from RTL:
- Ports: clk, resetn, uart_txd, uart_tx_busy, uart_tx_en, uart_tx_data[7:0]
- FSM: fsm_state: 0=IDLE, 1=START, 2=SEND, 3=STOP
- uart_tx_busy = (fsm_state != IDLE) — combinational
- Reset is SYNCHRONOUS — posedge clk only in all sensitivity lists
- uart_tx_en only read by FSM when in IDLE state

Coverage model (18 total bins):
```python
@CoverPoint("top.cp_resetn",
    xf=lambda dut: int(dut.resetn.value), bins=[0, 1])

@CoverPoint("top.cp_tx_en",
    xf=lambda dut: int(dut.uart_tx_en.value), bins=[0, 1])

@CoverPoint("top.cp_tx_busy",
    xf=lambda dut: int(dut.uart_tx_busy.value), bins=[0, 1])

@CoverPoint("top.cp_fsm",
    xf=lambda dut: int(dut.fsm_state.value), bins=[0, 1, 2, 3])

@CoverCross("top.cx_en_busy",
    items=["top.cp_tx_en", "top.cp_tx_busy"])

@CoverCross("top.cx_rst_en",
    items=["top.cp_resetn", "top.cp_tx_en"])
```

HARD BINS (base TB must NOT hit these — agent must hit them):
- cx_en_busy[(1,1)]: tx_en=1 while busy=1 (back-to-back TX)
- cx_rst_en[(0,1)]: resetn=0 while tx_en=1 (enable during reset)

Why these are hard: their Verilog TB sends bytes one at a time waiting
for busy=0 each time — it never asserts tx_en while busy, and never
asserts tx_en during reset. These are exactly what the API must hit.

---

### File 4: designs/uart_tx/tb/tb_uart_tx.py

Mirror tb_fifo.py structure exactly.
Use their Verilog TB stimulus patterns (already read in Step 0).

Their Verilog TB does:
- 50MHz clock (10ns period)
- Reset: resetn=0 for 40ns (4 cycles), then resetn=1
- Sends 20 random bytes, each waits for busy=0 before next

Your Python TB must do the same but:
1. Use Clock() helper — NEVER Timer() for clocking
2. Follow same reset pattern
3. Send several random bytes sequentially, wait busy=0 each time
4. Sample coverage with await ReadOnly() before EVERY sample call
5. Export to coverage_reports/coverage_base.yml
6. MUST NOT hit cx_en_busy[(1,1)] or cx_rst_en[(0,1)]

Timing: Clock(dut.clk, 10, units='ns') — 100MHz matches Makefile override.

Base TB must hit 16 of 18 bins (89%).
Deliberately leave cx_en_busy[(1,1)] and cx_rst_en[(0,1)] for the API.

Required cocotb rules (same as async_fifo):
- RULE 1: Clock() helper only, never Timer()
- RULE 2: await ReadOnly() before every sample_coverage() call
- RULE 3: Drive signals BEFORE ReadOnly(), never after
- RULE 4: Export at end: coverage_db.export_to_yaml(filename="coverage_reports/coverage_base.yml")

---

### File 5: designs/uart_tx/tb/uart_scoreboard.py

Mirror fifo_scoreboard.py structure.

For uart_tx: verify the transmitted data matches the expected UART frame.
UART frame format: start_bit(0) + 8 data bits LSB first + stop_bit(1)
Check uart_txd output bit by bit against expected sequence.

---

### File 6: designs/uart_tx/tb/test_scoreboard.py

Mirror test_scoreboard.py from async_fifo exactly.
Run the scoreboard verification against uart_tx.

---

## STEP 3 — Syntax check all Python files

```bash
cd /Users/krishna/uvm-coverage-agent-backup-v2

python3 -m py_compile designs/uart_tx/tb/uart_coverage.py && echo "uart_coverage OK"
python3 -m py_compile designs/uart_tx/tb/tb_uart_tx.py && echo "tb_uart_tx OK"
python3 -m py_compile designs/uart_tx/tb/uart_scoreboard.py && echo "uart_scoreboard OK"
python3 -m py_compile designs/uart_tx/tb/test_scoreboard.py && echo "test_scoreboard OK"
```

Fix any syntax errors before proceeding.

---

## STEP 4 — Run base simulation (BEFORE running agent)

```bash
cd /Users/krishna/uvm-coverage-agent-backup-v2/designs/uart_tx
make SIM=verilator 2>&1 | tail -20
```

Must show: TESTS=1 PASS=1 FAIL=0
Must create: coverage_reports/coverage_base.yml

Check base coverage:
```bash
python3 -c "
import yaml
d = yaml.safe_load(open('coverage_reports/coverage_base.yml'))
for k,v in d.items():
    if isinstance(v,dict) and 'cover_percentage' in v:
        print(f'{k}: {v[\"cover_percentage\"]}%')
"
```

Expected: most coverpoints 100%, hard bins at 0%.
If base test fails — fix it. Do NOT run agent until base passes.

---

## STEP 5 — Run the agent

```bash
cd /Users/krishna/uvm-coverage-agent-backup-v2/designs/uart_tx
python3 ../../agent/agent.py config.yaml
```

This calls agent.py from its original location — no copy needed.
All outputs go to designs/uart_tx/coverage_reports/

Watch for:
```
[SETUP][RTL-LOAD]      → uart_tx.v loaded
[ITER-N][PORT-EXTRACT] → 6 ports found
[ITER-N][MERGE]        → coverage increasing
cx_en_busy[(1,1)]      → hits > 0 (agent hit this)
cx_rst_en[(0,1)]       → hits > 0 (agent hit this)
```

The API generates directed tests and increases coverage.
Your job is done once the agent starts running.

---

## STEP 6 — Final verification

```bash
# Prove agent.py was never modified (compare to v2.5 production save)
diff /Users/krishna/uvm-coverage-agent-backup-v2/agent/agent.py \
     /Users/krishna/uvm-coverage-agent-backup-v2.5/agent/agent.py
echo "Must show: no output"

# Check hard bins hit by API
python3 -c "
import yaml
d = yaml.safe_load(open('coverage_reports/coverage_merged.yml'))
mb = d.get('_merged_bins', {})
for k,v in sorted(mb.items()):
    if 'cx_' in k:
        print(k, v)
"

# Verify nothing in main project was touched
ls -la /Users/krishna/uvm-coverage-agent-backup-v2/
# coverage_reports/ timestamps must not change (async_fifo results intact)
```

---

## SUCCESS CRITERIA

```
Base sim (make):         PASS before running agent
Base coverage:           ≥85% (hard bins at 0%)
Merged coverage:         ≥95% after agent runs
cx_en_busy[(1,1)]:       hits > 0  SOURCE=AGENT
cx_rst_en[(0,1)]:        hits > 0  SOURCE=AGENT
diff agent.py vs v2.5:   no output = reusability PROVEN
async_fifo results:      unchanged (not touched)
```

---

## WHAT THIS PROVES

uart_tx is completely different from async_fifo:
- Single clock vs dual clock CDC
- Synchronous reset vs async reset
- FSM-based TX vs pointer-based FIFO
- Different ports, different bins, TB written from scratch

If agent.py works unchanged → framework works for ANY cocotb design.
