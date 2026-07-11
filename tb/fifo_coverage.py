"""
tb/fifo_coverage.py
─────────────────────────────────────────────────────────────
DESIGN-SPECIFIC — async_fifo_flat.sv coverage model.
Imports reusable framework. Only adds FIFO-specific bin logic.

Generated from RTL: async_fifo_flat.sv
"""
from framework.coverage_base import CoverageBase
from tb.fifo_scoreboard import FIFO_ALL_BINS


class FIFOCoverage(CoverageBase):
    """
    Coverage model for async_fifo_flat.sv — extends CoverageBase.

    Mirrors the 36 bins from tb_fifo.py CoverPoints and CoverCrosses.
    Call sample() after every valid transaction.
    """

    def __init__(self):
        super().__init__(all_bins=FIFO_ALL_BINS)

    def sample(self, dut):
        """
        Sample all signal states from DUT.
        Call at ReadOnly() after every transaction.
        """
        self.total_samples += 1

        full       = int(dut.full.value)
        empty      = int(dut.empty.value)
        w_en       = int(dut.w_en.value)
        r_en       = int(dut.r_en.value)
        half_full  = int(dut.half_full.value)
        half_empty = int(dut.half_empty.value)
        w_rst_n    = int(dut.w_rst_n.value)
        r_rst_n    = int(dut.r_rst_n.value)

        # CoverPoints
        self._hit(f'cp_full[{full}]')
        self._hit(f'cp_empty[{empty}]')
        self._hit(f'cp_wen[{w_en}]')
        self._hit(f'cp_ren[{r_en}]')
        self._hit(f'cp_half_full[{half_full}]')
        self._hit(f'cp_half_empty[{half_empty}]')
        self._hit(f'cp_wrst[{w_rst_n}]')
        self._hit(f'cp_rrst[{r_rst_n}]')

        # CoverCrosses
        self._hit(f'cx_full_wen[({full},{w_en})]')
        self._hit(f'cx_empty_ren[({empty},{r_en})]')
        self._hit(f'cx_full_empty[({full},{empty})]')
        self._hit(f'cx_wrst_wen[({w_rst_n},{w_en})]')
        self._hit(f'cx_rrst_ren[({r_rst_n},{r_en})]')
