"""
test_scoreboard_buggy.py — UART TX Fault Injection Suite
─────────────────────────────────────────────────────────
PURPOSE: Validate that the UART scoreboard catches real data corruption.

METHODOLOGY: Mutation testing — industry standard technique for scoreboard
qualification. Each test injects a KNOWN fault and confirms the scoreboard
detects it. If a test reports SCOREBOARD FAIL → scoreboard is working.
If any test reports SCOREBOARD PASS → scoreboard has a blind spot.

FAULT CATEGORIES (based on hardware verification literature):
  FAULT 1 — Single bit flip: one bit corrupted in the transmitted byte
  FAULT 2 — Zero corruption: transmit all zeros regardless of input
  FAULT 3 — Offset corruption: transmitted byte is value+1 (off by one)
  FAULT 4 — Inversion: all data bits inverted on the wire

EXPECTED RESULT: ALL FOUR TESTS MUST REPORT SCOREBOARD FAIL.
A scoreboard that catches all four categories is robust against
the most common data corruption patterns in hardware.

Reference: "Functional Testbench Qualification by Mutation Analysis"
  Hindawi VLSI Design, 2015 — deterministic mutation operators
  Berkeley EECS-2024-157 — deterministic mutation techniques for RTL
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly
from tb.uart_scoreboard import UartScoreboard

CYCLES_PER_BIT = 10


async def sample_uart_frame(dut, sb, data, fault_type):
    """
    Drive one UART TX transaction and check all bits through scoreboard.
    fault_type controls what the scoreboard EXPECTS (not what the DUT sends).
    DUT always receives the true data and transmits correctly.
    Scoreboard is told to expect the FAULTY version.
    """
    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 1
    dut.uart_tx_data.value = data      # DUT gets TRUE data
    await RisingEdge(dut.clk)
    dut.uart_tx_en.value = 0

    await ReadOnly()
    assert int(dut.uart_tx_busy.value) == 1, \
        f"FAIL: busy must assert for 0x{data:02X}"

    # Tell scoreboard to expect the FAULTY version
    if fault_type == 'bit_flip':
        faulty = data ^ 0x08           # FAULT 1: flip bit 3
    elif fault_type == 'zero':
        faulty = 0x00                  # FAULT 2: expect all zeros
    elif fault_type == 'offset':
        faulty = (data + 1) & 0xFF     # FAULT 3: expect value+1
    elif fault_type == 'inversion':
        faulty = data ^ 0xFF           # FAULT 4: expect all bits inverted
    else:
        faulty = data                  # No fault (baseline)

    sb.expect_frame(faulty)            # Scoreboard expects WRONG data

    # Sample start bit
    await RisingEdge(dut.clk)
    await ReadOnly()
    start_bit = int(dut.uart_txd.value)
    sb.check_and_count(start_bit, 'cx_en_busy[(0,1)]')

    # Sample 8 data bits + 1 stop bit at midpoint of each bit period
    for bit_idx in range(9):
        wait_cycles = (CYCLES_PER_BIT + CYCLES_PER_BIT // 2) if bit_idx == 0 else CYCLES_PER_BIT + 1
        for _ in range(wait_cycles):
            await RisingEdge(dut.clk)
        await ReadOnly()
        expected_bit = sb.expected_bits[0] if sb.expected_bits else -1
        bit_val = int(dut.uart_txd.value)
        result = sb.check_and_count(bit_val, 'cp_tx_busy[1]')
        if not result:
            cocotb.log.info(
                f"  [{fault_type}] BIT {bit_idx} correctly caught: "
                f"got {bit_val}, scoreboard expected {expected_bit}")

    # Wait for FSM to return to IDLE
    for _ in range(CYCLES_PER_BIT):
        await RisingEdge(dut.clk)
    await ReadOnly()
    sb.record_hit('cp_tx_busy[0]')
    sb.record_hit('cp_tx_en[0]')
    sb.record_hit('cx_en_busy[(0,0)]')
    sb.record_hit('cx_rst_en[(1,0)]')
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def reset_dut(dut, sb):
    dut.resetn.value = 0
    dut.uart_tx_en.value = 0
    dut.uart_tx_data.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    sb.record_hit('cp_resetn[0]')
    sb.record_hit('cx_rst_en[(0,0)]')
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    await RisingEdge(dut.clk)
    sb.record_hit('cp_resetn[1]')
    sb.record_hit('cp_tx_busy[0]')
    sb.record_hit('cx_rst_en[(1,0)]')


@cocotb.test()
async def fault1_single_bit_flip(dut):
    """
    FAULT 1 — Single bit flip (bit 3).
    DUT transmits 0x55 correctly. Scoreboard expects 0x5D (bit 3 flipped).
    Expected: SCOREBOARD FAIL on bit 3.
    """
    cocotb.log.info("=" * 60)
    cocotb.log.info("FAULT 1: Single bit flip (bit 3) on 0x55")
    cocotb.log.info("DUT sends: 0x55 = 01010101")
    cocotb.log.info("SB expect: 0x5D = 01011101 (bit 3 flipped)")
    cocotb.log.info("=" * 60)
    sb = UartScoreboard()
    cocotb.start_soon(Clock(dut.clk, 10, unit='ns').start())
    await reset_dut(dut, sb)
    await sample_uart_frame(dut, sb, 0x55, 'bit_flip')
    result = sb.report()
    assert not result, \
        "SCOREBOARD BLIND SPOT: bit flip NOT detected — scoreboard failed to catch corruption"
    cocotb.log.info("FAULT 1 CONFIRMED: Scoreboard correctly detected bit flip")


@cocotb.test()
async def fault2_zero_corruption(dut):
    """
    FAULT 2 — Zero corruption.
    DUT transmits 0xAA correctly. Scoreboard expects 0x00 (all zeros).
    Simulates a DUT that pulls the TX line low (stuck-at-0).
    Expected: SCOREBOARD FAIL on all data bits.
    """
    cocotb.log.info("=" * 60)
    cocotb.log.info("FAULT 2: Zero corruption on 0xAA")
    cocotb.log.info("DUT sends: 0xAA = 10101010")
    cocotb.log.info("SB expect: 0x00 = 00000000 (simulates stuck-at-0)")
    cocotb.log.info("=" * 60)
    sb = UartScoreboard()
    cocotb.start_soon(Clock(dut.clk, 10, unit='ns').start())
    await reset_dut(dut, sb)
    await sample_uart_frame(dut, sb, 0xAA, 'zero')
    result = sb.report()
    assert not result, \
        "SCOREBOARD BLIND SPOT: zero corruption NOT detected"
    cocotb.log.info("FAULT 2 CONFIRMED: Scoreboard correctly detected zero corruption")


@cocotb.test()
async def fault3_offset_corruption(dut):
    """
    FAULT 3 — Off-by-one corruption.
    DUT transmits 0xFF correctly. Scoreboard expects 0x00 (0xFF+1 wraps to 0).
    Simulates an incrementer bug in the data path.
    Expected: SCOREBOARD FAIL on bit 0 (LSB differs).
    """
    cocotb.log.info("=" * 60)
    cocotb.log.info("FAULT 3: Off-by-one corruption on 0xFF")
    cocotb.log.info("DUT sends: 0xFF = 11111111")
    cocotb.log.info("SB expect: 0x00 = 00000000 (0xFF+1 wraps)")
    cocotb.log.info("=" * 60)
    sb = UartScoreboard()
    cocotb.start_soon(Clock(dut.clk, 10, unit='ns').start())
    await reset_dut(dut, sb)
    await sample_uart_frame(dut, sb, 0xFF, 'offset')
    result = sb.report()
    assert not result, \
        "SCOREBOARD BLIND SPOT: offset corruption NOT detected"
    cocotb.log.info("FAULT 3 CONFIRMED: Scoreboard correctly detected offset corruption")


@cocotb.test()
async def fault4_full_inversion(dut):
    """
    FAULT 4 — Full inversion (all bits flipped).
    DUT transmits 0xA5 correctly. Scoreboard expects 0x5A (all bits inverted).
    Simulates an inverter bug on the TX data path.
    Expected: SCOREBOARD FAIL on every data bit.
    """
    cocotb.log.info("=" * 60)
    cocotb.log.info("FAULT 4: Full inversion on 0xA5")
    cocotb.log.info("DUT sends: 0xA5 = 10100101")
    cocotb.log.info("SB expect: 0x5A = 01011010 (all bits inverted)")
    cocotb.log.info("=" * 60)
    sb = UartScoreboard()
    cocotb.start_soon(Clock(dut.clk, 10, unit='ns').start())
    await reset_dut(dut, sb)
    await sample_uart_frame(dut, sb, 0xA5, 'inversion')
    result = sb.report()
    assert not result, \
        "SCOREBOARD BLIND SPOT: full inversion NOT detected"
    cocotb.log.info("FAULT 4 CONFIRMED: Scoreboard correctly detected full inversion")
