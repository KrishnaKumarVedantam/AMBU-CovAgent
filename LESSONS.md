
## Iteration 1 — 2026-07-11 02:35
What failed: sim failed: CRASH LINE 132: await ReadOnly()
raise RuntimeError(
RuntimeError: Attempted illegal transition: awa
Avoid: NEVER assign dut.signal.value = X inside or after await ReadOnly(). Drive signals BEFORE ReadOnly, sample coverage AFTER ReadOnly. Any signal assignment in the ReadOnly phase raises RuntimeError.

## Iteration 3 — 2026-07-11 02:38
What failed: sim failed: CRASH LINE 92: dut.data_in.value = (i * 7 + 13) & 0xFF
raise RuntimeError("Attempting settings a val
Avoid: sim failed: CRASH LINE 92: dut.data_in.value = (i * 7 + 13) & 0xFF
raise RuntimeError("Attempting settings a val

## Iteration 4 — 2026-07-11 02:38
What failed: sim failed: CRASH LINE 59: dut.w_en.value = 1
raise RuntimeError("Attempting settings a value during the ReadOnl
Avoid: sim failed: CRASH LINE 59: dut.w_en.value = 1
raise RuntimeError("Attempting settings a value during the ReadOnl

## Iteration 5 — 2026-07-11 02:39
What failed: sim failed: CRASH LINE 54: dut.w_en.value = 1
raise RuntimeError("Attempting settings a value during the ReadOnl
Avoid: sim failed: CRASH LINE 54: dut.w_en.value = 1
raise RuntimeError("Attempting settings a value during the ReadOnl
