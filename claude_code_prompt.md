# UVM Coverage Agent — 6 Robustness Additions

## THE REAL GOAL — READ THIS FIRST

This agent currently works on one design (async_fifo) that was built
by its author. The real test is: does it work on a completely new
design with zero changes to agent.py?

These 6 additions exist to make the agent robust enough for that test.
Every implementation decision must ask: "does this work for any design,
not just this one?"

Current proven state:
- async_fifo: 91.7% → 100% coverage in 3 iterations ✓
- Zero hardcoded design terms in agent.py ✓
- F1/F2/F3 feedback loop working ✓

What broke us before and why each addition fixes it:
1. LOGGING   → we lost days to MODULE= silent failure. Logging shows what runs.
2. TOKENS    → we cannot prove prompt caching works without seeing cache_read.
3. LESSONS   → API repeated Timer() mistake 8 iterations. Memory stops this.
4. RETRY     → 429 errors silently skipped iterations, losing coverage progress.
5. SINGLE-BIN→ API wrote diluted tests hitting no bins precisely.
6. CoT       → API coded without reasoning about RTL — hit wrong timing.

These 6 are ONE system. Logging makes everything else visible.
LESSONS feeds into CoT. Retry protects LESSONS from gaps.
Implement in order — each one depends on the previous.

---

## RULES — NON-NEGOTIABLE

- Modify ONLY agent/agent.py and CHANGES.md
- Zero hardcoded design terms in agent.py (grep check after every change)
- One priority at a time — do not start next until current passes all checks
- If something fails — fix it completely before moving on
- Every implementation must work for ANY cocotb design via config.yaml only

---

## AFTER EVERY SINGLE PRIORITY — RUN THESE 4 CHECKS

```bash
# 1. Syntax
python3 -c "import ast; ast.parse(open('agent/agent.py').read()); print('SYNTAX OK')"

# 2. Reusability — must be zero matches outside comments
grep -n "tb_fifo\|wclk\|w_en\|w_rst\|async_fifo\|cx_wrst\|cx_rrst\|cx_full" agent/agent.py

# 3. Run agent
python3 agent/agent.py config.yaml 2>&1 | head -60

# 4. Verify SUCCESS CRITERION for that specific priority (listed below)
```

Write CHANGES.md entry after each: What / Where / Why / How / Test result / Reusability

---

## PRIORITY 1 — Pipeline Logging
**Why:** Silent failures waste days. The MODULE= bug ran the wrong test
for days with no indication. Logging makes every stage joint visible.

**Goal:** Every pipeline stage shows what it received and what it produced.
Use Python logging module (not print). Format: `[ITER-{i}][STAGE-NAME] message`
No design-specific terms in any log message — use cfg['design_name'] dynamically.

Log these 8 joints — no more, no less:
- After RTL load: chars loaded, file count
- After port extraction: port count
- After prompt build: token estimate, unhit bin count  
- After API call: stop_reason
- After sim run: ok=True/False, elapsed seconds
- After coverage check: whether yml was updated
- After merge: merged percentage
- Before next iteration: sim errors being sent as feedback

**SUCCESS CRITERION:** All 8 stage tags visible in output for every iteration.
Zero design terms in any log line.

---

## PRIORITY 2 — Token and Cost Tracking
**Why:** We added prompt caching but never confirmed it works.
cache_read_input_tokens > 0 proves the cache is being hit.

**Goal:** After every API call log:
`[ITER-{i}][API] input=X output=Y cache_read=Z`

**SUCCESS CRITERION:** [API] line appears after every API call.
cache_read > 0 from iteration 2 onwards.
If cache_read stays 0 every iteration — prompt caching is broken, investigate.

---

## PRIORITY 3 — LESSONS.md Persistent Memory
**Why:** The API used Timer() instead of Clock() for 8 iterations because
it had no memory of what failed before. LESSONS.md gives it that memory.

**Goal:**
- Write: after any failed sim (ok=False) OR coverage did not move (Δ=0%),
  append to LESSONS.md:
  ```
  ## Iteration {i} — {datetime}
  What failed: {first line of sim errors or "coverage did not move"}
  Avoid: {error type or "same stimulus pattern"}
  ```
