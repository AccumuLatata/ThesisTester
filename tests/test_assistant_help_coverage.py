"""HC-1 Help coverage bank: retrieval presence for core workflow how-tos."""

from __future__ import annotations

from pathlib import Path

from thesistester.assistant.help_corpus import select_help_corpus_chunks

REPO_ROOT = Path(__file__).resolve().parents[1]

# Default product_help budget from config/assistant.toml (§8).
_MAX_CHARS = 24_000

# HC §5.2 / §5.4 — primary targets for HC-1 questions.
_HC1_HOWTO_BANK = (
    (
        "Q-H1",
        "How do I import data and set instrument/timezone?",
        "user_guide",
        "Data",
    ),
    (
        "Q-H2",
        "How do I build levels for a session?",
        "user_guide",
        "Levels",
    ),
    (
        "Q-H3",
        "How do I configure a setup in Setup Builder?",
        "user_guide",
        "Setup Builder",
    ),
    (
        "Q-H4",
        "How do I generate signals?",
        "user_guide",
        "Signals",
    ),
    (
        "Q-H5",
        "How do I run a backtest and what do costs/exposure mean?",
        "user_guide",
        "Backtest",
    ),
)


def _selected_pairs(question: str) -> set[tuple[str, str]]:
    chunks = select_help_corpus_chunks(
        question,
        repo_root=REPO_ROOT,
        max_chars=_MAX_CHARS,
    )
    return {(chunk.doc_id, chunk.section) for chunk in chunks}


def test_hc1_howto_bank_retrieves_primary_user_guide_sections():
    for qid, question, doc_id, section in _HC1_HOWTO_BANK:
        pairs = _selected_pairs(question)
        assert (doc_id, section) in pairs, (
            f"{qid} expected primary {(doc_id, section)} in selected set; got {sorted(pairs)}"
        )


def test_qd2_expectancy_still_retrieves_metrics():
    """Definition Q-D2 must keep glossary present under §5 pass rule."""
    pairs = _selected_pairs("What is expectancy_r?")
    assert any(doc_id == "metrics" for doc_id, _section in pairs), (
        f"Q-D2 must include metrics chunks; got {sorted(pairs)}"
    )


def test_qh5_keeps_glossary_cost_chunks_with_user_guide():
    """Mixed how-to + cost nouns: USER_GUIDE primary must not drop glossary."""
    question = "How do I run a backtest and what do costs/exposure mean?"
    chunks = select_help_corpus_chunks(
        question,
        repo_root=REPO_ROOT,
        max_chars=_MAX_CHARS,
    )
    pairs = {(chunk.doc_id, chunk.section) for chunk in chunks}
    assert ("user_guide", "Backtest") in pairs
    assert any(chunk.doc_id == "metrics" for chunk in chunks), (
        "Q-H5 selected set must still include metrics (cost/slippage definitions)"
    )
    # Glossary gap-fill from HC-1 should be loadable in the metrics whole_file set.
    metrics_text = "\n".join(chunk.text for chunk in chunks if chunk.doc_id == "metrics")
    assert "slippage_ticks" in metrics_text or "slippage" in metrics_text.lower()


def test_howto_scoring_prefers_user_guide_without_killing_definition_metrics():
    from thesistester.assistant.help_corpus import (
        CorpusChunk,
        _tokenize_query,
        score_corpus_chunk,
    )

    guide = CorpusChunk(doc_id="user_guide", section="Data", text="import csv timezone")
    metrics = CorpusChunk(
        doc_id="metrics",
        section="Core formulas",
        text="expectancy_r win_rate slippage_ticks",
    )
    how_tokens = _tokenize_query("How do I import data and set instrument/timezone?")
    def_tokens = _tokenize_query("What is expectancy_r?")
    assert score_corpus_chunk(guide, query_tokens=how_tokens) > score_corpus_chunk(
        metrics, query_tokens=how_tokens
    )
    assert score_corpus_chunk(metrics, query_tokens=def_tokens) >= score_corpus_chunk(
        guide, query_tokens=def_tokens
    )
