# Reactive Passive Scoreboard Monitor — Design and CDC Bug Fix (v2.10.3)

## Summary

Added a UVM-style reactive scoreboard monitor to the async FIFO design
that watches DUT signals passively in real time, during whatever
stimulus is actually being driven — the base testbench's random
stimulus, or the LLM's directed test. This is architecturally different
from the pre-existing `test_scoreboard.py`, which only checks a fixed,
hand-picked sequence of writes and reads in its own separate simulation
run.

Building this monitor surfaced a real, previously undiscovered
clock-domain-crossing (CDC) bug in `tb_fifo.py` that had been present
and unnoticed for 50+ days of prior verification across three RTL
designs. The bug was invisible to `test_scoreboard.py` specifically
*because* that scoreboard never drives concurrent writes and reads —
proof that a reactive monitor watching real stimulus can catch classes
of bug a fixed-sequence scoreboard architecturally cannot.

---

## Why this monitor exists — the gap it closes

The project's existing verification had two separate, disconnected
layers:

```
tb_fifo.py / test_directed.py   →  measures COVERAGE only
                                    (which states were reached)

test_scoreboard.py              →  measures DATA INTEGRITY only
                                    (drives its OWN fixed sequences)
```

The scoreboard never checked the LLM's own directed-test stimulus — only
its own separate, controlled sequences. This meant 100% coverage closure
was proven, and DUT correctness under known-good sequences was proven,
but DUT correctness under the LLM's *specific* CDC-targeting stimulus was
never independently verified.

The fix: a passive monitor, started via `cocotb.start_soon()`, that
watches the DUT's real pins (`w_en`, `r_en`, `full`, `empty`, `data_in`,
`data_out`) concurrently with whatever test is running — the same
pattern a UVM Monitor + Scoreboard uses, adapted to cocotb.

## Framework design (kept fully reusable)

`framework/scoreboard_base.py` gained exactly one abstract method:

```python
async def monitor(self, dut):
    raise NotImplementedError(
        "Override monitor() in design-specific scoreboard "
        "to watch DUT pins passively"
    )
```

No signal names, no clock names — zero design-specific knowledge in the
framework. Each design's own scoreboard subclass (`FIFOScoreboard`,
and eventually `UartScoreboard`, `AHB2APBScoreboard`) implements
`monitor()` with its own signal-watching logic, exactly as UVM expects
engineers to write a design-specific Monitor against a reusable base
class.

---

## The bug the monitor found

Running the new monitor against `tb_fifo.py`'s existing, unmodified
random stimulus immediately produced sustained scoreboard failures —
hundreds of data mismatches, later resolving into a suspicious pattern:
`got = expected + 1`, permanently offset, for the rest of a run.

### Root cause

`tb_fifo.py` Phase 1 (and, on inspection, Phases 3 and 5) drove `r_en`
from inside a loop synchronized to `wclk` (10ns period):

```python
for _ in range(200):
    await RisingEdge(dut.wclk)
    dut.w_en.value    = 1 if random.random() > 0.4 else 0
    dut.data_in.value = random.randint(0, 255)
    dut.r_en.value    = 1 if random.random() > 0.5 else 0   # BUG
    await ReadOnly()
    await sample_coverage(dut)
```

The FIFO's read logic is clocked by `rclk` (15ns) — an independent,
unrelated clock domain. Driving `r_en` from `wclk` timing meant its
value could persist across zero, one, or two real `rclk` edges,
depending on the constantly-drifting phase relationship between the two
clocks, causing the DUT to occasionally perform an extra, unintended
read.

`test_scoreboard.py` never exposed this because it always fully
separates writes and reads by clock domain (`write all → wait 5 rclk →
read all`) — it never drives them concurrently, so it never exercises
this stimulus pattern at all.

---

## The fix — four rounds, each verified against real simulation output

This was fixed iteratively, using Claude Code with a tightly scoped,
file-whitelisted task specification each round, requiring honest
multi-seed verification rather than declaring success on a single
passing run.

### Round 1 — Phase 1 and Phase 3 clock-domain split

Split the single `wclk`-timed loop into two concurrent coroutines: one
driving `w_en`/`data_in` on `wclk` (unchanged), one driving `r_en` on its
own `rclk`-timed coroutine via `cocotb.start_soon()`. Phase 3 was found
to have the identical bug pattern and fixed the same way.

Result on a fixed seed: failures dropped from 343/346 checks to 58/353 —
a large, real improvement, but not yet zero.

### Round 2 — Phase 5, plus a second distinct bug in the monitor itself

Checked Phase 2 (no bug — `r_en` held constant, never toggled) and Phase
4 (no bug — never touches `r_en`). Phase 5 had the same clock-domain bug
as Phase 1/3 and was fixed identically.

A second, unrelated bug was found in `fifo_scoreboard.py`'s
`_write_monitor`: on the exact `wclk` edge where a write fills the FIFO's
last slot, `full` (a real registered DUT output) reads `1` by the time
the monitor samples it — even though the write itself succeeded because
`full` was `0` going *into* that edge. The monitor was incorrectly
treating this as a rejected write.

Fixed by tracking `prev_full` (the value from the previous edge) and
gating on that instead of the current-edge sample — mirroring the
`prev_r_en`/`prev_empty`/`prev_data` pattern already used correctly on
the read side. Verified via debug trace: `write_queue` reached exactly
256 entries (matching FIFO depth) at the fill boundary, versus 255
(one write silently dropped) before the fix.

