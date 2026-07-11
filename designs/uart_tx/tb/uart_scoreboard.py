"""
tb/uart_scoreboard.py
DESIGN-SPECIFIC — uart_tx scoreboard.
Extends framework ScoreboardBase. No framework modifications.
"""
import cocotb
from framework.scoreboard_base import ScoreboardBase

UART_ALL_BINS = [
    'cp_resetn[0]',      'cp_resetn[1]',
    'cp_tx_en[0]',       'cp_tx_en[1]',
    'cp_tx_busy[0]',     'cp_tx_busy[1]',
    'cx_en_busy[(0,0)]', 'cx_en_busy[(0,1)]',
    'cx_en_busy[(1,0)]', 'cx_en_busy[(1,1)]',
    'cx_rst_en[(0,0)]',  'cx_rst_en[(0,1)]',
    'cx_rst_en[(1,0)]',  'cx_rst_en[(1,1)]',
]


class UartScoreboard(ScoreboardBase):
    """
    UART TX scoreboard.
    Verifies uart_txd outputs correct UART frame:
    start(0) + 8 data bits LSB first + stop(1)
    """
    def __init__(self):
        super().__init__(all_bins=UART_ALL_BINS)
        self.expected_bits = []

    def expect_frame(self, data: int):
        """Queue expected UART frame for next TX."""
        bits = [0]  # start bit
        for i in range(8):
            bits.append((data >> i) & 1)
        bits.append(1)  # stop bit
        self.expected_bits = bits

    def check(self, actual_data: int) -> bool:
        """
        Compare actual bit against next expected bit.
        actual_data is a single bit (0 or 1).
        """
        if not self.expected_bits:
            cocotb.log.error("UART SB: no expected frame queued")
            return False
        expected = self.expected_bits.pop(0)
        if actual_data != expected:
            cocotb.log.error(
                f"UART SB FAIL: expected {expected} got {actual_data}")
            return False
        return True

    def on_reset(self):
        self.expected_bits = []
