"""RS-D5 external Grok routine pack — docs/examples acceptance locks."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PACK = REPO / "docs" / "STUDY_RUNNER_GROK_ROUTINE_PACK.md"
AGENTS = REPO / "examples" / "studies" / "agents"
OPERATOR = REPO / "docs" / "STUDY_RUNNER.md"


@pytest.mark.parametrize(
    "path",
    [
        PACK,
        AGENTS / "README.md",
        AGENTS / "SYSTEM.md",
        AGENTS / "ROUTINE_STAGE_FIRST.md",
        AGENTS / "ROUTINE_CONFIRM_BOUND.md",
        AGENTS / "ROUTINE_SURVIVOR_DIAGNOSTICS.md",
    ],
)
def test_routine_pack_files_exist(path: Path):
    assert path.is_file(), f"missing RS-D5 artifact: {path.relative_to(REPO)}"


def test_pack_hard_rules_and_surfaces():
    text = PACK.read_text(encoding="utf-8")
    lower = text.lower()
    # Non-goals / hard rules
    assert "never invent" in lower or "invent factor" in lower
    assert "bypass" in lower and "confirm" in lower
    assert "promote" in lower and ("draft" in lower or "auto-run" in lower)
    assert "min_trades" in text
    assert "multiple-testing" in lower or "multiple_testing" in text
    # RS6 default-off + CLI fallback
    assert "assistant.study_tools" in text
    assert "enabled=false" in text or "enabled = false" in text or "enabled=false" in lower
    assert "cli" in lower
    # RS-D7 index PF
    assert "profit_factor" in text
    assert "win_rate" in text
    # No product host / MCP
    assert "mcp" in lower
    assert "rabbitmq" in lower
    # Recipe spine
    assert "stage-first" in lower or "stage first" in lower
    assert "rollup" in lower


def test_system_prompt_forbids_auto_promote_execute():
    system = (AGENTS / "SYSTEM.md").read_text(encoding="utf-8")
    lower = system.lower()
    assert "never auto-run promote" in lower or "never auto-run" in lower
    assert "never invent" in lower
    assert "never bypass confirm" in lower
    assert "no" in lower and "mcp" in lower
    # Survivor overfitting gate + promote overwrite (docs drift locks).
    assert "validation.enabled" in system
    assert "validation.overfitting.enabled" in system
    assert "--force" in system or "force=true" in lower
    assert "no `STUDY.rollup`" in system or "no STUDY.rollup" in system


def test_stage_first_mentions_promote_force_gate():
    text = (AGENTS / "ROUTINE_STAGE_FIRST.md").read_text(encoding="utf-8")
    assert "--force" in text
    assert "do not auto-run the draft" in text.lower()


def test_pack_documents_validation_parent_gate_and_cli_rollup():
    text = PACK.read_text(encoding="utf-8")
    assert "validation.enabled: true" in text
    assert "validation.overfitting.enabled: true" in text
    assert "STUDY.rollup" in text  # explicitly "no STUDY.rollup"
    assert "no `STUDY.rollup`" in text or "no STUDY.rollup" in text
    assert "--force" in text


def test_operator_contract_points_at_pack():
    text = OPERATOR.read_text(encoding="utf-8")
    assert "STUDY_RUNNER_GROK_ROUTINE_PACK.md" in text
    assert "examples/studies/agents" in text
    assert "RS-D5" in text


def test_confirm_bound_extends_rs6_not_fork():
    text = (AGENTS / "ROUTINE_CONFIRM_BOUND.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "payload.approval" in text
    assert "study_identity_hash" in text
    assert "confirmed=true" in lower or "confirmed=True" in text
    assert "extends" in lower
    assert "insufficient" in lower or "alone" in lower
    assert "study rollup" in lower
    assert "force" in lower
