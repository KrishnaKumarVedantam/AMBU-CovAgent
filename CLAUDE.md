# CLAUDE.md — Bug #1 Fix: Coverage Accumulator Regression
# Adversarial verification + piece-by-piece implementation

## CONTEXT
- What this code does: Python agent (agent/agent.py) that runs a Claude API
  loop to generate directed cocotb hardware verification tests, iterating up
  to max_iter times to close functional coverage gaps in RTL designs.
- Language/framework: Python 3.11, cocotb 2.0.1, Verilator 5.048
- Known symptom: In two separate live runs, merged coverage regressed
  mid-run: [ITER-6][MERGE] 97.2% -> 91.7%. Bins proven reachable in
  iteration 5 showed as unreached in iteration 7. Confirmed root cause:
  merge_coverage(base_bins, directed_bins) uses ONLY the most-recent
  directed-test YAML each iteration. No accumulator exists.
- Evidence file: agent/agent.py (the only file you may modify)

## ACCESS MODEL

WRITE: agent/agent.py only.
READ (no approval needed): framework/coverage_base.py,
  framework/scoreboard_base.py, designs/ahb2apb/tb/*.py,
  designs/uart_tx/tb/*.py, tb/*.py, config.yaml,
  coverage_reports/*.yml
BLOCKED (never, no framing changes this):
  - Do not run python3 agent/agent.py without my explicit "run Piece 8" approval
  - Do not modify any file other than agent/agent.py
  - Do not run make for any design without my explicit approval
  - Do not git add, commit, or push anything
  - Do not modify coverage_reports/*.yml or LESSONS.md

## SAFETY BACKUP — first action, before anything else

Run: cp agent/agent.py agent/agent.py.bug1_backup
Verify: ls -la agent/agent.py.bug1_backup
Report size and timestamp. Do not proceed until confirmed.

---

## PHASE 1 — SPEC AUDIT

Read these requirements. List each as a checkbox. Then for each one,
state whether the CURRENT CODE meets it or violates it.

REQUIREMENT CHECKLIST:
  R1: Once a bin is proven hit in ANY iteration during a run, it must
      remain credited as hit for ALL subsequent iterations of that run,
      regardless of what later tests do or do not exercise.

  R2: Merged coverage percentage must be monotonically non-decreasing
      within a single run. It may plateau but must never drop.

  R3: The FINAL REPORT (after the loop exits) must reflect the best-ever
      coverage achieved during the run, not just the last iteration's result.

  R4: Accumulation must use per-bin maximum semantics. If bin X shows
      8 hits in iteration 2 and 3 hits in iteration 5, the accumulated
      result must be 8, not 3 and not 11.

  R5: The accumulator must be in-memory only, reset at the start of
      each python3 agent/agent.py invocation. It must NOT persist to disk
      and must NOT be read from disk at startup.

  R6: An empty accumulator (zero prior successful iterations) must not
      raise any error or produce wrong output. Iteration 1 must work
      correctly.

  R7: The accumulator must ONLY be updated after a SUCCESSFUL sim run
      where coverage.yml was actually updated (was_updated check passes).
      Failed sims must not corrupt the accumulator.

  R8: The function signature of merge_coverage(base_bins, directed_bins)
      must not change. Internal behavior is unchanged. Only the argument
      passed as directed_bins at call sites changes.

  R9: No design-specific code (signal names, bin names, design names)
      may appear in the accumulator logic. It must be design-agnostic.

  R10: After the fix, all three verified designs (async_fifo 36/36,
       uart_tx 18/18, ahb2apb 46/46) must still converge correctly.

For each requirement: state CURRENTLY MET or CURRENTLY VIOLATED,
with the exact line number that proves your answer.
Output this as your Phase 1 response before proceeding.

---

## PHASE 2 — CODE AUDIT

Read these specific functions and code blocks. For each one, verify it
matches the spec checklist. Flag every mismatch, suspicious assumption,
or unclear logic. Do not filter by severity.

BLOCK A — merge_coverage() at line 267:
  Read the full function body.
  Check: Does it modify either input parameter? (it should not)
  Check: What happens if directed_bins is {} (empty dict)?
  Check: What does it return? Does the return shape match what callers expect?

BLOCK B — Line 786 initialization (directed_bins = {}):
  Check: What value does directed_bins hold before any successful iteration?
  Check: What does merge_coverage(base_bins, {}) return? Is this correct
         for iteration 1 before any directed test has run?

BLOCK C — Line 803 (loop-top merge):
  Check: At what point in the iteration is this called?
  Check: What does it use as directed_bins input?
  Check: If this produces wrong merged_bins, what downstream code is affected?

BLOCK D — Lines 946-949 (success branch: parse, merge, save):
  Read all four lines carefully.
  Check: Is directed_bins updated here or read here or both?
  Check: What is the exact sequence: parse → merge → save? Is this order correct?
  Check: What is save_merged() doing with the data it receives?

BLOCK E — Line 973 (final report merge):
  Check: This is OUTSIDE the for loop. What value does directed_bins hold here?
  Check: Is the value at line 973 guaranteed to be the BEST result, or just the LAST?

BLOCK F — Line 993 (print_option_c_table call):
  Check: What does the second argument (directed_bins) represent in the table?
  Check: Should this show the last iteration's directed data or the accumulated best?

Report findings for all six blocks before proceeding.

---

## PHASE 3 — ADVERSARIAL BREAK ATTEMPT

Imagine you are trying to break the proposed fix. The proposed fix adds:
  accumulated_directed_bins = {}  (before the loop)
  for _bin, _hits in directed_bins.items():
      accumulated_directed_bins[_bin] = max(
          accumulated_directed_bins.get(_bin, 0), _hits)
  (after successful parse at line 946)
  And replaces directed_bins with accumulated_directed_bins at call sites.

Try to break it with each of these attack scenarios:

ATTACK 1 — Empty accumulator on iteration 1:
  accumulated_directed_bins = {}
  merge_coverage(base_bins, {})
  What does this return? Is it correct (all bins attributed as BASE or NONE)?
  Does it crash? Does it produce wrong attribution?

ATTACK 2 — All iterations fail (no successful sim runs):
  The update loop never executes. accumulated_directed_bins stays {}.
  merge_coverage(base_bins, {}) is called at line 803 every iteration.
  What does this produce? Does the agent crash or handle this gracefully?

ATTACK 3 — Type mismatch in accumulated values:
  We saw the real warning: "Coverage note: '>' not supported between
  instances of 'collections.OrderedDict' and 'int'"
  If directed_bins contains a value that is not an int (e.g., an
  OrderedDict from YAML parsing), what does max(OrderedDict, int) do?
  Does it crash or silently produce wrong output?

ATTACK 4 — Same bin hit in iteration 1 (count=8) and iteration 5 (count=1):
  accumulated_directed_bins['bin_x'] should be max(8, 1) = 8.
  Verify the max() call produces 8, not 1, not 9 (sum).
  What if the loop runs in a different order? Does order matter for max()?

ATTACK 5 — Bin present in base_bins but not in any directed test:
  accumulated_directed_bins.get('missing_bin', 0) = 0
  merge_coverage(base_bins, accumulated_directed_bins) for this bin:
  base_bins has it, accumulated doesn't → attributed as BASE.
  Is this correct? (Yes — it was covered by the base test, not the agent)

ATTACK 6 — Bin present in directed test but not in base_bins:
  base_bins.get('new_bin', 0) = 0
  accumulated_directed_bins has it with count > 0 → attributed as AGENT.
  Is this correct? (Yes — the agent discovered coverage base test never had)

ATTACK 7 — max_iter = 1 (single iteration scenario):
  The loop runs exactly once.
  If iter 1 succeeds: accumulator gets filled, all three merge calls use it.
  If iter 1 fails: accumulator stays {}, final report uses {}.
  Both paths must work without crash.

ATTACK 8 — Bin name key normalization:
  What if parse_coverage() returns a bin named 'cx_full[(0, 1)]' (with space)
  and another iteration returns 'cx_full[(0,1)]' (no space)?
  Would max() silently create two separate entries instead of accumulating?
  Check if normalize_bin_key() is called in parse_coverage() before the update.

For each attack: state SAFE (does not break) or VULNERABLE (breaks or
produces wrong output), with the exact reasoning.
Report all 8 before proceeding.

---

## PHASE 4 — FIX (implement in pieces, the golden rule)

Only proceed here after Phase 3 is complete and you have addressed
any VULNERABLE finding. If any attack exposed a real flaw, fix it
before implementing the accumulator.

### PIECE 4a — Syntax check before touching anything
  Run: python3 -c "import ast; ast.parse(open('agent/agent.py').read()); print('SYNTAX OK')"
  If not SYNTAX OK: stop and report. Do not continue.

### PIECE 4b — Add initialization (ONE line)
  After line 786 (directed_bins = {}), add:
    accumulated_directed_bins = {}

  Note on Attack 3 (type safety): if Phase 3 confirmed the OrderedDict
  risk is real, also add a safe_int helper before the loop:
    def safe_int(v):
        try: return int(v)
        except (TypeError, ValueError): return 0
  And use safe_int(_hits) in the max() call. Decide based on Phase 3 finding.

  Verify: grep -n "accumulated_directed_bins" agent/agent.py
  Syntax check: python3 -c "import ast; ast.parse(open('agent/agent.py').read()); print('SYNTAX OK')"
  Report both before proceeding to 4c.

### PIECE 4c — Add the accumulator update (after line 946, in success branch only)
  After: _, directed_bins, _ = parse_coverage(cfg['yml_directed'])
  Insert:
        # Bug #1 fix: UCIS union-merge accumulation (per-bin max, never decreases)
        for _bin, _hits in directed_bins.items():
            accumulated_directed_bins[_bin] = max(
                accumulated_directed_bins.get(_bin, 0), _hits
            )

  Verify: grep -n "for _bin" agent/agent.py
  Syntax check.
  Report before proceeding to 4d.

### PIECE 4d — Swap post-sim merge + save (lines 947 and 949)
  Change:
    merge_coverage(base_bins, directed_bins)     → merge_coverage(base_bins, accumulated_directed_bins)
    save_merged(base_bins, directed_bins, cfg)   → save_merged(base_bins, accumulated_directed_bins, cfg)

  Verify: grep -n "save_merged\|merge_coverage" agent/agent.py
  Syntax check.
  Report before proceeding to 4e.

### PIECE 4e — Swap loop-top merge (line 803)
  Change:
    merge_coverage(base_bins, directed_bins)  at line ~803
    → merge_coverage(base_bins, accumulated_directed_bins)

  Verify: grep -n "merge_coverage" agent/agent.py
  Syntax check.
  Report before proceeding to 4f.

### PIECE 4f — Swap final report merge and table (lines 973 and 993)
  Change:
    final_merged, final_attr = merge_coverage(base_bins, directed_bins)
    → final_merged, final_attr = merge_coverage(base_bins, accumulated_directed_bins)

    print_option_c_table(base_bins, directed_bins, final_merged, final_attr, cfg)
    → print_option_c_table(base_bins, accumulated_directed_bins, final_merged, final_attr, cfg)

  Verify COMPLETE final state:
    grep -n "merge_coverage\|accumulated_directed_bins\|directed_bins" agent/agent.py

  Expected: function defs (lines 267, 286, 703) still say directed_bins.
            all active call sites say accumulated_directed_bins.
            line 946 (parse) still says directed_bins (it is the source, unchanged).

  Syntax check.
  Import check: python3 -c "import sys; sys.path.insert(0,'.'); from agent.agent import merge_coverage; print('IMPORT OK')"
  Report both before proceeding to Phase 5.

---

## PHASE 5 — SPEC RE-VERIFICATION

Go back to the Phase 1 checklist. For each requirement R1-R10, state:
  MET — with the exact line of code that satisfies it
  NOT MET — with explanation

This must be done by reading the actual modified code, not by assuming.
Quote the relevant lines for each requirement.

---

## PHASE 6 — TESTS

Write a standalone test file at /tmp/test_bug1_accumulator.py

It must import merge_coverage directly from agent/agent.py and test
the accumulator logic WITHOUT running the real agent or any simulation.

REQUIRED TEST CASES (one function per test, print PASS or FAIL):

test_1_empty_accumulator():
  # R6: Empty dict must not crash
  # merge_coverage(base_bins={A:5}, accumulated={}) should return A as BASE
  base = {'cp_a[0]': 5}
  result, attr = merge_coverage(base, {})
  assert result['cp_a[0]'] == 5
  assert attr['cp_a[0]'] == 'BASE'
  print('test_1_empty_accumulator: PASS')

test_2_max_not_sum():
  # R4: max() semantics, not sum()
  # Hit 8 in iter2, hit 8 again in iter5 → accumulated = 8, not 16
  acc = {}
  for _bin, _hits in {'cp_x[0]': 8}.items():
      acc[_bin] = max(acc.get(_bin, 0), _hits)
  for _bin, _hits in {'cp_x[0]': 8}.items():
      acc[_bin] = max(acc.get(_bin, 0), _hits)
  assert acc['cp_x[0]'] == 8, f"Expected 8, got {acc['cp_x[0]']}"
  print('test_2_max_not_sum: PASS')

test_3_regression_prevention():
  # R1 and R2: The EXACT real v2.7 Mac data that proved Bug #1
  # iter1: cx_full_empty[(1,1)] = 0 (not present)
  # iter3: cx_full_empty[(1,1)] = 2 (HIT — proven reachable)
  # iter4: cx_full_empty[(1,1)] = 0 (not present — regression with old code)
  # iter6-8: cx_full_empty[(1,1)] = 0 (still not present)
  acc = {}
  iterations = [
      {'cx_full_empty[(0,0)]': 106, 'cx_full_empty[(0,1)]': 34},
      {'cx_full_empty[(0,0)]': 439, 'cx_full_empty[(0,1)]': 31,
       'cx_full_empty[(1,0)]': 2,   'cx_full_empty[(1,1)]': 2},
      {'cx_full_empty[(0,0)]': 213, 'cx_full_empty[(0,1)]': 29},
      {'cx_full_empty[(0,0)]': 918, 'cx_full_empty[(0,1)]': 18, 'cx_full_empty[(1,0)]': 6},
      {'cx_full_empty[(0,0)]': 53,  'cx_full_empty[(0,1)]': 31},
      {'cx_full_empty[(0,0)]': 901, 'cx_full_empty[(0,1)]': 14, 'cx_full_empty[(1,0)]': 6},
  ]
  for it in iterations:
      for _bin, _hits in it.items():
          acc[_bin] = max(acc.get(_bin, 0), _hits)
  result = acc.get('cx_full_empty[(1,1)]', 0)
  assert result == 2, f"Expected 2, got {result} — Bug #1 regression not fixed"
  print('test_3_regression_prevention: PASS')

test_4_monotonic_pct():
  # R2: Coverage % must never decrease when accumulating
  from agent.agent import merge_coverage, coverage_pct
  base = {'cp_a[0]': 5, 'cp_b[0]': 0, 'cp_c[0]': 0}
  acc = {}
  prev_pct = 0
  iterations = [
      {'cp_a[0]': 5, 'cp_b[0]': 3},
      {'cp_a[0]': 0, 'cp_b[0]': 0},
      {'cp_c[0]': 7},
  ]
  for it in iterations:
      for _bin, _hits in it.items():
          acc[_bin] = max(acc.get(_bin, 0), _hits)
      merged, _ = merge_coverage(base, acc)
      pct = coverage_pct(merged)
      assert pct >= prev_pct, f"Coverage regressed: {prev_pct}% -> {pct}%"
      prev_pct = pct
  print('test_4_monotonic_pct: PASS')

test_5_type_safety():
  # Attack 3: What happens with non-int hit values?
  # The safe_int() helper (if added) must coerce bad values to 0
  acc = {}
  import collections
  bad_val = collections.OrderedDict()
  try:
      v = max(acc.get('bin_x', 0), int(bad_val) if isinstance(bad_val, (int, float)) else 0)
      acc['bin_x'] = v
      assert acc['bin_x'] == 0
      print('test_5_type_safety: PASS')
  except Exception as e:
      print(f'test_5_type_safety: FAIL — {e}')

test_6_attribution_correct():
  # R1: A bin hit only by agent must be AGENT attribution
  # A bin hit by both must be BOTH
  from agent.agent import merge_coverage
  base = {'cp_a[0]': 5, 'cp_b[0]': 0}
  acc = {'cp_b[0]': 3}
  merged, attr = merge_coverage(base, acc)
  assert attr['cp_a[0]'] == 'BASE', f"Expected BASE got {attr['cp_a[0]']}"
  assert attr['cp_b[0]'] == 'AGENT', f"Expected AGENT got {attr['cp_b[0]']}"
  print('test_6_attribution_correct: PASS')

test_7_single_iteration():
  # Attack 7: max_iter=1, single successful iteration
  acc = {}
  one_iter = {'cp_x[0]': 5, 'cp_y[0]': 3}
  for _bin, _hits in one_iter.items():
      acc[_bin] = max(acc.get(_bin, 0), _hits)
  assert acc['cp_x[0]'] == 5
  assert acc['cp_y[0]'] == 3
  print('test_7_single_iteration: PASS')

test_8_all_iters_fail():
  # Attack 2: All iterations fail, accumulator never updated
  acc = {}
  from agent.agent import merge_coverage, coverage_pct
  base = {'cp_a[0]': 5, 'cp_b[0]': 0}
  merged, attr = merge_coverage(base, acc)
  pct = coverage_pct(merged)
  assert pct == 50.0, f"Expected 50.0% (base only), got {pct}"
  assert attr['cp_a[0]'] == 'BASE'
  assert attr['cp_b[0]'] == 'NONE'
  print('test_8_all_iters_fail: PASS')

Run all 8 tests:
  cd /Users/krishna/uvm-coverage-agent-backup-v2.8-ahb2apb
  python3 /tmp/test_bug1_accumulator.py

Report exact output. Every test must print PASS. Any FAIL stops the session.

---

## AFTER ALL PHASES PASS — Piece 8 (live run, requires my approval)

Do NOT run this without my explicit "run Piece 8" message.

When approved, run:
  python3 agent/agent.py config.yaml

Watch every [ITER-N][MERGE] line. Coverage must never decrease.
Report: every [ITER-N][MERGE] line in order, the final %, and whether
the 97.2% → 91.7% regression pattern appeared or not.

## IF ANYTHING FAILS

If any phase, piece, or test fails: STOP.
Show the exact error. Do not attempt self-repair.
Restore from backup: cp agent/agent.py.bug1_backup agent/agent.py
Then report what failed and wait for my instruction.
