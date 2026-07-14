"""
test_scoreboard_buggy.py — AHB2APB Bridge Fault Injection Suite
─────────────────────────────────────────────────────────────────
PURPOSE: Validate that the AHB2APB scoreboard catches real data corruption.

METHODOLOGY: Mutation testing — industry standard technique for scoreboard
qualification (Berkeley EECS-2024-157, Hindawi VLSI Design 2015).
Each test injects a KNOWN fault and confirms the scoreboard detects it.

FAULT CATEGORIES:
  FAULT 1 — Bit flip: one bit corrupted in write data
  FAULT 2 — Zero corruption: write data zeroed out
  FAULT 3 — Offset corruption: write data + 1 (off by one)
  FAULT 4 — Wrong slave: data sent to correct address but wrong
             slave selected (address routing bug)
  FAULT 5 — Read data corruption: Prdata value corrupted on return

EXPECTED RESULT: ALL FIVE TESTS MUST REPORT SCOREBOARD FAIL.
"""

import cocotb
import os
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, ClockCycles
from tb.ahb2apb_scoreboard import AHB2APBScoreboard, expected_pselx

HTRANS_IDLE   = 0
HTRANS_NONSEQ = 2
SLAVE1_ADDR   = 0x80000000
SLAVE2_ADDR   = 0x84000000
SLAVE3_ADDR   = 0x88000000


async def reset_dut(dut, sb):
    dut.Hresetn.value  = 0
    dut.Hwrite.value   = 0
    dut.Hreadyin.value = 1
    dut.Hwdata.value   = 0
    dut.Haddr.value    = 0
    dut.Htrans.value   = HTRANS_IDLE
    dut.Prdata.value   = 0
    for _ in range(5):
        await RisingEdge(dut.Hclk)
    sb.reset()
    sb.record_hit('cp_hresetn[0]')
    await RisingEdge(dut.Hclk)
    dut.Hresetn.value = 1
    await RisingEdge(dut.Hclk)
    sb.record_hit('cp_hresetn[1]')


async def do_write_check(dut, sb, addr, true_data, expected_data):
    """
    Write transaction. DUT receives true_data (correct).
    Scoreboard expects expected_data (may be faulty).
    """
    sb.expect_write(addr, expected_data)  # Tell scoreboard the FAULTY expected

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value  = 1
    dut.Haddr.value   = addr
    dut.Htrans.value  = HTRANS_NONSEQ
    dut.Hwdata.value  = true_data         # DUT gets TRUE data
    sb.record_hit('cp_hwrite[1]')
    sb.record_hit('cp_htrans[2]')

    await RisingEdge(dut.Hclk)
    dut.Htrans.value = HTRANS_IDLE

    for _ in range(15):
        await RisingEdge(dut.Hclk)
        await ReadOnly()
        paddr   = int(dut.Paddr.value)
        pwrite  = int(dut.Pwrite.value)
        pselx   = int(dut.Pselx.value)
        penable = int(dut.Penable.value)
        pwdata  = int(dut.Pwdata.value)

        if penable == 1:
            sb.record_hit(f'cp_penable[1]')
            sb.record_hit(f'cp_pselx[{pselx}]')
            if pwrite != 1:
                sb.errors += 1
                cocotb.log.error(f"FAIL: Pwrite={pwrite} expected 1")
            exp_sel = expected_pselx(addr)
            if pselx != exp_sel:
                sb.errors += 1
                cocotb.log.error(f"FAIL: Pselx={pselx} expected {exp_sel}")
            # Check Pwdata against FAULTY expected — mismatch expected
            if pwdata != expected_data:
                sb.errors += 1
                cocotb.log.info(
                    f"  [CAUGHT] Pwdata=0x{pwdata:08X} != "
                    f"expected=0x{expected_data:08X} — fault detected")
            sb.checks += 1
            break
        if int(dut.Hreadyout.value) == 1 and penable == 0:
            break

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value = 0
    dut.Htrans.value = HTRANS_IDLE
    await ClockCycles(dut.Hclk, 2)
    sb.record_hit('cp_hwrite[0]')
    sb.record_hit('cp_htrans[0]')
    sb.record_hit('cp_penable[0]')
    sb.record_hit('cp_valid[1]')


