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

    def on_reset(self):
        """Clear reference queue on reset. Not an error."""
        self.write_queue.clear()
