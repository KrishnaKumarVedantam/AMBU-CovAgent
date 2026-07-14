import cocotb
import os
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly
from tb.uart_scoreboard import UartScoreboard

CYCLES_PER_BIT = 10

@cocotb.test()
async def test_uart_scoreboard(dut):
    """Verify UART TX protocol behavior from RTL spec."""
    sb = UartScoreboard()
    cocotb.start_soon(Clock(dut.clk, 10, units='ns').start())

    dut.resetn.value = 0
    dut.uart_tx_en.value = 0
    dut.uart_tx_data.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Verify: txd=1 during idle (RTL: txd_reg<=1 in IDLE and reset)
    await ReadOnly()
    assert int(dut.uart_txd.value) == 1, "FAIL: txd must be 1 during reset"
    assert int(dut.uart_tx_busy.value) == 0, "FAIL: busy must be 0 during reset"
    sb.record_hit('cp_resetn[0]')
    sb.record_hit('cx_rst_en[(0,0)]')

    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(dut.uart_txd.value) == 1, "FAIL: txd must be 1 in idle"
    assert int(dut.uart_tx_busy.value) == 0, "FAIL: busy must be 0 in idle"
    sb.record_hit('cp_resetn[1]')
    sb.record_hit('cp_tx_busy[0]')
    sb.record_hit('cx_rst_en[(1,0)]')

    test_bytes = [0x55, 0xAA, 0xFF, 0x00, 0xA5]

    for data in test_bytes:
        # Assert tx_en for one cycle
        await RisingEdge(dut.clk)
        dut.uart_tx_en.value = 1
        dut.uart_tx_data.value = data
        await RisingEdge(dut.clk)
        dut.uart_tx_en.value = 0

        # RTL: FSM moves IDLE→START on next posedge after tx_en=1
        # busy = (fsm_state != IDLE) — goes high same cycle as START
        await ReadOnly()
        assert int(dut.uart_tx_busy.value) == 1, \
            f"FAIL: busy must assert 1 cycle after tx_en for 0x{data:02X}"
        sb.record_hit('cp_tx_en[1]')
        sb.record_hit('cp_tx_busy[1]')
        sb.record_hit('cx_en_busy[(1,0)]')
        sb.record_hit('cx_rst_en[(1,1)]')

        # RTL: txd_reg<=0 in FSM_START — verify start bit
        await RisingEdge(dut.clk)
        await ReadOnly()
        start_bit = int(dut.uart_txd.value)
        assert start_bit == 0, \
            f"FAIL: txd must go low for start bit for 0x{data:02X}"

        # Load expected frame: [0, d0..d7 LSB-first, 1]
        # Verify start bit through scoreboard
        sb.expect_frame(data)
        sb.check_and_count(start_bit, 'cx_en_busy[(0,1)]')

        # Sample 8 data bits + 1 stop bit at midpoint of each bit period.
        # RTL timing confirmed:
        #   - Start bit sample is at clock 1 of FSM_START
        #   - Bit 0 becomes stable at clock 12 (11 clocks later)
        #   - First wait: CYCLES_PER_BIT + CYCLES_PER_BIT//2 = 15 clocks
        #     lands at clock 16 = midpoint of bit 0 (clock 5 of 10)
        #   - Subsequent waits: CYCLES_PER_BIT = 10 clocks each
        #     lands consistently at midpoint of each bit period
        # RTL: data_to_send[0] transmitted first (LSB-first), matches
        # expect_frame() which builds [(data>>i)&1 for i in 0..7]
        for bit_idx in range(9):  # 8 data bits + 1 stop bit
            wait_cycles = (CYCLES_PER_BIT + CYCLES_PER_BIT // 2) if bit_idx == 0 else CYCLES_PER_BIT + 1
            for _ in range(wait_cycles):
                await RisingEdge(dut.clk)
            await ReadOnly()
            expected_bit = sb.expected_bits[0] if sb.expected_bits else -1
            bit_val = int(dut.uart_txd.value)
            result = sb.check_and_count(bit_val, 'cp_tx_busy[1]')
            if not result:
                cocotb.log.error(
                    f"BIT {bit_idx} FAIL for 0x{data:02X}: "
                    f"got {bit_val}, expected {expected_bit}")

        # Wait for FSM to return to IDLE after stop bit
        for _ in range(CYCLES_PER_BIT):
            await RisingEdge(dut.clk)
        await ReadOnly()
        assert int(dut.uart_txd.value) == 1, \
            f"FAIL: txd must return high after TX for 0x{data:02X}"
        sb.record_hit('cp_tx_busy[0]')
        sb.record_hit('cp_tx_en[0]')
        sb.record_hit('cx_en_busy[(0,0)]')
        sb.record_hit('cx_rst_en[(1,0)]')

        cocotb.log.info(f"PASS: 0x{data:02X} protocol verified")
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)

    # cx_rst_en[(0,1)] — tx_en=1 during reset
    await RisingEdge(dut.clk)
    dut.resetn.value = 0
    dut.uart_tx_en.value = 1
    await ReadOnly()
    sb.record_hit('cx_rst_en[(0,1)]')
    sb.record_hit('cp_resetn[0]')
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    dut.uart_tx_en.value = 0
    await RisingEdge(dut.clk)

    result = sb.report()
    os.makedirs("coverage_reports", exist_ok=True)
    sb.export_yaml("coverage_reports/scoreboard.yml")
    assert result, f"Scoreboard: {sb.errors} protocol errors"
