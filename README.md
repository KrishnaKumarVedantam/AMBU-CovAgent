# uvm-coverage-agent-backup-v2.10 — Export Fix + Full Cross-Platform Verification

## What This Version Is

This is the stable, production version of the UVM Coverage Agent
framework with two confirmed fixes applied and all three supported
RTL designs verified at 100% merged functional coverage on both
Mac (ARM64) and GitHub Codespaces (x86_64).

This checkpoint follows v2.9, which fixed Bug #1 (coverage accumulator
regression). v2.10 adds the export placement fix that enables reliable
100% coverage convergence in Codespaces environments.

---

## What We Fixed in v2.9 (carried forward)

### Bug #1 — Coverage Accumulator Regression

**The symptom:** During a single agent run, merged coverage could
decrease mid-run. A bin proven reachable in iteration 3 would
disappear from the merged result in iteration 4, and coverage would
drop from 97.2% back to 91.7%. Observed live, twice, in GitHub
Codespaces — the original trigger for this fix.

**The root cause:** In agent.py, the variable `directed_bins` was
reassigned from the most recent successful directed-test YAML file
at line 946 every iteration:

    _, directed_bins, _ = parse_coverage(cfg['yml_directed'])

This replaced `directed_bins` with ONLY the most recent iteration's
result. There was no mechanism to remember what previous iterations
had proven. When iteration N's test hit bins X and Y but iteration
N+1's test did not re-exercise those paths, bins X and Y reverted
to zero in the merged result — a silent regression.

**The fix (agent.py — 2 additions, 5 substitutions):**

Addition 1 — Initialize accumulator before the loop (line 787):

    accumulated_directed_bins = {}

Addition 2 — Update accumulator after each successful sim:

    # Bug #1 fix: UCIS union-merge accumulation (per-bin max, never decreases)
    for _bin, _hits in directed_bins.items():
        accumulated_directed_bins[_bin] = max(
            accumulated_directed_bins.get(_bin, 0), _hits
        )

All five merge_coverage() call sites updated to use
accumulated_directed_bins instead of directed_bins.

**Why max() and not sum():** max() correctly answers "has this bin
ever been proven reachable." sum() would double-count hits across
iterations, falsely implying more evidence than exists.

**Research backing:**
- Accellera UCIS 1.0 (June 2012): union-merge semantics — a bin hit
  in any run remains credited regardless of later runs.
- Elitism in evolutionary algorithms (ACM CISAI 2025): preserve the
  highest-performing solution across generations unconditionally.
- AFL/libFuzzer corpus model (IRFuzzer 2024): inputs that prove new
  coverage are permanently saved, never discarded.

---

## What We Fixed in v2.10

### Fix 2 — Export Placement (clean_code function in agent.py)

**The symptom:** In Codespaces (x86_64 Linux), every successful
simulation showed exactly 0% coverage gain — merged coverage never
moved despite the sim completing without errors. The agent would
write "coverage did not move despite successful sim run" in LESSONS.md
and continue iterating with no progress. All AGENT bins showed 0
in the final report.

**The root cause:** When the LLM generates long test files (250+ lines)
targeting hard CDC bins in Codespaces, it places
`coverage_db.export_to_yaml(...)` at module level — zero indentation,
outside the test function. This was confirmed directly:

    tail -5 tb/test_directed.py
    # showed: coverage_db.export_to_yaml("/path/coverage.yml")
    # at zero indent — outside the function

Python executes module-level code at import time, before any test
runs. So the sequence was:

    1. Python imports test file
    2. export_to_yaml fires immediately — coverage_db has zero hits
    3. Zeros written to YAML
    4. Test function runs — signals driven — bins hit — data in memory
    5. Test function ends — no second export fires
    6. Python exits — real coverage data gone forever
    7. Agent reads YAML — sees zeros — concludes "coverage did not move"

On Mac (ARM64), the LLM generates shorter tests (~100-150 lines)
where the export naturally lands inside the function at 4-space indent.
In Codespaces, longer tests cause the export to fall at module level.

**The fix (5 lines added to clean_code() in agent.py):**

    # Strip module-level (zero-indent) export_to_yaml before ast.parse.
    # LLM places this outside the function in long Codespaces tests.
    # Export guard at line 905 then injects correctly indented version.
    code = '\n'.join(
        line for line in code.split('\n')
        if not line.startswith('coverage_db.export_to_yaml')
    )

