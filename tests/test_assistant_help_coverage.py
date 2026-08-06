"""HC-1 Help coverage bank: retrieval presence for core workflow how-tos."""

from __future__ import annotations

from pathlib import Path

from thesistester.assistant.help_corpus import (
    CorpusChunk,
    _tokenize_query,
    load_allowlisted_corpus,
    score_corpus_chunk,
    select_help_corpus_chunks,
)

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


def _selected_chunks(question: str) -> tuple[CorpusChunk, ...]:
    return select_help_corpus_chunks(
        question,
        repo_root=REPO_ROOT,
        max_chars=_MAX_CHARS,
    )


def _selected_pairs(question: str) -> set[tuple[str, str]]:
    return {(chunk.doc_id, chunk.section) for chunk in _selected_chunks(question)}


def test_hc1_howto_bank_retrieves_primary_user_guide_sections():
    for qid, question, doc_id, section in _HC1_HOWTO_BANK:
        pairs = _selected_pairs(question)
        assert (doc_id, section) in pairs, (
            f"{qid} expected primary {(doc_id, section)} in selected set; got {sorted(pairs)}"
        )


def test_qd2_expectancy_retrieves_core_formulas_definition():
    """Definition Q-D2 must retrieve the Expectancy glossary section, not any metrics chunk."""
    chunks = _selected_chunks("What is expectancy_r?")
    pairs = {(chunk.doc_id, chunk.section) for chunk in chunks}
    assert ("metrics", "Core formulas") in pairs, (
        f"Q-D2 must include metrics/Core formulas; got {sorted(pairs)}"
    )
    core = next(c.text for c in chunks if c.doc_id == "metrics" and c.section == "Core formulas")
    assert "expectancy_r" in core.lower() or "expectancy (r)" in core.lower()


def test_qh5_keeps_execution_cost_glossary_with_user_guide():
    """Mixed how-to + cost nouns: USER_GUIDE primary must not drop cost gap-fill."""
    question = "How do I run a backtest and what do costs/exposure mean?"
    chunks = _selected_chunks(question)
    pairs = {(chunk.doc_id, chunk.section) for chunk in chunks}
    assert ("user_guide", "Backtest") in pairs
    assert ("metrics", "Execution cost inputs") in pairs, (
        f"Q-H5 must keep metrics/Execution cost inputs; got {sorted(pairs)}"
    )
    cost_text = next(
        c.text for c in chunks if c.doc_id == "metrics" and c.section == "Execution cost inputs"
    )
    assert "commission_per_side" in cost_text
    assert "slippage_ticks" in cost_text


def test_commission_per_side_definition_retrieves_execution_cost_inputs():
    pairs = _selected_pairs("What is commission_per_side?")
    assert ("metrics", "Execution cost inputs") in pairs, (
        f"commission_per_side definition must retrieve Execution cost inputs; got {sorted(pairs)}"
    )


def test_howto_title_overlap_ignores_stopwords_like_and():
    """'Purpose and honesty' must not get +5 merely because the query contains 'and'."""
    purpose = CorpusChunk(
        doc_id="user_guide",
        section="Purpose and honesty",
        text="Help answers from allowlisted docs only",
    )
    data = CorpusChunk(
        doc_id="user_guide",
        section="Data",
        text="import csv timezone instrument",
    )
    how_tokens = _tokenize_query("How do I import data and set instrument/timezone?")
    purpose_score = score_corpus_chunk(purpose, query_tokens=how_tokens)
    data_score = score_corpus_chunk(data, query_tokens=how_tokens)
    assert data_score > purpose_score
    # Stopword-only title overlap must not apply the strong +5 how-to boost.
    assert purpose_score < 5 + 3  # base lexical hits without title +5


def test_howto_scoring_prefers_user_guide_without_killing_definition_metrics():
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


def test_metrics_h2_bodies_respect_soft_chunk_budget():
    """HC chunk-fit: Help-readable metrics H2 bodies stay near ≤ ~4500 chars."""
    chunks = load_allowlisted_corpus(repo_root=REPO_ROOT, doc_ids=["metrics"])
    oversized = [
        (chunk.section, len(chunk.text))
        for chunk in chunks
        if chunk.section != "__preface__" and len(chunk.text) > 4500
    ]
    assert oversized == [], f"metrics H2 bodies exceed soft budget: {oversized}"


def test_exposure_definition_prefers_backtest_guide_not_cost_glossary():
    """Exposure policy is a Backtest concept — must not rank Execution cost inputs first."""
    question = "What does exposure mean on backtest?"
    pairs = _selected_pairs(question)
    assert ("user_guide", "Backtest") in pairs, (
        f"exposure definition should retrieve user_guide/Backtest; got {sorted(pairs)}"
    )
    corpus = load_allowlisted_corpus(repo_root=REPO_ROOT)
    backtest = next(c for c in corpus if c.doc_id == "user_guide" and c.section == "Backtest")
    cost = next(c for c in corpus if c.doc_id == "metrics" and c.section == "Execution cost inputs")
    q = _tokenize_query(question)
    assert score_corpus_chunk(backtest, query_tokens=q) > score_corpus_chunk(cost, query_tokens=q)
