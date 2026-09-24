"""Automated grading for bench_cases results.

Grades a finished bench run against each case's structured `expected_result`
(task.json). The grading core is snapshot-based: it takes the FINAL model state
(the same schema as `bench_runner.backend.snapshot`) plus the
case's env BASELINE (the pre-state, `<case dir>/env/start/baseline.json`)
and returns a per-criterion score report.

The snapshot source (sources.py) is LIVE: reopen the collected result project in the
application and take a fresh snapshot + composite list — independent of anything the
agent recorded.

Units: expected_result and all checker math are in MILLIMETRES (the dataset
convention); snapshots arrive in metres and are normalized once in grade.py.
"""
