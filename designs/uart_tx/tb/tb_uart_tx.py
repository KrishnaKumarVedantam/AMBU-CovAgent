import cocotb
import random
import os
import atexit as _atexit
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, ClockCycles
from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db

# Guarantee export fires even when test_directed.py puts coverage_db.export_to_yaml()
# at module scope (runs at import time, before any test, writing zeros).
# Since test_directed.py always imports sample_coverage from this module, this atexit
# fires after all tests complete, overwriting any premature zero-export.
_cov_yml = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'coverage_reports', 'coverage.yml'
)

@_atexit.register
def _auto_export_coverage():
    os.makedirs(os.path.dirname(_cov_yml), exist_ok=True)
    coverage_db.export_to_yaml(filename=_cov_yml)


@CoverPoint("top.cp_resetn",
    xf=lambda dut: int(dut.resetn.value), bins=[0, 1])
@CoverPoint("top.cp_tx_en",
    xf=lambda dut: int(dut.uart_tx_en.value), bins=[0, 1])
@CoverPoint("top.cp_tx_busy",
    xf=lambda dut: int(dut.uart_tx_busy.value), bins=[0, 1])
@CoverPoint("top.cp_fsm",
    xf=lambda dut: int(dut.fsm_state.value), bins=[0, 1, 2, 3])
@CoverCross("top.cx_en_busy",
    items=["top.cp_tx_en", "top.cp_tx_busy"])
@CoverCross("top.cx_rst_en",
    items=["top.cp_resetn", "top.cp_tx_en"])
async def sample_coverage(dut):
    pass


@cocotb.test()
async def test_uart_base(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units='ns').start())

    # Drive initial values
    dut.resetn.value = 0
    dut.uart_tx_en.value = 0
    dut.uart_tx_data.value = 0

    # Sample DURING reset — hits cp_resetn[0]
    for _ in range(5):
        await RisingEdge(dut.clk)
        await ReadOnly()
        await sample_coverage(dut)

    # Release reset — must be in active phase after RisingEdge
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    await sample_coverage(dut)

    # Send 3 random bytes
    for _ in range(3):
        data = random.randint(0, 255)

        # Assert tx_en=1 while busy=0 — hits cx_en_busy[(1,0)]
        await RisingEdge(dut.clk)
        dut.uart_tx_en.value = 1
        dut.uart_tx_data.value = data
        await ReadOnly()
        await sample_coverage(dut)

        # Next edge — FSM moves to START, busy=1
        await RisingEdge(dut.clk)
        dut.uart_tx_en.value = 0

        # Wait for TX complete
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            await sample_coverage(dut)
            if int(dut.uart_tx_busy.value) == 0:
                break

        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)

    # Final sample at idle
    await RisingEdge(dut.clk)
    await ReadOnly()
    await sample_coverage(dut)

    os.makedirs("coverage_reports", exist_ok=True)
    coverage_db.export_to_yaml(
        filename="coverage_reports/coverage_base.yml")
    coverage_db.export_to_yaml(
        filename="coverage_reports/coverage.yml")

    try:
        total = hit = 0
        for name, attrs in coverage_db.items():
            if hasattr(attrs, 'detailed_coverage'):
                for b, c in attrs.detailed_coverage.items():
                    total += 1
                    if c > 0: hit += 1
        pct = (hit / total * 100) if total > 0 else 0.0
        print(f"\n=== BASE COVERAGE: {pct:.1f}% ({hit}/{total} bins) ===\n")
    except Exception as e:
        print(f"Coverage note: {e}")
