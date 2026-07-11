## Change 1 — Fix zero coverage: module-level export runs before tests

**What:** `coverage_db.export_to_yaml(...)` in `test_directed.py` was at module scope (line 183). Python executes module-level code at import time — before any coroutine runs. So `coverage_db` had 0 hits when the export fired, writing an all-zeros YAML. The test ran correctly and accumulated hits, but those hits were never exported. All 8 prior iterations wrote zeros for this reason.

**Where:** `tb/test_directed.py` line 183 (moved inside `test_hit_priority_bins`)

**Why:** Python module-level code executes at import time. `cocotb` imports the test module to discover test functions before running any test. `coverage_db.export_to_yaml(...)` outside any function = export fires with 0 hits.

**How:** Moved `coverage_db.export_to_yaml(...)` from module scope to the end of `test_hit_priority_bins`, indented inside the function body. Export now fires after all `await sample_coverage(dut)` calls complete.

**Test result:** `cx_en_busy[(1,1)]=6 hits`, `cx_rst_en[(0,1)]=6 hits`. `cover_percentage` from directed run alone = 88.89%; merged with base = 18/18 = 100%.

**Reusability:** Fix is in `designs/uart_tx/tb/test_directed.py` only. `agent.py` not touched.

---

## Change 2 — Systemic fix: atexit in tb_uart_tx.py overwrites premature zero-export

**What:** The Claude API consistently generates `coverage_db.export_to_yaml(...)` as the literal last line of the generated file (module scope), not inside the test function. This repeats Change 1's root cause on every agent iteration. Added an `atexit` handler in `tb_uart_tx.py` that exports coverage after all tests complete.

**Where:** `tb/tb_uart_tx.py` — import block, after existing imports

**Why:** `test_directed.py` always does `from tb_uart_tx import sample_coverage`. Importing `tb_uart_tx` registers the atexit handler. Atexit fires after the Python interpreter finishes all tests (after cocotb teardown). At that point, `coverage_db` holds all accumulated hits. The atexit export overwrites any earlier module-level zero-export written at import time.

**How:**
```python
import atexit as _atexit
_cov_yml = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'coverage_reports', 'coverage.yml'
)
@_atexit.register
def _auto_export_coverage():
    os.makedirs(os.path.dirname(_cov_yml), exist_ok=True)
    coverage_db.export_to_yaml(filename=_cov_yml)
```

Path is constructed from `__file__` at module import time — absolute, CWD-independent.

**Test result:** `coverage.yml` now contains real hit counts after every directed sim run, regardless of where the API places the export line.

**Reusability:** Fix is in `designs/uart_tx/tb/tb_uart_tx.py` only. `agent.py` not touched.

---

## Execution order (why atexit wins over module-level export)

1. cocotb imports `tb.test_directed`
2. `from tb_uart_tx import sample_coverage` → imports `tb_uart_tx` → atexit registered
3. Module-level `coverage_db.export_to_yaml(...)` fires → writes **zeros** to coverage.yml
4. cocotb runs `test_hit_priority_bins` → hits accumulate in coverage_db singleton
5. (If fixed) test function exports → overwrites zeros with actual hits
6. Python exits → atexit fires → exports actual hits → **guarantees correct YAML**

Step 6 is the safety net that makes every future agent-generated test correct.
