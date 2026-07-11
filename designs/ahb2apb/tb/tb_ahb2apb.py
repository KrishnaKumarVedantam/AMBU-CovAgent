"""
tb/tb_ahb2apb.py
DESIGN-SPECIFIC — AHB2APB Bridge base testbench.

Verified against:
- ARM AMBA AHB/APB spec
- Ghonimo's verification suite
- RTL: bridge-top.v, AHB_Slave_Interface.v, APB_Controller.v

Address map (from RTL):
  Slave 1: 0x8000_0000 to 0x8400_0000 (Pselx=3'b001)
  Slave 2: 0x8400_0000 to 0x8800_0000 (Pselx=3'b010)
  Slave 3: 0x8800_0000 to 0x8C00_0000 (Pselx=3'b100)

Pipeline timing (AHB_Slave_Interface.v):
  Haddr1 = Haddr delayed 1 cycle
  Haddr2 = Haddr delayed 2 cycles
  Write: Paddr = Haddr1 (from WWAIT state output)
  Read:  Paddr = Haddr  (from IDLE state output)

FSM states (APB_Controller.v):
  ST_IDLE=0 ST_WWAIT=1 ST_READ=2  ST_WRITE=3
  ST_WRITEP=4 ST_RENABLE=5 ST_WENABLE=6 ST_WENABLEP=7

Hard bins left for agent:
  cp_htrans[1]: BUSY transfer
  cp_htrans[3]: SEQ transfer
  cp_fsm[4]:    ST_WRITEP (pipelined write)
  cp_fsm[7]:    ST_WENABLEP (pipelined write enable)
  cp_pselx[2]:  slave2 selected
  cp_pselx[4]:  slave3 selected
  cx_write_htrans[(1,3)]: write SEQ
  cx_write_htrans[(0,3)]: read SEQ
  cx_psel_enable[(2,1)]: slave2 in enable phase
  cx_psel_enable[(4,1)]: slave3 in enable phase
"""
import cocotb
import os
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, ClockCycles
from cocotb_coverage.coverage import coverage_db
from tb.ahb2apb_coverage import sample_coverage

# Address map constants
SLAVE1_ADDR = 0x80000000
SLAVE2_ADDR = 0x84000000
SLAVE3_ADDR = 0x88000000

# Htrans values
HTRANS_IDLE  = 0
HTRANS_BUSY  = 1
HTRANS_NONSEQ = 2
HTRANS_SEQ   = 3


async def do_reset(dut):
    """Reset sequence — samples cp_hresetn[0]."""
    dut.Hresetn.value  = 0
    dut.Hwrite.value   = 0
    dut.Hreadyin.value = 1
    dut.Hwdata.value   = 0
    dut.Haddr.value    = 0
    dut.Htrans.value   = HTRANS_IDLE
    dut.Prdata.value   = 0

    for _ in range(5):
        await RisingEdge(dut.Hclk)
        await ReadOnly()
        await sample_coverage(dut)  # cp_hresetn[0]

    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 1
    await RisingEdge(dut.Hclk)
    await ReadOnly()
    await sample_coverage(dut)  # cp_hresetn[1]


async def do_write(dut, addr, data):
    """
    Single AHB write transaction.
    Address phase: NONSEQ + addr
    Data phase: data on Hwdata
    Hits: cp_hwrite[1], cp_htrans[2], cp_valid[1],
          cp_fsm[1](WWAIT), cp_fsm[3](WRITE), cp_fsm[6](WENABLE)
          cp_pselx based on addr, cp_penable[1]
    """
    # Address phase
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value   = 1
    dut.Haddr.value    = addr
    dut.Htrans.value   = HTRANS_NONSEQ
    dut.Hreadyin.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    # Data phase — drive data, keep address
    await RisingEdge(dut.Hclk)
    dut.Hwdata.value = data
    dut.Htrans.value = HTRANS_IDLE
    await ReadOnly()
    await sample_coverage(dut)

    # Wait for Hreadyout=1 (transaction complete)
    for _ in range(10):
        await RisingEdge(dut.Hclk)
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.Hreadyout.value) == 1:
            break

    # Idle after transaction
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Htrans.value = HTRANS_IDLE
    await ReadOnly()
    await sample_coverage(dut)


async def do_read(dut, addr, prdata=0xDEADBEEF):
    """
    Single AHB read transaction.
    Hits: cp_hwrite[0], cp_htrans[2], cp_valid[1],
          cp_fsm[2](READ), cp_fsm[5](RENABLE)
    """
    # Address phase — all assignments after RisingEdge to avoid ReadOnly violation
    await RisingEdge(dut.Hclk)
    dut.Prdata.value   = prdata  # APB slave response
    dut.Hwrite.value   = 0
    dut.Haddr.value    = addr
    dut.Htrans.value   = HTRANS_NONSEQ
    dut.Hreadyin.value = 1
    await ReadOnly()
    await sample_coverage(dut)

    # Data phase
    await RisingEdge(dut.Hclk)
    dut.Htrans.value = HTRANS_IDLE
    await ReadOnly()
    await sample_coverage(dut)

    # Wait for Hreadyout=1
    for _ in range(10):
        await RisingEdge(dut.Hclk)
        await ReadOnly()
        await sample_coverage(dut)
        if int(dut.Hreadyout.value) == 1:
            break

    await RisingEdge(dut.Hclk)
    dut.Htrans.value = HTRANS_IDLE
    await ReadOnly()
    await sample_coverage(dut)


@cocotb.test()
async def test_ahb2apb_base(dut):
    """
    Base testbench for AHB2APB bridge.
    Hits 36 of 46 bins (78%).
    Leaves 10 hard bins for agent.
    """
    cocotb.start_soon(Clock(dut.Hclk, 10, units='ns').start())

    # Reset
    await do_reset(dut)

    # Test 1: Single write to slave 1
    await do_write(dut, SLAVE1_ADDR + 0x100, 0xAABBCCDD)

    # Test 2: Single read from slave 1
    await do_read(dut, SLAVE1_ADDR + 0x200, prdata=0x12345678)

    # Test 3: Invalid address — valid=0, FSM stays IDLE
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 1
    dut.Haddr.value  = 0x00001000  # outside valid range
    dut.Htrans.value = HTRANS_NONSEQ
    await ReadOnly()
    await sample_coverage(dut)  # valid=0, Pselx=0
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Htrans.value = HTRANS_IDLE
    await ReadOnly()
    await sample_coverage(dut)

    # Test 4: Hreadyin=0 — valid=0 even with correct address
    await RisingEdge(dut.Hclk)
    dut.Hreadyin.value = 0
    dut.Haddr.value    = SLAVE1_ADDR
    dut.Htrans.value   = HTRANS_NONSEQ
    await ReadOnly()
    await sample_coverage(dut)  # cp_hreadyin[0], valid=0
    await RisingEdge(dut.Hclk)
    dut.Hreadyin.value = 1
    dut.Htrans.value   = HTRANS_IDLE
    await ReadOnly()
    await sample_coverage(dut)

    # Test 5: Multiple writes to slave 1 — exercise more FSM states
    for i in range(3):
        await do_write(dut, SLAVE1_ADDR + i * 0x10, 0x1000 + i)

    # Test 6: Multiple reads from slave 1
    for i in range(3):
        await do_read(dut, SLAVE1_ADDR + i * 0x10, prdata=0xA000 + i)

    # Final idle cycles
    for _ in range(5):
        await RisingEdge(dut.Hclk)
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
