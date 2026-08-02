"""Capability audit release gate: every registry row is routed or limited."""

from thesistester.assistant.registry_audit import (
    audit_capability_registry,
    capability_audit_summary,
    render_capability_audit_markdown,
)


def test_capability_audit_has_no_invalid_rows():
    rows = audit_capability_registry()
    invalid = [row.capability_id for row in rows if row.status == "invalid"]
    assert invalid == []
    summary = capability_audit_summary(rows)
    assert summary["total"] == len(rows)
    assert summary["routed"] + summary["unsupported"] == summary["total"]
    assert summary["routed"] >= 1
    assert summary["unsupported"] >= 1


def test_capability_audit_markdown_lists_every_row():
    rows = audit_capability_registry()
    markdown = render_capability_audit_markdown(rows)
    assert markdown.startswith("# Assistant capability audit")
    for row in rows:
        assert f"`{row.capability_id}`" in markdown
    assert "unsupported" in markdown


def test_routed_rows_have_handlers_and_unsupported_have_limitations():
    for row in audit_capability_registry():
        if row.status == "routed":
            assert row.has_handler is True
            assert row.mode != "unsupported"
        elif row.status == "unsupported":
            assert row.has_handler is False
            assert isinstance(row.limitation, str) and row.limitation.strip()
