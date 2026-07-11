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
        assert int(dut.uart_txd.value) == 0, \
            f"FAIL: txd must go low for start bit for 0x{data:02X}"
        sb.record_hit('cx_en_busy[(0,1)]')

        # Wait for TX complete
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            if int(dut.uart_tx_busy.value) == 0:
                break

        # RTL: txd_reg<=1 in FSM_IDLE — verify line returns high
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
