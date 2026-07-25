import cocotb
import random
import os
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, ClockCycles, NextTimeStep, Event
from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db
from tb.fifo_scoreboard import FIFOScoreboard

@CoverPoint("top.cp_full",
    xf=lambda dut: int(dut.full.value), bins=[0, 1])
@CoverPoint("top.cp_empty",
    xf=lambda dut: int(dut.empty.value), bins=[0, 1])
@CoverPoint("top.cp_wen",
    xf=lambda dut: int(dut.w_en.value), bins=[0, 1])
@CoverPoint("top.cp_ren",
    xf=lambda dut: int(dut.r_en.value), bins=[0, 1])
@CoverPoint("top.cp_half_full",
    xf=lambda dut: int(dut.half_full.value), bins=[0, 1])
@CoverPoint("top.cp_half_empty",
    xf=lambda dut: int(dut.half_empty.value), bins=[0, 1])
@CoverPoint("top.cp_wrst",
    xf=lambda dut: int(dut.w_rst_n.value), bins=[0, 1])
@CoverPoint("top.cp_rrst",
    xf=lambda dut: int(dut.r_rst_n.value), bins=[0, 1])
@CoverCross("top.cx_full_wen",
    items=["top.cp_full", "top.cp_wen"])
@CoverCross("top.cx_empty_ren",
    items=["top.cp_empty", "top.cp_ren"])
@CoverCross("top.cx_full_empty",
    items=["top.cp_full", "top.cp_empty"])
@CoverCross("top.cx_wrst_wen",
    items=["top.cp_wrst", "top.cp_wen"])
@CoverCross("top.cx_rrst_ren",
    items=["top.cp_rrst", "top.cp_ren"])
async def sample_coverage(dut):
    pass

async def _drive_wclk_writes(dut):
    """PHASE 1 write half — wclk domain (200 iterations, as before)."""
    for _ in range(200):
        await RisingEdge(dut.wclk)
        dut.w_en.value    = 1 if random.random() > 0.4 else 0
        dut.data_in.value = random.randint(0, 255)
        await ReadOnly()
        await sample_coverage(dut)


async def _drive_rclk_reads(dut, stop):
    """PHASE 1 read half — rclk domain. Stops cooperatively via `stop`
    (a cocotb.triggers.Event) rather than being externally cancelled.

    _read_monitor (fifo_scoreboard.py) caches whatever r_en this task
    writes immediately after an rclk edge as the value that governs
    the FOLLOWING edge (its own prev_r_en/prev_data bookkeeping is one
    edge behind by design — confirmed via trace: a write made right
    after RisingEdge() is visible to another coroutine's same-timestep
    ReadOnly() sample, so _read_monitor's "curr" IS effectively a
    look-ahead value for the next edge). An external task.cancel() cuts
    the task off after its last random draw has already been cached as
    that look-ahead promise, but before the edge it was meant to gate
    — leaving _read_monitor expecting a read that a subsequent forced
    r_en=0 (via NextTimeStep) can prevent in real hardware but can't
    retroactively un-cache. Checking `stop` right after each RisingEdge
    — before drawing — lets this task instead write a deliberate,
    correctly-timed 0 as its own final act, so _read_monitor's cached
    look-ahead matches what actually governs the next edge. The caller
    must set `stop` and then await this task's completion (e.g. via
    `task.join()`) before proceeding, since the final write only
    happens on the next rclk edge after `stop` is set."""
    while True:
        await RisingEdge(dut.rclk)
        if stop.is_set():
            dut.r_en.value = 0
            return
        dut.r_en.value = 1 if random.random() > 0.5 else 0


async def _hold_rclk_ren_high(dut):
    """Read half for any phase that continuously drains (Phase 3 and
    Phase 5) — rclk domain. Asserts r_en=1 on its native clock domain
    (read_ptr in rtl/async_fifo_flat.sv samples r_en on rclk) so the
    draining phase never depends on the wclk-timed caller for a clean
    transition edge. Runs until cancelled."""
    while True:
        await RisingEdge(dut.rclk)
        dut.r_en.value = 1


