# AHB2APB Bridge — Design Spec

## What is done

### RTL (3 files)
- `rtl/bridge-top.v` — top-level, instantiates both submodules
- `rtl/AHB_Slave_Interface.v` — pipeline registers (Haddr1/Haddr2, Hwdata1/Hwdata2), valid logic, tempselx decode
- `rtl/APB_Controller.v` — 8-state FSM (IDLE/WWAIT/READ/WRITE/WRITEP/RENABLE/WENABLE/WENABLEP), output registers

### Makefile
- Compiles all 3 RTL files (Verilator)
- Sets PYTHONPATH to include both `designs/ahb2apb/` and the project root
- Suppresses expected RTL warnings (MULTIDRIVEN, WIDTHEXPAND, WIDTHTRUNC, LATCH)

### config.yaml
- 11 coverage model items (8 CoverPoints, 3 CoverCrosses), 46 total bins
- threshold = 95%, max_iter = 8
- sample_function = sample_coverage

### Coverage model (`tb/ahb2apb_coverage.py`)
46 bins total:
- `cp_hresetn` [0,1]
- `cp_hwrite` [0,1]
- `cp_htrans` [0,1,2,3]
- `cp_hreadyin` [0,1]
- `cp_valid` [0,1]
- `cp_pselx` [0,1,2,4]
- `cp_fsm` [0,1,2,3,4,5,6,7]
- `cp_penable` [0,1]
- `cx_write_htrans` (hwrite × htrans — 8 bins)
- `cx_psel_enable` (pselx × penable — 8 bins)
- `cx_write_valid` (hwrite × valid — 4 bins)

### Scoreboard (`tb/ahb2apb_scoreboard.py`)
- Checks: Paddr == Haddr (pipelined), Pwdata == Hwdata, Pwrite correct, Pselx correct, Hrdata == Prdata

### Scoreboard test (`tb/test_scoreboard.py`)
- Writes and reads to all 3 slaves, verifies all protocol signals

### Base testbench (`tb/tb_ahb2apb.py`)
- Achieves 31/46 bins = 67.39% (measured after ReadOnly fix)
- Leaves 15 zero-hit bins for the coverage agent (docstring claimed 10 — stale)

### sim_build/
- Pre-built Verilator binary `Vtop` — simulation compiles cleanly

---

## What is broken

### Critical: ReadOnly violation in `do_read()` (tb/tb_ahb2apb.py:125)

**Error:** `Attempting settings a value during the ReadOnly phase.`
**Sim time:** 110 ns (first `do_read` call, right after `do_write`)

**Root cause:** `do_read()` opens with `dut.Prdata.value = prdata` **before any `await`**. It is called immediately after `do_write()`, which ends with:
```python
await ReadOnly()
await sample_coverage(dut)   # returns while still in ReadOnly phase
```
When `do_read()` starts, the simulation is still in ReadOnly. The assignment to `Prdata` violates the rule: **you cannot set a signal value during ReadOnly phase**.

**Result (before fix):** The base testbench crashed at line 125 before collecting any coverage. Base coverage = 0%.
**Result (after fix):** `test_ahb2apb_base` PASS, 31/46 bins = 67.39%.

### No test_directed.py
Agent has not been run against this design. Only the base test exists.

---

## What to do next

### Step 1 — Fix ReadOnly violation (tb/tb_ahb2apb.py)
Move `dut.Prdata.value = prdata` to after `await RisingEdge(dut.Hclk)` inside `do_read()`.

Correct pattern (matching `do_write`):
```python
async def do_read(dut, addr, prdata=0xDEADBEEF):
    await RisingEdge(dut.Hclk)
    dut.Prdata.value   = prdata      # set slave response after rising edge
    dut.Hwrite.value   = 0
    dut.Haddr.value    = addr
    dut.Htrans.value   = HTRANS_NONSEQ
    dut.Hreadyin.value = 1
    await ReadOnly()
    await sample_coverage(dut)
    ...
```

Verify:
```bash
cd designs/ahb2apb && make SIM=verilator COCOTB_TEST_MODULES=tb.tb_ahb2apb 2>&1 | tail -20
# Expect: BASE COVERAGE: ~78% (36/46 bins)
```

### Step 2 — Run agent
```bash
python3 agent/agent.py designs/ahb2apb/config.yaml
```

### Step 3 — Verify 15 zero-hit bins are hit (≥95% threshold)

| Bin | Signal states needed |
|-----|---------------------|
| `cp_htrans[1]` | BUSY transfer: Htrans=1 mid-burst |
| `cp_htrans[3]` | SEQ transfer: Htrans=3 in burst |
| `cp_fsm[4]` ST_WRITEP | Write while valid=1 in WWAIT state |
| `cp_fsm[7]` ST_WENABLEP | Follows WRITEP or WRITE with pending valid |
| `cp_pselx[2]` | Address in 0x8400_0000–0x87FF_FFFF |
| `cp_pselx[4]` | Address in 0x8800_0000–0x8BFF_FFFF |
| `cx_write_htrans[(0,1)]` | Hwrite=0, Htrans=BUSY |
| `cx_write_htrans[(0,3)]` | Hwrite=0, Htrans=SEQ |
| `cx_write_htrans[(1,1)]` | Hwrite=1, Htrans=BUSY |
| `cx_write_htrans[(1,3)]` | Hwrite=1, Htrans=SEQ |
| `cx_psel_enable[(0,1)]` | Penable=1 with no slave selected (edge case) |
| `cx_psel_enable[(2,0)]` | Slave 2 in APB setup phase |
| `cx_psel_enable[(2,1)]` | Slave 2 in APB enable phase |
| `cx_psel_enable[(4,0)]` | Slave 3 in APB setup phase |
| `cx_psel_enable[(4,1)]` | Slave 3 in APB enable phase |

**ST_WRITEP/ST_WENABLEP trigger condition (from RTL):**
In `WWAIT` state, if `valid=1` when the next cycle arrives, the FSM transitions to `WRITEP` (not `WRITE`). This requires back-to-back NONSEQ writes: drive a second valid write address on Haddr while the first write is still in the WWAIT state.

---

## Address map
| Slave | Haddr range | Pselx |
|-------|------------|-------|
| Slave 1 | 0x8000_0000 – 0x83FF_FFFF | 3'b001 (1) |
| Slave 2 | 0x8400_0000 – 0x87FF_FFFF | 3'b010 (2) |
| Slave 3 | 0x8800_0000 – 0x8BFF_FFFF | 3'b100 (4) |

## FSM state encoding (APB_Controller.v)
| State | Value | Description |
|-------|-------|-------------|
| ST_IDLE | 0 | Idle |
| ST_WWAIT | 1 | Write address registered, waiting for data |
| ST_READ | 2 | APB read setup |
| ST_WRITE | 3 | APB write setup |
| ST_WRITEP | 4 | Pipelined write setup |
| ST_RENABLE | 5 | APB read enable |
| ST_WENABLE | 6 | APB write enable |
| ST_WENABLEP | 7 | Pipelined APB write enable |
