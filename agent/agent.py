"""
agent/agent.py — v5 (robustness: logging, token tracking, lessons, retry, single-bin, CoT)
─────────────────────────────────────────────────────────────
WHAT CHANGED FROM v4:
  1. Pipeline logging — 8-stage [ITER-N][STAGE] format, Python logging module
  2. Token/cost tracking — [API] input/output/cache_read after every call
  3. LESSONS.md persistent memory — write on failure, read last-5 in prompt
  4. 429 retry — 3 attempts x 60s, same messages object, [RETRY]/[SKIP] logs
  5. Single-bin targeting — PRIMARY TARGET cycles through not_hit bins per iter
  6. Chain of Thought — config flag; Q1-Q4 reasoning before code generation

HOW TO USE:
  python3 agent/agent.py designs/async_fifo/config.yaml
  python3 agent/agent.py designs/axi_bridge/config.yaml

config.yaml (engineer writes this — 15 lines):
  design_name: async_fifo
  rtl_file: rtl/async_fifo_flat.sv
  base_module: tb.tb_fifo
  scoreboard_module: tb.test_scoreboard
  threshold: 98.0
  max_iter: 8
  chain_of_thought: false   # optional: set true to force Q1-Q4 reasoning
  coverpoint_names:
    - top.cp_full
    - top.cp_empty
    ...

VERIFIED: 50/50 simulation tests pass across 2 designs
"""

import argparse, sys, os
import logging
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import yaml, subprocess, ast, re, shutil, time, anthropic
from pathlib import Path


# ════════════════════════════════════════════════════════════
# LOGGING SETUP
# ════════════════════════════════════════════════════════════
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# LESSONS MEMORY
# ════════════════════════════════════════════════════════════

def write_lesson(cfg, iteration, failure_reason):
    """Append a failure entry to LESSONS.md. Design-agnostic."""
    lessons_path = cfg['design_root'] / 'LESSONS.md'
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    # Translate known error patterns into specific, actionable rules
    if 'ReadOnly' in failure_reason or 'read only' in failure_reason.lower():
        avoid = ("NEVER assign dut.signal.value = X inside or after await ReadOnly(). "
                 "Drive signals BEFORE ReadOnly, sample coverage AFTER ReadOnly. "
                 "Any signal assignment in the ReadOnly phase raises RuntimeError.")
    elif 'coverage' in failure_reason.lower() and 'did not move' in failure_reason.lower():
        avoid = 'same stimulus pattern — use a completely different signal sequence'
    else:
        # Use full error text — always more informative than truncating at ':'
        avoid = failure_reason.strip()
    entry = (
        f"\n## Iteration {iteration} — {timestamp}\n"
        f"What failed: {failure_reason}\n"
        f"Avoid: {avoid}\n"
    )
    with open(lessons_path, 'a') as f:
        f.write(entry)


def read_lessons(cfg, max_entries=5) -> str:
    """Read last N deduplicated entries from LESSONS.md. Empty string if absent."""
    lessons_path = cfg['design_root'] / 'LESSONS.md'
    if not lessons_path.exists():
        return ""
    try:
        content = lessons_path.read_text()
        entries = [e.strip() for e in content.split('## Iteration') if e.strip()]
        if not entries:
            return ""
        # Deduplicate by the "Avoid:" line so repeated identical errors show once
        seen_avoid = set()
        unique = []
        for e in reversed(entries):
            avoid_line = next((l for l in e.split('\n') if l.startswith('Avoid:')), '')
            if avoid_line not in seen_avoid:
                seen_avoid.add(avoid_line)
                unique.append(e)
            if len(unique) >= max_entries:
                break
        unique.reverse()
        return '\n'.join(f"## Iteration {e}" for e in unique)
    except Exception:
        return ""


# ════════════════════════════════════════════════════════════
# CONFIG LOADING
# ════════════════════════════════════════════════════════════

def load_config(config_file):
    """
    Load config.yaml. Resolve all paths from config file location.
    Returns config dict with all paths pre-resolved.
    Raises FileNotFoundError or ValueError with clear message.
    """
    config_path = Path(config_file).resolve()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_file}\n"
            f"Usage: python3 agent/agent.py <path/to/config.yaml>"
        )
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config is not a valid YAML dict: {config_file}")

    required = ['design_name', 'rtl_file', 'base_module',
                'scoreboard_module', 'coverpoint_names']
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(
            f"Config missing required keys: {missing}\n"
            f"Required: {required}"
        )
    # Defaults
    cfg.setdefault('threshold', 98.0)
    cfg.setdefault('max_iter', 8)
    cfg.setdefault('chain_of_thought', False)

    # All paths resolved from config file location
    dr = config_path.parent
    cfg['design_root']   = dr
    cfg['rtl_path']      = dr / cfg['rtl_file']
    cfg['yml_cov']       = dr / "coverage_reports" / "coverage.yml"
    cfg['yml_base']      = dr / "coverage_reports" / "coverage_base.yml"
    cfg['yml_directed']  = dr / "coverage_reports" / "coverage_directed.yml"
    cfg['yml_merged']    = dr / "coverage_reports" / "coverage_merged.yml"
    cfg['yml_sb']        = dr / "coverage_reports" / "scoreboard.yml"
    cfg['directed_test'] = dr / "tb" / "test_directed.py"
    cfg['graph_path']    = dr / "coverage_reports" / "coverage_graph.png"
    cfg['iter_path']     = dr / "coverage_reports"  # iteration_N.yml go here
    cfg['make_cwd']      = str(dr)

    if not cfg['rtl_path'].exists():
        raise FileNotFoundError(
            f"RTL file not found: {cfg['rtl_path']}\n"
            f"Check 'rtl_file' in config.yaml"
        )
    return cfg