- Read: in build_prompt(), after coverage status section and BEFORE
  instructions section, inject last 5 entries from LESSONS.md.
  If file does not exist or is empty — skip silently, no error.
  Maximum 5 entries to limit token cost (~50 tokens).

**SUCCESS CRITERION:** Run agent twice.
First run: LESSONS.md created when any failure occurs.
Second run: LESSONS content visible in what gets sent to API.

---

## PRIORITY 4 — Retry on 429 Rate Limit
**Why:** 429 errors silently skipped iterations. If an iteration is skipped,
LESSONS.md does not get updated and coverage progress is lost.

**Goal:** When API raises 429 error:
- Log: `[ITER-{i}][RETRY] Rate limit. Waiting 60s. Attempt {n}/3`
- Wait 60 seconds exactly
- Retry the SAME call — identical messages, model, max_tokens, temperature
- After 3 failed retries: log `[ITER-{i}][SKIP]` then continue to next iteration
- Do NOT change anything between retries

**SUCCESS CRITERION:** Code inspection confirms same messages object
used in retry. Syntax passes. Logic is verifiable by reading the code.

---

## PRIORITY 5 — Single-Bin Targeting
**Why:** API wrote general tests that diluted effort across all bins
and hit none of them precisely. Focusing on one bin per iteration
forces precise stimulus.

**Goal:** In build_prompt() — not in the main loop:
- Compute: primary = not_hit[iteration_index % len(not_hit)]
- Add to prompt after the not_hit list:
  "PRIMARY TARGET THIS ITERATION: {primary}"
  "Write stimulus specifically to hit this bin. Use full not_hit list
  above for context but focus all effort on the primary target."
- Pass iteration_index as new parameter to build_prompt()
- Zero hardcoded bin names

**SUCCESS CRITERION:** Run agent. PRIMARY TARGET line changes each
iteration (cycles through not_hit bins). Verify in agent output or
by checking what gets sent to API each iteration.

---

## PRIORITY 6 — Chain of Thought (Config Flag)
**Why:** API jumped straight to coding without reasoning about RTL structure.
It used Timer() because it did not analyze whether signals were sync or async.
CoT forces reasoning before coding.

**Goal:**
- Add to load_config() with default False: chain_of_thought
- Add to config.yaml: `chain_of_thought: false`
- In build_prompt(), if cfg.get('chain_of_thought', False):
  Add BEFORE instructions section:
  ```
  === REASONING REQUIRED BEFORE CODING ===
  Before writing any code, answer these 4 questions for the PRIMARY TARGET bin:
  Q1: What signal values must co-occur simultaneously for this bin?
  Q2: For each signal — check always_ff sensitivity list in RTL.
      SYNC = posedge clk only. ASYNC = includes negedge rst.
  Q3: If reset x enable bin: does if(!reset) take priority? Then simultaneous drive is legal.
  Q4: If cross-domain bin: what timing window exists between sync clock edges?
  Write your reasoning, then write the cocotb test.
  ```

**SUCCESS CRITERION:** Set chain_of_thought: true in config.yaml.
Run agent. Generated test_directed.py must contain reasoning text
answering Q1-Q4 before the cocotb code. Reset to false after test.

---

## FINAL VERIFICATION — ALL 6 COMPLETE

```bash
# Syntax
python3 -c "import ast; ast.parse(open('agent/agent.py').read()); print('SYNTAX OK')"

# Reusability
grep -n "tb_fifo\|wclk\|w_en\|w_rst\|async_fifo" agent/agent.py

# Full run
python3 agent/agent.py config.yaml

# Must see:
# - All 8 stage tags every iteration
# - [API] token lines with cache_read > 0 from iter 2
# - Coverage reaches 100% still
# - CHANGES.md has 6 entries

# CHANGES.md check
cat CHANGES.md
```

If coverage is NOT 100% after all 6: use the stage logs from Priority 1
to identify which stage failed. The logs will show exactly where the
pipeline broke — that is what they were built for.
