import cocotb
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly
from cocotb_coverage.coverage import coverage_db

try:
    from tb_fifo import sample_coverage
except ImportError:
    from tb.tb_fifo import sample_coverage


@cocotb.test()
async def test_full_empty_simultaneous(dut):
    """
    Target cx_full_empty[(1,1)]: full=1 AND empty=1 simultaneously.
    Fill FIFO to get full=1, then assert r_rst_n=0 which asynchronously
    forces empty=1 per RTL (negedge r_rst_n in always_ff).
    """

    cocotb.start_soon(Clock(dut.wclk, 10, units='ns').start())
    cocotb.start_soon(Clock(dut.rclk, 13, units='ns').start())

    # --- Reset both domains ---
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    dut.w_en.value = 0
    dut.r_en.value = 0
    dut.data_in.value = 0

    for _ in range(8):
        await RisingEdge(dut.wclk)

    for _ in range(8):
        await RisingEdge(dut.rclk)

    # Release reset - assign BEFORE any ReadOnly
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1

    for _ in range(4):
        await RisingEdge(dut.wclk)

    # --- Phase 1: Fill FIFO to get full=1 ---
    # Pattern: await RisingEdge first, then set signals, then await ReadOnly, then sample
    # This ensures we are NOT in ReadOnly phase when assigning signals

    for i in range(512):
        await RisingEdge(dut.wclk)
        # Now safe to assign - we just passed the rising edge, not in ReadOnly
        dut.w_en.value = 1
        dut.r_en.value = 0
        dut.data_in.value = (i * 7 + 13) & 0xFF
        await ReadOnly()
        await sample_coverage(dut)

        if int(dut.full.value):
            break

    # --- Phase 2: Assert r_rst_n=0 while full=1 ---
    # empty has async reset: negedge r_rst_n forces empty=1 immediately
    # full remains 1 since w_rst_n is still high and FIFO is full

    await RisingEdge(dut.wclk)
    dut.w_en.value = 0
    dut.r_en.value = 0
    dut.r_rst_n.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.rclk)
    # Do NOT assign signals here - just sample
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.wclk)
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.rclk)
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.wclk)
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.rclk)
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.wclk)
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.rclk)
    await ReadOnly()
    await sample_coverage(dut)

    # Release r_rst_n
    await RisingEdge(dut.rclk)
    dut.r_rst_n.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(4):
        await RisingEdge(dut.rclk)

    # --- Phase 3: Read out FIFO ---
    for _ in range(300):
        await RisingEdge(dut.rclk)
        dut.r_en.value = 1
        dut.w_en.value = 0
        await ReadOnly()
        await sample_coverage(dut)

        if int(dut.empty.value):
            break

    await RisingEdge(dut.rclk)
    dut.r_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # --- Phase 4: Full reset and refill for half_full/half_empty coverage ---
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    dut.w_en.value = 0
    dut.r_en.value = 0
    dut.data_in.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(6):
        await RisingEdge(dut.wclk)

    for _ in range(6):
        await RisingEdge(dut.rclk)

    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(3):
        await RisingEdge(dut.wclk)

    # Write to trigger half_full (waddr == 8'b01011000 = 88)
    for i in range(200):
        await RisingEdge(dut.wclk)
        dut.w_en.value = 1
        dut.r_en.value = 0
        dut.data_in.value = (i * 5 + 3) & 0xFF
        await ReadOnly()
        await sample_coverage(dut)

        if int(dut.full.value):
            break

    await RisingEdge(dut.wclk)
    dut.w_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(3):
        await RisingEdge(dut.wclk)
        await ReadOnly()
        await sample_coverage(dut)

    # Read to trigger half_empty (raddr == 8'b01011000 = 88)
    for _ in range(200):
        await RisingEdge(dut.rclk)
        dut.r_en.value = 1
        await ReadOnly()
        await sample_coverage(dut)

        if int(dut.empty.value):
            break

    await RisingEdge(dut.rclk)
    dut.r_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(5):
        await RisingEdge(dut.rclk)
        await ReadOnly()
        await sample_coverage(dut)

    # --- Phase 5: Second attempt at full+empty simultaneously ---
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    dut.w_en.value = 0
    dut.r_en.value = 0
    dut.data_in.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(8):
        await RisingEdge(dut.wclk)

    for _ in range(8):
        await RisingEdge(dut.rclk)

    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(4):
        await RisingEdge(dut.wclk)

    # Fill FIFO completely
    for i in range(512):
        await RisingEdge(dut.wclk)
        dut.w_en.value = 1
        dut.r_en.value = 0
        dut.data_in.value = (i * 3 + 17) & 0xFF
        await ReadOnly()
        await sample_coverage(dut)

        if int(dut.full.value):
            break

    # Assert r_rst_n=0 - empty goes to 1 asynchronously
    await RisingEdge(dut.wclk)
    dut.w_en.value = 0
    dut.r_en.value = 0
    dut.r_rst_n.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(8):
        await RisingEdge(dut.wclk)
        await ReadOnly()
        await sample_coverage(dut)

    for _ in range(8):
        await RisingEdge(dut.rclk)
        await ReadOnly()
        await sample_coverage(dut)

    await RisingEdge(dut.rclk)
    dut.r_rst_n.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(4):
        await RisingEdge(dut.rclk)
        await ReadOnly()
        await sample_coverage(dut)

    coverage_db.export_to_yaml("/Users/krishna/uvm-coverage-agent-backup-v2.9/coverage_reports/coverage.yml")