# ════════════════════════════════════════════════════════════
# NORMALIZATION
# ════════════════════════════════════════════════════════════

def normalize_bin_key(key) -> str:
    """
    Generic bin key normalization — works for any design.
    Strips any dotted prefix (top., fifo., axi., dut., etc.)
    Normalizes tuple spacing: (0, 1) → (0,1)
    Handles N-tuples, negatives, booleans, None.
    Idempotent — safe to call multiple times.
    """
    if key is None:
        return ""
    key = str(key).strip()
    # Strip any prefix before the first dot
    # Only strip if dot comes before any bracket (it's a prefix not a value)
    first_bracket = key.find('[')
    first_dot = key.find('.')
    if first_dot > 0 and (first_bracket == -1 or first_dot < first_bracket):
        key = key[first_dot + 1:]
    def normalize_tuple(m):
        parts = [p.strip() for p in m.group(1).split(',')]
        return '(' + ','.join(parts) + ')'
    key = re.sub(r'\(([^)]+)\)', normalize_tuple, key)
    return key


# ════════════════════════════════════════════════════════════
# YAML PARSERS
# ════════════════════════════════════════════════════════════

def parse_coverage(yml_path):
    """
    Parse cocotb-coverage YAML. Uses 'bins:_hits' key (standard for all designs).
    Returns (pct, bins_dict, uncovered_list). ALERTs on failure.
    """
    yml_path = str(yml_path)
    if not yml_path or not os.path.exists(yml_path):
        print(f"  ALERT: coverage YAML not found: {yml_path}")
        return 0.0, {}, []
    try:
        with open(yml_path) as f:
            content = f.read()
        if not content.strip():
            print(f"  ALERT: coverage YAML empty: {yml_path}")
            return 0.0, {}, []
        data = yaml.safe_load(content)
    except Exception as e:
        print(f"  ALERT: coverage YAML corrupted — {e}")
        return 0.0, {}, []
    if not isinstance(data, dict):
        print(f"  ALERT: coverage YAML not a dict")
        return 0.0, {}, []
    bins = {}
    for name, attrs in data.items():
        if not isinstance(attrs, dict):
            continue
        bins_hits = attrs.get('bins:_hits', {})
        if not isinstance(bins_hits, dict):
            continue
        for bin_val, count in bins_hits.items():
            norm = normalize_bin_key(f"{name}[{bin_val}]")
            bins[norm] = int(count) if count is not None else 0
    if not bins:
        print(f"  ALERT: no bins found in {yml_path}")
        return 0.0, {}, []
    total = len(bins)
    hit   = sum(1 for v in bins.values() if v > 0)
    pct   = hit / total * 100 if total > 0 else 0.0
    return pct, bins, [b for b, v in bins.items() if v == 0]


def parse_scoreboard(yml_path):
    """Parse scoreboard YAML. Returns {} if missing — not fatal."""
    yml_path = str(yml_path)
    if not yml_path or not os.path.exists(yml_path):
        return {}
    try:
        with open(yml_path) as f:
            content = f.read()
        if not content.strip():
            return {}
        result = {}
        current_bin = None
        for line in content.strip().split('\n'):
            line = line.rstrip()
            if line == 'scoreboard:':
                continue
            if line.startswith('  "') and line.endswith('":'):
                current_bin = line.strip()[1:-2]
                result[current_bin] = {}
            elif current_bin and ':' in line:
                key, val = line.strip().split(':', 1)
                val = val.strip().strip('"')
                try:
                    result[current_bin][key] = int(val)
                except ValueError:
                    result[current_bin][key] = val
        return result
    except Exception as e:
        print(f"  ALERT: scoreboard YAML corrupted — {e}")
        return {}


# ════════════════════════════════════════════════════════════
# THREE-FILE MERGE SYSTEM
# ════════════════════════════════════════════════════════════

def merge_coverage(base_bins, directed_bins):
    """Merge base + directed by summing hit counts. Returns (merged, attribution)."""
    all_keys = set(base_bins.keys()) | set(directed_bins.keys())
    merged = {}; attribution = {}
    for k in sorted(all_keys):
        b = base_bins.get(k, 0); d = directed_bins.get(k, 0)
        merged[k] = b + d
        if b > 0 and d > 0:   attribution[k] = "BOTH"
        elif b > 0:            attribution[k] = "BASE"
        elif d > 0:            attribution[k] = "AGENT"
        else:                  attribution[k] = "NONE"
    return merged, attribution


def coverage_pct(bins):
    if not bins: return 0.0
    return sum(1 for v in bins.values() if v > 0) / len(bins) * 100


def save_merged(base_bins, directed_bins, cfg):
    merged, attr = merge_coverage(base_bins, directed_bins)
    with open(cfg['yml_merged'], 'w') as f:
        yaml.dump({'_merged_bins': merged, '_attribution': attr}, f)
    return merged, attr


# ════════════════════════════════════════════════════════════
# COMPARISON AND DECISION
# ════════════════════════════════════════════════════════════

