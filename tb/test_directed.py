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
async def test_async_fifo_priority1(dut):
    cocotb.start_soon(Clock(dut.wclk, 10, units='ns').start())
    cocotb.start_soon(Clock(dut.rclk, 15, units='ns').start())

    write_queue = []

    # Initialize signals
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    dut.w_en.value = 0
    dut.r_en.value = 0
    dut.data_in.value = 0

    for _ in range(5):
        await RisingEdge(dut.wclk)

    # =========================================================
    # TARGET: cx_wrst_wen[(0,1)] — w_rst_n=0 AND w_en=1
    # =========================================================
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 0
    dut.w_en.value = 1
    dut.data_in.value = 0xAA
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 0
    dut.w_en.value = 1
    dut.data_in.value = 0xBB
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 0
    dut.w_en.value = 1
    dut.data_in.value = 0xCC
    await ReadOnly()
    await sample_coverage(dut)

    # =========================================================
    # TARGET: cx_rrst_ren[(0,1)] — r_rst_n=0 AND r_en=1
    # =========================================================
    await RisingEdge(dut.rclk)
    dut.r_rst_n.value = 0
    dut.r_en.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.rclk)
    dut.r_rst_n.value = 0
    dut.r_en.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.rclk)
    dut.r_rst_n.value = 0
    dut.r_en.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    # =========================================================
    # Release resets — all assignments before ReadOnly
    # =========================================================
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1
    dut.w_en.value = 0
    dut.r_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(3):
        await RisingEdge(dut.wclk)

    # =========================================================
    # TARGET: cx_full_empty[(1,1)]
    # Fill FIFO to get full=1, then assert r_rst_n=0 to get empty=1
    # =========================================================

    # Fill the FIFO — all signal assignments before ReadOnly
    for i in range(300):
        await RisingEdge(dut.wclk)
        dut.w_en.value = 1
        dut.data_in.value = i & 0xFF
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.full.value):
            break

    await RisingEdge(dut.wclk)
    dut.w_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(5):
        await RisingEdge(dut.wclk)
        await ReadOnly()
        await sample_coverage(dut)

    # Assert r_rst_n=0 asynchronously — empty goes to 1 per RTL
    # full remains 1 since write domain not reset
    for _ in range(10):
        await RisingEdge(dut.rclk)
        dut.r_rst_n.value = 0
        await ReadOnly()
        await sample_coverage(dut)

    await RisingEdge(dut.rclk)
    dut.r_rst_n.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    # =========================================================
    # PRIORITY 2: Data integrity — full reset then write/read
    # =========================================================
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    dut.w_en.value = 0
    dut.r_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(5):
        await RisingEdge(dut.wclk)

    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    write_queue.clear()

    for _ in range(3):
        await RisingEdge(dut.wclk)

    # Sample empty=1 state
    await RisingEdge(dut.wclk)
    dut.w_en.value = 0
    dut.r_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # Write entries and track data
    written = 0
    for i in range(300):
        await RisingEdge(dut.wclk)
        val = (i * 5 + 13) & 0xFF
        dut.w_en.value = 1
        dut.data_in.value = val
        await ReadOnly()
        is_full = int(dut.full.value)
        await sample_coverage(dut)
        if not is_full:
            write_queue.append(val)
            written += 1
        if is_full:
            break

    await RisingEdge(dut.wclk)
    dut.w_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # Sample full=1
    for _ in range(3):
        await RisingEdge(dut.wclk)
        await ReadOnly()
        await sample_coverage(dut)

    # Read back and verify data integrity
    prev_empty = int(dut.empty.value)
    for i in range(written + 20):
        await RisingEdge(dut.rclk)
        dut.r_en.value = 1
        await ReadOnly()
        cur_empty = int(dut.empty.value)
        await sample_coverage(dut)
        if not prev_empty and len(write_queue) > 0:
            actual = int(dut.data_out.value)
            expected = write_queue.pop(0)
            assert actual == expected, f'DATA FAIL: {actual} != {expected}'
        prev_empty = cur_empty
        if cur_empty and i > 5:
            break

    await RisingEdge(dut.rclk)
    dut.r_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # Sample empty after draining
    for _ in range(5):
        await RisingEdge(dut.rclk)
        await ReadOnly()
        await sample_coverage(dut)

    # =========================================================
    # Second attempt at cx_full_empty with fresh fill
    # =========================================================
    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 0
    dut.r_rst_n.value = 0
    dut.w_en.value = 0
    dut.r_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(5):
        await RisingEdge(dut.wclk)

    await RisingEdge(dut.wclk)
    dut.w_rst_n.value = 1
    dut.r_rst_n.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(3):
        await RisingEdge(dut.wclk)

    write_queue.clear()

    for i in range(300):
        await RisingEdge(dut.wclk)
        dut.w_en.value = 1
        dut.data_in.value = i & 0xFF
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.full.value):
            break

    await RisingEdge(dut.wclk)
    dut.w_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(10):
        await RisingEdge(dut.wclk)
        await ReadOnly()
        await sample_coverage(dut)

    # Assert r_rst_n=0 while full=1 to get empty=1 simultaneously
    for _ in range(15):
        await RisingEdge(dut.rclk)
        dut.r_rst_n.value = 0
        await ReadOnly()
        await sample_coverage(dut)

    await RisingEdge(dut.rclk)
    dut.r_rst_n.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    coverage_db.export_to_yaml("/Users/krishna/uvm-coverage-agent-backup-v2.10.3.git/coverage_reports/coverage.yml")