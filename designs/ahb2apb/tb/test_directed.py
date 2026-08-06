import cocotb
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly

try:
    from tb_ahb2apb import sample_coverage
except ImportError:
    from tb.tb_ahb2apb import sample_coverage

from cocotb_coverage.coverage import coverage_db

async def do_reset(dut):
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

async def drive_and_sample(dut, hwrite, htrans, haddr, hwdata, prdata, hreadyin=1):
    """Drive signals on rising edge, then sample in ReadOnly phase."""
    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = hwrite
    dut.Htrans.value = htrans
    dut.Haddr.value = haddr
    dut.Hwdata.value = hwdata
    dut.Prdata.value = prdata
    dut.Hreadyin.value = hreadyin
    await ReadOnly()
    await sample_coverage(dut)

@cocotb.test()
async def test_cx_write_htrans_priority_bins(dut):
    """
    Target bins:
      cx_write_htrans[(0,3)]: Hwrite=0, Htrans=3 (SEQ read)
      cx_write_htrans[(1,1)]: Hwrite=1, Htrans=1 (BUSY write)
    
    The cross cx_write_htrans samples Hwrite and Htrans values.
    We need to present these combinations directly to the DUT.
    
    Key fix: never call reset_dut (which assigns signals) after ReadOnly().
    All signal assignments happen only after RisingEdge, never after ReadOnly.
    """
    cocotb.start_soon(Clock(dut.Hclk, 10, units='ns').start())

    write_queue = []

    # --- Initial reset ---
    await do_reset(dut)

    # =========================================================
    # Target cx_write_htrans[(1,1)]: Hwrite=1, Htrans=1 (BUSY)
    # Drive a write NONSEQ first, then BUSY with write
    # =========================================================

    # Cycle 1: Write NONSEQ to establish write context
    await drive_and_sample(dut,
        hwrite=1, htrans=2, haddr=0x80000100,
        hwdata=0xDEADBEEF, prdata=0, hreadyin=1)

    # Cycle 2: Write BUSY - Hwrite=1, Htrans=1 => cx_write_htrans[(1,1)]
    await drive_and_sample(dut,
        hwrite=1, htrans=1, haddr=0x80000104,
        hwdata=0x11111111, prdata=0, hreadyin=1)

    # Cycle 3: Write BUSY again with hreadyin=0
    await drive_and_sample(dut,
        hwrite=1, htrans=1, haddr=0x80000108,
        hwdata=0x22222222, prdata=0, hreadyin=0)

    # Cycle 4: Write BUSY with different address range
    await drive_and_sample(dut,
        hwrite=1, htrans=1, haddr=0x84000000,
        hwdata=0x33333333, prdata=0, hreadyin=1)

    # Cycle 5: Write BUSY with another address range
    await drive_and_sample(dut,
        hwrite=1, htrans=1, haddr=0x88000000,
        hwdata=0x44444444, prdata=0, hreadyin=1)

    # =========================================================
    # Target cx_write_htrans[(0,3)]: Hwrite=0, Htrans=3 (SEQ read)
    # Drive a read NONSEQ first, then SEQ read
    # =========================================================

    # Cycle 6: Read NONSEQ to start burst
    await drive_and_sample(dut,
        hwrite=0, htrans=2, haddr=0x80000200,
        hwdata=0, prdata=0xCAFEBABE, hreadyin=1)

    # Cycle 7: Read SEQ - Hwrite=0, Htrans=3 => cx_write_htrans[(0,3)]
    await drive_and_sample(dut,
        hwrite=0, htrans=3, haddr=0x80000204,
        hwdata=0, prdata=0xCAFEBABE, hreadyin=1)

    # Cycle 8: Read SEQ again
    await drive_and_sample(dut,
        hwrite=0, htrans=3, haddr=0x80000208,
        hwdata=0, prdata=0x11223344, hreadyin=1)

    # Cycle 9: Read SEQ with hreadyin=0
    await drive_and_sample(dut,
        hwrite=0, htrans=3, haddr=0x8000020C,
        hwdata=0, prdata=0x55667788, hreadyin=0)

    # Cycle 10: Read SEQ with different address range
    await drive_and_sample(dut,
        hwrite=0, htrans=3, haddr=0x84000100,
        hwdata=0, prdata=0xAABBCCDD, hreadyin=1)

    # Cycle 11: Read SEQ with another address range
    await drive_and_sample(dut,
        hwrite=0, htrans=3, haddr=0x88000100,
        hwdata=0, prdata=0xEEFF0011, hreadyin=1)

    # =========================================================
    # Additional FSM coverage - walk through states
    # =========================================================

    # Idle
    await drive_and_sample(dut,
        hwrite=0, htrans=0, haddr=0x00000000,
        hwdata=0, prdata=0, hreadyin=1)

    # Write sequence: NONSEQ -> BUSY -> SEQ
    await drive_and_sample(dut,
        hwrite=1, htrans=2, haddr=0x80000300,
        hwdata=0xABCD1234, prdata=0, hreadyin=1)
    write_queue.append(0xABCD1234)

    await drive_and_sample(dut,
        hwrite=1, htrans=1, haddr=0x80000304,
        hwdata=0xABCD1234, prdata=0, hreadyin=1)

    await drive_and_sample(dut,
        hwrite=1, htrans=3, haddr=0x80000308,
        hwdata=0xDEAD5678, prdata=0, hreadyin=1)

    # Read sequence: NONSEQ -> SEQ -> SEQ
    await drive_and_sample(dut,
        hwrite=0, htrans=2, haddr=0x80000400,
        hwdata=0, prdata=0x99887766, hreadyin=1)

    await drive_and_sample(dut,
        hwrite=0, htrans=3, haddr=0x80000404,
        hwdata=0, prdata=0x55443322, hreadyin=1)

    await drive_and_sample(dut,
        hwrite=0, htrans=3, haddr=0x80000408,
        hwdata=0, prdata=0x11009988, hreadyin=1)

    # More write BUSY attempts
    await drive_and_sample(dut,
        hwrite=1, htrans=2, haddr=0x80000500,
        hwdata=0xFEDCBA98, prdata=0, hreadyin=1)

    await drive_and_sample(dut,
        hwrite=1, htrans=1, haddr=0x80000500,
        hwdata=0xFEDCBA98, prdata=0, hreadyin=0)

    await drive_and_sample(dut,
        hwrite=1, htrans=1, haddr=0x80000500,
        hwdata=0xFEDCBA98, prdata=0, hreadyin=1)

    # More read SEQ attempts
    await drive_and_sample(dut,
        hwrite=0, htrans=2, haddr=0x80000600,
        hwdata=0, prdata=0x76543210, hreadyin=1)

    await drive_and_sample(dut,
        hwrite=0, htrans=3, haddr=0x80000604,
        hwdata=0, prdata=0x76543210, hreadyin=0)

    await drive_and_sample(dut,
        hwrite=0, htrans=3, haddr=0x80000608,
        hwdata=0, prdata=0x76543210, hreadyin=1)

    # Final idle
    await drive_and_sample(dut,
        hwrite=0, htrans=0, haddr=0x00000000,
        hwdata=0, prdata=0, hreadyin=1)

    await RisingEdge(dut.Hclk)
    await RisingEdge(dut.Hclk)

    coverage_db.export_to_yaml("/Users/krishna/uvm-coverage-agent-backup-v2.10.3.git/designs/ahb2apb/coverage_reports/coverage.yml")