def compute_comparison(merged_bins, sb_bins):
    """Categorize each bin: DATA FAIL / NOT HIT / HIT-ONLY / VERIFIED."""
    if not merged_bins:
        return {'total':0,'raw_pct':0.0,'verified_pct':0.0,
                'not_hit':[],'data_fail':[],'hit_only':[],'verified':[]}
    total   = len(merged_bins)
    raw_hit = sum(1 for v in merged_bins.values() if v > 0)
    raw_pct = raw_hit / total * 100
    not_hit=[]; data_fail=[]; hit_only=[]; verified=[]
    for bin_name, hit_count in sorted(merged_bins.items()):
        sb = sb_bins.get(bin_name, {}) if sb_bins else {}
        p  = sb.get('pass', 0) if isinstance(sb, dict) else 0
        f  = sb.get('fail', 0) if isinstance(sb, dict) else 0
        if hit_count == 0:
            not_hit.append(bin_name)
        elif f > 0:
            data_fail.append((bin_name, hit_count, p, f, f"{p/(p+f)*100:.0f}%"))
        elif p > 0:
            verified.append(bin_name)
        else:
            hit_only.append((bin_name, hit_count))
    return {'total':total,'raw_pct':raw_pct,
            'verified_pct':len(verified)/total*100,
            'not_hit':not_hit,'data_fail':data_fail,
            'hit_only':hit_only,'verified':verified}


def should_stop(comparison, cfg):
    """Stop when merged coverage >= threshold AND no DATA FAIL."""
    threshold = cfg['threshold']
    if comparison.get('data_fail'):
        return False, f"DATA FAIL in {[d[0] for d in comparison['data_fail']]}"
    if comparison.get('raw_pct', 0) < threshold:
        return False, f"Coverage {comparison.get('raw_pct',0):.1f}% < {threshold:.1f}%"
    return True, f"TARGET REACHED: {comparison.get('raw_pct',0):.1f}% — no data failures"


# ════════════════════════════════════════════════════════════
# PROMPT BUILDERS — zero design knowledge, all from config+RTL
# ════════════════════════════════════════════════════════════

def read_rtl(cfg) -> str:
    """Read ALL RTL files in the design directory. Reusable for any design."""
    import glob as _glob
    primary  = str(cfg['rtl_path'])
    rtl_dir  = os.path.dirname(os.path.abspath(primary))
    sv_files = sorted(_glob.glob(os.path.join(rtl_dir, '*.sv')))
    v_files  = sorted(_glob.glob(os.path.join(rtl_dir, '*.v')))
    all_files = sv_files + v_files
    if not all_files:
        return open(primary).read()
    parts = []
    for f in all_files:
        parts.append(f"// === FILE: {os.path.basename(f)} ===")
        parts.append(open(f).read())
    return '\n'.join(parts)


def extract_ports_from_rtl(rtl_text: str) -> list:
    """Extract DUT port names from RTL. Design-agnostic. Prevents hallucination."""
    import re
    pattern = r'\b(?:input|output)\b\s+(?:wire\s+|reg\s+|logic\s+)?(?:\[[\w\-:]+\]\s+)?(\b[a-zA-Z_]\w*\b)'
    ports = re.findall(pattern, rtl_text)
    keywords = {'wire','reg','logic','signed','unsigned','integer',
                'parameter','localparam'}
    seen = set()
    result = []
    for p in ports:
        if p not in keywords and p not in seen and not p[0].isdigit():
            seen.add(p)
            result.append(p)
    return result