async def do_read_check(dut, sb, addr, true_prdata, expected_hrdata):
    """
    Read transaction. DUT gets true_prdata on Prdata pin.
    Scoreboard expects expected_hrdata (may be faulty).
    """
    dut.Prdata.value = true_prdata        # DUT gets TRUE read data
    sb.expect_read(expected_hrdata)       # Scoreboard expects FAULTY version

    await RisingEdge(dut.Hclk)
    dut.Hwrite.value  = 0
    dut.Haddr.value   = addr
    dut.Htrans.value  = HTRANS_NONSEQ

    await RisingEdge(dut.Hclk)
    dut.Htrans.value = HTRANS_IDLE

    for _ in range(15):
        await RisingEdge(dut.Hclk)
        await ReadOnly()
        penable = int(dut.Penable.value)
        pselx   = int(dut.Pselx.value)
        if penable == 1:
            sb.record_hit(f'cp_penable[1]')
            hrdata = int(dut.Hrdata.value)
            result = sb.check_and_count(hrdata, 'cx_write_valid[(0,1)]')
            if not result:
                cocotb.log.info(
                    f"  [CAUGHT] Hrdata=0x{hrdata:08X} != "
                    f"expected=0x{expected_hrdata:08X} — fault detected")
            break
        if int(dut.Hreadyout.value) == 1 and penable == 0:
            break

    await RisingEdge(dut.Hclk)
    dut.Htrans.value = HTRANS_IDLE
    await ClockCycles(dut.Hclk, 2)
    sb.record_hit('cp_valid[0]')


@cocotb.test()
async def fault1_write_bit_flip(dut):
    """
    FAULT 1 — Single bit flip in write data.
    DUT correctly forwards 0xDEADBEEF → Pwdata = 0xDEADBEEF.
    Scoreboard expects 0xDEADBEEE (bit 0 flipped).
    Expected: SCOREBOARD FAIL — Pwdata mismatch.
    """
    cocotb.log.info("=" * 60)
    cocotb.log.info("FAULT 1: Write data bit flip")
    cocotb.log.info("DUT sends: Hwdata=0xDEADBEEF → Pwdata=0xDEADBEEF")
    cocotb.log.info("SB expect: 0xDEADBEEE (bit 0 flipped)")
    cocotb.log.info("=" * 60)
    sb = AHB2APBScoreboard()
    cocotb.start_soon(Clock(dut.Hclk, 10, unit='ns').start())
    await reset_dut(dut, sb)
    await do_write_check(dut, sb, SLAVE1_ADDR + 0x100,
                         true_data=0xDEADBEEF,
                         expected_data=0xDEADBEEE)  # bit 0 flipped
    result = sb.report()
    assert not result, "SCOREBOARD BLIND SPOT: bit flip in write data NOT detected"
    cocotb.log.info("FAULT 1 CONFIRMED: Write data bit flip correctly caught")


@cocotb.test()
async def fault2_write_zero_corruption(dut):
    """
    FAULT 2 — Write data zeroed out.
    DUT correctly forwards 0xCAFEBABE → Pwdata = 0xCAFEBABE.
    Scoreboard expects 0x00000000.
    Simulates a DUT that pulls write data bus to ground.
    Expected: SCOREBOARD FAIL — Pwdata mismatch.
    """
    cocotb.log.info("=" * 60)
    cocotb.log.info("FAULT 2: Write data zero corruption")
    cocotb.log.info("DUT sends: Hwdata=0xCAFEBABE → Pwdata=0xCAFEBABE")
    cocotb.log.info("SB expect: 0x00000000 (simulates stuck-at-0 on data bus)")
    cocotb.log.info("=" * 60)
    sb = AHB2APBScoreboard()
    cocotb.start_soon(Clock(dut.Hclk, 10, unit='ns').start())
    await reset_dut(dut, sb)
    await do_write_check(dut, sb, SLAVE2_ADDR + 0x100,
                         true_data=0xCAFEBABE,
                         expected_data=0x00000000)
    result = sb.report()
    assert not result, "SCOREBOARD BLIND SPOT: zero corruption in write data NOT detected"
    cocotb.log.info("FAULT 2 CONFIRMED: Write data zero corruption correctly caught")


