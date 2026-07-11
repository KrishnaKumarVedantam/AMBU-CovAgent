import cocotb
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from tb_uart_tx import sample_coverage
except ImportError:
    from tb.tb_uart_tx import sample_coverage

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, Timer
from cocotb_coverage.coverage import coverage_db

@cocotb.test()
async def test_hit_priority_bins(dut):
    """
    Target:
    1. cx_en_busy[(1,1)]: uart_tx_en=1 AND uart_tx_busy=1 simultaneously
       - uart_tx_busy is high when fsm_state != FSM_IDLE
       - So we need to assert uart_tx_en=1 while a transmission is in progress
    2. cx_rst_en[(0,1)]: resetn=0 AND uart_tx_en=1 simultaneously
    """

    write_queue = []

    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, units='ns').start())

    # -------------------------------------------------------------------------
    # Initial reset
    # -------------------------------------------------------------------------
    dut.resetn.value = 0
    dut.uart_tx_en.value = 0
    dut.uart_tx_data.value = 0xA5

    for _ in range(5):
        await RisingEdge(dut.clk)

    await ReadOnly()
    await sample_coverage(dut)

    # -------------------------------------------------------------------------
    # TARGET: cx_rst_en[(0,1)] — resetn=0, uart_tx_en=1
    # -------------------------------------------------------------------------
    await RisingEdge(dut.clk)
    dut.resetn.value = 0
    dut.uart_tx_en.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    # Sample a few more times to ensure it's captured
    for _ in range(3):
        await RisingEdge(dut.clk)
        dut.resetn.value = 0
        dut.uart_tx_en.value = 1
        await ReadOnly()
        await sample_coverage(dut)

    # -------------------------------------------------------------------------
    # Release reset, start a transmission
    # -------------------------------------------------------------------------
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    dut.uart_tx_en.value = 0
    await RisingEdge(dut.clk)

    # Send a byte to get the FSM out of IDLE (busy=1)
    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0x55
    write_queue.append(0x55)

    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 0

    await ReadOnly()
    await sample_coverage(dut)

    # -------------------------------------------------------------------------
    # TARGET: cx_en_busy[(1,1)] — uart_tx_en=1 AND uart_tx_busy=1
    # uart_tx_busy goes high when fsm_state != FSM_IDLE
    # After the first enable pulse, FSM moves to FSM_START on next clock
    # We need to assert uart_tx_en=1 while busy=1
    # -------------------------------------------------------------------------

    # Wait a few cycles for FSM to enter FSM_START (busy=1)
    for _ in range(3):
        await RisingEdge(dut.clk)
        await ReadOnly()
        busy_val = int(dut.uart_tx_busy.value)
        if busy_val == 1:
            break

    # Now assert uart_tx_en=1 while busy=1
    # We need to drive signals before ReadOnly
    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0xAA
    await ReadOnly()
    busy_now = int(dut.uart_tx_busy.value)
    en_now = int(dut.uart_tx_en.value)
    await sample_coverage(dut)

    # Keep asserting en while busy for multiple cycles to ensure capture
    for _ in range(10):
        await RisingEdge(dut.clk)
        dut.uart_tx_en.value = 1
        dut.uart_tx_data.value = 0xAA
        await ReadOnly()
        busy_now = int(dut.uart_tx_busy.value)
        await sample_coverage(dut)
        if busy_now == 1:
            # Good, we have the cross condition
            pass

    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 0

    # -------------------------------------------------------------------------
    # Let the transmission complete and do data integrity check
    # -------------------------------------------------------------------------
    # Wait for busy to go low (transmission complete)
    timeout = 10000
    count = 0
    while count < timeout:
        await RisingEdge(dut.clk)
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.uart_tx_busy.value) == 0:
            break
        count += 1

    # -------------------------------------------------------------------------
    # Additional test: send another byte with en=1 while busy=1
    # Start a new transmission
    # -------------------------------------------------------------------------
    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0x33
    write_queue.append(0x33)
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.clk)
    # Keep en=1 for several cycles while FSM transitions to busy
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0x33
    await ReadOnly()
    await sample_coverage(dut)

    # Now FSM should be in FSM_START (busy=1), keep en=1
    for _ in range(20):
        await RisingEdge(dut.clk)
        dut.uart_tx_en.value = 1
        dut.uart_tx_data.value = 0x33
        await ReadOnly()
        await sample_coverage(dut)

    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 0

    # Wait for completion
    timeout = 10000
    count = 0
    while count < timeout:
        await RisingEdge(dut.clk)
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.uart_tx_busy.value) == 0:
            break
        count += 1

    # -------------------------------------------------------------------------
    # cx_rst_en[(0,1)] — also try while busy to cover more scenarios
    # -------------------------------------------------------------------------
    # Start another transmission
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0xF0
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # Wait for FSM to be busy
    for _ in range(3):
        await RisingEdge(dut.clk)
        await ReadOnly()
        await sample_coverage(dut)

    # Now assert reset=0 and en=1 simultaneously
    await RisingEdge(dut.clk)
    dut.resetn.value = 0
    dut.uart_tx_en.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(5):
        await RisingEdge(dut.clk)
        dut.resetn.value = 0
        dut.uart_tx_en.value = 1
        await ReadOnly()
        await sample_coverage(dut)

    # Release reset
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    dut.uart_tx_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # Wait for any ongoing transmission to complete
    timeout = 10000
    count = 0
    while count < timeout:
        await RisingEdge(dut.clk)
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.uart_tx_busy.value) == 0:
            break
        count += 1

    # Final sampling
    for _ in range(10):
        await RisingEdge(dut.clk)
        await ReadOnly()
        await sample_coverage(dut)

    coverage_db.export_to_yaml("/Users/krishna/uvm-coverage-agent-backup-v2.9/designs/uart_tx/coverage_reports/coverage.yml")