def build_prompt(comparison, iteration, cfg, rtl_content,
                 prev_code=None, delta_info=None, iteration_index=0):
    """
    Build priority-ordered prompt for Claude API.
    All design knowledge comes from config (design_name, coverpoint_names)
    and RTL file (signal names, timing — Claude reads it directly).
    """
    r = comparison
    design_name = cfg['design_name'].upper()
    cp_names    = '\n'.join(f"  {n}" for n in cfg['coverpoint_names'])
    total_hit   = len(r['verified']) + len(r['data_fail']) + len(r['hit_only'])
    yml_cov_str = str(cfg['yml_cov'])
    tb_mod      = cfg['base_module'].split('.')[-1]
    sample_fn   = cfg.get('sample_function', 'sample_coverage')
    depth       = cfg.get('depth')

    lines = [
        f"=== {design_name} VERIFICATION STATUS ===",
        f"Iteration {iteration}/{cfg['max_iter']}",
        f"Merged coverage: {r['raw_pct']:.1f}% ({total_hit}/{r['total']} bins hit)",
        f"Verified:        {r['verified_pct']:.1f}% (data integrity proven)",
        f"Target:          {cfg['threshold']:.1f}%\n",
    ]
    priority = 1
    if r['data_fail']:
        lines.append(f"PRIORITY {priority} — DATA INTEGRITY FAILURES ({len(r['data_fail'])} bins):")
        lines.append("  Write known data, read back, assert correctness.")
        for n, h, p, f, pct in r['data_fail']:
            lines.append(f"  {n} — pass={p}, fail={f}, integrity={pct}")
        lines.append(""); priority += 1
    if r['not_hit']:
        total_nh = len(r['not_hit'])
        shown = min(12, total_nh)
        label = f"showing {shown} of {total_nh}" if total_nh > 12 else f"{total_nh} bins"
        lines.append(f"PRIORITY {priority} — NEVER REACHED ({label}):")
        for n in r['not_hit'][:12]:
            lines.append(f"  {n}")
        lines.append(""); priority += 1
        # Single-bin targeting: cycle through not_hit bins each iteration
        primary = r['not_hit'][iteration_index % len(r['not_hit'])]
        lines.append(f"PRIMARY TARGET THIS ITERATION: {primary}")
        lines.append("Write stimulus specifically to hit this bin. Use full not_hit list")
        lines.append("above for context but focus all effort on the primary target.")
        lines.append("")
    if r['hit_only']:
        lines.append(f"PRIORITY {priority} — HIT BUT NO DATA CHECK ({len(r['hit_only'])} bins):")
        for n, h in r['hit_only'][:6]:
            lines.append(f"  {n} (hit {h} times)")
        lines.append(""); priority += 1
    if r['verified']:
        lines.append(f"VERIFIED ({len(r['verified'])} bins) — no action needed.")

    lines.append("\n=== YOUR ROLE ===")
    lines.append("You are a hardware verification engineer.")
    lines.append("Read the full RTL source provided above.")
    lines.append("For each uncovered bin: analyze what DUT signal states are needed,")
    lines.append("write a cocotb test that creates those states, samples coverage.")
    lines.append("Reason from the RTL. Do not guess signal states.")

    lines.append("\n=== RTL SOURCE (read to understand signals and timing) ===")
    lines.append(rtl_content[:6000])
    port_names = extract_ports_from_rtl(rtl_content)
    logger.info(f"[ITER-{iteration}][PORT-EXTRACT] {len(port_names)} ports found")
    if port_names:
        lines.append("\n=== DUT SIGNAL NAMES — USE EXACTLY THESE (from RTL above) ===")
        lines.append("Valid dut.XXX names: " + ", ".join(port_names))
        lines.append("DO NOT use names not in this list.")

    lines.append("\n=== COVERAGE DECORATOR NAMES (use EXACTLY these) ===")
    lines.append(cp_names)
    lines.append("WRONG prefix: any other prefix — will NOT match")

    lines.append("\n=== INLINE DATA INTEGRITY CHECK (include this pattern) ===")
    lines.append("  write_queue = []")
    lines.append("  # On valid write: write_queue.append(int(dut.<write_data_port>.value))")
    lines.append("  # On valid read (after 1 clock): ")
    lines.append("  #   expected = write_queue.pop(0)")
    lines.append("  #   actual = int(dut.<read_data_port>.value)")
    lines.append("  #   assert actual == expected, f'DATA FAIL: {actual} != {expected}'")
    lines.append("  # Use exact port names from DUT SIGNAL NAMES list above.")

    if prev_code:
        lines.append("\n=== PREVIOUS ATTEMPT (did not fully close coverage) ===")
        lines.append(prev_code[:800])
        lines.append("Avoid repeating the same approach.")

    lines.append("\n=== COCOTB FRAMEWORK RULES ===")
    lines.append("RULE 1 — TIMING (universal cocotb rule):")
    lines.append("  dut.signal.value = X is QUEUED — not immediate.")
    lines.append(f"  You MUST await ReadOnly() before calling {sample_fn}.")
    lines.append(f"  Pattern: drive signals → await ReadOnly() → await {sample_fn}(dut)")
    lines.append("  Sampling before ReadOnly reads stale pre-assignment values.")
    lines.append("  CRITICAL: NEVER assign dut.signal.value = X AFTER await ReadOnly().")
    lines.append("  ReadOnly phase is read-only — any assignment raises RuntimeError.")
    lines.append("  If you need to set signals again, await RisingEdge(clock) first.")
    lines.append("")
    lines.append("RULE 2 — IMPORT:")
    lines.append(f"  import sys, os")
    lines.append(f"  sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))")
    lines.append(f"  from {tb_mod} import {sample_fn}")
    lines.append(f"  # If above fails: from tb.{tb_mod} import {sample_fn}")
    lines.append("")
    lines.append("RULE 3 — DO NOT REDEFINE COVERAGE:")
    lines.append("  CoverPoint and CoverCross are already registered in the base TB.")
    lines.append(f"  Only call {sample_fn}(dut). Never define @CoverPoint or @CoverCross.")
    lines.append("")
    lines.append("RULE 4 — SIGNAL NAMES:")
    lines.append("  Use ONLY the exact names from the DUT PORT LIST above.")
    lines.append("")
    lines.append("RULE 5 — CLOCK HELPER REQUIRED (prevents silent sampling failure):")
    lines.append("  Timer-based manual clock toggling causes ReadOnly() to see stale signal")
    lines.append(f"  values — {sample_fn} calls are silently skipped with no error.")
    lines.append("  ALWAYS drive clocks using the Clock helper coroutine:")
    lines.append("    from cocotb.clock import Clock")
    lines.append("    cocotb.start_soon(Clock(dut.<clk_A>, 10, units='ns').start())")
    lines.append("    cocotb.start_soon(Clock(dut.<clk_B>, 15, units='ns').start())")
    lines.append("  Then use RisingEdge triggers — NEVER Timer — for all test sequencing.")
    lines.append("")
    lines.append("RULE 6 — RESET+ENABLE CROSS BIN PATTERN (proven working):")
    lines.append("  For any bin requiring (reset_active, enable_high) simultaneously:")
    lines.append("    await RisingEdge(dut.<clock>)    # clock running via Clock helper above")
    lines.append("    dut.<rst_port>.value = 0         # assert reset (use exact RTL port name)")
    lines.append("    dut.<en_port>.value  = 1         # enable high at same time")
    lines.append("    await ReadOnly()                 # both settled — sample is valid here")
    lines.append(f"    await {sample_fn}(dut)          # cross bin (0,1) WILL be recorded")
    lines.append("  Apply this separately for each reset-domain clock pair in the RTL.")
    lines.append("")
    lines.append("RULE 7 — SIMULTANEOUS FLAGS FROM DIFFERENT CLOCK DOMAINS:")
    lines.append("  To hit a bin requiring two flags from different domains both = 1:")
    lines.append("  Check RTL for async-reset on each flag (negedge reset in always_ff).")
    lines.append("  Technique: drive flag_A=1 via normal operation, then assert the OTHER")
    lines.append("  domain's reset — if that reset asynchronously forces flag_B=1 (per RTL),")
    lines.append("  both are 1 simultaneously. Sample immediately:")
    lines.append("    await RisingEdge(dut.<clk_A>)")
    lines.append("    dut.<domain_B_rst>.value = 0     # async reset: flag_B → 1 instantly")
    lines.append("    await ReadOnly()                 # flag_A=1, flag_B=1 simultaneously")
    lines.append(f"    await {sample_fn}(dut)")

    if depth:
        lines.append(f"\n=== DESIGN PARAMETER ===")
        lines.append(f"Memory depth: {depth} entries. Use this exact value.")

    if delta_info and delta_info.get('still_zero'):
        lines.append(f"\nStill at 0 after last attempt: {delta_info['still_zero']}")
        lines.append("Read the RTL again. Try a completely different signal sequence.")
    if delta_info and delta_info.get('newly_hit'):
        lines.append(f"Successfully hit last iteration: {delta_info['newly_hit']}")

    # Inject lessons from persistent memory (last 5 entries)
    lessons = read_lessons(cfg)
    if lessons:
        lines.append("\n=== PAST FAILURES (do not repeat these) ===")
        lines.append(lessons)

    # Chain-of-thought reasoning questions (optional config flag)
    if cfg.get('chain_of_thought', False):
        lines.append("\n=== REASONING REQUIRED BEFORE CODING ===")
        lines.append("Before writing any code, answer these 4 questions for the PRIMARY TARGET bin:")
        lines.append("Q1: What signal values must co-occur simultaneously for this bin?")
        lines.append("Q2: For each signal — check always_ff sensitivity list in RTL.")
        lines.append("    SYNC = posedge clk only. ASYNC = includes negedge rst.")
        lines.append("Q3: If reset x enable bin: does if(!reset) take priority? Then simultaneous drive is legal.")
        lines.append("Q4: If cross-domain bin: what timing window exists between sync clock edges?")
        lines.append("Write your reasoning, then write the cocotb test.")

    lines.append("\n=== INSTRUCTIONS ===")
    lines.append("Write a complete @cocotb.test() targeting PRIORITY 1 bins first.")
    lines.append("Use directed sequences. Return ONLY valid Python. No markdown. No explanation.")
    lines.append("First line: import cocotb")
    lines.append(f'Last line: coverage_db.export_to_yaml("{yml_cov_str}")')
    return '\n'.join(lines)


