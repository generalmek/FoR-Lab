"""Replay recorded number-correction controls with the frozen FoR 154 parser."""
import json
from pathlib import Path
from for_discourse_151 import analyze

expected_recorded_mismatches = 1
mismatches = 0
total = 0
with (Path(__file__).resolve().parents[1] / 'results' / 'controls-154.jsonl').open(encoding='utf-8') as stream:
    for line in stream:
        row = json.loads(line)
        if row['kind'] != 'correction_probe':
            continue
        total += 1
        observed = analyze([('1:01', row['input'])])
        assert json.loads(json.dumps(observed)) == row['actual'], row['input']
        mismatch = bool(observed) != row['expected']
        mismatches += int(mismatch)
        print(f"{'RECORDED FAILURE' if mismatch else 'PASS'}: {row['input']} -> {observed}")
assert total == 3 and mismatches == expected_recorded_mismatches
print(f'Reproduced {total} controls, including {mismatches} documented failure.')