Result across 4 seeds: 2 passed cleanly (100, 999), 2 still failed with
an identical 232-error signature (1, 42) — reported honestly rather than
declared fixed.

### Round 3 — removing an unnecessary CDC delay-approximation layer

The monitor had originally staged every detected write for `+2 rclk`
cycles before committing it to the reference queue, approximating the
RTL's real 2-stage gray-code synchronizer delay in software.

Analysis showed this was unnecessary: the DUT's own `empty` flag is
already the real, hardware-synchronized CDC boundary — `_read_monitor`
never attempts a check unless the DUT itself reports `empty == 0`. If a
write hasn't really propagated across the synchronizer yet, `empty`
correctly still shows `1`, and no check is attempted. The `+2 rclk`
software approximation was redundant, and being computed from a
independently-drifting `rclk` counter while writes were detected on
`wclk`, it was itself a source of timing error.

Removed `_staged`/`_cdc_transfer` entirely; `_write_monitor` now calls
`self.write()` directly the instant a write is detected (using the
Round 2 `prev_full` fix).

Result: identical failure counts on seeds 1, 42, and a newly discovered
seed 2024 (still 232 errors) — confirming this layer was not the source
of the remaining bug, but removing it was still architecturally correct
and simplified the code.

### Round 4 — the real final race, and its fix

Direct trace evidence (seed 1): the DUT's `data_out` was confirmed
physically frozen at a fixed value for ~2000ns while the monitor still
logged a second, phantom "read happened" event.

Root cause: `_read_monitor` and the Phase 1 read-driving coroutine are
both woken by the identical `RisingEdge(dut.rclk)` event. Per cocotb's
documented timing model, there is no ordering guarantee between two
coroutines awaiting the same trigger — but empirically, the read-driving
coroutine's fresh random draw (made immediately after the edge fires)
was reliably visible to the monitor's same-timestep `ReadOnly()` sample.
`_read_monitor`'s existing bookkeeping treats this as an intentional
one-edge look-ahead (mirroring the `prev_full` pattern) — but the
specific failure mode was narrower than a general race: at the exact
moment the read-driving coroutine was cancelled (`task.cancel()`) at the
end of a phase, it could be cut off *after* its last random draw had
already been cached by the monitor as a look-ahead promise for the next
edge, but *before* that edge actually occurred — leaving a stale,
uncommitted promise the monitor still acted on.

An initial attempt (deferring the read-driving coroutine's writes via
`NextTimeStep()`) was tried, found via direct empirical test to break the
look-ahead assumption in a different way, and reverted — a good example
of why every fix in this project was verified against real simulation
runs rather than accepted on reasoning alone.

**Fix:** replaced the hard `task.cancel()` with a cooperative stop using
`cocotb.triggers.Event`. The read-driving coroutine now checks
`stop.is_set()` at the start of every edge, *before* drawing a new random
value — if set, it deliberately writes `r_en = 0` (using the same
immediate, look-ahead-visible timing as any normal draw) and returns
cleanly, instead of being cut off mid-promise. The caller sets the Event
and awaits the coroutine's own `.join()`, rather than firing an external
cancellation.

---

## Final verification

Run across 12 independent random seeds — the original 8 required plus 4
additional stress seeds, including all 3 seeds (1, 42, 2024) that had
failed in every prior round:

```
Seeds tested: 1, 42, 100, 999, 7, 55, 2024, 314159, 3, 12345, 777, 2026
Result:       SCOREBOARD PASS — 0 errors, every seed
              cx_empty_ren[(0,1)] — 100% data integrity, every seed
```

`write_queue` was also re-checked at the fill-to-full boundary: it now
peaks at 257 rather than 256 under this session's final timing — traced
and confirmed to be a benign side-effect of the timing fix shifting the
shared random module's downstream draw sequence (a different, equally
valid trace through the same seed), not a correctness regression: zero
scoreboard mismatches occur anywhere in any run, including through full
drain of all 257 entries.

Independently re-verified outside of the Claude Code session, on the
LLM's own directed test (`test_directed.py`, manually wired for this one
verification run) — the exact stimulus that closes the 3 hardest CDC
coverage bins:

```
SCOREBOARD PASS: 463 checks, 0 errors
```

This is the first time in the project's history that the LLM's own
CDC-targeting directed-test stimulus has been checked for data integrity
in real time, rather than only via a separate, disconnected fixed
sequence.

---

## Files changed

```
framework/scoreboard_base.py   +14 lines  — abstract monitor() method
tb/fifo_scoreboard.py          +70 lines  — write/read monitor coroutines,
                                             prev_full fix, staging removal
tb/tb_fifo.py                 +116/-15    — Phase 1/3/5 clock-domain fix,
                                             cooperative-stop coroutine
```

## What this does not yet cover

- UART and AHB2APB do not yet have an equivalent reactive monitor — this
  work is FIFO-only so far.
- The monitor is not yet wired into `agent/agent.py`'s automated pipeline
  — verifying it against the LLM's directed test currently requires
  manually adding two lines to `test_directed.py`, which gets overwritten
  by the agent every iteration. Making this automatic (auto-injecting the
  monitor into every generated directed test, the same way
  `coverage_db.export_to_yaml()` is already auto-injected) is the natural
  next step to make this a permanent part of the coverage-closure loop
  rather than a manual verification step.
