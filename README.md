# FoR-Lab

Download **FoR-Lab.zip** and extract it into an empty folder. The archive contains the complete publication snapshot (309 files): source code, tests, protocols, historical runs, results and negative cases. Open the README.md inside the extracted folder for setup and execution instructions.

This repository currently distributes the laboratory as an archive; the source tree is inside that archive. No new experiments were run during publication preparation. The original local laboratory was not modified.

## Quick start after extraction (Windows)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m unittest discover -s . -p "test_*.py" -v
.\.venv\Scripts\python.exe -B research/measurement-fix-2026-10-23/run.py
```

Python 3.11+; NumPy is used by the legacy environment. Later research pilots use the standard library. Tkinter is needed only for the legacy GUI. Root tests do not cover all research suites; see individual launchers and protocols.

## Honest limits

Finite symbolic research prototypes, not demonstrated artificial Reason, AGI, consciousness or autonomous value formation. The full Core/Compass architecture is not validated. No scientific advantage over a strong independent baseline is established: B2 is equal or cheaper in final pilots. Unit-test success is not proof of the theory.

Historical failures and negative cases are retained. A nonlinear measurement counterexample passes reference-point checks yet fails elsewhere. The integrated pilot can reach its goal with a wrong model. These limitations are part of the results, not omitted exceptions.

## Publication checks

Virtual environments, caches and raw browser/chat captures are excluded. Personal directory names and emails are redacted. RELEASE_MANIFEST.json records per-file original/publication hashes and exclusions. Historical hashes may reference unsanitized originals. Common secret patterns were checked and Python files syntax-parsed; this is not an exhaustive security audit or independent replication.