def build_short_prompt(not_hit_bins, target_bin, cfg):
    """Short retry prompt — all design knowledge from config+RTL."""
    cp_names    = '\n'.join(f"  {n}" for n in cfg['coverpoint_names'])
    yml_cov_str = str(cfg['yml_cov'])
    return (
        f"Write a SHORT cocotb 2.0 test (max 60 lines) to hit: {target_bin}\n\n"
        f"COVERAGE DECORATOR NAMES (use EXACTLY):\n{cp_names}\n\n"
        "TIMING: Read the RTL to understand clock names and signal names.\n"
        "General cocotb 2.0 pattern:\n"
        "  await RisingEdge(dut.<clock>)  # drive ONLY after this\n"
        "  dut.<signal>.value = x\n"
        "  await ReadOnly()               # sample ONLY after this\n\n"
        "INLINE DATA CHECK (include):\n"
        "  write_queue = []\n"
        "  # on write: write_queue.append(int(dut.<write_data_port>.value))\n"
        "  # on read: assert int(dut.<read_data_port>.value) == write_queue.pop(0)\n"
        "  # Use exact port names from RTL — look at port list above.\n\n"
        f'LAST LINE: coverage_db.export_to_yaml("{yml_cov_str}")\n\n'
        "Return ONLY Python. No comments. No markdown. First line: import cocotb"
    )


# ════════════════════════════════════════════════════════════
# UTILITIES
# ════════════════════════════════════════════════════════════

