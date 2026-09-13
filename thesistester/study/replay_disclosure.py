"""AGENT_GUIDE Replay clause shared by expand CLI, experiment.yaml, overview MD.

Lives below ``expand`` / ``report`` so Observatory and Viewer do not import
``thesistester.cli`` via ``report`` → ``expand``. Disclosure only — not a
``run_batch`` behavior change (AH §2 item 7 / QI-07-06).
"""

from __future__ import annotations

REPLAY_NOT_STUDY_RUN = (
    "same dataset bytes when the expand-time file still exists; "
    "still run_batch — fail-fast, origin=cli, no index status — not study run"
)
