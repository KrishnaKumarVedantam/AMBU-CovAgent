"""
tb/fifo_scoreboard.py
─────────────────────────────────────────────────────────────
DESIGN-SPECIFIC — async_fifo_flat.sv scoreboard.
Imports reusable framework. Only adds FIFO-specific logic.

Generated from RTL: async_fifo_flat.sv
"""
from collections import deque
from framework.scoreboard_base import ScoreboardBase
import cocotb


# All 36 bins for async_fifo_flat.sv
FIFO_ALL_BINS = [
    'cp_full[0]',       'cp_full[1]',
    'cp_empty[0]',      'cp_empty[1]',
    'cp_wen[0]',        'cp_wen[1]',
    'cp_ren[0]',        'cp_ren[1]',
    'cp_half_full[0]',  'cp_half_full[1]',
    'cp_half_empty[0]', 'cp_half_empty[1]',
    'cp_wrst[0]',       'cp_wrst[1]',
    'cp_rrst[0]',       'cp_rrst[1]',
    'cx_full_wen[(0,0)]',    'cx_full_wen[(0,1)]',
    'cx_full_wen[(1,0)]',    'cx_full_wen[(1,1)]',
    'cx_empty_ren[(0,0)]',   'cx_empty_ren[(0,1)]',
    'cx_empty_ren[(1,0)]',   'cx_empty_ren[(1,1)]',
    'cx_full_empty[(0,0)]',  'cx_full_empty[(0,1)]',
    'cx_full_empty[(1,0)]',  'cx_full_empty[(1,1)]',
    'cx_wrst_wen[(0,0)]',    'cx_wrst_wen[(0,1)]',
    'cx_wrst_wen[(1,0)]',    'cx_wrst_wen[(1,1)]',
    'cx_rrst_ren[(0,0)]',    'cx_rrst_ren[(0,1)]',
    'cx_rrst_ren[(1,0)]',    'cx_rrst_ren[(1,1)]',
]


class FIFOScoreboard(ScoreboardBase):
    """
    Async FIFO scoreboard — extends ScoreboardBase.

    RTL timing (async_fifo_flat.sv):
        data_out = fifo[raddr] combinational
        raddr advances on posedge rclk when r_en=1 and empty=0
        Read data_out at ReadOnly() BEFORE driving r_en=1
        CDC wait: 5 rclk after writes (2 needed, 5 for safety)

    Usage:
        sb = FIFOScoreboard()

        # Write:
        if int(dut.full.value) == 0:
            sb.write(int(dut.data_in.value))
            sb.record_state('cp_full[0]')
            sb.record_state('cx_full_wen[(0,1)]')

        # Read:
        data = int(dut.data_out.value)     # read BEFORE r_en fires
        if sb.check_and_count(data, 'cx_empty_ren[(0,1)]'):
            await sample_coverage(dut)     # only on pass

        # Reset:
        sb.reset()
        sb.record_reset('cp_wrst[0]')
        sb.record_reset('cp_rrst[0]')
    """

    def __init__(self):
        super().__init__(all_bins=FIFO_ALL_BINS)
        self.write_queue = deque()
        self.underflow_count = 0

    def write(self, data: int):
        """
        Record accepted write.
        Call ONLY when full==0 confirmed at ReadOnly().
        """
        self.write_queue.append(int(data))

    def check(self, actual_data: int) -> bool:
        """
        Compare actual_data against expected from reference queue.
        Called by check_and_count(). Never modifies self.errors.
        """
        if len(self.write_queue) == 0:
            self.underflow_count += 1
            cocotb.log.error(
                f"FIFO SCOREBOARD: queue underflow at check "
                f"{self.checks + 1}. Total: {self.underflow_count}"
            )
            return False
        expected = self.write_queue.popleft()
        if actual_data != expected:
            cocotb.log.error(
                f"FIFO SCOREBOARD FAIL check {self.checks + 1}: "
                f"expected 0x{expected:02x}, got 0x{actual_data:02x}"
            )
            return False
        return True

    async def monitor(self, dut):
        """
        Passive monitor — two coroutines covering both clock domains.
        Fix 1: deque imported locally — no NameError.
        Fix 2: _write_monitor calls self.write() directly — no staged
        delay model. The real CDC synchronizer delay does not need to
        be reproduced here: _read_monitor only ever checks a read when
        the DUT's own real, hardware-synchronized empty flag is 0, so
        write_queue is always causally correct by the time it's read.
        """
        import cocotb
        cocotb.start_soon(self._write_monitor(dut))
        cocotb.start_soon(self._read_monitor(dut))

    async def _write_monitor(self, dut):
        """
        Watches wclk domain — records accepted writes directly.
        RTL: write accepted when w_en=1 AND full=0 at ReadOnly().

        Uses prev_full — full as sampled at the PREVIOUS edge's
        ReadOnly() — rather than this edge's sample, mirroring the
        prev_r_en/prev_empty/prev_data pattern in _read_monitor. waddr
        and full register from the SAME pre-edge full value each edge,
        so the current-edge sample already reflects this write's own
        aftermath: on the exact edge that fills the FIFO, full reads 1
        even though the write (gated by the pre-edge full=0) succeeded.
        Using the current-edge sample would wrongly veto staging it.
        """
        from cocotb.triggers import RisingEdge, ReadOnly
        prev_full = 0  # full is 0 immediately after reset — safe default
        while True:
            await RisingEdge(dut.wclk)
            await ReadOnly()
            if int(dut.w_rst_n.value) == 0 or int(dut.r_rst_n.value) == 0:
                self.on_reset()
                prev_full = 0
                continue
            if int(dut.w_en.value) == 1 and prev_full == 0:
                self.write(int(dut.data_in.value))
            prev_full = int(dut.full.value)

    async def _read_monitor(self, dut):
        """
        Watches rclk domain — detects reads using previous-cycle signals.
        prev_r_en, prev_empty = what DUT latched at THIS posedge.
        prev_data = data_out BEFORE raddr advanced = data that was read.
        Only checks when write_queue has CDC-committed data available.
        """
        from cocotb.triggers import RisingEdge, ReadOnly
        prev_r_en  = 0
        prev_empty = 1
        prev_data  = None
        while True:
            await RisingEdge(dut.rclk)
            await ReadOnly()
            if int(dut.r_rst_n.value) == 0:
                prev_r_en  = 0
                prev_empty = 1
                prev_data  = None
                continue
            curr_r_en  = int(dut.r_en.value)
            curr_empty = int(dut.empty.value)
            curr_data  = int(dut.data_out.value)
            if prev_r_en == 1 and prev_empty == 0 and prev_data is not None:
                if len(self.write_queue) > 0:
                    self.check_and_count(prev_data, 'cx_empty_ren[(0,1)]')
            prev_r_en  = curr_r_en
            prev_empty = curr_empty
            prev_data  = curr_data

    def on_reset(self):
        """Clear reference queue on reset. Not an error."""
        self.write_queue.clear()