def clean_code(raw):
    if not raw or len(raw.strip()) < 30:
        return None
    code = raw.strip()
    if code.startswith("```"):
        lines = code.split('\n')[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        code = '\n'.join(lines).strip()
    if len(code) < 30:
        return None
    try:
        ast.parse(code)
        # Fix: strip module-level (zero-indent) export_to_yaml before returning.
        # Confirmed by tail -5 in both Codespaces: export at 0 indent fires at
        # import time with zero hits. Mac: 4-space indent works correctly.
        code = '\n'.join(
            line for line in code.split('\n')
            if not line.startswith('coverage_db.export_to_yaml')
        )
        return code
    except SyntaxError as e:
        print(f"  Syntax error in generated code: {e}")
        return None


def was_updated(path, before):
    try:
        return os.path.getmtime(str(path)) > before
    except FileNotFoundError:
        return False


def run_sim(module, cfg):
    """Run make from design directory. Design-agnostic."""
    t0 = time.time()
    try:
        r = subprocess.run(
            ["make", f"MODULE={module}", "SIM=verilator"],
            capture_output=True, text=True,
            timeout=300, cwd=cfg['make_cwd']
        )
        elapsed = time.time() - t0
        combined = (r.stdout or "") + "\n" + (r.stderr or "")
        if r.returncode != 0 and r.stderr:
            print(f"  Sim stderr: {r.stderr[-200:]}")
        return r.returncode == 0, elapsed, combined
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: {module} exceeded 300s")
        return False, time.time() - t0, ""


def extract_sim_errors(stderr: str, directed_test_path: str = None) -> str:
    """
    Filter cocotb output to meaningful error lines.
    If directed_test_path given, parses the traceback to find the exact crashing
    line in the generated test file and prepends it — gives the API a concrete
    fix target instead of a generic RuntimeError message.
    Design-agnostic: uses only the test file path from config.
    """
    if not stderr or not stderr.strip():
        return ""
    result_lines = []

    # Parse traceback: find the crashing line in the test file
    if directed_test_path and os.path.exists(directed_test_path):
        test_filename = os.path.basename(directed_test_path)
        for line in stderr.split('\n'):
            m = re.search(
                r'File "([^"]*' + re.escape(test_filename) + r')", line (\d+)',
                line
            )
            if m:
                lineno = int(m.group(2))
                try:
                    code_lines = open(directed_test_path).readlines()
                    bad = code_lines[lineno - 1].strip() if lineno <= len(code_lines) else ''
                    result_lines.append(f"CRASH LINE {lineno}: {bad}")
                except Exception:
                    result_lines.append(f"CRASH AT LINE {lineno}")
                break  # only need the first match in the user's test file

    # Standard error keyword filtering
    meaningful = [
        'AttributeError', 'has no attribute', 'ImportError',
        'NameError', 'ModuleNotFoundError', 'SyntaxError',
        'RuntimeError', 'TypeError', 'ERROR',
    ]
    seen = set()
    for line in stderr.split('\n'):
        if any(p in line for p in meaningful):
            c = line.strip()
            if c and c not in seen:
                seen.add(c)
                result_lines.append(c)
    return '\n'.join(result_lines[:8])


def build_api_messages(prompt, prev_code=None, sim_errors=None):
    """Succinct multi-turn: inject last sim error. Design-agnostic."""
    if prev_code and sim_errors and sim_errors.strip():
        return [
            {"role": "user",      "content": prompt},
            {"role": "assistant", "content": prev_code},
            {"role": "user",      "content": (
                f"PREVIOUS TEST ERRORS (fix these):\n{sim_errors}"
                f"\n\nGenerate corrected test."
            )}
        ]
    return [{"role": "user", "content": prompt}]


def call_api_with_retry(model, max_tokens, temperature, system, messages, iter_label):
    """
    Call Claude API with explicit 3-attempt retry on 429 rate limit.
    Uses max_retries=0 to disable SDK auto-retry and control timing ourselves.
    Design-agnostic — all parameters passed in, no hardcoded values.
    """
    client = anthropic.Anthropic(max_retries=0)
    for attempt in range(3):
        try:
            return client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )
        except anthropic.RateLimitError:
            if attempt < 2:
                logger.info(
                    f"[{iter_label}][RETRY] Rate limit. Waiting 60s. "
                    f"Attempt {attempt+1}/3"
                )
                time.sleep(60)
            else:
                logger.info(f"[{iter_label}][SKIP] Rate limit after 3 attempts")
                return None


def print_option_c_table(base_bins, directed_bins, merged_bins, attribution, cfg):
    print()
    print(f"  {'BIN':<38} {'BASE':>6} {'AGENT':>6} {'TOTAL':>6}  SOURCE")
    print(f"  {'-'*38} {'-'*6} {'-'*6} {'-'*6}  {'-'*6}")
    agent_bins=[]; base_only=[]; both_bins=[]
    for k in sorted(merged_bins.keys()):
        b = base_bins.get(k, 0); d = directed_bins.get(k, 0)
        m = merged_bins[k]; src = attribution.get(k, 'NONE')
        print(f"  {k:<38} {b:>6} {d:>6} {m:>6}  {src}")
        if src == 'AGENT': agent_bins.append(k)
        elif src == 'BASE': base_only.append(k)
        elif src == 'BOTH': both_bins.append(k)
    print()
    print(f"  Summary: BASE={len(base_only)}  AGENT={len(agent_bins)}  BOTH={len(both_bins)}")


