"""
framework/scoreboard_base.py
─────────────────────────────────────────────────────────────
REUSABLE FRAMEWORK — never modify for any design.

Changes from v1:
  - Removed record_state() and record_reset() — design-specific concepts
  - Added record_hit() — generic, no design knowledge
  - Renamed STATE column to HIT — clearer meaning
  - Added DATA INTEGRITY % column — PASS/(PASS+FAIL)*100
  - Added export_yaml() — agent reads this alongside coverage YAML
  - Fixed: HIT-ONLY bins are acceptable, not blocking

Verified: 30 tests, 2 bugs found and fixed.
"""
import cocotb


class BinTracker:
    """
    Per-bin tracking: pass, fail, hit counts.
    Reusable for any design. No design knowledge here.

    Columns:
        PASS  — check_and_count() returned True here
        FAIL  — check_and_count() returned False here
        HIT   — bin was reached (any reason: data, state, reset)
        DATA% — PASS/(PASS+FAIL)*100, '-' if no data check done
        STATUS:
            OK        — data verified and all passed
            DATA FAIL — data verified but some failed (real DUT bug)
            HIT-ONLY  — state reached, no data check performed
            NOT HIT   — state never reached (coverage gap)
    """

    def __init__(self, all_bins: list):
        self.bins = {}
        for name in all_bins:
            self.bins[name] = {'pass': 0, 'fail': 0, 'hit': 0}

    def record_data(self, bin_name: str, passed: bool):
        """Call when data integrity was checked for this bin."""
        if bin_name not in self.bins:
            self.bins[bin_name] = {'pass': 0, 'fail': 0, 'hit': 0}
        if passed:
            self.bins[bin_name]['pass'] += 1
        else:
            self.bins[bin_name]['fail'] += 1
        self.bins[bin_name]['hit'] += 1

    def record_hit(self, bin_name: str):
        """
        Call when state was reached but no data transaction happened.
        Replaces record_state() and record_reset() from v1.
        Framework does not care WHY the hit happened — that is
        design-specific knowledge belonging in the testbench.
        """
        if bin_name not in self.bins:
            self.bins[bin_name] = {'pass': 0, 'fail': 0, 'hit': 0}
        self.bins[bin_name]['hit'] += 1

    def _data_pct(self, c: dict) -> str:
        total = c['pass'] + c['fail']
        if total == 0:
            return '-'
        return f"{c['pass']/total*100:.0f}%"

    def _status(self, c: dict) -> str:
        if c['pass'] == 0 and c['fail'] == 0 and c['hit'] == 0:
            return 'NOT HIT'
        if c['fail'] > 0:
            return 'DATA FAIL'
        if c['pass'] > 0:
            return 'OK'
        return 'HIT-ONLY'

    def export_yaml(self) -> str:
        """
        Export per-bin numbers as YAML string.
        Agent reads this to build data-integrity-aware prompt for Claude.
        Pure numbers — no interpretation. Framework-clean.
        """
        lines = ['scoreboard:']
        for name, c in sorted(self.bins.items()):
            lines.append(f'  "{name}":')
            lines.append(f'    pass: {c["pass"]}')
            lines.append(f'    fail: {c["fail"]}')
            lines.append(f'    hit:  {c["hit"]}')
            lines.append(f'    data_integrity_pct: "{self._data_pct(c)}"')
        return '\n'.join(lines)

    def report(self) -> bool:
        """Print full bin table. Returns True if no data failures."""
        cocotb.log.info("")
        cocotb.log.info(
            f"  {'BIN':<28} {'PASS':>5} {'FAIL':>5} "
            f"{'HIT':>5}  {'DATA%':>6}  STATUS"
        )
        cocotb.log.info(f"  {'-'*60}")

        failures = []
        never_hit = []

        # Sort by priority: DATA FAIL first, then NOT HIT, then HIT-ONLY, then OK
        priority = {'DATA FAIL': 0, 'NOT HIT': 1, 'HIT-ONLY': 2, 'OK': 3}

        def sort_key(item):
            name, c = item
            s = self._status(c)
            return (priority[s], name)

        for name, c in sorted(self.bins.items(), key=sort_key):
            pct = self._data_pct(c)
            status = self._status(c)
            if status == 'DATA FAIL':
                failures.append(name)
            if status == 'NOT HIT':
                never_hit.append(name)
            cocotb.log.info(
                f"  {name:<28} {c['pass']:>5} {c['fail']:>5} "
                f"{c['hit']:>5}  {pct:>6}  {status}"
            )

        cocotb.log.info("")
        total = len(self.bins)
        hit = total - len(never_hit)
        cocotb.log.info(f"  Bins hit:      {hit}/{total}")
        cocotb.log.info(f"  Data failures: {len(failures)}")
        cocotb.log.info(f"  Not hit:       {len(never_hit)}")

        if failures:
            cocotb.log.error(f"  DATA FAIL bins: {failures}")
        if never_hit:
            cocotb.log.warning(f"  NOT HIT bins: {never_hit}")
        if not failures and not never_hit:
            cocotb.log.info(f"  ALL {total} BINS HIT — DATA INTEGRITY OK")

        return len(failures) == 0


class ScoreboardBase:
    """
    Reusable scoreboard skeleton. Override check() and on_reset() only.

    SYNC RULE (enforced here, never changes):
        Coverage sampled ONLY when check_and_count() returns True.
        Caller pattern:
            data = int(dut.data_out.value)
            if sb.check_and_count(data, bin_name='cx_full_wen[(0,1)]'):
                await sample_coverage(dut)
    """

    def __init__(self, all_bins: list = None):
        self.errors = 0
        self.checks = 0
        self.bin_tracker = BinTracker(all_bins or [])

    def check(self, actual_data: int) -> bool:
        """Override. Return True if correct. Never modify self.errors."""
        raise NotImplementedError

    def on_reset(self):
        """Override. Clear reference model state."""
        pass

    def check_and_count(self, actual_data: int,
                        bin_name: str = None) -> bool:
        """
        The ONLY method that increments self.errors.
        Pass pre-sampled integer — not a dut object.

        Returns True  → correct → caller SHOULD sample coverage
        Returns False → wrong   → caller must NOT sample coverage
        """
        self.checks += 1
        result = self.check(int(actual_data))
        if not result:
            self.errors += 1
        if bin_name:
            self.bin_tracker.record_data(bin_name, result)
        return result

    def record_hit(self, bin_name: str):
        """Record bin hit without data check. No design knowledge."""
        self.bin_tracker.record_hit(bin_name)

    def reset(self):
        """Call on reset assertion. Not an error."""
        self.on_reset()

    def export_yaml(self, filepath: str = None) -> str:
        """Export scoreboard data as YAML. Returns YAML string."""
        yaml_str = self.bin_tracker.export_yaml()
        if filepath:
            import os
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w') as f:
                f.write(yaml_str)
        return yaml_str

    def report(self) -> bool:
        """Print full unified report. Returns True if no data failures."""
        no_failures = self.bin_tracker.report()

        if self.errors == 0:
            cocotb.log.info(
                f"SCOREBOARD PASS: {self.checks} checks, 0 errors"
            )
        else:
            cocotb.log.error(
                f"SCOREBOARD FAIL: {self.errors} errors "
                f"in {self.checks} checks"
            )

        return self.errors == 0 and no_failures