@cocotb.test()
async def test_fifo_coverage(dut):
    # RULE: Start clocks FIRST before any other await
    cocotb.start_soon(Clock(dut.wclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.rclk, 15, units="ns").start())

    # Passive monitor — watches DUT pins on both clock domains
    # Runs concurrently with coverage stimulus — same simulation
    # Results exported to scoreboard_passive.yml — NOT read by agent
    _sb = FIFOScoreboard()
    cocotb.start_soon(_sb.monitor(dut))

    # Drive initial values — active phase at t=0
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    dut.w_en.value    = 0
    dut.r_en.value    = 0
    dut.data_in.value = 0

    # Wait 2 rclk cycles then sample reset state
    await ClockCycles(dut.rclk, 2)   # active phase after edges
    await ReadOnly()
    await sample_coverage(dut)        # w_rst_n=0, r_rst_n=0, empty=1

    # Hold reset 10 rclk cycles — ClockCycles returns in active phase
    await ClockCycles(dut.rclk, 10)

    # Release reset — active phase, safe to drive
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1
    await ClockCycles(dut.wclk, 5)   # active phase
    await ReadOnly()
    await sample_coverage(dut)

    # PHASE 1: Random stimulus
    # w_en/data_in driven on wclk (their native domain) while r_en is
    # driven concurrently on rclk (its native domain, per read_ptr in
    # rtl/async_fifo_flat.sv) — two independent coroutines instead of
    # one wclk-timed loop driving both signals.
    _stop_reads = Event()
    _read_task = cocotb.start_soon(_drive_rclk_reads(dut, _stop_reads))
    await _drive_wclk_writes(dut)

    # Signal — don't cancel. The read task writes its own final r_en=0
    # on the next rclk edge it wakes on (see _drive_rclk_reads), so
    # _read_monitor's cached look-ahead value matches what actually
    # governs that edge. join() waits for that write to complete.
    _stop_reads.set()
    await _read_task.join()

    # PHASE 2: Fill FIFO — hit full=1
    full_hit = False
    for _ in range(350):
        await RisingEdge(dut.wclk)
        dut.r_en.value    = 0
        dut.w_en.value    = 1
        dut.data_in.value = random.randint(0, 255)
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.full.value) == 1:
            full_hit = True
            break

    # Sample full=1 AND w_en=1 (blocked write — safe per RTL analysis)
    if full_hit:
        await RisingEdge(dut.wclk)
        dut.w_en.value    = 1
        dut.data_in.value = 0xFF
        await ReadOnly()
        await sample_coverage(dut)

    # Clear w_en
    await RisingEdge(dut.wclk)
    dut.w_en.value = 0
    # no ReadOnly needed — just need active phase for next section

    # PHASE 3: Drain FIFO — hit empty=1
    # r_en held on rclk (its native domain) via a concurrent coroutine —
    # same fix pattern as Phase 1 — while this wclk loop only clears
    # w_en and polls empty. Found during per-phase review: r_en's
    # 0→1 transition here was previously wclk-timed even though it is
    # held constant afterward, which was enough to desync the passive
    # monitor's reference queue by one entry at the Phase 2/3 boundary.
    empty_hit = False
    _ren_task = cocotb.start_soon(_hold_rclk_ren_high(dut))
    for _ in range(350):
        await RisingEdge(dut.wclk)
        dut.w_en.value = 0
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.empty.value) == 1:
            empty_hit = True
            break

    # Sample empty=1 AND r_en=1 (blocked read — safe per RTL analysis)
    if empty_hit:
        await RisingEdge(dut.wclk)
        await ReadOnly()
        await sample_coverage(dut)

    _ren_task.cancel()

    # Deassert r_en at the next time step, not the next clock edge —
    # see the identical Phase 1/2 boundary comment above.
    await NextTimeStep()
    dut.r_en.value = 0

    # PHASE 4: Hit half_full — waddr must reach exactly 88
    # Reset to guarantee waddr=0 (active phase, safe to drive)
    dut.w_en.value    = 0
    dut.r_en.value    = 0
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    await ClockCycles(dut.rclk, 8)   # active phase
    await ReadOnly()
    await sample_coverage(dut)

    # Release reset — need active phase; ClockCycles gives us that
    await ClockCycles(dut.rclk, 1)   # active phase
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1
    await ClockCycles(dut.wclk, 3)   # active phase

    # Write exactly 88 times to hit half_full
    for i in range(88):
        await RisingEdge(dut.wclk)
        dut.w_en.value    = 1
        dut.data_in.value = i % 256
        await ReadOnly()
        await sample_coverage(dut)

    # Stop writing — waddr stays 88
    await RisingEdge(dut.wclk)
    dut.w_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)  # waddr=88, half_full=1

    # PHASE 5: Hit half_empty — raddr must reach exactly 88
    # r_en held on rclk (its native domain) via the same concurrent
    # coroutine used for Phase 3 — this wclk loop only counts
    # iterations and samples coverage, it no longer drives r_en.
    _ren_task = cocotb.start_soon(_hold_rclk_ren_high(dut))
    for i in range(88):
        await RisingEdge(dut.wclk)
        await ReadOnly()
        await sample_coverage(dut)

    _ren_task.cancel()

    # Deassert r_en at the next time step, not the next clock edge —
    # see the identical Phase 1/2 and Phase 2/3 boundary comments above.
    await NextTimeStep()
    dut.r_en.value = 0

    await RisingEdge(dut.wclk)
    await ReadOnly()
    await sample_coverage(dut)  # raddr=88, half_empty=1

    # Export passive scoreboard results — observation only, agent never reads this
    _sb.report()
    _sb.export_yaml("coverage_reports/scoreboard_passive.yml")
    cocotb.log.info("Passive scoreboard exported: coverage_reports/scoreboard_passive.yml")

    # Export
    os.makedirs("coverage_reports", exist_ok=True)
    coverage_db.export_to_yaml(filename="coverage_reports/coverage.yml")

    try:
        total = hit = 0
        for name, attrs in coverage_db.items():
            if hasattr(attrs, 'detailed_coverage'):
                for b, c in attrs.detailed_coverage.items():
                    total += 1
                    if c > 0: hit += 1
        pct = (hit / total * 100) if total > 0 else 0.0
        print(f"\n=== INITIAL COVERAGE: {pct:.1f}% ({hit}/{total} bins) ===\n")
    except Exception as e:
        print(f"Coverage note: {e}")
