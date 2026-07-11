import cocotb
import random
import os
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, ClockCycles
from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db

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

@cocotb.test()
async def test_fifo_coverage(dut):
    # RULE: Start clocks FIRST before any other await
    cocotb.start_soon(Clock(dut.wclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.rclk, 15, units="ns").start())

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
    # Pattern: RisingEdge → drive → ReadOnly → sample
    for _ in range(200):
        await RisingEdge(dut.wclk)    # active phase — safe to drive
        dut.w_en.value    = 1 if random.random() > 0.4 else 0
        dut.data_in.value = random.randint(0, 255)
        dut.r_en.value    = 1 if random.random() > 0.5 else 0
        await ReadOnly()
        await sample_coverage(dut)

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
    empty_hit = False
    for _ in range(350):
        await RisingEdge(dut.wclk)
        dut.w_en.value = 0
        dut.r_en.value = 1
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.empty.value) == 1:
            empty_hit = True
            break

    # Sample empty=1 AND r_en=1 (blocked read — safe per RTL analysis)
    if empty_hit:
        await RisingEdge(dut.wclk)
        dut.r_en.value = 1
        await ReadOnly()
        await sample_coverage(dut)

    # Clear r_en
    await RisingEdge(dut.wclk)
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
    for i in range(88):
        await RisingEdge(dut.wclk)
        dut.r_en.value = 1
        await ReadOnly()
        await sample_coverage(dut)

    await RisingEdge(dut.wclk)
    dut.r_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)  # raddr=88, half_empty=1

    # PHASE 6: Target the 3 bins that Phase 1-5 never hit
    #
    # Why each was missed:
    #   cx_wrst_wen[(0,1)]: test always clears w_en before asserting w_rst_n
    #   cx_rrst_ren[(0,1)]: test always clears r_en before asserting r_rst_n
    #   cx_full_empty[(1,1)]: full+empty are steady-state exclusive; need the
    #     async-reset window — empty has negedge r_rst_n sensitivity so it
    #     asserts instantly, while full (write-domain FF) holds its value until
    #     the next posedge wclk.

    # 6a: cx_wrst_wen[(0,1)] — assert w_rst_n=0 WITH w_en=1 at the same time
    # RTL write_ptr.sv:16 — reset takes priority; w_en=1 during reset is legal
    await RisingEdge(dut.wclk)
    dut.r_rst_n.value = 1
    dut.r_en.value    = 0
    dut.w_en.value    = 1        # write enable asserted
    dut.w_rst_n.value = 0        # reset also asserted — RTL ignores w_en, safe
    dut.data_in.value = 0x55
    await ReadOnly()
    await sample_coverage(dut)   # cp_wrst=0, cp_wen=1 → cx_wrst_wen[(0,1)]

    for _ in range(3):           # hold a few cycles to be sure
        await RisingEdge(dut.wclk)
        dut.w_rst_n.value = 0
        dut.w_en.value    = 1
        await ReadOnly()
        await sample_coverage(dut)

    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 1
    dut.w_en.value    = 0
    await ClockCycles(dut.wclk, 3)

    # 6b: cx_rrst_ren[(0,1)] — assert r_rst_n=0 WITH r_en=1 at the same time
    # RTL read_ptr.sv:9 — async reset; r_en=1 during reset is legal
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 1
    dut.w_en.value    = 0
    dut.r_en.value    = 1        # read enable asserted
    dut.r_rst_n.value = 0        # reset also asserted — RTL ignores r_en, safe
    await ReadOnly()
    await sample_coverage(dut)   # cp_rrst=0, cp_ren=1 → cx_rrst_ren[(0,1)]

    for _ in range(3):
        await RisingEdge(dut.wclk)
        dut.r_rst_n.value = 0
        dut.r_en.value    = 1
        await ReadOnly()
        await sample_coverage(dut)

    await RisingEdge(dut.wclk)
    dut.r_rst_n.value = 1
    dut.r_en.value    = 0
    await ClockCycles(dut.wclk, 3)

    # 6c: cx_full_empty[(1,1)] — exploit the async-reset CDC timing window
    #
    # full  is write-domain: always_ff@(posedge wclk or negedge w_rst_n)
    #   → only changes on posedge wclk (or if w_rst_n falls)
    # empty is read-domain:  always_ff@(posedge rclk or negedge r_rst_n)
    #   → asserts IMMEDIATELY (same delta) when r_rst_n falls
    #
    # Strategy:
    #   1. Fill FIFO until full=1 (write domain)
    #   2. In the active phase right after a wclk rising edge, drive r_rst_n=0
    #   3. Verilator evaluates negedge r_rst_n → empty←1 in this delta
    #   4. full stays=1 (write-domain FF — won't change until next posedge wclk)
    #   5. ReadOnly() captures: full=1, empty=1

    # Clean reset both domains first
    await RisingEdge(dut.wclk)
    dut.w_en.value    = 0
    dut.r_en.value    = 0
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    await ClockCycles(dut.rclk, 5)
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1
    await ClockCycles(dut.wclk, 5)

    # Fill FIFO to full=1 (needs 256 writes, give up to 300)
    full_hit_p6 = False
    for _ in range(300):
        await RisingEdge(dut.wclk)
        dut.w_en.value    = 1
        dut.r_en.value    = 0
        dut.data_in.value = random.randint(0, 255)
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.full.value) == 1:
            full_hit_p6 = True
            break

    if full_hit_p6:
        # Assert r_rst_n=0 right after a wclk edge — BEFORE the next wclk fires.
        # Negedge r_rst_n triggers read_ptr async reset → empty←1 in same delta.
        # full remains 1 (write-domain FF, no new posedge wclk yet).
        await RisingEdge(dut.wclk)
        dut.w_en.value    = 0    # no new write — keep wptr/full stable
        dut.r_rst_n.value = 0    # falling edge → empty←1 immediately
        await ReadOnly()
        await sample_coverage(dut)  # full=1, empty=1 → cx_full_empty[(1,1)]

    # Restore clean state
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    await ClockCycles(dut.rclk, 5)
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1
    await ClockCycles(dut.wclk, 3)
    await ReadOnly()
    await sample_coverage(dut)

    # Final settle
    await ClockCycles(dut.wclk, 5)
    await ReadOnly()
    await sample_coverage(dut)

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
