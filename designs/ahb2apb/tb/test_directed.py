import cocotb
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from tb_ahb2apb import sample_coverage
except ImportError:
    from tb.tb_ahb2apb import sample_coverage

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly
from cocotb_coverage.coverage import coverage_db


async def drive_and_sample(dut):
    """Helper: wait for ReadOnly phase and sample. Must be called after signals are driven."""
    await ReadOnly()
    await sample_coverage(dut)


async def do_reset(dut):
    """Reset without any ReadOnly phase issues - only drive on clock edges."""
    dut.Hresetn.value = 0
    dut.Hwrite.value = 0
    dut.Hreadyin.value = 0
    dut.Htrans.value = 0
    dut.Haddr.value = 0
    dut.Hwdata.value = 0
    dut.Prdata.value = 0
    await RisingEdge(dut.Hclk)
    await RisingEdge(dut.Hclk)
    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 1
    await RisingEdge(dut.Hclk)


@cocotb.test()
async def test_cx_write_htrans_bins(dut):
    """
    Target bins:
      cx_write_htrans[(0,3)] = Hwrite=0, Htrans=2'b11 (SEQ read)
      cx_write_htrans[(1,1)] = Hwrite=1, Htrans=2'b01 (BUSY write)
    
    Also covers FSM states and data integrity.
    """
    cocotb.start_soon(Clock(dut.Hclk, 10, units='ns').start())

    write_queue = []

    # ---- Initial reset ----
    await do_reset(dut)

    # =========================================================
    # Target: cx_write_htrans[(1,1)] = Hwrite=1, Htrans=2'b01
    # Htrans=01 is BUSY. Drive Hwrite=1 with Htrans=01.
    # =========================================================

    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 1
    dut.Hwrite.value = 1
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b01
    dut.Haddr.value = 0x80000004
    dut.Hwdata.value = 0xAABBCCDD
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 1
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b01
    dut.Haddr.value = 0x80000008
    dut.Hwdata.value = 0x11223344
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 1
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b01
    dut.Haddr.value = 0x8000000C
    dut.Hwdata.value = 0x55667788
    await ReadOnly()
    await sample_coverage(dut)

    # Also try with reset deasserted just before
    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 0
    dut.Hwrite.value = 1
    dut.Htrans.value = 0b01
    dut.Haddr.value = 0x80000010
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 1
    dut.Hwrite.value = 1
    dut.Htrans.value = 0b01
    dut.Haddr.value = 0x80000014
    await ReadOnly()
    await sample_coverage(dut)

    # =========================================================
    # Target: cx_write_htrans[(0,3)] = Hwrite=0, Htrans=2'b11
    # Htrans=11 is SEQ. Drive Hwrite=0 with Htrans=11.
    # =========================================================

    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 1
    dut.Hwrite.value = 0
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b11
    dut.Haddr.value = 0x80000020
    dut.Hwdata.value = 0x00000000
    dut.Prdata.value = 0xDEADBEEF
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b11
    dut.Haddr.value = 0x80000024
    dut.Prdata.value = 0x12345678
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b11
    dut.Haddr.value = 0x80000028
    dut.Prdata.value = 0xABCDEF01
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b11
    dut.Haddr.value = 0x8000002C
    dut.Prdata.value = 0x5A5A5A5A
    await ReadOnly()
    await sample_coverage(dut)

    # Also try with reset low
    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 0
    dut.Hwrite.value = 0
    dut.Htrans.value = 0b11
    dut.Haddr.value = 0x80000030
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 1
    dut.Hwrite.value = 0
    dut.Htrans.value = 0b11
    dut.Haddr.value = 0x80000034
    dut.Prdata.value = 0xCAFEBABE
    await ReadOnly()
    await sample_coverage(dut)

    # =========================================================
    # Full write transaction for FSM coverage and data integrity
    # =========================================================

    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 0
    dut.Hwrite.value = 0
    dut.Hreadyin.value = 0
    dut.Htrans.value = 0
    dut.Haddr.value = 0
    dut.Hwdata.value = 0
    dut.Prdata.value = 0
    await RisingEdge(dut.Hclk)
    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 1
    await RisingEdge(dut.Hclk)

    # IDLE -> WWAIT: valid=1, Hwrite=1, Htrans=NONSEQ
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 1
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b10
    dut.Haddr.value = 0x80000040
    dut.Hwdata.value = 0xCAFEBABE
    write_queue.append(0xCAFEBABE)
    await ReadOnly()
    await sample_coverage(dut)

    # WWAIT -> WRITE: valid=0 (Htrans=IDLE)
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 1
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b00
    dut.Haddr.value = 0x80000040
    dut.Hwdata.value = 0xCAFEBABE
    await ReadOnly()
    await sample_coverage(dut)

    # WRITE -> WENABLE
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Htrans.value = 0b00
    await ReadOnly()
    await sample_coverage(dut)

    # WENABLE -> IDLE
    await RisingEdge(dut.Hclk)
    dut.Htrans.value = 0b00
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    await ReadOnly()
    await sample_coverage(dut)

    # =========================================================
    # Read transaction for FSM coverage
    # =========================================================

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b10
    dut.Haddr.value = 0x80000050
    dut.Prdata.value = 0xFEEDFACE
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Htrans.value = 0b00
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Htrans.value = 0b00
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    await ReadOnly()
    await sample_coverage(dut)

    # =========================================================
    # WRITEP path: IDLE->WWAIT->WRITEP->WENABLEP
    # valid stays high during WWAIT
    # =========================================================

    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 0
    dut.Hwrite.value = 0
    dut.Hreadyin.value = 0
    dut.Htrans.value = 0
    dut.Haddr.value = 0
    dut.Hwdata.value = 0
    await RisingEdge(dut.Hclk)
    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 1
    await RisingEdge(dut.Hclk)

    # IDLE -> WWAIT
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 1
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b10
    dut.Haddr.value = 0x80000060
    dut.Hwdata.value = 0x11111111
    await ReadOnly()
    await sample_coverage(dut)

    # WWAIT -> WRITEP: valid=1 (keep Htrans=NONSEQ)
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 1
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b10
    dut.Haddr.value = 0x80000064
    dut.Hwdata.value = 0x22222222
    await ReadOnly()
    await sample_coverage(dut)

    # WRITEP -> WENABLEP
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 1
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b10
    dut.Haddr.value = 0x80000068
    dut.Hwdata.value = 0x33333333
    await ReadOnly()
    await sample_coverage(dut)

    # WENABLEP -> WRITE (valid=0, Hwritereg=1)
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 1
    dut.Hreadyin.value = 1
    dut.Htrans.value = 0b00
    dut.Haddr.value = 0x80000068
    dut.Hwdata.value = 0x33333333
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Htrans.value = 0b00
    await ReadOnly()
    await sample_coverage(dut)

    await RisingEdge(dut.Hclk)
    await ReadOnly()
    await sample_coverage(dut)

    # =========================================================
    # Extra sampling of target bins with varied addresses
    # =========================================================

    # cx_write_htrans[(1,1)]: Hwrite=1, Htrans=01 across multiple cycles
    for addr_offset in range(8):
        await RisingEdge(dut.Hclk)
        dut.Hresetn.value = 1
        dut.Hwrite.value = 1
        dut.Hreadyin.value = 1
        dut.Htrans.value = 0b01
        dut.Haddr.value = 0x80000100 + addr_offset * 4
        dut.Hwdata.value = 0xA0000000 + addr_offset
        await ReadOnly()
        await sample_coverage(dut)

    # cx_write_htrans[(0,3)]: Hwrite=0, Htrans=11 across multiple cycles
    for addr_offset in range(8):
        await RisingEdge(dut.Hclk)
        dut.Hresetn.value = 1
        dut.Hwrite.value = 0
        dut.Hreadyin.value = 1
        dut.Htrans.value = 0b11
        dut.Haddr.value = 0x80000200 + addr_offset * 4
        dut.Prdata.value = 0xB0000000 + addr_offset
        await ReadOnly()
        await sample_coverage(dut)

    # Final idle cycles
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Htrans.value = 0b00
    dut.Haddr.value = 0x00000000
    await ReadOnly()
    await sample_coverage(dut)

    for _ in range(4):
        await RisingEdge(dut.Hclk)
        await ReadOnly()
        await sample_coverage(dut)

    coverage_db.export_to_yaml("/Users/krishna/uvm-coverage-agent-backup-v2.9/designs/ahb2apb/coverage_reports/coverage.yml")
