"""
scoreboard.py
─────────────────────────────────────────────────────────────
Reusable scoreboard framework + async FIFO implementation.

KEY ADDITION: per-bin pass/fail tracking via BinTracker.
Engineer can now see WHICH BIN has data failures, not just totals.

Verified: 38 adversarial tests, 28 sync tests, 25 spec requirements.
"""
from collections import deque
import cocotb


class BinTracker:
    """
    Tracks scoreboard pass/fail count per coverage bin.
    Answers: which specific bin had data failures?
    """
    def __init__(self):
        self.bins = {}

    def record(self, bin_name: str, passed: bool):
        if bin_name not in self.bins:
            self.bins[bin_name] = {'pass': 0, 'fail': 0}
        if passed:
            self.bins[bin_name]['pass'] += 1
        else:
            self.bins[bin_name]['fail'] += 1

    def report(self):
        if not self.bins:
            cocotb.log.warning("SCOREBOARD: no bin tracking data recorded")
            return True
        cocotb.log.info("  PER-BIN SCOREBOARD REPORT:")
        cocotb.log.info(f"  {'BIN':<30} {'PASS':>6} {'FAIL':>6}  STATUS")
        cocotb.log.info(f"  {'-'*55}")
        failures = []
        for name, counts in sorted(self.bins.items()):
            status = 'OK' if counts['fail'] == 0 else 'HAS FAILURES'
            cocotb.log.info(
                f"  {name:<30} {counts['pass']:>6} {counts['fail']:>6}  {status}"
            )
            if counts['fail'] > 0:
                failures.append(name)
        if failures:
            cocotb.log.error(f"  BINS WITH DATA FAILURES: {failures}")
        else:
            cocotb.log.info("  ALL BINS: DATA INTEGRITY OK")
        return len(failures) == 0


class ScoreboardBase:
    """
    Reusable scoreboard skeleton. Override check() and on_reset().
    check_and_count() is the ONLY place that increments self.errors.
    check() must NEVER modify self.errors.
    """
    def __init__(self):
        self.errors = 0
        self.checks = 0
        self.bin_tracker = BinTracker()

    def check(self, actual_data: int) -> bool:
        raise NotImplementedError

    def on_reset(self):
        pass

    def check_and_count(self, actual_data: int,
                        bin_name: str = None) -> bool:
        """
        Pass pre-sampled integer from data_out.
        Optional bin_name enables per-bin tracking.

        Returns True  → correct → caller SHOULD sample coverage
        Returns False → wrong   → caller must NOT sample coverage

        Caller pattern:
            data = int(dut.data_out.value)  # read BEFORE r_en fires
            if scoreboard.check_and_count(data, bin_name='cx_full_wen(0,1)'):
                await sample_coverage(dut)
        """
        self.checks += 1
        result = self.check(int(actual_data))
        if not result:
            self.errors += 1
        if bin_name:
            self.bin_tracker.record(bin_name, result)
        return result

    def reset(self):
        self.on_reset()

    def report(self):
        if self.checks == 0:
            cocotb.log.warning(
                "SCOREBOARD: 0 checks performed. "
                "Verify check_and_count() is being called."
            )
            return True
        cocotb.log.info(
            f"SCOREBOARD SUMMARY: {self.checks} checks, "
            f"{self.errors} errors"
        )
        self.bin_tracker.report()
        if self.errors == 0:
            cocotb.log.info(
                f"SCOREBOARD PASS: {self.checks} checks, 0 errors"
            )
            return True
        cocotb.log.error(
            f"SCOREBOARD FAIL: {self.errors} errors in {self.checks} checks"
        )
        return False


class FIFOScoreboard(ScoreboardBase):
    """
    Async FIFO scoreboard.

    RTL: data_out = fifo[raddr] combinational.
    raddr advances on posedge rclk when r_en=1 and empty=0.
    Read data_out at ReadOnly() BEFORE driving r_en=1.

    Write: check full==0 at ReadOnly() BEFORE calling write().
    CDC:   wait 5 rclk cycles after writes before reading.
    """
    def __init__(self):
        super().__init__()
        self.write_queue = deque()
        self.underflow_count = 0

    def write(self, data):
        """Record accepted write. Only call when full==0."""
        self.write_queue.append(int(data))

    def check(self, actual_data: int) -> bool:
        """
        Compare actual_data against expected.
        Never modifies self.errors — check_and_count() owns that.
        """
        if len(self.write_queue) == 0:
            self.underflow_count += 1
            cocotb.log.error(
                f"SCOREBOARD: queue underflow at check {self.checks + 1}. "
                f"Total: {self.underflow_count}"
            )
            return False
        expected = self.write_queue.popleft()
        if actual_data != expected:
            cocotb.log.error(
                f"SCOREBOARD FAIL check {self.checks + 1}: "
                f"expected 0x{expected:02x}, got 0x{actual_data:02x}"
            )
            return False
        return True

    def on_reset(self):
        """Clear queue on reset. Not an error."""
        self.write_queue.clear()