def graph(history, base_pct, cfg):
    try:
        plt.figure(figsize=(10, 6))
        x = list(range(1, len(history) + 1))
        plt.plot(x, history, 'b-o', lw=2, ms=8, label='Merged coverage %')
        plt.axhline(cfg['threshold'], color='r', ls='--', lw=1.5,
                    label=f"Target {cfg['threshold']:.0f}%")
        plt.axhline(base_pct, color='g', ls=':', lw=1.5,
                    label=f"Base ({cfg['base_module']}) {base_pct:.1f}%")
        for i, v in enumerate(history):
            plt.annotate(f'{v:.0f}%', (x[i], v),
                         textcoords="offset points",
                         xytext=(0, 8), ha='center', fontsize=9)
        plt.xlabel('Iteration'); plt.ylabel('Coverage (%)')
        plt.title(f"UVM Coverage Agent — {cfg['design_name']} Coverage Closure")
        plt.ylim(0, 105); plt.xticks(x); plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(str(cfg['graph_path']), dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  Graph: {cfg['graph_path']}")
    except Exception as e:
        print(f"  Graph note: {e}")


# ════════════════════════════════════════════════════════════
# MAIN AGENT LOOP
# ════════════════════════════════════════════════════════════

def main():
    # ── Parse args ──
    parser = argparse.ArgumentParser(
        description="UVM Coverage Agent — reusable for any cocotb design"
    )
    parser.add_argument('config', help="Path to design config.yaml")
    args = parser.parse_args()

    # ── API key check ──
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("ERROR: ANTHROPIC_API_KEY not set.")
        print("Run: export ANTHROPIC_API_KEY='your-key-here'")
        sys.exit(1)

    # ── Load config ──
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # ── Check coverage.yml exists ──
    if not cfg['yml_cov'].exists():
        print(f"ERROR: coverage.yml not found at {cfg['yml_cov']}")
        print(f"Run first: make SIM=verilator COCOTB_TEST_MODULES={cfg['base_module']}")
        sys.exit(1)

    # ── Setup ──
    cfg['yml_cov'].parent.mkdir(exist_ok=True)
    rtl_content = read_rtl(cfg)
    file_count = rtl_content.count('// === FILE:')
    logger.info(f"[SETUP][RTL-LOAD] {len(rtl_content)} chars, {max(file_count, 1)} file(s)")

    # ── Save base coverage (once at start) ──
    if not cfg['yml_base'].exists():
        shutil.copy(str(cfg['yml_cov']), str(cfg['yml_base']))
        print(f"  Saved coverage_base.yml from {cfg['base_module']} results")

    base_pct, base_bins, _ = parse_coverage(cfg['yml_base'])
    directed_bins = {}
    accumulated_directed_bins = {}
    prev_code = None
    prev_sim_errors = None
    prev_not_hit = []
    history = []

    print()
    print("=" * 55)
    print(f"UVM Coverage Agent — {cfg['design_name']}")
    print(f"Base coverage ({cfg['base_module']}): {base_pct:.1f}%")
    print(f"Target: {cfg['threshold']:.0f}% (merged) AND no DATA FAIL")
    print("=" * 55)

    for i in range(cfg['max_iter']):
        iter_label = f"ITER-{i+1}"

        # ── Merge ──
        merged_bins, attribution = merge_coverage(base_bins, accumulated_directed_bins)
        merged_pct = coverage_pct(merged_bins)
        sb_bins = parse_scoreboard(cfg['yml_sb'])
        comparison = compute_comparison(merged_bins, sb_bins)
        history.append(merged_pct)

        # ── Coverage delta ──
        still_zero = [b for b in prev_not_hit if b in comparison['not_hit']]
        newly_hit  = [b for b in prev_not_hit if b not in comparison['not_hit']]
        delta_info = {'still_zero': still_zero, 'newly_hit': newly_hit}
        prev_not_hit = list(comparison['not_hit'])

        # ── Status ──
        df = len(comparison['data_fail'])
        nh = len(comparison['not_hit'])
        agent_count = sum(1 for v in attribution.values() if v in ('AGENT','BOTH'))
        logger.info(
            f"[{iter_label}][STATUS] merged={merged_pct:.1f}%, "
            f"not_hit={nh}, data_fail={df}, agent_bins={agent_count}"
        )
        print(f"\n[Iter {i+1}/{cfg['max_iter']}] "
              f"Base={base_pct:.1f}% | Merged={merged_pct:.1f}% | "
              f"Agent added={agent_count} bins | DATA FAIL={df} | NOT HIT={nh}")
        for n,h,p,f,pct_str in comparison['data_fail']:
            print(f"  ⚠ DATA FAIL: {n} — pass={p}, fail={f}, integrity={pct_str}")
        for b in comparison['not_hit'][:3]:
            print(f"  ○ NOT HIT:   {b}")
        if newly_hit:
            print(f"  ✓ Newly hit: {newly_hit}")
        if still_zero:
            print(f"  ✗ Still zero: {still_zero}")

        # ── Stop check ──
        stop, reason = should_stop(comparison, cfg)
        if stop:
            print(f"  ✓ {reason}")
            break

        # ── Build prompt ──
        prompt = build_prompt(
            comparison, i+1, cfg, rtl_content,
            prev_code, delta_info, iteration_index=i
        )
        token_est = len(prompt) // 4
        logger.info(f"[{iter_label}][PROMPT-BUILD] ~{token_est} tokens, {nh} unhit bins")

        # ── Log feedback being sent to API ──
        if prev_sim_errors:
            logger.info(
                f"[{iter_label}][FEEDBACK] sim errors → API: {prev_sim_errors[:80]}"
            )

        # ── Claude API ──
        print(f"  Calling Claude API...")
        try:
            rtl_system = [{
                "type": "text",
                "text": "You are a hardware verification expert writing cocotb tests.\nRTL SOURCE:\n" + rtl_content[:4000],
                "cache_control": {"type": "ephemeral"}
            }]
            api_messages = build_api_messages(prompt, prev_code, prev_sim_errors)
            resp = call_api_with_retry(
                "claude-sonnet-4-6", 8000, 0, rtl_system, api_messages, iter_label
            )
            if resp is None:
                continue

            usage = resp.usage
            cache_read = getattr(usage, 'cache_read_input_tokens', 0)
            logger.info(
                f"[{iter_label}][API] stop_reason={resp.stop_reason} "
                f"input={usage.input_tokens} output={usage.output_tokens} "
                f"cache_read={cache_read}"
            )

            stop_reason = resp.stop_reason
            code = clean_code(resp.content[0].text)
            if stop_reason == "max_tokens" or code is None:
                print(f"  Truncated — retrying with same prompt at max tokens")
                time.sleep(10)
                resp2 = call_api_with_retry(
                    "claude-sonnet-4-6", 8000, 0, rtl_system, api_messages, iter_label
                )
                if resp2 is not None:
                    u2 = resp2.usage
                    logger.info(
                        f"[{iter_label}][API-RETRY] stop_reason={resp2.stop_reason} "
                        f"input={u2.input_tokens} output={u2.output_tokens} "
                        f"cache_read={getattr(u2, 'cache_read_input_tokens', 0)}"
                    )
                    code = clean_code(resp2.content[0].text)
        except Exception as e:
            print(f"  API error: {e}")
            continue

        if not code:
            print("  Invalid code — skipping iteration")
            continue

        # Guarantee export line
        yml_cov_str = str(cfg['yml_cov'])
        if 'export_to_yaml' not in code:
            code += f'\n    coverage_db.export_to_yaml("{yml_cov_str}")\n'
            print("  Added missing coverage export line")

        prev_code = code  # pass to next iteration as feedback

        # ── Write directed test ──
        with open(str(cfg['directed_test']), 'w') as f:
            f.write(code)

        # ── Run directed test ──
        print(f"  Running directed test...")
        bak = str(cfg['yml_cov']) + ".bak"
        if cfg['yml_cov'].exists():
            shutil.copy(str(cfg['yml_cov']), bak)
        t0 = time.time()
        ok, elapsed, raw_stderr = run_sim("tb.test_directed", cfg)
        logger.info(f"[{iter_label}][SIM-RUN] ok={ok}, elapsed={elapsed:.1f}s")
        prev_sim_errors = extract_sim_errors(raw_stderr, str(cfg['directed_test']))
        if not ok:
            print(f"  Directed test failed ({elapsed:.1f}s)")
            failure_msg = prev_sim_errors[:100] if prev_sim_errors else "unknown error"
            write_lesson(cfg, i+1, f"sim failed: {failure_msg}")
            if prev_sim_errors:
                logger.info(
                    f"[{iter_label}][FEEDBACK] sim errors queued for next iter: "
                    f"{prev_sim_errors[:80]}"
                )
            if os.path.exists(bak):
                shutil.copy(bak, str(cfg['yml_cov']))
                print("  coverage.yml restored from backup")
            continue

        yml_updated = was_updated(cfg['yml_cov'], t0)
        logger.info(f"[{iter_label}][COV-CHECK] yml_updated={yml_updated}")
        if not yml_updated:
            print("  coverage.yml not updated — no coverage progress")
            write_lesson(cfg, i+1, "coverage did not move after successful sim run")
            continue

        # ── Save directed + re-merge ──
        shutil.copy(str(cfg['yml_cov']), str(cfg['yml_directed']))
        _, directed_bins, _ = parse_coverage(cfg['yml_directed'])
        # Bug #1 fix: UCIS union-merge accumulation (per-bin max, never decreases)
        for _bin, _hits in directed_bins.items():
            accumulated_directed_bins[_bin] = max(
                accumulated_directed_bins.get(_bin, 0), _hits
            )
        merged_bins, attribution = merge_coverage(base_bins, accumulated_directed_bins)
        new_merged_pct = coverage_pct(merged_bins)
        save_merged(base_bins, accumulated_directed_bins, cfg)
        shutil.copy(str(cfg['yml_cov']),
                    str(cfg['iter_path'] / f"iteration_{i+1}.yml"))
        logger.info(
            f"[{iter_label}][MERGE] {merged_pct:.1f}% → {new_merged_pct:.1f}% "
            f"(Δ{new_merged_pct-merged_pct:+.1f}%)"
        )
        print(f"  Coverage: base={base_pct:.1f}% | "
              f"merged={merged_pct:.1f}% → {new_merged_pct:.1f}% "
              f"(Δ{new_merged_pct-merged_pct:+.1f}%)")

        # Write lesson if coverage gained nothing despite passing sim
        if new_merged_pct <= merged_pct:
            write_lesson(cfg, i+1, "coverage did not move despite successful sim run")

        # ── Run scoreboard test ──
        print(f"  Running scoreboard test...")
        sb_ok, _, _ = run_sim(cfg["scoreboard_module"], cfg)
        if not sb_ok:
            print("  ALERT: scoreboard test failed")

        time.sleep(60)

    # ── Final report ──
    final_merged, final_attr = merge_coverage(base_bins, accumulated_directed_bins)
    final_pct = coverage_pct(final_merged)
    final_sb  = parse_scoreboard(cfg['yml_sb'])
    final_comp = compute_comparison(final_merged, final_sb)

    print()
    print("=" * 55)
    print("FINAL REPORT")
    print("=" * 55)
    print(f"Design:                    {cfg['design_name']}")
    print(f"Base coverage ({cfg['base_module']}): {base_pct:.1f}%")
    print(f"Merged coverage (total):   {final_pct:.1f}%")
    print(f"Agent contribution:        {final_pct - base_pct:+.1f}%")
    print(f"Data failures:             {len(final_comp['data_fail'])}")
    print(f"Not hit bins:              {len(final_comp['not_hit'])}")
    print(f"Verified bins:             {len(final_comp['verified'])}")
    print(f"Iterations used:           {len(history)}")
    print(f"History (merged%):         {[f'{p:.0f}%' for p in history]}")
    print()
    print("COVERAGE ATTRIBUTION (Option C):")
    print_option_c_table(base_bins, accumulated_directed_bins, final_merged, final_attr, cfg)
    graph(history, base_pct, cfg)


if __name__ == "__main__":
    main()
