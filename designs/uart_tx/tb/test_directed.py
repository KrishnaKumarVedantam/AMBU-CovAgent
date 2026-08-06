import cocotb
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tb_uart_tx import sample_coverage
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, Timer
from cocotb_coverage.coverage import coverage_db

@cocotb.test()
async def test_hit_priority_bins(dut):
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 20, units='ns').start())

    write_queue = []

    # Initialize signals
    dut.resetn.value = 0
    dut.uart_tx_en.value = 0
    dut.uart_tx_data.value = 0

    # Apply reset for a few cycles
    for _ in range(5):
        await RisingEdge(dut.clk)

    await ReadOnly()
    await sample_coverage(dut)

    # De-assert reset
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    dut.uart_tx_en.value = 0
    dut.uart_tx_data.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # -----------------------------------------------------------------------
    # TARGET: cx_rst_en[(0,1)] — resetn=0 AND uart_tx_en=1 simultaneously
    # -----------------------------------------------------------------------
    await RisingEdge(dut.clk)
    dut.resetn.value = 0       # reset active (low)
    dut.uart_tx_en.value = 1   # enable high at same time
    await ReadOnly()
    await sample_coverage(dut)

    # Keep for a few cycles to ensure sampling
    for _ in range(3):
        await RisingEdge(dut.clk)
        dut.resetn.value = 0
        dut.uart_tx_en.value = 1
        await ReadOnly()
        await sample_coverage(dut)

    # De-assert reset, keep enable low
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    dut.uart_tx_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # -----------------------------------------------------------------------
    # TARGET: cx_en_busy[(1,1)] — uart_tx_en=1 AND uart_tx_busy=1 simultaneously
    # uart_tx_busy = (fsm_state != FSM_IDLE)
    # So we need to assert uart_tx_en while the module is already busy (transmitting)
    # -----------------------------------------------------------------------

    # First, start a transmission to make the module busy
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0xA5
    write_queue.append(0xA5)
    await ReadOnly()
    await sample_coverage(dut)

    # Wait one clock so FSM transitions to FSM_START (busy=1)
    await RisingEdge(dut.clk)
    # Keep uart_tx_en=1 while busy=1
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0xA5
    await ReadOnly()
    # At this point fsm_state should be FSM_START (busy=1) and uart_tx_en=1
    await sample_coverage(dut)

    # Sample a few more cycles with en=1 and busy=1
    for _ in range(10):
        await RisingEdge(dut.clk)
        dut.uart_tx_en.value = 1
        dut.uart_tx_data.value = 0xA5
        await ReadOnly()
        await sample_coverage(dut)

    # Now let the transmission complete - drop enable
    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # Wait for transmission to complete (PAYLOAD_BITS + START + STOP bits * CYCLES_PER_BIT)
    # BIT_RATE=9600, CLK_HZ=50MHz => CYCLES_PER_BIT = 5208
    # Total bits = 1 start + 8 data + 1 stop = 10 bits
    # Total cycles = 10 * 5208 = 52080
    cycles_per_bit = 5208
    total_cycles = (1 + 8 + 1) * cycles_per_bit + 100

    for i in range(total_cycles):
        await RisingEdge(dut.clk)
        if i % 1000 == 0:
            await ReadOnly()
            await sample_coverage(dut)

    await ReadOnly()
    await sample_coverage(dut)

    # -----------------------------------------------------------------------
    # Do another transmission to hit cx_en_busy more reliably
    # Start a new transmission, then immediately assert en again while busy
    # -----------------------------------------------------------------------
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0x55
    write_queue.append(0x55)
    await ReadOnly()
    await sample_coverage(dut)

    # Next cycle: module should be busy (FSM_START), keep en=1
    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0x55
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(20):
        await RisingEdge(dut.clk)
        dut.uart_tx_en.value = 1
        dut.uart_tx_data.value = 0x55
        await ReadOnly()
        await sample_coverage(dut)

    # Drop enable and wait for completion
    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for i in range(total_cycles):
        await RisingEdge(dut.clk)
        if i % 1000 == 0:
            await ReadOnly()
            await sample_coverage(dut)

    await ReadOnly()
    await sample_coverage(dut)

    # -----------------------------------------------------------------------
    # Additional coverage: hit all FSM states and resetn bins
    # -----------------------------------------------------------------------

    # Reset again
    await RisingEdge(dut.clk)
    dut.resetn.value = 0
    dut.uart_tx_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(3):
        await RisingEdge(dut.clk)
        dut.resetn.value = 0
        dut.uart_tx_en.value = 0
        await ReadOnly()
        await sample_coverage(dut)

    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    dut.uart_tx_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # Start another transmission and sample through all FSM states
    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = 0xFF
    write_queue.append(0xFF)
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 0
    await ReadOnly()
    await sample_coverage(dut)

    # Sample through the full transmission
    for i in range(total_cycles):
        await RisingEdge(dut.clk)
        if i % 500 == 0:
            await ReadOnly()
            await sample_coverage(dut)

    await ReadOnly()
    await sample_coverage(dut)

    coverage_db.export_to_yaml("/Users/krishna/uvm-coverage-agent-backup-v2.10.3.git/designs/uart_tx/coverage_reports/coverage.yml")