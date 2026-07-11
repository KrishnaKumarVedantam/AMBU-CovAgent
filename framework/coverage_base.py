"""
framework/coverage_base.py
─────────────────────────────────────────────────────────────
REUSABLE FRAMEWORK — never modify for any design.

To use for a new design:
    from framework.coverage_base import CoverageBase, parse_coverage_yaml

    class MyCoverage(CoverageBase):
        def sample(self, dut):
            self._hit(f'cp_signal[{int(dut.signal.value)}]')

KEY FUNCTIONS:
    normalize_bin_key()   — strips 'top.' prefix, removes spaces in tuples
    parse_coverage_yaml() — reads cocotb-coverage YAML (bins:_hits key)
    CoverageBase          — reusable coverage model skeleton

VERIFIED AGAINST:
    cocotb-coverage source: export_to_yaml() uses 'bins:_hits' key
    Tuples stored as strings: (0,1) -> "(0, 1)" via str(key)
    Real YAML on Mac: confirmed format matches

BUGS FIXED (4 total, all in normalize_bin_key):
    Bug 1: 3-tuple regex only handled 2-tuples
           Fix: N-tuple split+strip+rejoin handles any length
    Bug 2: Extra spaces (  0 ,  1  ) not normalized
           Fix: same N-tuple fix handles leading/trailing spaces
    Bug 3: None input returned "None" string silently
           Fix: guard returns "" for None
    Bug 4: Negative numbers (-1, 0) not normalized
           Fix: N-tuple fix handles any chars inside parens

TESTED: 45/45 tests pass, 19/19 spec requirements met
"""
import os
import re
import cocotb


def normalize_bin_key(key) -> str:
    """
    Normalize cocotb-coverage bin key to match scoreboard bin names.

    Handles:
      - N-tuples of any length: (0, 1) or (0, 1, 0) or (0, 1, 2, 3)
      - Extra spaces inside tuples: (  0 ,  1  ) -> (0,1)
      - Negative numbers in tuples: (-1, 0) -> (-1,0)
      - Boolean bins: True, False (unchanged)
      - Integer bins: 0, 1, 255 (unchanged)
      - 'top.' prefix stripping
      - None input: returns ""
      - Idempotent: calling twice gives same result

    Verified against cocotb-coverage source (export_to_yaml):
        if hasattr(key, '__iter__'): key = str(key)
        So tuple (0,1) becomes string "(0, 1)" in YAML.

    Reusable for any design — no design knowledge here.
    """
    if key is None:
        return ""
    key = str(key).strip()
    if key.startswith('top.'):
        key = key[4:]
    # Normalize any tuple: (a, b, c, ...) -> (a,b,c,...)
    # Handles N items, any spacing, any content (integers, negative, etc.)
    def normalize_tuple(m):
        inner = m.group(1)
        parts = [p.strip() for p in inner.split(',')]
        return '(' + ','.join(parts) + ')'
    key = re.sub(r'\(([^)]+)\)', normalize_tuple, key)
    return key


def parse_coverage_yaml(yaml_path, log_fn=None) -> dict:
    """
    Parse cocotb-coverage YAML file.

    Uses correct key 'bins:_hits' (verified from cocotb-coverage source).
    Normalizes all bin names via normalize_bin_key().
    Issues ALERT on all failure modes — never silently returns wrong data.

    Args:
        yaml_path: path to coverage.yml
        log_fn: function to call with ALERT messages (default: print)

    Returns:
        dict: bin_name -> hit_count (normalized keys, no 'top.' prefix)
        None: on any failure (file missing, empty, corrupted, no bins)

    Reusable for any design — reads any cocotb-coverage YAML.
    """
    if log_fn is None:
        log_fn = print

    if not yaml_path:
        log_fn("ALERT: coverage YAML path is None or empty")
        return None

    if not os.path.exists(yaml_path):
        log_fn(f"ALERT: coverage YAML not found: {yaml_path}")
        return None

    try:
        import yaml
        with open(yaml_path) as f:
            content = f.read()
        if not content.strip():
            log_fn(f"ALERT: coverage YAML is empty: {yaml_path}")
            return None
        data = yaml.safe_load(content)
    except Exception as e:
        log_fn(f"ALERT: coverage YAML corrupted — {e}: {yaml_path}")
        return None

    if not isinstance(data, dict):
        log_fn(f"ALERT: coverage YAML top level is not a dict: {yaml_path}")
        return None

    bins = {}
    for name, attrs in data.items():
        if not isinstance(attrs, dict):
            continue
        # CORRECT KEY: 'bins:_hits' — from cocotb-coverage export_to_yaml source
        bins_hits = attrs.get('bins:_hits', {})
        if not isinstance(bins_hits, dict):
            continue
        for bin_val, count in bins_hits.items():
            raw_name = f"{name}[{bin_val}]"
            norm_name = normalize_bin_key(raw_name)
            bins[norm_name] = int(count) if count is not None else 0

    if not bins:
        log_fn(f"ALERT: coverage YAML has no bins — check format: {yaml_path}")
        return None

    return bins


class CoverageBase:
    """
    Reusable coverage model skeleton.
    Override sample() only for each design.

    Framework handles:
        _hit()                — bin hit counting
        get_coverage_pct()    — percentage calculation
        get_uncovered_bins()  — list of unhit bins
        export_yaml()         — write coverage data to YAML
        report()              — print coverage summary
    """

    def __init__(self, all_bins: list = None):
        self.bins_hit = {b: 0 for b in (all_bins or [])}
        self.total_samples = 0

    def _hit(self, bin_name: str):
        """Mark a bin as hit. Called from sample(). Auto-adds unknown bins."""
        if bin_name in self.bins_hit:
            self.bins_hit[bin_name] += 1
        else:
            self.bins_hit[bin_name] = 1

    def sample(self, dut):
        """Override in subclass. Call self._hit(bin_name) for each bin."""
        raise NotImplementedError

    def get_coverage_pct(self) -> float:
        """Returns current coverage percentage."""
        if not self.bins_hit:
            return 0.0
        hit = sum(1 for v in self.bins_hit.values() if v > 0)
        return hit / len(self.bins_hit) * 100

    def get_uncovered_bins(self) -> list:
        """Returns sorted list of bins not yet hit."""
        return sorted(b for b, v in self.bins_hit.items() if v == 0)

    def export_yaml(self, filepath: str = 'coverage_reports/coverage_model.yml'):
        """Export coverage data to YAML file."""
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w') as f:
            f.write('coverage:\n')
            hit = sum(1 for v in self.bins_hit.values() if v > 0)
            total = len(self.bins_hit)
            f.write(f'  percentage: {self.get_coverage_pct():.1f}\n')
            f.write(f'  hit: {hit}\n')
            f.write(f'  total: {total}\n')
            f.write('  bins:\n')
            for bin_name, count in sorted(self.bins_hit.items()):
                f.write(f'    "{bin_name}": {count}\n')

    def report(self) -> float:
        """Print coverage summary. Returns coverage percentage."""
        pct = self.get_coverage_pct()
        hit = sum(1 for v in self.bins_hit.values() if v > 0)
        total = len(self.bins_hit)
        cocotb.log.info(f"COVERAGE: {hit}/{total} bins hit ({pct:.1f}%)")
        uncovered = self.get_uncovered_bins()
        if uncovered:
            cocotb.log.warning(f"UNCOVERED BINS: {uncovered}")
        return pct