The strip runs BEFORE ast.parse(), so the post-strip code is
validated. The export guard at line 905 then sees no export in
the code and injects a correctly 4-space-indented version inside
the test function. This is design-agnostic — no signal names, bin
names, or paths are hardcoded.

**Confirmation:** After the fix, "Added missing coverage export line"
appears in the agent log when the fix fires, and successful sims
immediately show real coverage gains instead of 0%.

### Fix 3 — Coverage Thresholds Updated

    uart_tx config.yaml:  threshold 95 → 98
    ahb2apb config.yaml:  threshold 95 → 98

Both designs consistently reach 100% in 1-2 iterations. Setting
threshold to 98 ensures the agent continues past easy wins and
closes hard bins before stopping.

---

## Key Operational Rule

**Clear LESSONS.md before every fresh evaluation run.**

Stale LESSONS.md entries from a prior session contaminate the LLM's
prompt with irrelevant historical context, causing it to generate
lower-quality test code. This was confirmed live — runs with polluted
LESSONS.md stayed at 91.7% indefinitely while clean runs converged
to 100% consistently.

    rm -f LESSONS.md                        # async_fifo
    rm -f designs/uart_tx/LESSONS.md        # uart_tx
    rm -f designs/ahb2apb/LESSONS.md        # ahb2apb
    python3 agent/agent.py <config.yaml>

---

## Verification Results — All Three Designs at 100% on Both Platforms

### Mac ARM64 (Apple Silicon)

    async_fifo: 100% — 36/36 bins — AGENT: cx_full_empty[(1,1)],
                cx_rrst_ren[(0,1)], cx_wrst_wen[(0,1)]
    uart_tx:    100% — 18/18 bins — AGENT: cx_en_busy[(1,1)],
                cx_rst_en[(0,1)]
    ahb2apb:    100% — 46/46 bins — AGENT: 15 bins including all
                cp_fsm hard states and cx_psel_enable variants

### GitHub Codespaces x86_64 (Debian Trixie, Azure/Intel)

    async_fifo: 100% — verified across two independent runs
                Run 1: 4 iterations, Run 2: 8 iterations
    uart_tx:    100% — 1 iteration (14.3s including compilation)
    ahb2apb:    100% — 2 iterations, all 15 hard bins closed

All histories monotonically non-decreasing. No regression observed
in any run across either platform. Summary: BASE=0, AGENT=3+,
BOTH=majority on all designs.

---

## Architecture — Why This Works Across Platforms

The two key fixes together address the full Codespaces problem:

Bug #1 fix ensures coverage never regresses — bins proven hit in
iteration N stay credited in iterations N+1 through max_iter.

Export fix ensures successful sims always save their data — the
LLM's module-level export is stripped before the test is written
to disk, and a correctly-indented version is injected inside the
function by the existing guard at line 905.

Both fixes are in agent.py only — shared across all designs. Zero
design-specific code was introduced. Adding a new design requires
no knowledge of either fix.

---

## Branches

    uvm-coverage-agent-backup-v2.10-dev      Active development branch
    uvm-coverage-agent-backup-v2.10-untouch  Frozen verified reference

---

## What Is Still Pending

**Bug #2 — LESSONS.md deduplication without bin identity (P1):**
write_lesson() has no parameter for which bin was the primary target.
Global deduplication by "Avoid:" text can silently evict bin-specific
lessons when different bins produce similar error text. Impact:
efficiency only — may cost extra iterations, does not corrupt any
reported coverage number.

**time.sleep(60) (P2):**
8 iterations x 60 seconds = 8 minutes of dead wait per full run.
Safe to reduce to time.sleep(2). One line change, not yet applied.

**setup.sh zlibc (P2):**
The devcontainer setup.sh still includes zlibc in the apt-get
install list. zlibc does not exist on Debian Trixie (the Codespaces
base image), causing the postCreateCommand to fail on every new
Codespace. Manual workaround required: remove zlibc from the
apt-get line and run setup.sh manually. Fix is a one-line sed
command, not yet committed.

---

## File Structure

    agent/agent.py              Fixed agent (Bug #1 + export fix)
    agent/agent.py.bug1_backup  Pre-Bug#1-fix backup
    framework/                  Shared base classes (unchanged)
    config.yaml                 async_fifo config (threshold: 98)
    designs/uart_tx/            UART transmitter (threshold: 98)
    designs/ahb2apb/            AHB-to-APB bridge (threshold: 98)
