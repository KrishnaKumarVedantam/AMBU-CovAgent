"""
tb/ahb2apb_coverage.py
DESIGN-SPECIFIC — AHB2APB Bridge coverage model.

Coverage model verified against:
- Official ARM AMBA AHB/APB spec
- Ghonimo's UVM verification suite (Pre_Silicon-AHB-to_APB-Verification)
- RTL: AHB_Slave_Interface.v + APB_Controller.v + bridge-top.v

Key findings from Ghonimo's files:
- Hsize and Hburst NOT in RTL — not included in coverage
- Final UVM model covers: Hwrite, Htrans, reset, pselx, fsm, penable
- Scoreboard checks: Paddr==Haddr, Pwdata==Hwdata, Hrdata==Prdata

Total bins: 46
  CoverPoints: 26 bins
  CoverCrosses: 20 bins

APB FSM states (APB_Controller.v):
  ST_IDLE=0, ST_WWAIT=1, ST_READ=2, ST_WRITE=3
  ST_WRITEP=4, ST_RENABLE=5, ST_WENABLE=6, ST_WENABLEP=7

Htrans values (AMBA spec):
  IDLE=0, BUSY=1, NONSEQ=2, SEQ=3
"""
from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db


@CoverPoint("top.cp_hresetn",
    xf=lambda dut: int(dut.Hresetn.value),
    bins=[0, 1])
@CoverPoint("top.cp_hwrite",
    xf=lambda dut: int(dut.Hwrite.value),
    bins=[0, 1])
@CoverPoint("top.cp_htrans",
    xf=lambda dut: int(dut.Htrans.value),
    bins=[0, 1, 2, 3])
@CoverPoint("top.cp_hreadyin",
    xf=lambda dut: int(dut.Hreadyin.value),
    bins=[0, 1])
@CoverPoint("top.cp_valid",
    xf=lambda dut: int(dut.AHBSlave.valid.value),
    bins=[0, 1])
@CoverPoint("top.cp_pselx",
    xf=lambda dut: int(dut.Pselx.value),
    bins=[0, 1, 2, 4])
@CoverPoint("top.cp_fsm",
    xf=lambda dut: int(dut.APBControl.PRESENT_STATE.value),
    bins=[0, 1, 2, 3, 4, 5, 6, 7])
@CoverPoint("top.cp_penable",
    xf=lambda dut: int(dut.Penable.value),
    bins=[0, 1])
@CoverCross("top.cx_write_htrans",
    items=["top.cp_hwrite", "top.cp_htrans"])
@CoverCross("top.cx_psel_enable",
    items=["top.cp_pselx", "top.cp_penable"])
@CoverCross("top.cx_write_valid",
    items=["top.cp_hwrite", "top.cp_valid"])
async def sample_coverage(dut):
    pass
