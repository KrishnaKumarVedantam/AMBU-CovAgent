"""
Apply F5, F6, F8 to agent/agent.py
Run this on Mac from inside the project folder:
  python3 apply_f5_f6_f8.py
"""
import ast, sys

path = 'agent/agent.py'
with open(path) as f:
    content = f.read()

original = content
errors = []

# ── F6: strip fifo. prefix ──
old6 = "    if key.startswith('top.'):\n        key = key[4:]"
new6 = "    if key.startswith('top.'):\n        key = key[4:]\n    elif key.startswith('fifo.'):\n        key = key[5:]"
if old6 in content:
    content = content.replace(old6, new6, 1)
    print("F6 APPLIED: fifo. prefix stripping")
else:
    errors.append("F6 pattern not found")
    print("F6 NOT FOUND")

# ── F8: build_short_prompt() ──
if 'def build_short_prompt' not in content:
    short_fn = (
        '\ndef build_short_prompt(not_hit_bins, target_bin=None):\n'
        '    """Short focused prompt — max 60 lines, one bin at a time."""\n'
        '    focus = target_bin or (not_hit_bins[0] if not_hit_bins else "uncovered bins")\n'
        '    return (\n'
        '        f"Write a SHORT cocotb 2.0 test (max 60 lines) to hit: {focus}\\n\\n"\n'
        '        "EXACT COVERPOINT NAMES (copy exactly):\\n"\n'
        '        "  CoverPoints:  top.cp_full, top.cp_empty, top.cp_wen, top.cp_ren\\n"\n'
        '        "                top.cp_half_full, top.cp_half_empty, top.cp_wrst, top.cp_rrst\\n"\n'
        '        "  CoverCrosses: top.cx_full_wen, top.cx_empty_ren, top.cx_full_empty\\n"\n'
        '        "                top.cx_wrst_wen, top.cx_rrst_ren\\n\\n"\n'
        '        "TIMING: await RisingEdge(dut.wclk) then drive. await ReadOnly() then sample.\\n"\n'
        '        "Clocks: cocotb.start_soon(Clock(dut.wclk, 10, unit=\\"ns\\").start())\\n"\n'
        '        "        cocotb.start_soon(Clock(dut.rclk, 15, unit=\\"ns\\").start())\\n\\n"\n'
        '        "LAST LINE MUST BE EXACTLY:\\n"\n'
        '        "  coverage_db.export_to_yaml(\\"coverage_reports/coverage.yml\\")\\n\\n"\n'
        '        "Return ONLY Python. No comments. No markdown.\\n"\n'
        '        "First line: import cocotb"\n'
        '    )\n'
    )
    insert_before = '\ndef build_prompt(comparison, iteration):'
    if insert_before in content:
        content = content.replace(insert_before, short_fn + insert_before, 1)
        print("F8 APPLIED: build_short_prompt() added")
    else:
        errors.append("F8 insert point not found")
        print("F8 NOT FOUND")
else:
    print("F8 already exists")

# ── F5: stop_reason check + retry ──
old5 = (
    '        try:\n'
    '            prompt = build_prompt(comparison, i + 1)\n'
    '            resp   = anthropic.Anthropic().messages.create(\n'
    '                model      = "claude-sonnet-4-6",\n'
    '                max_tokens = 4000,\n'
    '                messages   = [{"role": "user", "content": prompt}]\n'
    '            )\n'
    '            code = clean_code(resp.content[0].text)\n'
    '        except Exception as e:\n'
    '            print(f"  API error: {e}")\n'
    '            continue\n'
    '\n'
    '        if not code:\n'
    '            print("  Invalid code \xe2\x80\x94 skipping iteration")\n'
    '            continue'
)

new5 = (
    '        try:\n'
    '            prompt = build_prompt(comparison, i + 1)\n'
    '            resp   = anthropic.Anthropic().messages.create(\n'
    '                model      = "claude-sonnet-4-6",\n'
    '                max_tokens = 4000,\n'
    '                messages   = [{"role": "user", "content": prompt}]\n'
    '            )\n'
    '            stop_reason = resp.stop_reason\n'
    '            code = clean_code(resp.content[0].text)\n'
    '            if stop_reason == "max_tokens" or code is None:\n'
    '                print(f"  Truncated (stop_reason={stop_reason}) \xe2\x80\x94 retrying shorter")\n'
    '                target = comparison["not_hit"][0] if comparison["not_hit"] else None\n'
    '                short_p = build_short_prompt(comparison["not_hit"], target)\n'
    '                resp2 = anthropic.Anthropic().messages.create(\n'
    '                    model      = "claude-sonnet-4-6",\n'
    '                    max_tokens = 4000,\n'
    '                    messages   = [{"role": "user", "content": short_p}]\n'
    '                )\n'
    '                code = clean_code(resp2.content[0].text)\n'
    '        except Exception as e:\n'
    '            print(f"  API error: {e}")\n'
    '            continue\n'
    '\n'
    '        if not code:\n'
    '            print("  Invalid code \xe2\x80\x94 skipping iteration")\n'
    '            continue'
)

if old5 in content:
    content = content.replace(old5, new5, 1)
    print("F5 APPLIED: stop_reason check + retry")
else:
    # Try to find the API call block to show context
    idx = content.find('Invalid code')
    if idx > 0:
        print("F5 NOT FOUND — showing context around 'Invalid code':")
        print(repr(content[max(0,idx-400):idx+50]))
    errors.append("F5 pattern not found")

# ── Syntax check ──
try:
    ast.parse(content)
    print("SYNTAX OK")
except SyntaxError as e:
    errors.append(f"SYNTAX ERROR: {e}")
    print(f"SYNTAX ERROR: {e}")
    content = original

# ── Write ──
if not errors:
    with open(path, 'w') as f:
        f.write(content)
    print()
    print("ALL 3 FIXES APPLIED TO agent/agent.py")
    print("Run: python3 -c \"import ast; ast.parse(open('agent/agent.py').read()); print('OK')\"")
else:
    print()
    print("ERRORS — file NOT written:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
