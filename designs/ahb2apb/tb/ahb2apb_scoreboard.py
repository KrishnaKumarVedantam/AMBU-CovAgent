"""
tb/ahb2apb_scoreboard.py
DESIGN-SPECIFIC — AHB2APB Bridge scoreboard.

Verified checks from Ghonimo's UVM scoreboard:
  Write: Paddr == Haddr (with 1-cycle pipeline delay)
  Write: Pwdata == Hwdata
  Write: Pwrite == 1
  Write: Pselx matches address range
  Read:  Hrdata == Prdata (combinational passthrough)
  Read:  Pwrite == 0

Address map (RTL verified):
  Slave 1: 0x8000_0000 to 0x8400_0000 → Pselx=1
  Slave 2: 0x8400_0000 to 0x8800_0000 → Pselx=2
  Slave 3: 0x8800_0000 to 0x8C00_0000 → Pselx=4
"""
import cocotb
from framework.scoreboard_base import ScoreboardBase

AHB2APB_ALL_BINS = [
    'cp_hresetn[0]',    'cp_hresetn[1]',
    'cp_hwrite[0]',     'cp_hwrite[1]',
    'cp_htrans[0]',     'cp_htrans[1]',
    'cp_htrans[2]',     'cp_htrans[3]',
    'cp_hreadyin[0]',   'cp_hreadyin[1]',
    'cp_valid[0]',      'cp_valid[1]',
    'cp_pselx[0]',      'cp_pselx[1]',
    'cp_pselx[2]',      'cp_pselx[4]',
    'cp_fsm[0]',  'cp_fsm[1]',  'cp_fsm[2]',  'cp_fsm[3]',
    'cp_fsm[4]',  'cp_fsm[5]',  'cp_fsm[6]',  'cp_fsm[7]',
    'cp_penable[0]',    'cp_penable[1]',
    'cx_write_htrans[(0,0)]', 'cx_write_htrans[(0,1)]',
    'cx_write_htrans[(0,2)]', 'cx_write_htrans[(0,3)]',
    'cx_write_htrans[(1,0)]', 'cx_write_htrans[(1,1)]',
    'cx_write_htrans[(1,2)]', 'cx_write_htrans[(1,3)]',
    'cx_psel_enable[(0,0)]',  'cx_psel_enable[(0,1)]',
    'cx_psel_enable[(1,0)]',  'cx_psel_enable[(1,1)]',
    'cx_psel_enable[(2,0)]',  'cx_psel_enable[(2,1)]',
    'cx_psel_enable[(4,0)]',  'cx_psel_enable[(4,1)]',
    'cx_write_valid[(0,0)]',  'cx_write_valid[(0,1)]',
    'cx_write_valid[(1,0)]',  'cx_write_valid[(1,1)]',
]


def expected_pselx(haddr):
    """Return expected Pselx value for given Haddr."""
    if 0x80000000 <= haddr < 0x84000000:
        return 1
    elif 0x84000000 <= haddr < 0x88000000:
        return 2
    elif 0x88000000 <= haddr < 0x8C000000:
        return 4
    return 0


class AHB2APBScoreboard(ScoreboardBase):
    """
    AHB2APB Bridge scoreboard.
    Checks address routing, data integrity, and protocol signals.
    """
    def __init__(self):
        super().__init__(all_bins=AHB2APB_ALL_BINS)
        self.expected_paddr  = None
        self.expected_pwdata = None
        self.expected_pwrite = None
        self.expected_pselx  = None
        self.expected_hrdata = None
        self.check_type      = None  # 'write' or 'read'

    def expect_write(self, haddr, hwdata):
        """Queue expected write transaction."""
        self.expected_paddr  = haddr
        self.expected_pwdata = hwdata
        self.expected_pwrite = 1
        self.expected_pselx  = expected_pselx(haddr)
        self.check_type      = 'write'

    def expect_read(self, prdata):
        """Queue expected read transaction."""
        self.expected_hrdata = prdata
        self.expected_pwrite = 0
        self.check_type      = 'read'

    def check(self, actual_data: int) -> bool:
        """
        Check actual vs expected.
        actual_data is a packed integer:
          For write: actual Paddr
          For read:  actual Hrdata
        """
        if self.check_type == 'write':
            if self.expected_paddr is None:
                return True
            if actual_data != self.expected_paddr:
                cocotb.log.error(
                    f"WRITE FAIL: Paddr=0x{actual_data:08X} "
                    f"expected=0x{self.expected_paddr:08X}")
                return False
            return True
        elif self.check_type == 'read':
            if self.expected_hrdata is None:
                return True
            if actual_data != self.expected_hrdata:
                cocotb.log.error(
                    f"READ FAIL: Hrdata=0x{actual_data:08X} "
                    f"expected=0x{self.expected_hrdata:08X}")
                return False
            return True
        return True

    def on_reset(self):
        self.expected_paddr  = None
        self.expected_pwdata = None
        self.expected_pwrite = None
        self.expected_pselx  = None
        self.expected_hrdata = None
        self.check_type      = None