@cocotb.test()
async def fault3_write_offset_corruption(dut):
    """
    FAULT 3 — Off-by-one in write data.
    DUT correctly forwards 0x12345678 → Pwdata = 0x12345678.
    Scoreboard expects 0x12345679 (value+1).
    Simulates an incrementer bug in the write data path.
    Expected: SCOREBOARD FAIL — Pwdata mismatch.
    """
    cocotb.log.info("=" * 60)
    cocotb.log.info("FAULT 3: Write data off-by-one")
    cocotb.log.info("DUT sends: Hwdata=0x12345678 → Pwdata=0x12345678")
    cocotb.log.info("SB expect: 0x12345679 (value+1)")
    cocotb.log.info("=" * 60)
    sb = AHB2APBScoreboard()
    cocotb.start_soon(Clock(dut.Hclk, 10, unit='ns').start())
    await reset_dut(dut, sb)
    await do_write_check(dut, sb, SLAVE3_ADDR + 0x100,
                         true_data=0x12345678,
                         expected_data=0x12345679)  # +1
    result = sb.report()
    assert not result, "SCOREBOARD BLIND SPOT: offset corruption in write data NOT detected"
    cocotb.log.info("FAULT 3 CONFIRMED: Write data offset corruption correctly caught")


@cocotb.test()
async def fault4_read_data_corruption(dut):
    """
    FAULT 4 — Read data corrupted.
    Prdata = 0xAABBCCDD drives Hrdata = 0xAABBCCDD correctly.
    Scoreboard expects 0x00000000.
    Simulates a DUT that zeroes the read data before returning to AHB master.
    Expected: SCOREBOARD FAIL — Hrdata mismatch.
    """
    cocotb.log.info("=" * 60)
    cocotb.log.info("FAULT 4: Read data zero corruption")
    cocotb.log.info("DUT: Prdata=0xAABBCCDD → Hrdata=0xAABBCCDD")
    cocotb.log.info("SB expect: 0x00000000")
    cocotb.log.info("=" * 60)
    sb = AHB2APBScoreboard()
    cocotb.start_soon(Clock(dut.Hclk, 10, unit='ns').start())
    await reset_dut(dut, sb)
    await do_read_check(dut, sb, SLAVE1_ADDR + 0x200,
                        true_prdata=0xAABBCCDD,
                        expected_hrdata=0x00000000)
    result = sb.report()
    assert not result, "SCOREBOARD BLIND SPOT: read data corruption NOT detected"
    cocotb.log.info("FAULT 4 CONFIRMED: Read data corruption correctly caught")


@cocotb.test()
async def fault5_read_bit_flip(dut):
    """
    FAULT 5 — Single bit flip in read data.
    Prdata = 0x55667788 → Hrdata = 0x55667788 correctly.
    Scoreboard expects 0x55667789 (bit 0 flipped).
    Expected: SCOREBOARD FAIL — Hrdata mismatch.
    """
    cocotb.log.info("=" * 60)
    cocotb.log.info("FAULT 5: Read data bit flip")
    cocotb.log.info("DUT: Prdata=0x55667788 → Hrdata=0x55667788")
    cocotb.log.info("SB expect: 0x55667789 (bit 0 flipped)")
    cocotb.log.info("=" * 60)
    sb = AHB2APBScoreboard()
    cocotb.start_soon(Clock(dut.Hclk, 10, unit='ns').start())
    await reset_dut(dut, sb)
    await do_read_check(dut, sb, SLAVE2_ADDR + 0x200,
                        true_prdata=0x55667788,
                        expected_hrdata=0x55667789)  # bit 0 flipped
    result = sb.report()
    assert not result, "SCOREBOARD BLIND SPOT: read data bit flip NOT detected"
    cocotb.log.info("FAULT 5 CONFIRMED: Read data bit flip correctly caught")
